#!/usr/bin/env python
"""Compare one or more eval summary JSON files.

Usage:
    python scripts/compare_evals.py reports/eval_heldout_seed1.json \
        reports/eval_heldout_seed2.json
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

FIELDS = [
    "pass_rate",
    "citation_support_rate",
    "avg_steps",
    "avg_tokens",
    "p50_latency_ms",
    "p95_latency_ms",
    "total_cost_usd",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()

    summaries = []
    for raw in args.files:
        path = Path(raw)
        payload = json.loads(path.read_text(encoding="utf-8"))
        summary = payload.get("summary", payload)
        summaries.append(summary)
        print(f"{path.name}: tasks={summary.get('tasks')} pass={summary.get('passed')}")

    print("\nmetric                 mean        std")
    for field in FIELDS:
        values = [float(summary.get(field, 0.0) or 0.0) for summary in summaries]
        mean = statistics.fmean(values)
        std = statistics.pstdev(values) if len(values) > 1 else 0.0
        print(f"{field:22} {mean:10.3f} {std:10.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
