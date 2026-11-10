"""Pure helpers for the ResearchState lifecycle."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..models import (
    Conflict,
    Coverage,
    Evidence,
    Gap,
    ResearchState,
    SubQuestion,
)


def new_state(question: str, constraints: dict[str, Any] | None = None) -> ResearchState:
    return ResearchState(question=question, constraints=dict(constraints or {}))


def set_plan(state: ResearchState, questions: Iterable[str]) -> ResearchState:
    cleaned = [text.strip() for text in questions if text.strip()]
    state.plan = [
        SubQuestion(id=f"q{index}", text=text, status="pending")
        for index, text in enumerate(cleaned, start=1)
    ]
    for item in state.plan:
        state.coverage[item.id] = Coverage(status="pending")
    return state


def mark_coverage(
    state: ResearchState,
    subquestion_id: str,
    status: str = "covered",
    evidence_ids: Iterable[str] | None = None,
) -> None:
    existing = state.coverage.get(subquestion_id, Coverage())
    merged = list(dict.fromkeys([*existing.evidence_ids, *(evidence_ids or [])]))
    state.coverage[subquestion_id] = Coverage(status=status, evidence_ids=merged)
    for item in state.plan:
        if item.id == subquestion_id:
            item.status = status
            break


def add_evidence(state: ResearchState, evidence: Evidence) -> bool:
    key = (evidence.doc_id, evidence.content_hash or evidence.quote[:120])
    for current in state.evidence_board:
        current_key = (current.doc_id, current.content_hash or current.quote[:120])
        if current_key == key:
            return False
    state.evidence_board.append(evidence)
    return True


def add_conflict(state: ResearchState, conflict: Conflict) -> bool:
    key = tuple(sorted((conflict.claim_a, conflict.claim_b)))
    for current in state.conflicts:
        if tuple(sorted((current.claim_a, current.claim_b))) == key:
            return False
    state.conflicts.append(conflict)
    return True


def add_gap(state: ResearchState, gap: Gap) -> bool:
    for current in state.gaps:
        if current.subquestion_id == gap.subquestion_id:
            current.attempts += 1
            if gap.reason:
                current.reason = gap.reason
            return False
    state.gaps.append(gap)
    return True


def tick(
    state: ResearchState,
    *,
    steps: int = 1,
    tokens: int = 0,
    cost_usd: float = 0.0,
) -> None:
    state.budget.steps += steps
    state.budget.tokens += max(0, tokens)
    state.budget.cost_usd += max(0.0, cost_usd)


def budget_exceeded(
    state: ResearchState,
    *,
    max_steps: int,
    token_budget: int,
    cost_budget_usd: float,
) -> bool:
    return (
        state.budget.steps >= max_steps
        or state.budget.tokens >= token_budget
        or state.budget.cost_usd >= cost_budget_usd
    )


def covered_ratio(state: ResearchState) -> float:
    if not state.plan:
        return 0.0
    covered = sum(1 for item in state.plan if state.coverage.get(item.id, Coverage()).status == "covered")
    return covered / len(state.plan)


def uncovered_subquestions(state: ResearchState) -> list[SubQuestion]:
    return [
        item
        for item in state.plan
        if state.coverage.get(item.id, Coverage()).status != "covered"
    ]


def evidence_summary(state: ResearchState, limit: int = 12) -> list[dict[str, Any]]:
    return [
        {
            "id": evidence.id,
            "claim": evidence.claim[:240],
            "doc_id": evidence.doc_id,
            "trust": evidence.trust.value,
            "support": evidence.support.value,
            "quote": evidence.quote[:240],
        }
        for evidence in state.evidence_board[:limit]
    ]


def finalize_gaps(state: ResearchState, reason: str = "not covered within budget") -> None:
    for item in uncovered_subquestions(state):
        add_gap(state, Gap(subquestion_id=item.id, reason=reason))


def plan_text(state: ResearchState) -> list[dict[str, Any]]:
    return [
        {
            "id": item.id,
            "text": item.text,
            "status": item.status,
            "evidence_ids": state.coverage.get(item.id, Coverage()).evidence_ids,
        }
        for item in state.plan
    ]
