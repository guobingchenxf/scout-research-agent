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
    args = parser.parse_args()

    path = Path(args.csv)
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    pairs: list[tuple[bool, bool]] = []
    skipped = 0
    for row in rows:
        rule = _label(row.get("rule_pass", ""))
        human = _label(row.get("human_pass", ""))
        if rule is None or human is None:
            skipped += 1
            continue
        pairs.append((rule, human))

    if not pairs:
        print(f"no labeled rows in {path}; fill human_pass with pass/fail")
        return 1

    agreement = sum(1 for rule, human in pairs if rule == human) / len(pairs)
    print(f"rows: {len(pairs)} (skipped {skipped})")
    print(f"agreement: {agreement:.3f}")
    print(f"cohen_kappa: {cohen_kappa(pairs):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
