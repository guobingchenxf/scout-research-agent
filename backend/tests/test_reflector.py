from __future__ import annotations

from scout.agent.reflector import Reflector
from scout.agent.state import add_evidence, mark_coverage, new_state, set_plan
from scout.models import Evidence, TrustLevel


def _evidence(doc_id: str, claim: str, quote: str) -> Evidence:
    return Evidence(
        id=f"e-{doc_id}",
        claim=claim,
        doc_id=doc_id,
        span="document",
        quote=quote,
        trust=TrustLevel.PRIMARY,
    )


def test_reflector_requires_coverage_and_gaps(store, sample_documents, sample_chunks) -> None:
    for document, chunk in zip(sample_documents, sample_chunks):
        store.ingest_document(document, [chunk])

    state = new_state("What is PagedAttention?")
    set_plan(state, ["definition", "comparison"])
    add_evidence(
        state,
        _evidence(
            "arxiv:1",
            "vLLM uses PagedAttention",
            "vLLM uses PagedAttention to manage the KV cache efficiently.",
        ),
    )
    mark_coverage(state, "q1", "covered", ["e-arxiv:1"])

    reflection = Reflector(store, coverage_threshold=0.5).reflect(state)
    assert not reflection.sufficient
    assert reflection.unresolved_gaps
    assert reflection.coverage_ratio == 0.5


def test_reflector_detects_citation_mismatch(store, sample_documents, sample_chunks) -> None:
    store.ingest_document(sample_documents[0], [sample_chunks[0]])
    state = new_state("q")
    set_plan(state, ["q1"])
    add_evidence(
        state,
        _evidence("arxiv:1", "a claim", "this quote is not in the document"),
    )
    mark_coverage(state, "q1", "covered", ["e-arxiv:1"])

    reflection = Reflector(store, coverage_threshold=0.5).reflect(state)
    assert not reflection.sufficient
    assert any("quote not found" in note for note in reflection.notes)


def test_reflector_detects_negation_conflict(store) -> None:
    state = new_state("q")
    set_plan(state, ["q1"])
    add_evidence(
        state,
        _evidence("arxiv:1", "vLLM uses PagedAttention for memory", "a"),
    )
    add_evidence(
        state,
        _evidence("arxiv:2", "vLLM does not use PagedAttention for memory", "b"),
    )
    reflection = Reflector(store, coverage_threshold=0.0).reflect(state)
    assert reflection.conflicts
