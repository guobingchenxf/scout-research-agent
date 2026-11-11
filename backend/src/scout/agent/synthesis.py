"""Final answer synthesis from the evidence board."""

from __future__ import annotations

from ..llm import ChatModel, LLMError, Usage, extract_json
from ..models import Citation, Claim, Conflict, Evidence, Report, ResearchState
from .report import build_report, render_markdown
from .state import covered_ratio

CONFLICT_PROMPT = """You are Scout's conflict synthesizer.
Answer whether the sources agree, using ONLY the evidence below.
If they disagree, fill `conflicts` with both claims and a reason. If they agree,
say so explicitly. Every claim must cite a doc_id from the evidence.
Prefer a best-supported answer even when the evidence is partial; use
INSUFFICIENT_EVIDENCE only when no evidence is relevant.
Return JSON:
{"answer": "...", "claims": [{"text": "...", "citations": [{"doc_id": "...", "quote": "..."}]}],
 "conflicts": [{"claim_a": "...", "claim_b": "...", "reason": "..."}],
 "gaps": [{"subquestion_id": "...", "reason": "..."}], "confidence": 0.0}
"""

PROCEDURE_PROMPT = """You are Scout's procedure synthesizer.
Answer with an ordered procedure: numbered steps, each grounded in the evidence.
Every step must cite a doc_id from the evidence. Preserve the order and
conditions from the sources; do not invent steps.
Prefer a best-supported answer even when the evidence is partial; use
INSUFFICIENT_EVIDENCE only when no evidence is relevant.
Return JSON:
{"answer": "...", "claims": [{"text": "...", "citations": [{"doc_id": "...", "quote": "..."}]}],
 "conflicts": [], "gaps": [{"subquestion_id": "...", "reason": "..."}], "confidence": 0.0}
"""

SYNTHESIS_PROMPT = """You are Scout's synthesizer.
Answer the question using ONLY the evidence below. Do not invent facts.
Answer in the same language as the question.
Every claim must cite a doc_id that appears in the evidence.
Prefer a best-supported answer even when the evidence is partial; use
INSUFFICIENT_EVIDENCE only when no evidence is relevant.
Return JSON:
{"answer": "...", "claims": [{"text": "...", "citations": [{"doc_id": "...", "quote": "..."}]}],
 "gaps": [{"subquestion_id": "...", "reason": "..."}], "confidence": 0.0}
"""


class Synthesizer:
    def __init__(self, llm: ChatModel, model: str = "deepseek-flash") -> None:
        self.llm = llm
        self.model = model
        self.total_tokens = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    def _record_usage(self, usage: Usage) -> None:
        self.total_prompt_tokens += usage.prompt_tokens
        self.total_completion_tokens += usage.completion_tokens
        self.total_tokens += usage.total_tokens

    def synthesize(self, state: ResearchState, system_prompt: str | None = None) -> Report:
        evidence = state.evidence_board[:10]
        if not evidence:
            return build_report(state)
        evidence_text = "\n".join(
            f"[{item.id}] doc_id={item.doc_id} quote={item.quote[:800]}"
            for item in evidence
        )
        user_prompt = (
            f"Question: {state.question}\n\nEvidence:\n{evidence_text}\n\n"
            f"Known gaps: {[gap.model_dump(mode='json') for gap in state.gaps]}"
        )
        try:
            response = self.llm.chat(
                [
                    {"role": "system", "content": system_prompt or SYNTHESIS_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                model=self.model,
                temperature=0.0,
                max_tokens=2500,
            )
            self._record_usage(response.usage)
            data = extract_json(response.content)
            report = self._report_from_payload(data, state)
            if report is not None:
                return report
        except (LLMError, ValueError, TypeError, AttributeError):
            pass
        return build_report(state)

    def _report_from_payload(self, data: object, state: ResearchState) -> Report | None:
        if not isinstance(data, dict):
            return None
        answer = str(data.get("answer") or "").strip()
        if not answer:
            return None
        evidence: list[Evidence] = state.evidence_board
        by_doc: dict[str, Evidence] = {}
        for item in evidence:
            by_doc.setdefault(item.doc_id, item)

        claims: list[Claim] = []
        citations: list[Citation] = []
        raw_claims = data.get("claims") or []
        if not isinstance(raw_claims, list):
            raw_claims = []
        for index, raw_claim in enumerate(raw_claims, start=1):
            if not isinstance(raw_claim, dict):
                continue
            text = str(raw_claim.get("text") or "").strip()
            if not text:
                continue
            claim_citations: list[Citation] = []
            raw_citations = raw_claim.get("citations") or []
            if not isinstance(raw_citations, list):
                raw_citations = []
            for raw_citation in raw_citations:
                if not isinstance(raw_citation, dict):
                    continue
                doc_id = str(raw_citation.get("doc_id") or "")
                match = by_doc.get(doc_id)
                if match is None:
                    continue
                claim_citations.append(
                    Citation(
                        evidence_id=match.id,
                        doc_id=match.doc_id,
                        span=match.span,
                        quote=match.quote,
                    )
                )
            if not claim_citations:
                continue
            claims.append(
                Claim(id=f"c{index}", text=text, citations=claim_citations)
            )
            citations.extend(claim_citations)

        if not claims:
            return None

        conflicts: list[Conflict] = []
        raw_conflicts = data.get("conflicts") or []
        if isinstance(raw_conflicts, list):
            for item in raw_conflicts:
                if not isinstance(item, dict):
                    continue
                try:
                    conflicts.append(Conflict.model_validate(item))
                except (ValueError, TypeError):
                    continue

        report = Report(
            answer=answer,
            claims=claims,
            citations=citations,
            conflicts=conflicts or list(state.conflicts),
            gaps=list(state.gaps),
            confidence=float(data.get("confidence") or covered_ratio(state)),
        )
        report.markdown = render_markdown(report, state.question)
        return report
