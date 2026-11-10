from __future__ import annotations

import numpy as np

from scout.retrieval import BM25Index, HashEmbedding, HybridIndex, tokenize


def test_tokenize_chinese_bigrams() -> None:
    tokens = tokenize("智能体记忆")
    assert "智能" in tokens
    assert "能体" in tokens
    assert "记忆" in tokens


def test_bm25_ranks_relevant_chunk(sample_chunks) -> None:
    index = BM25Index(sample_chunks)
    results = index.search("PagedAttention KV cache")
    assert results
    assert results[0][0] == "arxiv:1:0"


def test_hash_embedding_is_deterministic() -> None:
    first = HashEmbedding(dim=64)
    second = HashEmbedding(dim=64)
    assert np.allclose(first.embed("vLLM PagedAttention"), second.embed("vLLM PagedAttention"))


def test_hybrid_search_returns_expected_document(sample_documents, sample_chunks) -> None:
    index = HybridIndex(sample_chunks, sample_documents)
    hits = index.search("RadixAttention prefix sharing", k=2)
    assert hits
    assert hits[0].doc_id == "docs:sglang:index"
    assert hits[0].retrieval_method.value == "api"


def test_hybrid_search_source_filter(sample_documents, sample_chunks) -> None:
    index = HybridIndex(sample_chunks, sample_documents)
    hits = index.search("KV cache", k=5, source_types={"paper"})
    assert hits
    assert all(hit.doc_id == "arxiv:1" for hit in hits)
