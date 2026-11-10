"""Single-shot RAG baseline used to establish the first numbers."""

from __future__ import annotations

import re
from collections.abc import Sequence

from .llm import ChatModel, LLMError, estimate_cost, extract_json
from .models import BaselineResult, Citation, SearchHit
from .retrieval import HybridIndex

_CITATION_ID = re.compile(r"\[([A-Za-z0-9_:\-./]+)\]")

SYSTEM_PROMPT = (
    "You are Scout's baseline research assistant. Answer ONLY from the provided context. "
    "Every factual sentence must end with a citation in the form [doc_id]. "
    "If the context is insufficient, answer exactly INSUFFICIENT_EVIDENCE. "
    'Return JSON: {"answer": "...", "citations": ["doc_id"]}.'
)


class SingleShotRAG:
    """Retrieve top-k chunks and answer once.

    This is deliberately not an agent: no planning, no reflection, no evidence
    board. It exists so later phases can prove that the agent loop adds value.
    """

    def __init__(
        self,
        index: HybridIndex,
        llm: ChatModel | None = None,
        *,
        model: str = "deepseek-flash",
        top_k: int = 6,
        language: str = "zh",
        cost_input_per_1k: float = 0.0,
        cost_output_per_1k: float = 0.0,
    ) -> None:
        self.index = index
        self.llm = llm
        self.model = model
        self.top_k = top_k
        self.language = language
        self.cost_input_per_1k = cost_input_per_1k
        self.cost_output_per_1k = cost_output_per_1k

    def run(self, question: str) -> BaselineResult:
        hits = self.index.search(question, k=self.top_k)
        if not hits:
            return BaselineResult(
                question=question,
                answer="INSUFFICIENT_EVIDENCE",
                citations=[],
                hits=[],
                mode="no_hits",
            )
        if self.llm is None:
            return self._extractive(question, hits)

        context = "\n\n".join(f"[{hit.doc_id}] {hit.snippet}" for hit in hits)
        language_line = "Answer in Chinese." if self.language == "zh" else "Answer in English."
        messages = [
            {"role": "system", "content": f"{SYSTEM_PROMPT} {language_line}"},
            {
                "role": "user",
                "content": f"Question: {question}\n\nContext:\n{context}",
            },
        ]
        response = self.llm.chat(
            messages,
            model=self.model,
            temperature=0.0,
            max_tokens=1200,
        )
        answer, doc_ids = self._parse(response.content, hits)
        citations = self._citations(doc_ids, hits)
        return BaselineResult(
            question=question,
            answer=answer,
            citations=citations,
            hits=hits,
            usage=response.usage.as_dict(),
            cost_usd=estimate_cost(
                response.usage, self.cost_input_per_1k, self.cost_output_per_1k
            ),
            mode="llm",
        )

    def _extractive(self, question: str, hits: Sequence[SearchHit]) -> BaselineResult:
        selected = list(hits[:3])
        body = "\n".join(f"- {hit.snippet} [{hit.doc_id}]" for hit in selected)
        answer = f"根据检索到的资料：\n\n{body}"
        citations = self._citations([hit.doc_id for hit in selected], hits)
        return BaselineResult(
            question=question,
            answer=answer,
            citations=citations,
            hits=list(hits),
            mode="extractive",
        )

    def _parse(self, content: str, hits: Sequence[SearchHit]) -> tuple[str, list[str]]:
        doc_ids: list[str] = []
        answer = content.strip()
        try:
            data = extract_json(content)
        except LLMError:
            data = None
        if isinstance(data, dict):
            answer = str(data.get("answer") or answer).strip()
            raw = data.get("citations") or []
            if isinstance(raw, str):
                raw = [raw]
            for item in raw:
                if isinstance(item, dict):
                    doc_ids.append(str(item.get("doc_id", "")))
                else:
                    doc_ids.append(str(item))
        if not doc_ids:
            doc_ids = _CITATION_ID.findall(answer)

        known = {hit.doc_id for hit in hits}
        unique = [doc_id for doc_id in dict.fromkeys(doc_ids) if doc_id in known]
        if not unique and hits:
            unique = [hits[0].doc_id]
        return answer, unique

    def _citations(self, doc_ids: Sequence[str], hits: Sequence[SearchHit]) -> list[Citation]:
        by_doc: dict[str, SearchHit] = {}
        for hit in hits:
            by_doc.setdefault(hit.doc_id, hit)
        citations: list[Citation] = []
        for doc_id in doc_ids:
            match = by_doc.get(doc_id)
            if match is None:
                continue
            citations.append(
                Citation(
                    doc_id=doc_id,
                    span="chunk",
                    quote=match.snippet,
                    url=match.url,
                )
            )
        return citations
