"""Planners: a deterministic mock and a DeepSeek-backed planner."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from ..llm import ChatModel, LLMError, Usage, extract_json
from ..models import PlannerDecision, ResearchState, ToolName, ToolResult
from .state import (
    covered_ratio,
    evidence_summary,
    plan_text,
    set_plan,
    uncovered_subquestions,
)


@dataclass
class PlannerContext:
    available_sources: tuple[str, ...] = (
        "paper",
        "code_repo",
        "model_card",
        "official_doc",
    )
    max_steps: int = 25
    last_result: ToolResult | None = None
    last_error: str | None = None
    budget_remaining: int = 25


class Planner(Protocol):
    def plan(self, state: ResearchState, context: PlannerContext) -> PlannerDecision: ...


def _finish_arguments(state: ResearchState) -> dict[str, Any]:
    claims: list[dict[str, Any]] = []
    for evidence in state.evidence_board[:8]:
        claims.append(
            {
                "text": evidence.claim,
                "citations": [
                    {
                        "doc_id": evidence.doc_id,
                        "evidence_id": evidence.id,
                        "span": evidence.span,
                        "quote": evidence.quote,
                    }
                ],
            }
        )
    answer = " ".join(claim["text"] for claim in claims) if claims else "INSUFFICIENT_EVIDENCE"
    gaps = [
        {"subquestion_id": gap.subquestion_id, "reason": gap.reason}
        for gap in state.gaps
    ]
    known = {gap["subquestion_id"] for gap in gaps}
    for item in uncovered_subquestions(state):
        if item.id not in known:
            gaps.append({"subquestion_id": item.id, "reason": "not covered"})
    return {
        "answer": answer,
        "claims": claims,
        "conflicts": [
            {
                "claim_a": conflict.claim_a,
                "claim_b": conflict.claim_b,
                "reason": conflict.reason,
            }
            for conflict in state.conflicts
        ],
        "gaps": gaps,
        "confidence": covered_ratio(state),
    }


class MockPlanner:
    """Deterministic planner used by tests, CI and offline demos.

    It is intentionally simple: search, read the top hit, expand coverage,
    then finish. The point is to exercise the runtime, not to be smart.
    """

    def __init__(self, *, min_evidence: int = 3, coverage_threshold: float = 0.6) -> None:
        self.min_evidence = min_evidence
        self.coverage_threshold = coverage_threshold

    def plan(self, state: ResearchState, context: PlannerContext) -> PlannerDecision:
        if not state.plan:
            set_plan(
                state,
                [
                    state.question,
                    f"{state.question} 的关键证据",
                    f"{state.question} 的对比与限制",
                ],
            )

        last = context.last_result
        if (
            last
            and last.ok
            and isinstance(last.output, dict)
            and last.output.get("kind") == "search"
        ):
            hits = last.output.get("hits") or []
            known_docs = {evidence.doc_id for evidence in state.evidence_board}
            for hit in hits:
                doc_id = hit.get("doc_id")
                if doc_id and doc_id not in known_docs:
                    return PlannerDecision(
                        tool=ToolName.READ,
                        arguments={"source_id": doc_id},
                        rationale="read a new search hit",
                    )
            if state.evidence_board:
                return PlannerDecision(
                    tool=ToolName.FINISH,
                    arguments=_finish_arguments(state),
                    rationale="no new evidence from search; finish with gaps",
                )

        if not state.evidence_board:
            variants = [
                state.question,
                f"{state.question} survey",
                f"{state.question} benchmark",
            ]
            return PlannerDecision(
                tool=ToolName.SEARCH,
                arguments={"query": variants[state.budget.steps % len(variants)], "k": 8},
                rationale="gather initial evidence",
            )

        uncovered = uncovered_subquestions(state)
        if len(state.evidence_board) < self.min_evidence:
            variants = [
                state.question,
                f"{state.question} survey",
                f"{state.question} benchmark",
                f"{state.question} limitations",
            ]
            query = variants[state.budget.steps % len(variants)]
            return PlannerDecision(
                tool=ToolName.SEARCH,
                arguments={"query": query, "k": 6},
                rationale="increase evidence coverage",
            )

        if covered_ratio(state) < self.coverage_threshold and uncovered:
            return PlannerDecision(
                tool=ToolName.SEARCH,
                arguments={"query": uncovered[0].text, "k": 6},
                rationale="cover an open sub-question",
            )

        return PlannerDecision(
            tool=ToolName.FINISH,
            arguments=_finish_arguments(state),
            rationale="coverage sufficient",
        )


SYSTEM_PROMPT = """You are Scout, a citation-first research agent.
You answer a question using only evidence from tools. Never answer from
parametric memory. `memory_context` (if present) is long-term memory from
previous runs: use it to choose searches and sub-questions, but treat it as a
lead, not as evidence.

Tools (return one action each turn):
- search: {"query": str, "sources": [str], "k": int}
- read: {"source_id": str, "locator": str?}
- python: {"code": str}
- ask_human: {"question": str, "options": [str], "risk": str}
- finish: {"answer": str, "claims": [{"text": str, "citations": [{"doc_id": str, "quote": str}]}], "conflicts": [{"claim_a": str, "claim_b": str, "reason": str}], "gaps": [{"subquestion_id": str, "reason": str}], "confidence": float}

Rules:
1. Every claim must cite a doc_id returned by search/read.
2. If evidence is insufficient, search or read more; do not invent.
3. If the answer has conflicts, expose them instead of averaging.
4. If the budget is nearly exhausted, finish with explicit gaps.
5. Use ask_human only for ambiguity, high-risk actions or budget approval.
6. Never read the same source_id twice; check read_doc_ids first.
7. Do not repeat a search query already in searched_queries.
8. If budget_remaining_steps <= 3, you must call finish.
9. If coverage_ratio >= 0.5 and you have at least 2 evidence items, call finish
   with a synthesized answer instead of searching again.
10. For comparison or multi-hop questions, read at least two distinct doc_ids
    before finishing.
11. If the question asks for a specific price, acquisition, person, date or
    hardware number that is not present verbatim in the evidence, answer
    INSUFFICIENT_EVIDENCE instead of guessing.
12. If sources disagree, expose the conflict and cite both sources; do not
    average them into one claim.
13. If the question asks whether two sources agree or conflict, fill
    `conflicts` with both claims and a reason; do not only answer in prose.
14. For a procedure question, finish with numbered steps in order; do not
    concatenate abstracts.
15. If memory_context names a source or preference, verify it with search/read
    before citing it; memory alone cannot satisfy rule 1.
16. Return exactly one JSON object: {"tool": "...", "arguments": {...}, "rationale": "..."}.
"""


class LLMPlanner:
    def __init__(self, llm: ChatModel, model: str, *, fallback: Planner | None = None) -> None:
        self.llm = llm
        self.model = model
        self.fallback = fallback or MockPlanner()
        self.last_error: str | None = None
        self.total_tokens = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.last_usage: Usage | None = None

    def _record_usage(self, usage: Usage) -> None:
        self.total_prompt_tokens += usage.prompt_tokens
        self.total_completion_tokens += usage.completion_tokens
        self.total_tokens += usage.total_tokens
        if self.last_usage is None:
            self.last_usage = Usage()
        self.last_usage.prompt_tokens += usage.prompt_tokens
        self.last_usage.completion_tokens += usage.completion_tokens

    def _decompose(self, question: str) -> list[str]:
        prompt = (
            "Decompose this research question into 2-4 self-contained sub-questions. "
            "Cover definition, key evidence, and comparison or limitation where "
            'applicable. Return JSON: {"subquestions": ["..."]}.\n'
            f"Question: {question}"
        )
        try:
            response = self.llm.chat(
                [{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.0,
                max_tokens=300,
            )
            self._record_usage(response.usage)
            data = extract_json(response.content)
            if isinstance(data, dict):
                raw = data.get("subquestions") or []
                if isinstance(raw, list):
                    cleaned = [str(item).strip() for item in raw if str(item).strip()]
                    if cleaned:
                        return cleaned[:4]
        except (LLMError, ValueError, TypeError):
            pass
        return [
            question,
            f"{question} 的关键证据",
            f"{question} 的对比与限制",
        ]

    def plan(self, state: ResearchState, context: PlannerContext) -> PlannerDecision:
        self.last_usage = Usage()
        if not state.plan:
            set_plan(state, self._decompose(state.question))
        read_doc_ids = sorted(
            {
                str(item.get("arguments", {}).get("source_id"))
                for item in state.history
                if item.get("tool") == "read"
                and item.get("arguments", {}).get("source_id")
            }
        )
        searched_queries = [
            str(item.get("arguments", {}).get("query"))
            for item in state.history
            if item.get("tool") == "search"
            and item.get("arguments", {}).get("query")
        ][-6:]
        payload = {
            "question": state.question,
            "constraints": state.constraints,
            "memory_context": state.memory_context[-2000:],
            "plan": plan_text(state),
            "coverage_ratio": covered_ratio(state),
            "evidence": evidence_summary(state),
            "gaps": [gap.model_dump(mode="json") for gap in state.gaps],
            "budget": state.budget.model_dump(mode="json"),
            "budget_remaining_steps": context.budget_remaining,
            "last_result": (
                context.last_result.model_dump(mode="json") if context.last_result else None
            ),
            "last_error": context.last_error,
            "history": state.history[-8:],
            "read_doc_ids": read_doc_ids,
            "searched_queries": searched_queries,
            "available_sources": list(context.available_sources),
        }
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Current research state:\n"
                + json.dumps(payload, ensure_ascii=False, indent=2),
            },
        ]
        try:
            response = self.llm.chat(
                messages,
                model=self.model,
                temperature=0.0,
                max_tokens=900,
            )
            self._record_usage(response.usage)
            data = extract_json(response.content)
            decision = PlannerDecision.model_validate(data)
            self.last_error = None
            return decision
        except (LLMError, ValueError, TypeError) as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return self.fallback.plan(state, context)
