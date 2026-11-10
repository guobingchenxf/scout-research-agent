from __future__ import annotations

from scout.agent.abstention import unsupported_specific_claim


def test_price_question_without_price_evidence_abstains() -> None:
    reason = unsupported_specific_claim(
        "vLLM 的企业版授权价格是多少？",
        "vLLM is an open-source inference engine for LLMs.",
    )
    assert reason == "missing price evidence"


def test_entity_missing_abstains() -> None:
    reason = unsupported_specific_claim(
        "NVIDIA H200 的显存容量是多少？",
        "TensorRT-LLM optimizes inference with specialized kernels and memory reuse.",
    )
    assert reason is not None
    assert "entity" in reason


def test_normal_fact_question_is_not_gated() -> None:
    reason = unsupported_specific_claim(
        "vLLM 的 PagedAttention 是什么？",
        "vLLM uses PagedAttention to manage the KV cache.",
    )
    assert reason is None
