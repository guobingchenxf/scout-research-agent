from __future__ import annotations

from scout.agent.state import (
    add_evidence,
    add_gap,
    budget_exceeded,
    covered_ratio,
    mark_coverage,
    new_state,
    set_plan,
    tick,
    uncovered_subquestions,
)
from scout.models import Evidence, Gap


def _evidence(quote: str = "vLLM uses PagedAttention") -> Evidence:
    return Evidence(
        id="e1",
        claim="vLLM uses PagedAttention",
        doc_id="arxiv:1",
        span="document",
        quote=quote,
    )


def test_plan_and_coverage() -> None:
    state = new_state("What is PagedAttention?")
    set_plan(state, ["definition", "comparison"])
    assert [item.id for item in state.plan] == ["q1", "q2"]
    assert covered_ratio(state) == 0.0

    mark_coverage(state, "q1", "covered", ["e1"])
    assert covered_ratio(state) == 0.5
    assert [item.id for item in uncovered_subquestions(state)] == ["q2"]


def test_evidence_dedupe() -> None:
    state = new_state("q")
    assert add_evidence(state, _evidence())
    assert not add_evidence(state, _evidence())
    assert len(state.evidence_board) == 1


def test_gap_attempts_increment() -> None:
    state = new_state("q")
    add_gap(state, Gap(subquestion_id="q1", reason="missing"))
    add_gap(state, Gap(subquestion_id="q1", reason="still missing"))
    assert len(state.gaps) == 1
    assert state.gaps[0].attempts == 1
    assert state.gaps[0].reason == "still missing"


def test_budget_exceeded() -> None:
    state = new_state("q")
    tick(state, steps=2, tokens=10, cost_usd=0.5)
    assert budget_exceeded(state, max_steps=2, token_budget=100, cost_budget_usd=1.0)
    assert not budget_exceeded(state, max_steps=3, token_budget=100, cost_budget_usd=1.0)
