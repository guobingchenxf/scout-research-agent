"""Human-in-the-loop approval gate with risk levels."""

from __future__ import annotations

import uuid
from typing import Any

from .models import Approval, utc_now
from .policy.types import RiskLevel
from .storage import SQLiteStore


def _coerce_risk(value: str | RiskLevel) -> RiskLevel:
    if isinstance(value, RiskLevel):
        return value
    try:
        return RiskLevel(str(value).lower())
    except ValueError:
        return RiskLevel.MEDIUM


class ApprovalGate:
    def __init__(self, store: SQLiteStore, human: Any, run_id: str = "") -> None:
        self.store = store
        self.human = human
        self.run_id = run_id

    def set_run(self, run_id: str) -> None:
        self.run_id = run_id

    def needs_approval(self, risk: str | RiskLevel) -> bool:
        return _coerce_risk(risk) in {RiskLevel.HIGH, RiskLevel.CRITICAL}

    def request(
        self,
        question: str,
        options: list[str] | None = None,
        risk: str | RiskLevel = RiskLevel.MEDIUM,
        *,
        context: dict[str, Any] | None = None,
    ) -> Approval:
        choices = list(options or ["approve", "reject"])
        level = _coerce_risk(risk)
        if level == RiskLevel.LOW:
            decision = choices[0]
            decided_by = "auto"
        else:
            decision = self.human.ask(question, choices, level.value)
            decided_by = "human"
        approval = Approval(
            id=uuid.uuid4().hex,
            run_id=self.run_id,
            question=question,
            risk=level.value,
            options=choices,
            decision=decision,
            decided_by=decided_by,
            note=str((context or {}).get("note", "")),
            decided_at=utc_now(),
        )
        self.store.add_approval(approval)
        return approval
