"""Standalone HTML trace viewer for a single run."""

from __future__ import annotations

import html
import json

from .models import Event, Run


def _payload(event: Event) -> str:
    return html.escape(json.dumps(event.payload, ensure_ascii=False, indent=2))


def render_trace_html(
    events: list[Event],
    run: Run | None = None,
    *,
    title: str = "Scout trace",
) -> str:
    run_id = html.escape(run.id if run else "unknown")
    question = html.escape(run.question if run else "")
    status = html.escape(run.status.value if run else "unknown")
    rows: list[str] = []
    for event in events:
        extra = ""
        payload = event.payload
        if event.type == "plan":
            tokens = payload.get("tokens")
            cost = payload.get("cost_usd")
            if tokens is not None:
                extra = f'<span class="pill">tokens {html.escape(str(tokens))}</span>'
            if cost:
                extra += f'<span class="pill">${float(cost):.5f}</span>'
        rows.append(
            f"""
            <article class="event event-{html.escape(event.type)}">
              <header>
                <span class="seq">#{event.seq}</span>
                <strong>{html.escape(event.type)}</strong>
                <span class="time">{html.escape(event.ts[11:19])}</span>
                {extra}
              </header>
              <pre>{_payload(event)}</pre>
            </article>
            """
        )
    body = "\n".join(rows) or "<p class='muted'>No events recorded.</p>"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html.escape(title)}</title>
<style>
  :root {{ color-scheme: light; --bg:#f7f8fb; --ink:#0b0f19; --muted:#667085; --line:#e2e8f0; --blue:#2f6bff; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink); font-family:"Segoe UI","PingFang SC",system-ui,sans-serif; }}
  main {{ width:min(1080px, calc(100% - 32px)); margin:0 auto; padding:36px 0 70px; }}
  a {{ color:var(--blue); text-decoration:none; }}
  h1 {{ font-size:30px; letter-spacing:-.03em; margin:8px 0; }}
  .muted {{ color:var(--muted); }}
  .meta {{ display:flex; flex-wrap:wrap; gap:8px; margin:16px 0 24px; }}
  .pill {{ padding:4px 9px; border-radius:999px; background:#eef4ff; color:var(--blue); font-size:11px; }}
  .event {{ background:#fff; border:1px solid var(--line); border-radius:16px; padding:14px; margin:10px 0; box-shadow:0 10px 30px rgba(15,23,42,.04); }}
  .event header {{ display:flex; align-items:center; gap:8px; font-size:12px; }}
  .seq {{ color:var(--muted); font-family:ui-monospace,monospace; }}
  .time {{ margin-left:auto; color:var(--muted); font-family:ui-monospace,monospace; font-size:11px; }}
  pre {{ margin:10px 0 0; padding:12px; overflow:auto; border-radius:10px; background:#f6f8fb; color:#334155; font-size:12px; line-height:1.55; }}
  .event-plan {{ border-left:3px solid var(--blue); }}
  .event-tool_result {{ border-left:3px solid #0f9d6e; }}
  .event-reflect {{ border-left:3px solid #b26b00; }}
  .event-run_finished {{ border-left:3px solid #0f9d6e; }}
  .event-run_failed {{ border-left:3px solid #d92d20; }}
</style>
</head>
<body>
<main>
  <p class="muted"><a href="/">← Scout</a></p>
  <p class="muted">run {run_id}</p>
  <h1>{question or title}</h1>
  <div class="meta">
    <span class="pill">status {status}</span>
    <span class="pill">{len(events)} events</span>
  </div>
  {body}
</main>
</body>
</html>"""
