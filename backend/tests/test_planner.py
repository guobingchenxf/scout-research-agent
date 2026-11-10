from __future__ import annotations

from scout.agent.planner import LLMPlanner, MockPlanner, PlannerContext
from scout.agent.state import add_evidence, set_plan
from scout.llm import MockLLM
from scout.models import Evidence, ToolName, ToolResult


def _evidence(doc_id: str = "arxiv:1") -> Evidence:
    return Evidence(
        id=f"e-{doc_id}",
        claim="vLLM uses PagedAttention",
        doc_id=doc_id,
        span="document",
        quote="vLLM uses PagedAttention",
    )


def test_mock_planner_starts_with_search() -> None:
    from scout.agent.state import new_state

    state = new_state("What is PagedAttention?")
    decision = MockPlanner().plan(state, PlannerContext())
    assert decision.tool == ToolName.SEARCH
    assert state.plan


def test_mock_planner_reads_a_new_hit() -> None:
    from scout.agent.state import new_state

    state = new_state("What is PagedAttention?")
    set_plan(state, ["definition", "comparison"])
    add_evidence(state, _evidence("arxiv:1"))
    last = ToolResult(
        call_id="1",
        ok=True,
        output={"kind": "search", "hits": [{"doc_id": "arxiv:2"}]},
    )
    decision = MockPlanner().plan(state, PlannerContext(last_result=last))
    assert decision.tool == ToolName.READ
    assert decision.arguments["source_id"] == "arxiv:2"


def test_llm_planner_parses_json() -> None:
    from scout.agent.state import new_state

    llm = MockLLM(
        [
            '{"subquestions": ["definition", "comparison"]}',
            '{"tool": "search", "arguments": {"query": "PagedAttention"}, "rationale": "r"}',
        ]
    )
    planner = LLMPlanner(llm, "deepseek-flash")
    decision = planner.plan(new_state("q"), PlannerContext())
    assert decision.tool == ToolName.SEARCH
    assert decision.arguments["query"] == "PagedAttention"


def test_llm_planner_falls_back_on_invalid_json() -> None:
    from scout.agent.state import new_state

    llm = MockLLM(["this is not json"])
    planner = LLMPlanner(llm, "deepseek-flash")
    decision = planner.plan(new_state("q"), PlannerContext())
    assert decision.tool == ToolName.SEARCH
    assert planner.last_error is not None
