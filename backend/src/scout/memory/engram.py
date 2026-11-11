"""HTTP adapter for the Engram long-term memory layer.

Scout calls Engram through its public API instead of importing the package, so
the two projects stay independently deployable. The adapter is fail-open: a
memory outage never fails a research run, it only produces an empty context or
a skipped write.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import ScoutConfig

logger = logging.getLogger(__name__)


class EngramMemory:
    def __init__(
        self,
        base_url: str,
        *,
        user_id: str = "scout",
        tenant_id: str = "",
        api_key: str = "",
        top_k: int = 5,
        token_budget: int = 800,
        timeout: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.top_k = top_k
        self.token_budget = token_budget
        self._client = client or httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"X-API-Key": api_key} if api_key else {},
        )
        self._owns_client = client is None

    @classmethod
    def from_config(cls, config: ScoutConfig) -> EngramMemory | None:
        if not config.engram_url:
            return None
        return cls(
            config.engram_url,
            user_id=config.engram_user_id,
            tenant_id=config.engram_tenant_id,
            api_key=config.engram_api_key,
            top_k=config.engram_top_k,
            token_budget=config.engram_token_budget,
            timeout=config.engram_timeout_seconds,
        )

    def _scoped(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.tenant_id:
            payload["tenant_id"] = self.tenant_id
        return payload

    def search_context(self, query: str) -> str:
        payload = self._scoped(
            {
                "user_id": self.user_id,
                "query": query,
                "top_k": self.top_k,
                "token_budget": self.token_budget,
            }
        )
        try:
            response = self._client.post("/v1/memories/search", json=payload)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # noqa: BLE001 - memory must not fail a run
            logger.warning("Engram search failed: %s", exc)
            return ""
        context = data.get("context") if isinstance(data, dict) else ""
        return str(context or "").strip()

    def write_run(
        self,
        *,
        question: str,
        answer: str,
        run_id: str,
        sources: list[str] | None = None,
        status: str = "finished",
        importance: float = 0.6,
    ) -> str | None:
        content = f"Research run: {question}\n\nAnswer: {answer.strip()[:1200]}"
        cleaned_sources = [item for item in (sources or []) if item][:8]
        if cleaned_sources:
            content += "\n\nSources: " + ", ".join(cleaned_sources)
        payload = self._scoped(
            {
                "user_id": self.user_id,
                "content": content,
                "type": "episodic",
                "source_type": "agent",
                "source": "scout",
                "importance": max(0.0, min(1.0, importance)),
                "metadata": {
                    "kind": "research_run",
                    "run_id": run_id,
                    "question": question,
                    "status": status,
                    "sources": cleaned_sources,
                },
                "idempotency_key": f"scout-run-{run_id}",
            }
        )
        try:
            response = self._client.post("/v1/memories", json=payload)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # noqa: BLE001 - memory must not fail a run
            logger.warning("Engram write failed: %s", exc)
            return None
        if isinstance(data, dict) and data.get("id"):
            return str(data["id"])
        return None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
