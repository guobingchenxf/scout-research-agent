"""Tool registry: search, read, python, ask_human, finish."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from ..acquisition.router import AcquisitionRouter
from ..audit import AuditLogger
from ..hitl import ApprovalGate
from ..models import (
    Approval,
    Citation,
    Claim,
    Conflict,
    Gap,
    Report,
    ResearchState,
    ToolCall,
    ToolResult,
    TrustLevel,
    utc_now,
)
from ..policy.capability import PolicyEngine
from ..policy.injection import InjectionDetector
from ..retrieval import HybridIndex
from ..storage import SQLiteStore
from .report import render_markdown

_QUERY_SYNONYMS: dict[str, str] = {
    "价格": "price pricing cost",
    "授权": "license licensing",
    "收购": "acquisition acquired",
    "并购": "acquisition merger",
    "显存": "memory vram hbm",
    "容量": "capacity memory",
    "延迟": "latency p99 p95",
    "评测": "evaluation benchmark",
    "对比": "comparison compare",
    "差异": "difference comparison",
    "核心": "core key",
    "方法": "method approach",
    "结构": "structure architecture",
    "维度": "dimensions metrics",
    "流程": "procedure workflow",
    "冲突": "conflict disagreement",
    "记忆": "memory",
    "检索": "retrieval search",
    "推荐": "recommendation",
}


def expand_query(query: str) -> str:
    """Append small bilingual intent hints for BM25.

    This is deliberately tiny: it helps Chinese questions match English
    technical corpus text without an LLM call or a translation dependency.
    """

    extras = [value for key, value in _QUERY_SYNONYMS.items() if key in query]
    if not extras:
        return query
    return f"{query} {' '.join(extras)}"


class HumanResponder(Protocol):
    def ask(self, question: str, options: list[str], risk: str) -> str: ...


class AutoHuman:
    """Offline default: approve the first option, or return `approve`."""

    def ask(self, question: str, options: list[str], risk: str) -> str:
        return options[0] if options else "approve"


class PythonRunner(Protocol):
    def run(self, code: str) -> tuple[bool, str]: ...


class DisabledPythonRunner:
    """The sandbox lands in Phase 3; arbitrary code is not executed yet."""

    def run(self, code: str) -> tuple[bool, str]:
        return False, "python sandbox is disabled until Phase 3"


@dataclass
class ToolContext:
    store: SQLiteStore
    index: HybridIndex
    router: AcquisitionRouter | None = None
    human: HumanResponder = field(default_factory=AutoHuman)
    python_runner: PythonRunner = field(default_factory=DisabledPythonRunner)
    policy: PolicyEngine | None = None
    audit: AuditLogger | None = None
    injection: InjectionDetector | None = None
    hitl: ApprovalGate | None = None
    run_id: str = ""
    max_read_chars: int = 6000
    last_hits: list[Any] = field(default_factory=list)


class FinishClaim(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str
    citations: list[Citation] = Field(default_factory=list)


class FinishArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    answer: str
    claims: list[FinishClaim] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    confidence: float = 0.0


class ToolRegistry:
    def __init__(self, context: ToolContext) -> None:
        self.context = context

    # ------------------------------------------------------------------
    # Schemas exposed to the planner
    # ------------------------------------------------------------------
    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "search",
                "description": "Hybrid BM25 + embedding search over the frozen corpus.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "sources": {"type": "array", "items": {"type": "string"}},
                        "k": {"type": "integer", "default": 8},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "read",
                "description": "Read a document from the local store or acquisition router.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_id": {"type": "string"},
                        "locator": {"type": "string"},
                    },
                    "required": ["source_id"],
                },
            },
            {
                "name": "python",
                "description": "Run Python in the sandbox (disabled until Phase 3).",
                "parameters": {
                    "type": "object",
                    "properties": {"code": {"type": "string"}},
                    "required": ["code"],
                },
            },
            {
                "name": "ask_human",
                "description": "Ask a human to clarify or approve a risky action.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "options": {"type": "array", "items": {"type": "string"}},
                        "risk": {"type": "string"},
                    },
                    "required": ["question"],
                },
            },
            {
                "name": "finish",
                "description": "Finish with a citation-bound report and explicit gaps.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "answer": {"type": "string"},
                        "claims": {"type": "array"},
                        "gaps": {"type": "array"},
                        "confidence": {"type": "number"},
                    },
                    "required": ["answer", "claims"],
                },
            },
        ]

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def execute(self, call: ToolCall, state: ResearchState) -> ToolResult:
        started = time.perf_counter()
        if self.context.policy is not None:
            decision = self.context.policy.check_tool(call.name, call.arguments)
            if not decision.allowed:
                approved = decision.requires_approval and self._approve(call, decision.reason)
                if not approved:
                    result = ToolResult(
                        call_id=call.call_id,
                        ok=False,
                        error=f"policy denied: {decision.reason}",
                        latency_ms=(time.perf_counter() - started) * 1000.0,
                    )
                    self._audit(call, "denied", decision.reason)
                    return result
        try:
            handler = {
                "search": self._search,
                "read": self._read,
                "python": self._python,
                "ask_human": self._ask_human,
                "finish": self._finish,
            }.get(call.name)
            if handler is None:
                raise ValueError(f"unknown tool: {call.name}")
            output = handler(call.arguments, state)
            result = ToolResult(
                call_id=call.call_id,
                ok=True,
                output=output,
                latency_ms=(time.perf_counter() - started) * 1000.0,
            )
            self._audit(call, "allowed")
            return result
        except Exception as exc:  # noqa: BLE001 - tool boundary must not crash the loop
            result = ToolResult(
                call_id=call.call_id,
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
                latency_ms=(time.perf_counter() - started) * 1000.0,
            )
            self._audit(call, "error", result.error)
            return result

    def _approve(self, call: ToolCall, reason: str) -> bool:
        question = f"Approve {call.name}? {reason}"
        options = ["approve", "reject"]
        if self.context.hitl is not None:
            approval = self.context.hitl.request(
                question,
                options,
                risk="high",
                context={"tool": call.name},
            )
            answer = approval.decision
        else:
            answer = self.context.human.ask(question, options, "high")
        return str(answer).lower() in {"approve", "allow", "yes", "ok"}

    def _audit(self, call: ToolCall, decision: str, error: str | None = None) -> None:
        if self.context.audit is not None:
            self.context.audit.record_tool(call.name, decision, error)

    def _search(self, arguments: dict[str, Any], state: ResearchState) -> dict[str, Any]:
        query = str(arguments.get("query") or state.question).strip()
        if not query:
            raise ValueError("search requires a query")
        k = int(arguments.get("k", 8))
        sources = arguments.get("sources")
        source_types = {str(item) for item in sources} if sources else None
        search_query = expand_query(query)
        hits = self.context.index.search(search_query, k=k, source_types=source_types)
        self.context.last_hits = list(hits)
        return {
            "kind": "search",
            "query": query,
            "expanded_query": search_query,
            "hits": [hit.model_dump(mode="json") for hit in hits],
        }

    def _read(self, arguments: dict[str, Any], state: ResearchState) -> dict[str, Any]:
        source_id = str(arguments.get("source_id") or "").strip()
        if not source_id:
            raise ValueError("read requires a source_id")
        document = self.context.store.get_document(source_id)
        method = document.retrieval_method.value if document else ""
        if document is None and self.context.router is not None:
            result = self.context.router.read(source_id)
            if result.documents:
                document = result.documents[0]
                method = result.method.value
        if document is None:
            raise ValueError(f"source not found: {source_id}")
        text = document.text[: self.context.max_read_chars]
        untrusted = document.trust == TrustLevel.UNTRUSTED
        injection_matches: list[str] = []
        if self.context.injection is not None:
            scan = self.context.injection.scan(text)
            injection_matches = scan.matches
            if scan.blocked:
                untrusted = True
        return {
            "kind": "read",
            "doc_id": document.id,
            "title": document.title,
            "url": document.url,
            "trust": document.trust.value,
            "untrusted": untrusted,
            "injection_matches": injection_matches,
            "retrieval_method": method or document.retrieval_method.value,
            "content_hash": document.content_hash,
            "text": text,
            "truncated": len(document.text) > self.context.max_read_chars,
        }

    def _python(self, arguments: dict[str, Any], state: ResearchState) -> dict[str, Any]:
        code = str(arguments.get("code") or "")
        if not code.strip():
            raise ValueError("python requires code")
        ok, output = self.context.python_runner.run(code)
        if not ok:
            raise RuntimeError(output)
        return {"kind": "python", "output": output}

    def _ask_human(self, arguments: dict[str, Any], state: ResearchState) -> dict[str, Any]:
        question = str(arguments.get("question") or "").strip()
        if not question:
            raise ValueError("ask_human requires a question")
        options = [str(item) for item in (arguments.get("options") or [])]
        risk = str(arguments.get("risk") or "clarification")
        if self.context.hitl is not None:
            approval = self.context.hitl.request(question, options, risk=risk)
            decision = approval.decision
        else:
            decision = self.context.human.ask(question, options, risk)
            approval = Approval(
                id=uuid.uuid4().hex,
                run_id=self.context.run_id,
                question=question,
                risk=risk,
                options=options,
                decision=decision,
                decided_by="human",
                decided_at=utc_now(),
            )
            self.context.store.add_approval(approval)
        return {
            "kind": "ask_human",
            "approval_id": approval.id,
            "question": question,
            "decision": decision,
            "risk": risk,
        }

    def _finish(self, arguments: dict[str, Any], state: ResearchState) -> dict[str, Any]:
        parsed = FinishArgs.model_validate(arguments)
        if not parsed.claims:
            raise ValueError("finish requires at least one claim")
        known_docs = {evidence.doc_id for evidence in state.evidence_board}
        claims: list[Claim] = []
        citations: list[Citation] = []
        for index, claim in enumerate(parsed.claims, start=1):
            if not claim.citations:
                raise ValueError(f"claim {index} has no citation")
            for citation in claim.citations:
                if citation.doc_id not in known_docs and self.context.store.get_document(
                    citation.doc_id
                ) is None:
                    raise ValueError(f"unknown citation doc: {citation.doc_id}")
            claims.append(Claim(id=f"c{index}", text=claim.text, citations=claim.citations))
            citations.extend(claim.citations)
        conflicts = list(parsed.conflicts or state.conflicts)
        if not conflicts and len(claims) >= 2:
            answer_lower = parsed.answer.lower()
            question_lower = state.question.lower()
            disagreement = any(
                marker in answer_lower
                for marker in (
                    "不一致",
                    "冲突",
                    "矛盾",
                    "disagree",
                    "conflict",
                    "contradiction",
                )
            )
            asks_agreement = any(
                marker in question_lower
                for marker in ("一致", "冲突", "矛盾", "agree", "conflict", "contradiction")
            )
            if disagreement and asks_agreement:
                conflicts = [
                    Conflict(
                        claim_a=claims[0].text,
                        claim_b=claims[1].text,
                        reason="answer reports disagreement between sources",
                    )
                ]
        report = Report(
            answer=parsed.answer,
            claims=claims,
            citations=citations,
            conflicts=conflicts,
            gaps=parsed.gaps,
            confidence=parsed.confidence,
        )
        report.markdown = render_markdown(report, state.question)
        return {"kind": "finish", "report": report.model_dump(mode="json")}
