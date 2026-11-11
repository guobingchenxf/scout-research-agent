#!/usr/bin/env python
"""Compute Cohen's kappa between rule-grader and human pass/fail labels."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def _label(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized in {"pass", "passes", "1", "true", "yes", "y"}:
        return True
    if normalized in {"fail", "fails", "0", "false", "no", "n"}:
        return False
    return None


def cohen_kappa(pairs: list[tuple[bool, bool]]) -> float:
    if not pairs:
        return 0.0
    total = len(pairs)
    observed = sum(1 for rule, human in pairs if rule == human) / total
    rule_true = sum(1 for rule, _ in pairs if rule) / total
    human_true = sum(1 for _, human in pairs if human) / total
    expected = rule_true * human_true + (1 - rule_true) * (1 - human_true)
    if expected >= 1.0:
        return 1.0
    return (observed - expected) / (1.0 - expected)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="eval/calibration.csv")
    parser.add_argument(
        "--labels",
        default="",
        help="optional CSV with task_id,human_pass; overrides the --csv column",
    )
    parser.add_argument(
        "--label-column",
        default="human_pass",
        help="label column to read (e.g. human_pass or assistant_pass)",
    )
    args = parser.parse_args()

    path = Path(args.csv)
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    labels: dict[str, str] = {}
    if args.labels:
        with Path(args.labels).open(encoding="utf-8-sig", newline="") as handle:
            for label_row in csv.DictReader(handle):
                task_id = (label_row.get("task_id") or "").strip()
                if task_id:
                    labels[task_id] = label_row.get(args.label_column) or ""

    pairs: list[tuple[bool, bool]] = []
    skipped = 0
    for row in rows:
        rule = _label(row.get("rule_pass", ""))
        task_id = (row.get("task_id") or "").strip()
        human_value = labels.get(task_id, row.get(args.label_column, ""))
        human = _label(human_value)
        if rule is None or human is None:
            skipped += 1
            continue
        pairs.append((rule, human))

    if not pairs:
        print(f"no labeled rows in {path}; fill human_pass with pass/fail")
        return 1

    agreement = sum(1 for rule, human in pairs if rule == human) / len(pairs)
    print(f"labels: {args.labels or path} [{args.label_column}]")
    print(f"rows: {len(pairs)} (skipped {skipped})")
    print(f"agreement: {agreement:.3f}")
    print(f"cohen_kappa: {cohen_kappa(pairs):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
