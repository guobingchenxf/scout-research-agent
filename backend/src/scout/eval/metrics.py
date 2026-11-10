"""Aggregate evaluation metrics."""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
from typing import Any

from ..models import EvalResult, EvalTask


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return float(ordered[index])


def summarize(results: list[EvalResult], tasks: list[EvalTask] | None = None) -> dict[str, Any]:
    task_by_id = {task.id: task for task in (tasks or [])}
    by_category: dict[str, list[EvalResult]] = defaultdict(list)
    for result in results:
        task = task_by_id.get(result.task_id)
        category = task.category.value if task else "unknown"
        by_category[category].append(result)

    def _block(items: list[EvalResult]) -> dict[str, Any]:
        latencies = [item.latency_ms for item in items]
        steps = [item.metrics.get("steps", 0.0) for item in items]
        tokens = [item.metrics.get("tokens", 0.0) for item in items]
        return {
            "tasks": len(items),
            "passed": sum(1 for item in items if item.passed),
            "pass_rate": (
                sum(1 for item in items if item.passed) / len(items) if items else 0.0
            ),
            "citation_support_rate": (
                mean([item.citation_support_rate for item in items]) if items else 0.0
            ),
            "avg_steps": mean(steps) if steps else 0.0,
            "avg_tokens": mean(tokens) if tokens else 0.0,
            "total_tokens": sum(tokens),
            "p50_latency_ms": percentile(latencies, 0.50),
            "p95_latency_ms": percentile(latencies, 0.95),
            "total_cost_usd": sum(item.cost_usd for item in items),
        }

    overall = _block(results)
    overall["by_category"] = {
        category: _block(items) for category, items in sorted(by_category.items())
    }
    overall["failure_counts"] = dict(
        Counter(
            item.failure_category
            for item in results
            if item.failure_category is not None
        )
    )
    return overall
