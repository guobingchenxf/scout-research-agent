from __future__ import annotations

from scout.models import (
    EvalCategory,
    EvalTask,
    ResearchState,
    RetrievalMethod,
    SourceDocument,
    SourceType,
    TrustLevel,
)


def test_source_document_serializes_enums() -> None:
    document = SourceDocument(
        id="arxiv:1",
        title="Test",
        url="https://arxiv.org/abs/1",
        source_type=SourceType.PAPER,
        trust=TrustLevel.PRIMARY,
        retrieval_method=RetrievalMethod.API,
    )
    payload = document.model_dump(mode="json")
    assert payload["source_type"] == "paper"
    assert payload["trust"] == "primary"
    assert payload["retrieval_method"] == "api"


def test_research_state_defaults() -> None:
    state = ResearchState(question="What is PagedAttention?")
    assert state.plan == []
    assert state.evidence_board == []
    assert state.budget.steps == 0
    assert state.coverage == {}


def test_eval_task_validation() -> None:
    task = EvalTask(
        id="fact_001",
        category=EvalCategory.FACT,
        question="What does vLLM use for KV cache management?",
        gold_answer="PagedAttention",
        required_citations=["arxiv:2309.06180"],
    )
    assert task.category == EvalCategory.FACT
    assert task.max_steps == 20
    assert task.required_citations == ["arxiv:2309.06180"]
