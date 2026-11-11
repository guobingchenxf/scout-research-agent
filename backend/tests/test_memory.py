"""Tests for the Engram HTTP adapter."""

from __future__ import annotations

import json
from typing import Any

import httpx

from scout.memory.engram import EngramMemory


def _client(handler: Any) -> httpx.Client:
    return httpx.Client(
        base_url="http://engram.test",
        transport=httpx.MockTransport(handler),
    )


def test_search_context_returns_prompt_block() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/memories/search"
        payload = json.loads(request.content)
        assert payload["user_id"] == "scout"
        assert payload["query"] == "PagedAttention"
        assert payload["top_k"] == 3
        return httpx.Response(200, json={"context": "- prior run used docs.vllm.ai"})

    memory = EngramMemory(
        "http://engram.test", top_k=3, client=_client(handler)
    )
    assert memory.search_context("PagedAttention") == "- prior run used docs.vllm.ai"


def test_write_run_sends_agent_episodic_memory() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"id": "mem-123"})

    memory = EngramMemory("http://engram.test", client=_client(handler))
    memory_id = memory.write_run(
        question="What is PagedAttention?",
        answer="A KV-cache paging method.",
        run_id="run-1",
        sources=["arxiv:2309.06180"],
    )
    assert memory_id == "mem-123"
    assert captured["type"] == "episodic"
    assert captured["source_type"] == "agent"
    assert captured["metadata"]["run_id"] == "run-1"
    assert "arxiv:2309.06180" in captured["content"]


def test_memory_failure_is_fail_open() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "down"})

    memory = EngramMemory("http://engram.test", client=_client(handler))
    assert memory.search_context("q") == ""
    assert (
        memory.write_run(
            question="q", answer="a", run_id="run-2", sources=[]
        )
        is None
    )


def test_tenant_is_scoped_when_configured() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["tenant_id"] == "team-a"
        return httpx.Response(200, json={"context": ""})

    memory = EngramMemory(
        "http://engram.test",
        tenant_id="team-a",
        client=_client(handler),
    )
    assert memory.search_context("q") == ""
