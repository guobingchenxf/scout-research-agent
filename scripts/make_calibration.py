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
import html
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


def _write_html(records: list[dict], out: Path) -> None:
    escape = html.escape
    cards = []
    order = []
    for index, record in enumerate(records, start=1):
        task = record["task"]
        task_id = record["task_id"]
        order.append(task_id)
        citations = task.get("required_citations") or []
        citation_html = "".join(
            f'<span class="chip">{escape(str(item))}</span>' for item in citations
        )
        evidence = task.get("gold_evidence") or []
        evidence_html = ""
        if evidence:
            items = []
            for item in evidence:
                quote = (item.get("quote") or "")[:240].replace("\n", " ")
                items.append(
                    '<li><code>{}</code> <span class="muted">({})</span>'
                    "<br>{}</li>".format(
                        escape(str(item.get("doc_id", ""))),
                        escape(str(item.get("span", ""))),
                        escape(quote),
                    )
                )
            evidence_html = (
                f'<details class="evidence"><summary>Gold evidence '
                f'({len(evidence)})</summary><ul>{"".join(items)}</ul></details>'
            )
        cards.append(
            f"""
<section class="card" data-task="{escape(task_id)}">
  <div class="card-head">
    <span class="idx">{index:02d}</span>
    <code class="tid">{escape(task_id)}</code>
    <span class="tag">{escape(str(task.get("category", "")))} · difficulty {escape(str(task.get("difficulty", "?")))}</span>
  </div>
  <h2>{escape(str(task.get("question", "")))}</h2>
  <div class="block gold">
    <h3>Gold answer</h3>
    <p>{escape(str(task.get("gold_answer", "")))}</p>
  </div>
  <div class="chips">{citation_html}</div>
  {evidence_html}
  <div class="block model">
    <h3>Model answer</h3>
    <pre>{escape(record["answer"])}</pre>
  </div>
  <div class="verdict">
    <button type="button" class="pass" data-v="pass" aria-pressed="false">✓ 通过 Pass</button>
    <button type="button" class="fail" data-v="fail" aria-pressed="false">✕ 不通过 Fail</button>
    <input type="text" class="notes" placeholder="备注（可选，例如漏了哪条引用）" />
  </div>
</section>"""
        )

    template = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Scout 人工校准 · 盲标</title>
<style>
  :root { --ink:#1f2328; --muted:#667085; --line:#e4e7ec; --bg:#f6f7f9;
          --green:#067647; --green-bg:#ecfdf3; --red:#b42318; --red-bg:#fef3f2;
          --blue:#175cd3; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:16px/1.7 "PingFang SC","Microsoft YaHei","Noto Sans CJK SC",
         -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
  header { position:sticky; top:0; z-index:10; background:rgba(255,255,255,.94);
           backdrop-filter:blur(8px); border-bottom:1px solid var(--line); }
  .top { max-width:900px; margin:0 auto; padding:16px 24px;
         display:flex; gap:24px; align-items:center; justify-content:space-between; }
  h1 { font-size:19px; margin:0 0 2px; letter-spacing:-.01em; }
  .sub { margin:0; color:var(--muted); font-size:13px; }
  .progress-wrap { min-width:190px; text-align:right; }
  #progress { font-size:14px; font-weight:600; color:var(--blue); }
  .bar { height:6px; background:#e9edf5; border-radius:99px; margin-top:6px; overflow:hidden; }
  .bar i { display:block; height:100%; width:0; background:var(--blue);
           border-radius:99px; transition:width .2s ease; }
  main { max-width:900px; margin:0 auto; padding:24px 24px 120px; }
  .criteria { background:#fff; border:1px solid var(--line); border-radius:14px;
              padding:18px 22px; margin-bottom:22px; }
  .criteria h2 { font-size:15px; margin:0 0 8px; }
  .criteria ol { margin:0; padding-left:22px; color:#344054; font-size:14px; }
  .criteria li { margin:2px 0; }
  .criteria .note { margin:10px 0 0; color:var(--muted); font-size:13px; }
  .card { background:#fff; border:1px solid var(--line); border-radius:16px;
          padding:22px 24px; margin-bottom:18px; box-shadow:0 1px 2px rgba(16,24,40,.04); }
  .card-head { display:flex; align-items:center; gap:10px; flex-wrap:wrap;
               color:var(--muted); font-size:13px; }
  .idx { font-variant-numeric:tabular-nums; font-weight:700; color:#98a2b3; }
  .tid { background:#f2f4f7; border-radius:6px; padding:2px 7px; font-size:12px; }
  .tag { margin-left:auto; background:#eff4ff; color:var(--blue);
         border-radius:99px; padding:2px 10px; font-size:12px; }
  h2 { font-size:20px; line-height:1.45; margin:12px 0 16px; letter-spacing:-.01em; }
  .block { border-radius:12px; padding:14px 16px; margin:12px 0; }
  .block h3 { margin:0 0 6px; font-size:12px; letter-spacing:.08em;
              text-transform:uppercase; color:var(--muted); font-weight:600; }
  .block p { margin:0; white-space:pre-wrap; }
  .gold { background:var(--green-bg); border:1px solid #abefc6; }
  .gold p { color:#05603a; }
  .model { background:#fbfcfd; border:1px solid var(--line); }
  pre { margin:0; white-space:pre-wrap; word-break:break-word;
        font:inherit; font-size:15px; line-height:1.65; }
  .chips { display:flex; gap:6px; flex-wrap:wrap; margin:8px 0; }
  .chip { background:#f2f4f7; border:1px solid var(--line); border-radius:99px;
          padding:1px 9px; font-size:12px; color:#475467; }
  .evidence { margin:8px 0; font-size:13px; color:#475467; }
  .evidence summary { cursor:pointer; color:var(--blue); }
  .evidence ul { margin:8px 0 0; padding-left:20px; }
  .evidence li { margin:4px 0; }
  .muted { color:#98a2b3; }
  .verdict { display:flex; gap:8px; align-items:center; flex-wrap:wrap;
             margin-top:16px; padding-top:14px; border-top:1px dashed var(--line); }
  .verdict button { font:inherit; font-size:14px; font-weight:600; cursor:pointer;
                    border-radius:9px; padding:8px 16px; border:1px solid var(--line);
                    background:#fff; color:#475467; transition:all .12s ease; }
  .verdict button:hover { border-color:#98a2b3; }
  .verdict button.pass.active { background:var(--green-bg); border-color:#12b76a;
                                color:var(--green); }
  .verdict button.fail.active { background:var(--red-bg); border-color:#f97066;
                                color:var(--red); }
  .notes { flex:1; min-width:220px; font:inherit; font-size:14px; padding:8px 12px;
           border:1px solid var(--line); border-radius:9px; background:#fff; }
  .notes:focus { outline:2px solid #b2ccff; border-color:#84adff; }
  footer { position:fixed; bottom:0; left:0; right:0; background:rgba(255,255,255,.96);
           backdrop-filter:blur(8px); border-top:1px solid var(--line);
           padding:12px 24px; display:flex; gap:12px; align-items:center;
           justify-content:center; flex-wrap:wrap; z-index:10; }
  footer button { font:inherit; font-size:14px; font-weight:600; cursor:pointer;
                  border-radius:9px; padding:9px 18px; border:1px solid var(--blue);
                  background:var(--blue); color:#fff; }
  footer button.ghost { background:#fff; color:#475467; border-color:var(--line); }
  footer .hint { color:var(--muted); font-size:13px; }
  @media (max-width:640px) {
    .top { flex-direction:column; align-items:flex-start; gap:10px; }
    .progress-wrap { width:100%; text-align:left; }
    .card { padding:18px; }
    .tag { margin-left:0; }
  }
  @media print { header, footer, .verdict { display:none; } body { background:#fff; } }
</style>
</head>
<body>
<header>
  <div class="top">
    <div>
      <h1>Scout 人工校准 · 盲标</h1>
      <p class="sub">只判断 Model answer；本页不含 rule / judge 的判定结果。</p>
    </div>
    <div class="progress-wrap">
      <span id="progress">0 / __N__</span>
      <div class="bar"><i id="bar"></i></div>
    </div>
  </div>
</header>
<main>
  <section class="criteria">
    <h2>判定标准（全部满足才是 Pass）</h2>
    <ol>
      <li>覆盖 gold answer 的关键事实（语义一致即可，不要求措辞相同）。</li>
      <li>required citations 都在，且引用内容能支撑对应 claim。</li>
      <li>没有与 gold answer 冲突或 forbidden claims 中的断言。</li>
      <li>abstention 题明确说明“语料中没有足够证据”，且没有编造引用。</li>
      <li>conflict 题明确暴露来源分歧，而不是静默取一方或平均。</li>
    </ol>
    <p class="note">只判断答案，不判断 UI、延迟或成本。选完后点底部按钮下载 labels.csv，
    再替换 <code>D:\\scout\\eval\\calibration_labels.csv</code>。</p>
  </section>
__CARDS__
</main>
<footer>
  <button type="button" id="download">下载 calibration_labels.csv</button>
  <button type="button" id="reset" class="ghost">清空重来</button>
  <span class="hint">选择会自动保存在本机浏览器；刷新不会丢。</span>
</footer>
<script>
const tasks = __ORDER__;
const KEY = 'scout_calibration_labels_v1';
let state = {};
try { state = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { state = {}; }

function save() { localStorage.setItem(KEY, JSON.stringify(state)); }

function refresh() {
  let done = 0;
  for (const id of tasks) {
    const card = document.querySelector('[data-task="' + id + '"]');
    if (!card) continue;
    const entry = state[id] || {};
    if (entry.v) done++;
    card.querySelectorAll('.verdict button').forEach(function (btn) {
      const on = btn.dataset.v === entry.v;
      btn.classList.toggle('active', on);
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    const note = card.querySelector('.notes');
    if (document.activeElement !== note && note.value !== (entry.notes || '')) {
      note.value = entry.notes || '';
    }
  }
  document.getElementById('progress').textContent = done + ' / ' + tasks.length;
  document.getElementById('bar').style.width = (tasks.length ? 100 * done / tasks.length : 0) + '%';
}

document.querySelectorAll('.verdict button').forEach(function (btn) {
  btn.addEventListener('click', function () {
    const id = btn.closest('.card').dataset.task;
    state[id] = state[id] || {};
    state[id].v = btn.dataset.v;
    save();
    refresh();
  });
});

document.querySelectorAll('.notes').forEach(function (input) {
  input.addEventListener('input', function () {
    const id = input.closest('.card').dataset.task;
    state[id] = state[id] || {};
    state[id].notes = input.value;
    save();
  });
});

document.getElementById('download').addEventListener('click', function () {
  const missing = tasks.filter(function (id) { return !(state[id] || {}).v; });
  if (missing.length && !confirm('还有 ' + missing.length + ' 题未判定，仍然下载？')) {
    return;
  }
  const rows = ['task_id,human_pass,notes'];
  for (const id of tasks) {
    const entry = state[id] || {};
    const note = String(entry.notes || '').replace(/"/g, '""');
    rows.push(id + ',' + (entry.v || '') + ',"' + note + '"');
  }
  const blob = new Blob(['\\ufeff' + rows.join('\\r\\n') + '\\r\\n'],
                        { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'calibration_labels.csv';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(a.href);
});

document.getElementById('reset').addEventListener('click', function () {
  if (!confirm('清空所有判定？')) return;
  localStorage.removeItem(KEY);
  location.reload();
});

refresh();
</script>
</body>
</html>
"""
    content = template.replace("__CARDS__", "\n".join(cards)).replace(
        "__N__", str(len(records))
    ).replace("__ORDER__", json.dumps(order, ensure_ascii=False))
    out.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--details", required=True)
    parser.add_argument("--tasks", default="eval/tasks.json")
    parser.add_argument("--out", default="eval/calibration.csv")
    parser.add_argument("--labels", default="eval/calibration_labels.csv")
    parser.add_argument("--review", default="eval/calibration_review.md")
    parser.add_argument("--html", default="eval/calibration_review.html")
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

    review_html = Path(args.html)
    review_html.parent.mkdir(parents=True, exist_ok=True)
    _write_html(records, review_html)

    print(f"wrote {len(rows)} rows to {out}")
    print(f"wrote label sheet to {labels}; fill human_pass with pass/fail")
    print(f"wrote blind review sheet to {review}")
    print(f"wrote clickable review page to {review_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
