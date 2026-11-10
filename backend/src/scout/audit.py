"""Higher-level audit helpers on top of the SQLite hash chain."""

from __future__ import annotations

from typing import Any

from .policy.injection import InjectionDetector
from .storage import SQLiteStore


class AuditLogger:
    def __init__(
        self,
        store: SQLiteStore,
        run_id: str = "",
        *,
        detector: InjectionDetector | None = None,
    ) -> None:
        self.store = store
        self.run_id = run_id
        self.detector = detector or InjectionDetector()

    def set_run(self, run_id: str) -> None:
        self.run_id = run_id

    def record(self, actor: str, action: str, decision: str) -> dict[str, Any]:
        # Audit strings are redacted; payloads are not stored verbatim.
        safe_action = self.detector.redact_secrets(action)
        safe_decision = self.detector.redact_secrets(decision)
        return self.store.append_audit(self.run_id, actor, safe_action, safe_decision)

    def record_tool(self, tool: str, decision: str, error: str | None = None) -> dict[str, Any]:
        outcome = "error" if error else decision
        if error:
            outcome = f"{decision}: {error}"
        return self.record("agent", f"tool:{tool}", outcome)

    def verify(self) -> tuple[bool, int | None]:
        return self.store.verify_audit()
