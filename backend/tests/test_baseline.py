from __future__ import annotations

from scout.baseline import SingleShotRAG
from scout.llm import MockLLM
from scout.retrieval import HybridIndex


def test_extractive_baseline_returns_citations(sample_documents, sample_chunks) -> None:
    index = HybridIndex(sample_chunks, sample_documents)
    result = SingleShotRAG(index, None).run("RadixAttention prefix sharing")
    assert result.mode == "extractive"
    assert result.answer
    assert result.citations
    assert result.citations[0].doc_id == "docs:sglang:index"


def test_llm_baseline_parses_json(sample_documents, sample_chunks) -> None:
    index = HybridIndex(sample_chunks, sample_documents)
    llm = MockLLM(
        [
            (
                '{"answer": "SGLang uses RadixAttention [docs:sglang:index]", '
                '"citations": ["docs:sglang:index"]}'
            )
        ]
    )
    result = SingleShotRAG(index, llm).run("RadixAttention prefix sharing")
    assert result.mode == "llm"
    assert result.citations[0].doc_id == "docs:sglang:index"
    assert "RadixAttention" in result.answer


def test_no_hits_is_explicit(sample_documents, sample_chunks) -> None:
    index = HybridIndex(sample_chunks, sample_documents)
    result = SingleShotRAG(index, None, top_k=1).run("quantum entanglement bananas")
    assert result.answer == "INSUFFICIENT_EVIDENCE"
    assert result.mode == "no_hits"
