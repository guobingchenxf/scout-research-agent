"""Append-only run trace: SQLite events plus an optional JSONL mirror."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Event
from .storage import SQLiteStore


class Trace:
    def __init__(
        self,
        store: SQLiteStore,
        run_id: str,
        *,
        directory: str | Path | None = None,
    ) -> None:
        self.store = store
        self.run_id = run_id
        self.path: Path | None = None
        if directory is not None:
            root = Path(directory)
            root.mkdir(parents=True, exist_ok=True)
            self.path = root / f"{run_id}.jsonl"

    def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> Event:
        event = self.store.append_event(self.run_id, event_type, payload or {})
        if self.path is not None:
            record = {
                "seq": event.seq,
                "type": event.type,
                "payload": event.payload,
                "ts": event.ts,
            }
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return event

    def events(self) -> list[Event]:
        return self.store.list_events(self.run_id)
