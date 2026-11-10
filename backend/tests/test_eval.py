from __future__ import annotations

import json

from scout.config import ScoutConfig
from scout.eval.baselines import run_react_no_reflect, run_scout, run_single_shot_rag
from scout.eval.graders import RuleGrader
from scout.eval.metrics import summarize
from scout.eval.tasks import load_tasks, validate_task_evidence
from scout.models import (
    Citation,
    EvalCategory,
    EvalResult,
    EvalTask,
)
from scout.retrieval import build_index_from_store


def _fact_task() -> EvalTask:
    return EvalTask(
        id="t-fact",
        category=EvalCategory.FACT,
        question="What does vLLM use?",
        gold_answer="vLLM uses PagedAttention.",
        required_citations=["arxiv:1"],
        gold_evidence=[
            {
                "doc_id": "arxiv:1",
                "quote": "vLLM uses PagedAttention to manage the KV cache efficiently.",
            }
        ],
    )


def test_rule_grader_passes_supported_answer(store, sample_documents, sample_chunks) -> None:
    store.ingest_document(sample_documents[0], [sample_chunks[0]])
    citation = Citation(
        doc_id="arxiv:1",
        quote="vLLM uses PagedAttention to manage the KV cache efficiently.",
    )
    result = RuleGrader(store).grade(
        _fact_task(),
        "vLLM uses PagedAttention [arxiv:1]",
        [citation],
    )
    assert result.passed
    assert result.citation_support_rate == 1.0


def test_rule_grader_rejects_missing_citation(store, sample_documents, sample_chunks) -> None:
    store.ingest_document(sample_documents[0], [sample_chunks[0]])
    result = RuleGrader(store).grade(
        _fact_task(),
        "vLLM uses PagedAttention.",
        [],
    )
    assert not result.passed
    assert result.failure_category in {"missing_citation", "citation_mismatch"}


def test_rule_grader_abstention() -> None:
    task = EvalTask(
        id="t-abstain",
        category=EvalCategory.ABSTENTION,
        question="What is the price?",
        gold_answer="INSUFFICIENT_EVIDENCE",
    )
    grader = RuleGrader()
    assert grader.grade(task, "INSUFFICIENT_EVIDENCE", []).passed
    rejected = grader.grade(task, "The price is $10.", [])
    assert not rejected.passed
    assert rejected.failure_category == "over_answer"


def test_load_tasks_and_validate(tmp_path, store, corpus_dir) -> None:
    from scout.corpus import ingest_corpus

    ingest_corpus(store, corpus_dir)
    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(
        json.dumps(
            [
                {
                    "id": "valid",
                    "category": "fact",
                    "question": "What manages the KV cache?",
                    "gold_answer": "vLLM manages the KV cache with PagedAttention.",
                    "gold_evidence": [
                        {
                            "doc_id": "arxiv:1",
                            "quote": "vLLM manages the KV cache",
                        }
                    ],
                    "required_citations": ["arxiv:1"],
                }
            ]
        ),
        encoding="utf-8",
    )
    tasks = load_tasks(tasks_path)
    assert len(tasks) == 1
    assert validate_task_evidence(tasks, store) == []


def test_summarize_metrics() -> None:
    tasks = [
        EvalTask(
            id="a",
            category=EvalCategory.FACT,
            question="q",
            gold_answer="a",
        ),
        EvalTask(
            id="b",
            category=EvalCategory.MULTI_HOP,
            question="q",
            gold_answer="b",
        ),
    ]
    results = [
        EvalResult(
            task_id="a",
            passed=True,
            citation_support_rate=1.0,
            metrics={"steps": 2.0},
            latency_ms=100.0,
        ),
        EvalResult(
            task_id="b",
            passed=False,
            citation_support_rate=0.5,
            metrics={"steps": 4.0},
            failure_category="missing_fact",
            latency_ms=300.0,
        ),
    ]
    summary = summarize(results, tasks)
    assert summary["tasks"] == 2
    assert summary["passed"] == 1
    assert summary["pass_rate"] == 0.5
    assert summary["failure_counts"] == {"missing_fact": 1}
    assert summary["by_category"]["fact"]["pass_rate"] == 1.0


def test_single_shot_and_react_baselines(sample_documents, sample_chunks) -> None:
    index = build_index_from_store(
        type(
            "FakeStore",
            (),
            {
                "list_chunks": lambda self: sample_chunks,
                "list_documents": lambda self: sample_documents,
            },
        )()
    )
    single = run_single_shot_rag("PagedAttention", index, None)
    assert "PagedAttention" in single.answer
    assert single.citations

    react = run_react_no_reflect("PagedAttention", index, None)
    assert "PagedAttention" in react.answer
    assert react.citations


def test_scout_mock_baseline(store, sample_documents, sample_chunks, tmp_path) -> None:
    for document, chunk in zip(sample_documents, sample_chunks):
        store.ingest_document(document, [chunk])
    index = build_index_from_store(store)
    config = ScoutConfig(
        db_path=tmp_path / "eval.db",
        max_steps=6,
        token_budget=100_000,
        cost_budget_usd=1.0,
        verify_dns=False,
    )
    output = run_scout(
        "What is PagedAttention?",
        config,
        store,
        index,
        planner_name="mock",
        max_steps=6,
    )
    assert output.answer
    assert output.steps <= 6
