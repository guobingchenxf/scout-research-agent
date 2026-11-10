"""Load and validate the frozen evaluation task set."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..config import PROJECT_ROOT
from ..models import EvalTask
from ..storage import SQLiteStore


class EvalTaskError(Exception):
    pass


def default_tasks_path() -> Path:
    return PROJECT_ROOT / "eval" / "tasks.json"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and "tasks" in payload:
        tasks = payload["tasks"]
        if not isinstance(tasks, list):
            raise EvalTaskError("tasks must be a list")
        return [item for item in tasks if isinstance(item, dict)]
    if isinstance(payload, dict) and "id" in payload:
        return [payload]
    raise EvalTaskError("task payload must be a task, a list, or {'tasks': [...]}")


def load_tasks(path: str | Path | None = None) -> list[EvalTask]:
    target = Path(path) if path else default_tasks_path()
    if not target.exists():
        raise EvalTaskError(f"task file not found: {target}")
    files = sorted(target.glob("*.json")) if target.is_dir() else [target]
    tasks: list[EvalTask] = []
    for file in files:
        payload = json.loads(file.read_text(encoding="utf-8"))
        for item in _items(payload):
            tasks.append(EvalTask.model_validate(item))
    ids = [task.id for task in tasks]
    duplicates = {value for value in ids if ids.count(value) > 1}
    if duplicates:
        raise EvalTaskError(f"duplicate task ids: {sorted(duplicates)}")
    if not tasks:
        raise EvalTaskError(f"no tasks found in {target}")
    return tasks


def validate_task_evidence(tasks: list[EvalTask], store: SQLiteStore) -> list[str]:
    issues: list[str] = []
    for task in tasks:
        for evidence in task.gold_evidence:
            doc_id = str(evidence.get("doc_id", ""))
            quote = str(evidence.get("quote", ""))
            if not doc_id or not quote:
                issues.append(f"{task.id}: gold evidence needs doc_id and quote")
                continue
            document = store.get_document(doc_id)
            if document is None:
                issues.append(f"{task.id}: unknown doc_id {doc_id}")
                continue
            if _normalize(quote) not in _normalize(document.text):
                issues.append(f"{task.id}: quote not found in {doc_id}")
    return issues
