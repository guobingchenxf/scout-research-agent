"""Optional long-term memory adapters."""

from __future__ import annotations

from typing import Protocol

from ..config import ScoutConfig
from .engram import EngramMemory


class MemoryClient(Protocol):
    def search_context(self, query: str) -> str: ...

    def write_run(
        self,
        *,
        question: str,
        answer: str,
        run_id: str,
        sources: list[str] | None = None,
        status: str = "finished",
        importance: float = 0.6,
    ) -> str | None: ...

    def close(self) -> None: ...


def build_memory_client(config: ScoutConfig) -> EngramMemory | None:
    return EngramMemory.from_config(config)


__all__ = ["EngramMemory", "MemoryClient", "build_memory_client"]
