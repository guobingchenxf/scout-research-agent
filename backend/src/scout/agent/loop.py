"""The Scout agent state machine."""

from __future__ import annotations

import re
import uuid
from typing import Any

from ..config import ScoutConfig
from ..memory import MemoryClient
from ..models import (
    Evidence,
    Gap,
    Report,
    ResearchState,
    RetrievalMethod,
    Run,
    RunResult,
    RunStatus,
    SupportType,
    ToolCall,
    ToolResult,
    TrustLevel,
    utc_now,
)
from ..storage import SQLiteStore
from ..trace import Trace
from .abstention import unsupported_specific_claim
from .planner import Planner, PlannerContext
from .reflector import Reflector
from .report import build_report, render_markdown
from .state import (
    add_conflict,
    add_evidence,
    budget_exceeded,
    finalize_gaps,
    mark_coverage,
    new_state,
    tick,
    uncovered_subquestions,
)
from .synthesis import CONFLICT_PROMPT, PROCEDURE_PROMPT, Synthesizer
from .tools import ToolRegistry

_SENTENCE_END = re.compile(r"(?<=[。！？.!?])\s+")


def _relevant_span(text: str, question: str, max_chars: int = 800) -> str:
    """Pick the most relevant sentence plus the next two for context.

    Term length is used as a cheap rarity prior: a rare term such as
    "PagedAttention" should outrank a frequent product name such as "vLLM".
    The following sentences are included because conflict and multi-hop
    questions need the claim, not just a title or a one-line definition.
    """

    sentences = [part.strip() for part in _SENTENCE_END.split(text) if part.strip()]
    if not sentences:
        return text[:max_chars]
    terms = set(re.findall(r"[A-Za-z0-9_]+", question.lower()))
    terms.update(re.findall(r"[一-鿿]", question))

    def score(sentence: str) -> int:
        lowered = sentence.lower()
        return sum(len(term) for term in terms if term in lowered)

    best_index = max(range(len(sentences)), key=lambda index: score(sentences[index]))
    if score(sentences[best_index]) == 0:
        best_index = 0
    window = " ".join(sentences[best_index : best_index + 3])
    return window[:max_chars] or text[:max_chars]


class AgentLoop:
    def __init__(
        self,
        config: ScoutConfig,
        store: SQLiteStore,
        planner: Planner,
        tools: ToolRegistry,
        reflector: Reflector,
        *,
        synthesizer: Synthesizer | None = None,
        trace_directory: str | None = None,
        memory: MemoryClient | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.planner = planner
        self.tools = tools
        self.reflector = reflector
        self.synthesizer = synthesizer
        self.trace_directory = trace_directory
        self.memory = memory

    def run(
        self,
        question: str,
        *,
        constraints: dict[str, Any] | None = None,
        run_id: str | None = None,
        create_run: bool = True,
    ) -> RunResult:
        run_id = run_id or uuid.uuid4().hex
        if getattr(self.tools, "context", None) is not None:
            self.tools.context.run_id = run_id
            if self.tools.context.audit is not None:
                self.tools.context.audit.set_run(run_id)
            if self.tools.context.hitl is not None:
                self.tools.context.hitl.set_run(run_id)
        state = new_state(question, constraints)
        if create_run:
            self.store.create_run(
                Run(id=run_id, question=question, constraints=state.constraints)
            )
        trace = Trace(self.store, run_id, directory=self.trace_directory)
        trace.emit("run_started", {"question": question, "constraints": state.constraints})

        if self.memory is not None:
            try:
                state.memory_context = self.memory.search_context(question)
                trace.emit(
                    "memory_search",
                    {
                        "chars": len(state.memory_context),
                        "context": state.memory_context[:1200],
                    },
                )
            except Exception as exc:  # noqa: BLE001 - memory must not fail a run
                trace.emit("memory_error", {"stage": "search", "error": str(exc)})

        report: Report | None = None
        status = RunStatus.RUNNING
        error: str | None = None
        last_result: ToolResult | None = None
        last_error: str | None = None

        try:
            for _ in range(self.config.max_steps):
                exhausted = budget_exceeded(
                    state,
                    max_steps=self.config.max_steps,
                    token_budget=self.config.token_budget,
                    cost_budget_usd=self.config.cost_budget_usd,
                )
                if exhausted:
                    trace.emit("budget_exhausted", state.budget.model_dump(mode="json"))
                    finalize_gaps(state)
                    report = self._final_report(state)
                    status = RunStatus.FINISHED
                    break

                context = PlannerContext(
                    max_steps=self.config.max_steps,
                    last_result=last_result,
                    last_error=last_error,
                    budget_remaining=max(0, self.config.max_steps - state.budget.steps),
                )
                decision = self.planner.plan(state, context)
                last_error = None
                plan_payload = {
                    "step": state.budget.steps + 1,
                    **decision.model_dump(mode="json"),
                }
                usage = getattr(self.planner, "last_usage", None)
                if usage is not None:
                    plan_payload["tokens"] = usage.total_tokens
                    plan_payload["cost_usd"] = (
                        usage.prompt_tokens / 1000.0 * self.config.cost_input_per_1k
                        + usage.completion_tokens / 1000.0 * self.config.cost_output_per_1k
                    )
                trace.emit("plan", plan_payload)
                call = ToolCall(
                    call_id=f"{run_id}-{state.budget.steps + 1}",
                    name=decision.tool.value,
                    arguments=decision.arguments,
                )
                result = self.tools.execute(call, state)
                tick(
                    state,
                    steps=1,
                    tokens=result.tokens,
                    cost_usd=result.cost_usd,
                )
                state.history.append(
                    {
                        "step": state.budget.steps,
                        "tool": call.name,
                        "arguments": call.arguments,
                        "ok": result.ok,
                        "error": result.error,
                    }
                )
                trace.emit("tool_result", result.model_dump(mode="json"))

                if result.ok and isinstance(result.output, dict):
                    kind = result.output.get("kind")
                    if kind == "read":
                        self._add_evidence_from_read(state, result.output)
                    elif kind == "finish":
                        try:
                            mode = self._synthesis_mode(state)
                            if (
                                self.synthesizer is not None
                                and state.evidence_board
                                and mode is not None
                            ):
                                prompt = None
                                if mode == "conflict":
                                    prompt = CONFLICT_PROMPT
                                elif mode == "procedure":
                                    prompt = PROCEDURE_PROMPT
                                report = self.synthesizer.synthesize(
                                    state,
                                    system_prompt=prompt,
                                )
                            else:
                                report = self._report_from_output(result.output)
                            report = self._apply_abstention_gate(state, report)
                            status = RunStatus.FINISHED
                            break
                        except Exception as exc:  # noqa: BLE001 - planner gets another chance
                            last_error = f"invalid finish: {exc}"
                    elif kind == "ask_human":
                        state.approvals.append(result.output)
                if not result.ok:
                    last_error = result.error
                last_result = result

                reflection = self.reflector.reflect(
                    state,
                    result,
                    budget_exhausted=False,
                )
                for conflict in reflection.conflicts:
                    add_conflict(state, conflict)
                trace.emit("reflect", reflection.model_dump(mode="json"))
                if reflection.force_finish:
                    finalize_gaps(state)
                    report = self._final_report(state)
                    status = RunStatus.FINISHED
                    break

            if report is None:
                finalize_gaps(state)
                report = self._final_report(state)
                status = (
                    RunStatus.FINISHED
                    if state.evidence_board
                    else RunStatus.ESCALATED
                )
                if not state.evidence_board:
                    error = "no evidence found; finished with explicit gaps"
        except Exception as exc:  # noqa: BLE001 - the run must be persisted on failure
            status = RunStatus.FAILED
            error = f"{type(exc).__name__}: {exc}"
            finalize_gaps(state, reason="run failed before completion")
            report = self._final_report(state)
            trace.emit("run_failed", {"error": error})

        trace.emit(
            "run_finished",
            {
                "status": status.value,
                "steps": state.budget.steps,
                "tokens": state.budget.tokens,
                "cost_usd": state.budget.cost_usd,
                "error": error,
            },
        )
        self.store.update_run(
            run_id,
            status=status,
            ended_at=utc_now(),
            result={
                "report": report.model_dump(mode="json"),
                "state": state.model_dump(mode="json"),
                "error": error,
            },
            error=error,
        )

        if (
            self.memory is not None
            and report is not None
            and status == RunStatus.FINISHED
        ):
            try:
                sources: list[str] = []
                for citation in report.citations:
                    if citation.doc_id not in sources:
                        sources.append(citation.doc_id)
                memory_id = self.memory.write_run(
                    question=question,
                    answer=report.answer,
                    run_id=run_id,
                    sources=sources,
                    status=status.value,
                )
                trace.emit(
                    "memory_write",
                    {"memory_id": memory_id, "sources": sources[:8]},
                )
            except Exception as exc:  # noqa: BLE001 - memory must not fail a run
                trace.emit("memory_error", {"stage": "write", "error": str(exc)})

        return RunResult(
            run_id=run_id,
            status=status,
            report=report,
            state=state,
            steps=state.budget.steps,
            tokens=state.budget.tokens,
            cost_usd=state.budget.cost_usd,
            error=error,
        )

    def _synthesis_mode(self, state: ResearchState) -> str | None:
        mode = str(state.constraints.get("mode") or "")
        if mode in {"conflict", "analysis", "procedure"}:
            return mode
        if self.config.enable_synthesis:
            return "general"
        question = state.question.lower()
        if any(
            marker in question
            for marker in (
                "一致",
                "冲突",
                "矛盾",
                "agree",
                "conflict",
                "contradiction",
                "tension",
            )
        ):
            return "conflict"
        return None

    def _final_report(self, state: ResearchState) -> Report:
        mode = self._synthesis_mode(state)
        if self.synthesizer is not None and state.evidence_board and mode is not None:
            prompt = None
            if mode == "conflict":
                prompt = CONFLICT_PROMPT
            elif mode == "procedure":
                prompt = PROCEDURE_PROMPT
            report = self.synthesizer.synthesize(state, system_prompt=prompt)
        else:
            report = build_report(state)
        return self._apply_abstention_gate(state, report)

    def _apply_abstention_gate(self, state: ResearchState, report: Report) -> Report:
        if not state.evidence_board:
            return report
        evidence_text = "\n".join(
            f"{evidence.claim} {evidence.quote}" for evidence in state.evidence_board
        )
        reason = unsupported_specific_claim(state.question, evidence_text)
        if reason is None:
            return report
        gated = Report(
            answer="INSUFFICIENT_EVIDENCE",
            claims=[],
            citations=[],
            conflicts=report.conflicts,
            gaps=[Gap(subquestion_id="all", reason=reason)],
            confidence=0.0,
        )
        gated.markdown = render_markdown(gated, state.question)
        return gated

    def _report_from_output(self, output: dict[str, Any]) -> Report:
        payload = output.get("report")
        if not isinstance(payload, dict):
            raise TypeError("finish output missing report")
        return Report.model_validate(payload)

    def _add_evidence_from_read(
        self,
        state: ResearchState,
        output: dict[str, Any],
    ) -> None:
        text = str(output.get("text") or "").strip()
        doc_id = str(output.get("doc_id") or "").strip()
        if not text or not doc_id:
            return
        span = _relevant_span(text, state.question)
        claim = span[:400]
        trust = TrustLevel(
            "untrusted" if output.get("untrusted") else output.get("trust", "secondary")
        )
        evidence = Evidence(
            id=f"e{len(state.evidence_board) + 1}",
            claim=claim,
            doc_id=doc_id,
            span="document",
            quote=span,
            trust=trust,
            support=(
                SupportType.INDIRECT if trust == TrustLevel.UNTRUSTED else SupportType.DIRECT
            ),
            retrieval_method=RetrievalMethod(output.get("retrieval_method", "local")),
            content_hash=str(output.get("content_hash") or ""),
        )
        added = add_evidence(state, evidence)
        if not added:
            return
        uncovered = uncovered_subquestions(state)
        if uncovered:
            mark_coverage(state, uncovered[0].id, "covered", [evidence.id])
