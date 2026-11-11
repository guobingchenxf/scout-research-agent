#!/usr/bin/env python
"""Create human-calibration artifacts from an eval details JSON.

Writes three files:

- `eval/calibration.csv`: rule verdict + blank `human_pass` (machine-readable);
- `eval/calibration_labels.csv`: only task_id + blank human_pass + notes, easy
  to fill without touching the long CSV;
- `eval/calibration_review.md`: a blind review sheet with question, gold answer
  and model answer, but no rule/judge verdict.

Run `scripts/calibrate.py --labels eval/calibration_labels.csv` afterwards to
compute agreement and Cohen's kappa.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def _quote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def _write_review(records: list[dict], out: Path) -> None:
    lines = [
        "# 人工校准盲标表",
        "",
        "> 判断每条 answer 是否通过。**不要参考 rule grader 结果**；本文件也刻意",
        "> 不含 rule/judge verdict。判定标准见下，完成后把 pass/fail 填到",
        "> `eval/calibration_labels.csv`。",
        "",
        "判定为 pass 需同时满足：",
        "",
        "1. answer 覆盖 gold answer 的关键事实（语义一致即可，不要求措辞相同）；",
        "2. required citations 都存在，且引用内容能支撑对应 claim；",
        "3. 没有与 gold answer 冲突或 forbidden claims 中的断言；",
        "4. abstention 题明确说明“语料中没有足够证据”，且没有编造引用；",
        "5. conflict 题明确暴露来源分歧，而不是静默取一方或平均。",
        "",
        "任意一条不满足即 fail。只判断 answer，不判断 UI、延迟或成本。",
        "",
    ]
    for index, record in enumerate(records, start=1):
        task = record["task"]
        answer = record["answer"]
        lines += [
            (
                f"## {index}. `{record['task_id']}` — {task.get('category', '')}"
                f"（difficulty {task.get('difficulty', '?')}）"
            ),
            "",
            f"**Question:** {task.get('question', '')}",
            "",
            "**Gold answer:**",
            "",
            _quote(task.get("gold_answer", "")),
            "",
        ]
        citations = task.get("required_citations") or []
        if citations:
            lines += [f"**Required citations:** {', '.join(citations)}", ""]
        evidence = task.get("gold_evidence") or []
        if evidence:
            lines += ["**Gold evidence:**", ""]
            for item in evidence:
                quote = (item.get("quote") or "")[:200].replace("\n", " ")
                lines.append(
                    f"- `{item.get('doc_id', '')}` ({item.get('span', '')}): {quote}"
                )
            lines.append("")
        lines += [
            "**Model answer:**",
            "",
            _quote(answer),
            "",
            "**Human verdict:** 填 `pass` 或 `fail` → `eval/calibration_labels.csv`",
            "",
        ]
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--details", required=True)
    parser.add_argument("--tasks", default="eval/tasks.json")
    parser.add_argument("--out", default="eval/calibration.csv")
    parser.add_argument("--labels", default="eval/calibration_labels.csv")
    parser.add_argument("--review", default="eval/calibration_review.md")
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()

    results = json.loads(Path(args.details).read_text(encoding="utf-8"))
    task_payload = json.loads(Path(args.tasks).read_text(encoding="utf-8"))
    tasks = {task["id"]: task for task in task_payload["tasks"]}

    rows = []
    records = []
    for result in results[: args.limit]:
        task = tasks.get(result["task_id"], {})
        answer = result.get("answer") or ""
        rows.append(
            {
                "task_id": result["task_id"],
                "split": task.get("split", "dev"),
                "category": task.get("category", ""),
                "question": task.get("question", ""),
                "answer": answer[:2000],
                "rule_pass": "pass" if result.get("passed") else "fail",
                "rule_failure": result.get("failure_category") or "",
                "human_pass": "",
                "notes": "",
            }
        )
        records.append({"task_id": result["task_id"], "task": task, "answer": answer})

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    labels = Path(args.labels)
    labels.parent.mkdir(parents=True, exist_ok=True)
    with labels.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["task_id", "human_pass", "notes"]
        )
        writer.writeheader()
        for record in records:
            writer.writerow(
                {"task_id": record["task_id"], "human_pass": "", "notes": ""}
            )

    review = Path(args.review)
    review.parent.mkdir(parents=True, exist_ok=True)
    _write_review(records, review)

    print(f"wrote {len(rows)} rows to {out}")
    print(f"wrote label sheet to {labels}; fill human_pass with pass/fail")
    print(f"wrote blind review sheet to {review}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
