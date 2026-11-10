from __future__ import annotations

from scout.agent.state import add_evidence, new_state
from scout.agent.synthesis import Synthesizer
from scout.llm import MockLLM
from scout.models import Evidence, TrustLevel


def _state():
    state = new_state("What is PagedAttention?")
    add_evidence(
        state,
        Evidence(
            id="e1",
            claim="vLLM uses PagedAttention to manage the KV cache.",
            doc_id="arxiv:1",
            span="document",
            quote="vLLM uses PagedAttention to manage the KV cache.",
            trust=TrustLevel.PRIMARY,
        ),
    )
    return state


def test_synthesizer_builds_citation_bound_report() -> None:
    llm = MockLLM(
        [
            (
                '{"answer": "vLLM uses PagedAttention [arxiv:1].", '
                '"claims": [{"text": "vLLM uses PagedAttention.", '
                '"citations": [{"doc_id": "arxiv:1", "quote": "vLLM uses PagedAttention"}]}], '
                '"gaps": [], "confidence": 0.8}'
            )
        ]
    )
    report = Synthesizer(llm, "deepseek-flash").synthesize(_state())
    assert "PagedAttention" in report.answer
    assert report.claims
    assert report.citations[0].doc_id == "arxiv:1"
    assert report.confidence == 0.8


def test_synthesizer_falls_back_on_invalid_json() -> None:
    llm = MockLLM(["not json"])
    report = Synthesizer(llm, "deepseek-flash").synthesize(_state())
    assert report.answer
    assert report.claims
