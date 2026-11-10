"""Markdown evaluation report."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..models import EvalResult, EvalTask


def render_markdown(
    results: list[EvalResult],
    tasks: list[EvalTask],
    summary: dict[str, Any],
    *,
    system: str,
    planner: str,
) -> str:
    task_by_id = {task.id: task for task in tasks}
    lines = [
        "# Scout 评测报告",
        "",
        f"- system: `{system}`",
        f"- planner: `{planner}`",
        f"- tasks: {summary['tasks']}",
        f"- pass rate: {summary['pass_rate']:.1%}",
        f"- citation support: {summary['citation_support_rate']:.1%}",
        f"- avg steps: {summary['avg_steps']:.2f}",
        f"- avg / total tokens: {summary['avg_tokens']:.0f} / {summary['total_tokens']:.0f}",
        f"- p50 / p95 latency: {summary['p50_latency_ms']:.0f} / {summary['p95_latency_ms']:.0f} ms",
        f"- total cost: ${summary['total_cost_usd']:.4f}",
        "",
        "## 分类结果",
        "",
        "| category | tasks | passed | pass rate | citation support | avg steps | p95 latency |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for category, block in summary["by_category"].items():
        lines.append(
            f"| {category} | {block['tasks']} | {block['passed']} | "
            f"{block['pass_rate']:.1%} | {block['citation_support_rate']:.1%} | "
            f"{block['avg_steps']:.2f} | {block['p95_latency_ms']:.0f} ms |"
        )
    lines.extend(["", "## 失败分类", ""])
    if summary["failure_counts"]:
        for name, count in summary["failure_counts"].items():
            lines.append(f"- `{name}`: {count}")
    else:
        lines.append("（无失败）")
    lines.extend(["", "## 逐题结果", "", "| task | category | passed | failure |", "|---|---|---:|---|"])
    for result in results:
        task = task_by_id.get(result.task_id)
        category = task.category.value if task else "unknown"
        lines.append(
            f"| {result.task_id} | {category} | {'✅' if result.passed else '❌'} | "
            f"{result.failure_category or ''} |"
        )
    return "\n".join(lines) + "\n"


def write_markdown(path: str | Path, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
