from __future__ import annotations

import httpx
import pytest

from scout.llm import LLMClient, LLMError, MockLLM, build_chat_url, extract_json


def test_build_chat_url() -> None:
    assert build_chat_url("https://api.deepseek.com") == (
        "https://api.deepseek.com/chat/completions"
    )
    assert build_chat_url("https://api.deepseek.com/v1/") == (
        "https://api.deepseek.com/v1/chat/completions"
    )
    assert build_chat_url("https://api.deepseek.com/chat/completions") == (
        "https://api.deepseek.com/chat/completions"
    )


def test_extract_json_from_code_fence() -> None:
    assert extract_json('```json\n{"answer": "ok"}\n```') == {"answer": "ok"}
    assert extract_json('prefix {"answer": "ok"} suffix') == {"answer": "ok"}


def test_mock_llm_script() -> None:
    llm = MockLLM(["one", "two"])
    assert llm.chat([], "mock").content == "one"
    assert llm.chat([], "mock").content == "two"
    assert llm.chat([], "mock").content == "{}"
    assert len(llm.calls) == 3


def test_client_retries_then_succeeds() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(500, json={"error": "temporary"})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2},
                "model": "deepseek-flash",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = LLMClient(
        "https://api.deepseek.com",
        "sk-test",
        client=client,
        max_retries=1,
        sleep=lambda _: None,
    )
    response = llm.chat([{"role": "user", "content": "hi"}], "deepseek-flash")
    assert response.content == "ok"
    assert response.usage.total_tokens == 3
    assert calls["count"] == 2


def test_client_without_key_raises() -> None:
    llm = LLMClient("https://api.deepseek.com", "")
    with pytest.raises(LLMError):
        llm.chat([{"role": "user", "content": "hi"}], "deepseek-flash")
    llm.close()
