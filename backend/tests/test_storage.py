from __future__ import annotations

from scout.models import (
    Approval,
    Citation,
    Evidence,
    Run,
    RunStatus,
    SupportType,
)


def test_ingest_document_and_chunks(store, sample_documents, sample_chunks) -> None:
    document = sample_documents[0]
    chunks = [sample_chunks[0]]
    store.ingest_document(document, chunks)

    assert store.count_documents() == 1
    assert store.count_chunks() == 1
    loaded = store.get_document(document.id)
    assert loaded is not None
    assert loaded.title == document.title
    assert loaded.source_type.value == "paper"
    listed = store.list_chunks()
    assert listed[0].id == "arxiv:1:0"


def test_run_and_events(store) -> None:
    store.create_run(Run(id="r1", question="test question"))
    first = store.append_event("r1", "plan", {"steps": 1})
    second = store.append_event("r1", "search", {"query": "kv cache"})
    assert first.seq == 1
    assert second.seq == 2
    events = store.list_events("r1")
    assert [event.type for event in events] == ["plan", "search"]

    store.update_run("r1", status=RunStatus.FINISHED, result={"ok": True})
    run = store.get_run("r1")
    assert run is not None
    assert run.status == RunStatus.FINISHED
    assert run.result == {"ok": True}


def test_evidence_and_citations(store) -> None:
    evidence = Evidence(
        id="e1",
        claim="vLLM uses PagedAttention",
        doc_id="arxiv:1",
        span="Section 4",
        quote="PagedAttention",
        support=SupportType.DIRECT,
    )
    store.add_evidence("r1", evidence)
    stored = store.list_evidence("r1")
    assert len(stored) == 1
    assert stored[0].claim == evidence.claim

    store.add_citation(
        "r1",
        Citation(doc_id="arxiv:1", span="Section 4", quote="PagedAttention"),
    )
    citations = store.list_citations("r1")
    assert citations[0].doc_id == "arxiv:1"


def test_approvals(store) -> None:
    approval = Approval(
        id="a1",
        run_id="r1",
        question="Approve refund?",
        options=["approve", "reject"],
    )
    store.add_approval(approval)
    assert store.decide_approval("a1", "approve", "tester", "ok")
    assert not store.decide_approval("a1", "reject", "tester")
    decided = store.list_approvals("r1")[0]
    assert decided.decision == "approve"
    assert decided.decided_by == "tester"


def test_audit_chain_and_tamper(store) -> None:
    store.append_audit("r1", "policy", "allow", "sources:read")
    store.append_audit("r1", "policy", "deny", "sources:write")
    ok, broken = store.verify_audit()
    assert ok is True
    assert broken is None

    with store._conn:
        store._conn.execute("UPDATE audit SET entry_hash = 'tampered' WHERE id = 1")

    ok, broken = store.verify_audit()
    assert ok is False
    assert broken == 1
