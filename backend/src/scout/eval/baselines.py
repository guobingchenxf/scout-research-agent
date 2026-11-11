"""Baseline systems used in the evaluation."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from ..acquisition.router import AcquisitionRouter
from ..agent.loop import AgentLoop
from ..agent.planner import LLMPlanner, MockPlanner, Planner
from ..agent.reflector import Reflector
from ..agent.synthesis import Synthesizer
from ..agent.tools import AutoHuman, ToolContext, ToolRegistry
from ..audit import AuditLogger
from ..baseline import SingleShotRAG
from ..config import ScoutConfig
from ..hitl import ApprovalGate
from ..llm import ChatModel, LLMClient, LLMError, extract_json
from ..models import Citation, Report, SearchHit
from ..policy.allowlist import AllowlistPolicy
from ..policy.capability import PolicyEngine
from ..policy.injection import InjectionDetector
from ..policy.types import Capability
from ..retrieval import HybridIndex
from ..sandbox.python_sandbox import make_sandbox
from ..storage import SQLiteStore

_CITATION_ID = re.compile(r"\[([A-Za-z0-9_:\-./]+)\]")


@dataclass
class EvalOutput:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    report: Report | None = None
    steps: int = 0
    tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    error: str | None = None


def _citations_from_hits(hits: list[SearchHit], doc_ids: list[str] | None = None) -> list[Citation]:
    by_doc: dict[str, SearchHit] = {}
    for hit in hits:
        by_doc.setdefault(hit.doc_id, hit)
    selected = doc_ids or list(by_doc)
    citations: list[Citation] = []
    for doc_id in selected:
        match = by_doc.get(doc_id)
        if match is None:
            continue
        citations.append(
            Citation(doc_id=doc_id, span="chunk", quote=match.snippet, url=match.url)
        )
    return citations


def build_tools(config: ScoutConfig, store: SQLiteStore, index: HybridIndex) -> ToolRegistry:
    allowlist = AllowlistPolicy(
        config.source_allowlist,
        verify_dns=config.verify_dns,
        allow_http_local=config.allow_http_local,
    )
    capabilities = {
        Capability.SOURCES_READ,
        Capability.REPORT_EXPORT,
        Capability.MEMORY_READ,
    }
    if config.sandbox_backend != "disabled":
        capabilities.add(Capability.SANDBOX_EXEC)
    human = AutoHuman()
    return ToolRegistry(
        ToolContext(
            store=store,
            index=index,
            router=AcquisitionRouter(config),
            human=human,
            python_runner=make_sandbox(
                config.sandbox_backend,
                image=config.sandbox_image,
                timeout=config.sandbox_timeout_seconds,
            ),
            policy=PolicyEngine(capabilities, allowlist=allowlist),
            audit=AuditLogger(store),
            injection=InjectionDetector(),
            hitl=ApprovalGate(store, human),
        )
    )


def make_planner(
    config: ScoutConfig,
    planner_name: str,
) -> tuple[Planner, LLMClient | None]:
    if planner_name == "mock":
        return MockPlanner(), None
    if not config.deepseek_api_key:
        raise ValueError("DEEPSEEK_API_KEY is not configured")
    if not config.model_allowed(config.model_planner):
        raise ValueError(f"model is not allowed: {config.model_planner}")
    llm = LLMClient(
        config.deepseek_base_url,
        config.deepseek_api_key,
        timeout=config.llm_timeout_seconds,
        max_retries=config.llm_max_retries,
        backoff=config.llm_backoff_seconds,
    )
    return LLMPlanner(llm, config.model_planner), llm


def run_single_shot_rag(
    question: str,
    index: HybridIndex,
    llm: ChatModel | None = None,
    *,
    model: str = "deepseek-flash",
    top_k: int = 6,
) -> EvalOutput:
    started = time.perf_counter()
    result = SingleShotRAG(index, llm, model=model, top_k=top_k).run(question)
    return EvalOutput(
        answer=result.answer,
        citations=list(result.citations),
        steps=1,
        tokens=int(result.usage.get("total_tokens", 0)) if result.usage else 0,
        cost_usd=result.cost_usd,
        latency_ms=(time.perf_counter() - started) * 1000.0,
    )


def run_react_no_reflect(
    question: str,
    index: HybridIndex,
    llm: ChatModel | None = None,
    *,
    model: str = "deepseek-flash",
) -> EvalOutput:
    """Two searches, no evidence board, no reflection."""
    started = time.perf_counter()
    queries = [question, f"{question} evidence"]
    hits: list[SearchHit] = []
    seen: set[str] = set()
    for query in queries:
        for hit in index.search(query, k=4):
            if hit.chunk_id not in seen:
                seen.add(hit.chunk_id)
                hits.append(hit)
    hits = hits[:8]
    if not hits:
        return EvalOutput(
            answer="INSUFFICIENT_EVIDENCE",
            steps=len(queries),
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )
    if llm is None:
        selected = hits[:3]
        answer = "根据检索到的资料：\n\n" + "\n".join(
            f"- {hit.snippet} [{hit.doc_id}]" for hit in selected
        )
        return EvalOutput(
            answer=answer,
            citations=_citations_from_hits(selected),
            steps=len(queries),
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )

    context = "\n\n".join(f"[{hit.doc_id}] {hit.snippet}" for hit in hits)
    prompt = (
        "Answer only from the context. Every claim needs a [doc_id] citation. "
        "Return JSON: {\"answer\": \"...\", \"citations\": [\"doc_id\"]}.\n\n"
        f"Question: {question}\n\nContext:\n{context}"
    )
    response = llm.chat(
        [{"role": "user", "content": prompt}],
        model=model,
        temperature=0.0,
        max_tokens=800,
    )
    answer = response.content
    doc_ids: list[str] = []
    try:
        data = extract_json(response.content)
        if isinstance(data, dict):
            answer = str(data.get("answer") or answer)
            raw = data.get("citations") or []
            if isinstance(raw, str):
                raw = [raw]
            doc_ids = [str(item) for item in raw]
    except LLMError:
        pass
    if not doc_ids:
        doc_ids = _CITATION_ID.findall(answer)
    known = {hit.doc_id for hit in hits}
    doc_ids = [doc_id for doc_id in dict.fromkeys(doc_ids) if doc_id in known]
    if not doc_ids:
        doc_ids = [hits[0].doc_id]
    return EvalOutput(
        answer=answer,
        citations=_citations_from_hits(hits, doc_ids),
        steps=len(queries),
        tokens=response.usage.total_tokens,
        latency_ms=(time.perf_counter() - started) * 1000.0,
    )


def run_scout(
    question: str,
    config: ScoutConfig,
    store: SQLiteStore,
    index: HybridIndex,
    *,
    planner_name: str = "mock",
    max_steps: int = 20,
    constraints: dict | None = None,
) -> EvalOutput:
    started = time.perf_counter()
    planner, llm = make_planner(config, planner_name)
    try:
        tools = build_tools(config, store, index)
        run_config = config.with_overrides(max_steps=min(config.max_steps, max_steps))
        synthesizer = Synthesizer(llm, config.model_planner) if llm is not None else None
        loop = AgentLoop(
            run_config,
            store,
            planner,
            tools,
            Reflector(store),
            synthesizer=synthesizer,
            trace_directory=str(config.db_path.parent / "traces"),
        )
        result = loop.run(question, constraints=constraints)
        planner_tokens = int(getattr(planner, "total_tokens", 0))
        synthesizer_tokens = int(getattr(synthesizer, "total_tokens", 0))
        prompt_tokens = int(getattr(planner, "total_prompt_tokens", 0)) + int(
            getattr(synthesizer, "total_prompt_tokens", 0)
        )
        completion_tokens = int(getattr(planner, "total_completion_tokens", 0)) + int(
            getattr(synthesizer, "total_completion_tokens", 0)
        )
        cost = (
            prompt_tokens / 1000.0 * config.cost_input_per_1k
            + completion_tokens / 1000.0 * config.cost_output_per_1k
            + result.cost_usd
        )
        return EvalOutput(
            answer=result.report.answer,
            citations=list(result.report.citations),
            report=result.report,
            steps=result.steps,
            tokens=result.tokens + planner_tokens + synthesizer_tokens,
            cost_usd=cost,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            error=result.error,
        )
    finally:
        if llm is not None:
            llm.close()
