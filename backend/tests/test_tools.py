from __future__ import annotations

from scout.agent.state import new_state, set_plan
from scout.agent.tools import ToolContext, ToolRegistry
from scout.models import ToolCall
from scout.retrieval import HybridIndex


def _registry(store, sample_documents, sample_chunks) -> ToolRegistry:
    for document, chunk in zip(sample_documents, sample_chunks):
        store.ingest_document(document, [chunk])
    index = HybridIndex(sample_chunks, sample_documents)
    return ToolRegistry(ToolContext(store=store, index=index, run_id="run-1"))


def test_search_returns_hits(store, sample_documents, sample_chunks) -> None:
    registry = _registry(store, sample_documents, sample_chunks)
    result = registry.execute(
        ToolCall(call_id="1", name="search", arguments={"query": "PagedAttention", "k": 3}),
        new_state("q"),
    )
    assert result.ok
    assert result.output["kind"] == "search"
    assert result.output["hits"]
    assert result.output["hits"][0]["doc_id"] == "arxiv:1"


def test_read_returns_document_text(store, sample_documents, sample_chunks) -> None:
    registry = _registry(store, sample_documents, sample_chunks)
    result = registry.execute(
        ToolCall(call_id="1", name="read", arguments={"source_id": "arxiv:1"}),
        new_state("q"),
    )
    assert result.ok
    assert result.output["kind"] == "read"
    assert "PagedAttention" in result.output["text"]


def test_finish_builds_report(store, sample_documents, sample_chunks) -> None:
    registry = _registry(store, sample_documents, sample_chunks)
    state = new_state("What is PagedAttention?")
    set_plan(state, ["definition"])
    arguments = {
        "answer": "vLLM uses PagedAttention for KV cache management.",
        "claims": [
            {
                "text": "vLLM uses PagedAttention.",
                "citations": [
                    {
                        "doc_id": "arxiv:1",
                        "quote": "vLLM uses PagedAttention to manage the KV cache efficiently.",
                    }
                ],
            }
        ],
        "gaps": [],
        "confidence": 0.8,
    }
    result = registry.execute(
        ToolCall(call_id="1", name="finish", arguments=arguments), state
    )
    assert result.ok
    assert result.output["kind"] == "finish"
    assert result.output["report"]["claims"][0]["citations"][0]["doc_id"] == "arxiv:1"


def test_finish_accepts_reported_conflicts(store, sample_documents, sample_chunks) -> None:
    registry = _registry(store, sample_documents, sample_chunks)
    state = new_state("q")
    arguments = {
        "answer": "Sources disagree.",
        "claims": [
            {
                "text": "A source says vLLM uses PagedAttention.",
                "citations": [{"doc_id": "arxiv:1", "quote": "PagedAttention"}],
            }
        ],
        "conflicts": [
            {
                "claim_a": "vLLM uses PagedAttention",
                "claim_b": "vLLM does not use PagedAttention",
                "reason": "opposite claims",
            }
        ],
    }
    result = registry.execute(
        ToolCall(call_id="1", name="finish", arguments=arguments), state
    )
    assert result.ok
    assert result.output["report"]["conflicts"][0]["reason"] == "opposite claims"


def test_finish_rejects_uncited_claim(store, sample_documents, sample_chunks) -> None:
    registry = _registry(store, sample_documents, sample_chunks)
    state = new_state("q")
    result = registry.execute(
        ToolCall(
            call_id="1",
            name="finish",
            arguments={
                "answer": "unsupported",
                "claims": [{"text": "no citation", "citations": []}],
            },
        ),
        state,
    )
    assert not result.ok
    assert "no citation" in (result.error or "")


def test_ask_human_records_approval(store, sample_documents, sample_chunks) -> None:
    registry = _registry(store, sample_documents, sample_chunks)
    result = registry.execute(
        ToolCall(
            call_id="1",
            name="ask_human",
            arguments={
                "question": "Approve this step?",
                "options": ["approve", "reject"],
                "risk": "approval",
            },
        ),
        new_state("q"),
    )
    assert result.ok
    assert result.output["decision"] == "approve"
    approvals = store.list_approvals("run-1")
    assert approvals[0].decision == "approve"


def test_python_is_disabled_until_phase_three(store, sample_documents, sample_chunks) -> None:
    registry = _registry(store, sample_documents, sample_chunks)
    result = registry.execute(
        ToolCall(call_id="1", name="python", arguments={"code": "print(1)"}),
        new_state("q"),
    )
    assert not result.ok
    assert "disabled" in (result.error or "")
