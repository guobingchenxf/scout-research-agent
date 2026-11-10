"""Reflection: decide whether the evidence is sufficient to finish."""

from __future__ import annotations

import re
from typing import Any

from ..models import Conflict, Gap, Reflection, ResearchState, ToolResult, TrustLevel
from .state import covered_ratio, uncovered_subquestions

_WORD = re.compile(r"[A-Za-z0-9_]+|[一-鿿]")
_NEGATIONS = {"not", "no", "never", "without", "不", "没", "无", "非"}


class Reflector:
    def __init__(self, store: Any | None = None, *, coverage_threshold: float = 0.6) -> None:
        self.store = store
        self.coverage_threshold = coverage_threshold

    def reflect(
        self,
        state: ResearchState,
        last_result: ToolResult | None = None,
        *,
        budget_exhausted: bool = False,
    ) -> Reflection:
        coverage = covered_ratio(state)
        unresolved = [
            Gap(subquestion_id=item.id, reason="not covered")
            for item in uncovered_subquestions(state)
        ]
        conflicts = list(state.conflicts) + self._detect_conflicts(state)
        notes: list[str] = [
            f"coverage={coverage:.2f}",
            f"evidence={len(state.evidence_board)}",
        ]
        if last_result is not None:
            if last_result.ok:
                notes.append("last tool call succeeded")
            else:
                notes.append(f"last tool call failed: {last_result.error}")

        citation_issues = self._verify_citations(state)
        notes.extend(citation_issues)
        trusted = [
            evidence
            for evidence in state.evidence_board
            if evidence.trust != TrustLevel.UNTRUSTED
        ]
        if state.evidence_board and not trusted:
            notes.append("all evidence is untrusted")

        sufficient = (
            coverage >= self.coverage_threshold
            and not unresolved
            and not citation_issues
            and bool(trusted)
        )
        if budget_exhausted:
            notes.append("budget exhausted; finish with gaps")
        return Reflection(
            sufficient=sufficient,
            coverage_ratio=coverage,
            unresolved_gaps=unresolved,
            conflicts=conflicts,
            notes=notes,
            force_finish=budget_exhausted,
        )

    def _verify_citations(self, state: ResearchState) -> list[str]:
        if self.store is None:
            return []
        issues: list[str] = []
        for evidence in state.evidence_board:
            document = self.store.get_document(evidence.doc_id)
            if document is None:
                issues.append(f"citation doc missing: {evidence.doc_id}")
                continue
            quote = _normalize(evidence.quote)[:120]
            if quote and quote not in _normalize(document.text):
                issues.append(f"quote not found in {evidence.doc_id}")
        return issues

    def _detect_conflicts(self, state: ResearchState) -> list[Conflict]:
        conflicts: list[Conflict] = []
        evidence = state.evidence_board[:12]
        for index, left in enumerate(evidence):
            for right in evidence[index + 1 :]:
                if left.doc_id == right.doc_id:
                    continue
                left_words = set(_WORD.findall(left.claim.lower()))
                right_words = set(_WORD.findall(right.claim.lower()))
                if not left_words or not right_words:
                    continue
                overlap = len(left_words & right_words) / len(left_words | right_words)
                if overlap < 0.5:
                    continue
                left_negated = bool(left_words & _NEGATIONS)
                right_negated = bool(right_words & _NEGATIONS)
                if left_negated != right_negated:
                    conflicts.append(
                        Conflict(
                            claim_a=left.id,
                            claim_b=right.id,
                            reason="shared terms with opposite negation",
                        )
                    )
        return conflicts


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()
