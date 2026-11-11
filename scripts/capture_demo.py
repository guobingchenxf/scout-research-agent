#!/usr/bin/env python
"""Capture README screenshots and a short demo video with Playwright.

Prerequisite: the Scout API + UI is running at --base-url.
Uses the locally installed Microsoft Edge via Playwright's `channel="msedge"`,
so no browser download is required.
"""

from __future__ import annotations

import argparse
from pathlib import Path

QUESTION = "vLLM 和 SGLang 在 KV cache 管理上的核心差异是什么？"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--out-dir", default="docs/assets")
    parser.add_argument("--video-dir", default="reports/demo")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("playwright is not installed; pip install playwright")

    out_dir = Path(args.out_dir)
    video_dir = Path(args.video_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    video_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000},
            record_video_dir=str(video_dir),
            record_video_size={"width": 1280, "height": 800},
        )
        page = context.new_page()
        page.goto(args.base_url, wait_until="networkidle")
        page.screenshot(path=str(out_dir / "task.png"), full_page=True)

        page.locator("textarea").fill(QUESTION)
        page.locator("select").select_option("mock")
        page.get_by_role("button", name="开始调研").click()
        page.wait_for_selector(".status-finished", timeout=120_000)
        page.screenshot(path=str(out_dir / "run.png"), full_page=True)

        for name, label in (
            ("evidence", "证据板"),
            ("report", "报告"),
            ("eval", "评测"),
            ("sources", "来源/策略"),
        ):
            page.get_by_role("button", name=label).click()
            page.wait_for_timeout(900)
            page.screenshot(path=str(out_dir / f"{name}.png"), full_page=True)

        context.close()
        browser.close()

    videos = sorted(video_dir.glob("*.webm"))
    if videos:
        target = out_dir / "demo.webm"
        videos[-1].replace(target)
        print(f"video: {target}")
    print(f"screenshots: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
