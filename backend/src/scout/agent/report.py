"""Build a citation-bound report from the evidence board."""

from __future__ import annotations

from ..models import Citation, Claim, Gap, Report, ResearchState
from ..retrieval import tokenize
from .state import covered_ratio, uncovered_subquestions


def _overlap(text: str, query: str) -> float:
    query_tokens = set(tokenize(query))
    if not query_tokens:
        return 0.0
    return len(query_tokens & set(tokenize(text))) / len(query_tokens)


def _selected_evidence(state: ResearchState):
    evidence = state.evidence_board
    if not state.plan:
        return evidence[:10]
    selected = []
    for item in state.plan:
        coverage = state.coverage.get(item.id)
        chosen = []
        if coverage and coverage.evidence_ids:
            wanted = set(coverage.evidence_ids)
            chosen = [entry for entry in evidence if entry.id in wanted]
        if not chosen:
            chosen = sorted(
                evidence,
                key=lambda entry: _overlap(f"{entry.claim} {entry.quote}", item.text),
                reverse=True,
            )[:1]
        for entry in chosen:
            if entry not in selected:
                selected.append(entry)
    return selected[:10] or evidence[:10]


def build_report(
    state: ResearchState,
    *,
    answer: str | None = None,
    confidence: float | None = None,
) -> Report:
    claims: list[Claim] = []
    citations: list[Citation] = []
    for index, evidence in enumerate(_selected_evidence(state), start=1):
        citation = Citation(
            evidence_id=evidence.id,
            doc_id=evidence.doc_id,
            span=evidence.span,
            quote=evidence.quote,
        )
        claims.append(
            Claim(
                id=f"c{index}",
                text=evidence.claim,
                citations=[citation],
                support=evidence.support,
            )
        )
        citations.append(citation)

    if answer is None:
        if claims:
            answer = " ".join(claim.text for claim in claims)
        else:
            answer = "INSUFFICIENT_EVIDENCE"

    gaps = list(state.gaps)
    known_gaps = {gap.subquestion_id for gap in gaps}
    for item in uncovered_subquestions(state):
        if item.id not in known_gaps:
            gaps.append(Gap(subquestion_id=item.id, reason="not covered"))

    report = Report(
        answer=answer,
        claims=claims,
        citations=citations,
        conflicts=list(state.conflicts),
        gaps=gaps,
        confidence=covered_ratio(state) if confidence is None else confidence,
    )
    report.markdown = render_markdown(report, state.question)
    return report


def render_markdown(report: Report, question: str) -> str:
    lines: list[str] = ["# Scout 调研报告", "", "## 问题", "", question, "", "## 结论", ""]
    lines.append(report.answer.strip() or "INSUFFICIENT_EVIDENCE")
    lines.extend(["", "## 证据", ""])
    if not report.claims:
        lines.append("（无可用证据）")
    for claim in report.claims:
        lines.append(f"- {claim.text}")
        for citation in claim.citations:
            quote = citation.quote.strip()
            if quote:
                lines.append(f"  > {quote[:400]}")
            lines.append(f"  - 来源：`{citation.doc_id}` {citation.span}".rstrip())
    if report.gaps:
        lines.extend(["", "## 缺口", ""])
        for gap in report.gaps:
            lines.append(f"- `{gap.subquestion_id}`：{gap.reason or '未覆盖'}")
    lines.extend(
        [
            "",
            "## 置信度",
            "",
            f"{report.confidence:.2f}",
            "",
            "> 说明：本报告只保留有证据支持的 claim；缺口会显式列出，不做无依据补全。",
        ]
    )
    return "\n".join(lines)
