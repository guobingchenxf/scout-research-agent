"""OpenAI-compatible LLM client with a deterministic mock for tests."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx


class LLMError(Exception):
    """Raised when a provider call fails after retries or returns invalid data."""


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def as_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class ChatModel(Protocol):
    def chat(
        self,
        messages: Sequence[dict[str, Any]],
        model: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> LLMResponse: ...


def build_chat_url(base_url: str) -> str:
    """Accept a base URL with or without /v1 and without the endpoint."""

    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def extract_json(text: str) -> Any:
    """Parse a JSON object from a model response, tolerating code fences."""

    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        starts = [index for index in (cleaned.find("{"), cleaned.find("[")) if index >= 0]
        if not starts:
            raise LLMError("response does not contain JSON")
        start = min(starts)
        for end in range(len(cleaned), start, -1):
            try:
                return json.loads(cleaned[start:end])
            except json.JSONDecodeError:
                continue
    raise LLMError("could not parse JSON from model response")


def estimate_cost(usage: Usage, input_per_1k: float, output_per_1k: float) -> float:
    return (
        usage.prompt_tokens / 1000.0 * input_per_1k
        + usage.completion_tokens / 1000.0 * output_per_1k
    )


class LLMClient:
    """A thin OpenAI-compatible chat-completions client.

    DeepSeek exposes `POST {base_url}/chat/completions`. The base URL may be
    `https://api.deepseek.com` or `https://api.deepseek.com/v1`; both are
    accepted by `build_chat_url`.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 60.0,
        max_retries: int = 2,
        backoff: float = 0.5,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.max_retries = max_retries
        self.backoff = backoff
        self._sleep = sleep
        self._owns_client = client is None
        # trust_env=False avoids the broken Windows registry proxy for TLS.
        self._client = client or httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            trust_env=False,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def chat(
        self,
        messages: Sequence[dict[str, Any]],
        model: str,
        *,
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        if not self.api_key:
            raise LLMError("DEEPSEEK_API_KEY is not configured")

        payload: dict[str, Any] = {
            "model": model,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if response_format:
            payload["response_format"] = response_format

        url = build_chat_url(self.base_url)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_error = ""
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.post(url, json=payload, headers=headers)
            except httpx.RequestError as exc:
                last_error = f"request failed: {exc}"
                if attempt < self.max_retries:
                    self._sleep(self.backoff * (2**attempt))
                    continue
                raise LLMError(last_error) from exc

            if response.status_code in {429, 500, 502, 503, 504}:
                last_error = f"provider returned {response.status_code}"
                if attempt < self.max_retries:
                    retry_after = response.headers.get("retry-after")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() else self.backoff * (2**attempt)
                    self._sleep(delay)
                    continue
                raise LLMError(last_error)

            if response.status_code >= 400:
                raise LLMError(f"provider returned {response.status_code}: {response.text[:500]}")

            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                raise LLMError("provider returned no choices")
            message = choices[0].get("message") or {}
            usage_data = data.get("usage") or {}
            usage = Usage(
                prompt_tokens=int(usage_data.get("prompt_tokens", 0) or 0),
                completion_tokens=int(usage_data.get("completion_tokens", 0) or 0),
            )
            return LLMResponse(
                content=message.get("content") or "",
                tool_calls=message.get("tool_calls") or [],
                usage=usage,
                model=data.get("model", model),
                raw=data,
            )

        raise LLMError(last_error or "unknown provider error")


class MockLLM:
    """Deterministic test double.

    The mock records every call and returns scripted responses in order. When
    the script is exhausted it returns `default`.
    """

    def __init__(self, responses: Sequence[str] | None = None, default: str = "{}") -> None:
        self._responses = list(responses or [])
        self._default = default
        self.calls: list[list[dict[str, Any]]] = []

    def chat(
        self,
        messages: Sequence[dict[str, Any]],
        model: str = "mock",
        **kwargs: Any,
    ) -> LLMResponse:
        self.calls.append(list(messages))
        if self._responses:
            content = self._responses.pop(0)
        else:
            content = self._default
        return LLMResponse(content=content, model=model)

    def close(self) -> None:
        return None
