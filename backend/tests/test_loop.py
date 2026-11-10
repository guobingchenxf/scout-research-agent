from __future__ import annotations

from typing import Any

from scout.agent.loop import AgentLoop
from scout.agent.planner import PlannerContext
from scout.agent.reflector import Reflector
from scout.agent.state import set_plan
from scout.agent.tools import ToolContext, ToolRegistry
from scout.config import ScoutConfig
from scout.models import PlannerDecision, ResearchState, ToolName
from scout.retrieval import HybridIndex


class ScriptedPlanner:
    def __init__(self, decisions: list[PlannerDecision]) -> None:
        self.decisions = list(decisions)

    def plan(self, state: ResearchState, context: PlannerContext) -> PlannerDecision:
        if not state.plan:
            set_plan(state, ["definition", "comparison", "limitations"])
        if self.decisions:
            return self.decisions.pop(0)
        return PlannerDecision(
            tool=ToolName.FINISH,
            arguments=self._finish_arguments(state),
            rationale="scripted finish",
        )

    def _finish_arguments(self, state: ResearchState) -> dict[str, Any]:
        claims = [
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
            for evidence in state.evidence_board
        ]
        return {
            "answer": " ".join(evidence.claim for evidence in state.evidence_board),
            "claims": claims,
            "gaps": [],
            "confidence": 0.8,
        }


def _build(store, sample_documents, sample_chunks, decisions, *, max_steps=10):
    for document, chunk in zip(sample_documents, sample_chunks):
        store.ingest_document(document, [chunk])
    index = HybridIndex(sample_chunks, sample_documents)
    tools = ToolRegistry(ToolContext(store=store, index=index, run_id=""))
    config = ScoutConfig(max_steps=max_steps, token_budget=100_000, cost_budget_usd=1.0)
    planner = ScriptedPlanner(decisions)
    loop = AgentLoop(config, store, planner, tools, Reflector(store))
    return loop


def test_loop_searches_reads_and_finishes(store, sample_documents, sample_chunks) -> None:
    loop = _build(
        store,
        sample_documents,
        sample_chunks,
        [
            PlannerDecision(
                tool=ToolName.SEARCH,
                arguments={"query": "PagedAttention", "k": 3},
            ),
            PlannerDecision(tool=ToolName.READ, arguments={"source_id": "arxiv:1"}),
            PlannerDecision(
                tool=ToolName.READ,
                arguments={"source_id": "docs:sglang:index"},
            ),
            PlannerDecision(tool=ToolName.READ, arguments={"source_id": "blog:weather"}),
        ],
    )
    result = loop.run("What is PagedAttention?", run_id="run-1")
    assert result.status.value == "finished"
    assert len(result.report.claims) == 3
    assert result.steps == 5
    run = store.get_run("run-1")
    assert run is not None
    assert run.status.value == "finished"
    event_types = [event.type for event in store.list_events("run-1")]
    assert "run_started" in event_types
    assert "plan" in event_types
    assert "tool_result" in event_types
    assert "run_finished" in event_types


def test_loop_stops_at_budget_with_gaps(store, sample_documents, sample_chunks) -> None:
    loop = _build(
        store,
        sample_documents,
        sample_chunks,
        [
            PlannerDecision(
                tool=ToolName.SEARCH,
                arguments={"query": "PagedAttention", "k": 3},
            )
        ],
        max_steps=1,
    )
    result = loop.run("What is PagedAttention?", run_id="run-2")
    assert result.steps == 1
    assert result.report.gaps
    assert result.report.answer == "INSUFFICIENT_EVIDENCE"
    assert result.status.value == "escalated"
