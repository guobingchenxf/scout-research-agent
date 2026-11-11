#!/usr/bin/env python
"""Create a human-calibration CSV from an eval details JSON.

The CSV keeps the rule-grader verdict and leaves `human_pass` blank for a human
to fill with pass/fail. Run `scripts/calibrate.py` afterwards to compute
Cohen's kappa between the two.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--details", required=True)
    parser.add_argument("--tasks", default="eval/tasks.json")
    parser.add_argument("--out", default="eval/calibration.csv")
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()

    results = json.loads(Path(args.details).read_text(encoding="utf-8"))
    task_payload = json.loads(Path(args.tasks).read_text(encoding="utf-8"))
    tasks = {task["id"]: task for task in task_payload["tasks"]}

    rows = []
    for result in results[: args.limit]:
        task = tasks.get(result["task_id"], {})
        rows.append(
            {
                "task_id": result["task_id"],
                "split": task.get("split", "dev"),
                "category": task.get("category", ""),
                "question": task.get("question", ""),
                "answer": (result.get("answer") or "")[:2000],
                "rule_pass": "pass" if result.get("passed") else "fail",
                "rule_failure": result.get("failure_category") or "",
                "human_pass": "",
                "notes": "",
            }
        )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {out}; fill human_pass with pass/fail")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
