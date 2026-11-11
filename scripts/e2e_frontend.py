#!/usr/bin/env python
"""End-to-end smoke test for the Scout UI.

Starts from the task page, runs a mock job, then opens every deep link the
router exposes. Requires a running API/UI at --base-url and Playwright.

    python scripts/e2e_frontend.py --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import re
import sys

QUESTION = "vLLM 和 SGLang 在 KV cache 管理上的核心差异是什么？"


def _check(
    page, base_url: str, path: str, heading: str, checks: list[str]
) -> None:
    page.goto(f"{base_url}{path}", wait_until="networkidle")
    page.get_by_role("heading", name=heading, level=1, exact=True).wait_for(
        timeout=15_000
    )
    checks.append(f"{path} -> {heading}")
    print(f"ok {path} -> {heading}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--channel", default="msedge")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed", file=sys.stderr)
        return 1

    checks: list[str] = []
    console_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True, channel=args.channel or None
        )
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        try:
            page.goto(f"{args.base_url}/task", wait_until="networkidle")
            page.get_by_role("heading", name="把一个技术问题交给 Scout").wait_for(
                timeout=15_000
            )
            checks.append("/task -> 任务页")
            print("ok /task -> 任务页", flush=True)

            page.locator("textarea").fill(QUESTION)
            page.locator("select").select_option("mock")
            page.get_by_role("button", name="开始调研").click()
            page.wait_for_url(re.compile(r"/runs/[0-9a-f]+$"), timeout=20_000)
            run_id = page.url.rstrip("/").rsplit("/", 1)[-1]
            page.wait_for_selector(".status-finished", timeout=120_000)
            checks.append(f"/runs/{run_id[:8]} -> finished")
            print(f"ok /runs/{run_id[:8]} -> finished", flush=True)

            _check(page, args.base_url, f"/runs/{run_id}/evidence", "证据板", checks)
            _check(page, args.base_url, f"/runs/{run_id}/report", "报告", checks)
            _check(
                page, args.base_url, f"/runs/{run_id}/approvals", "审批与风险", checks
            )
            _check(page, args.base_url, "/eval", "评测面板", checks)
            _check(page, args.base_url, "/sources", "来源与策略", checks)
            _check(page, args.base_url, "/does-not-exist", "页面不存在", checks)

            page.goto(f"{args.base_url}/runs/{run_id}", wait_until="networkidle")
            page.go_back()
            page.wait_for_timeout(300)
            checks.append("history back")
            print("ok history back", flush=True)
        finally:
            browser.close()

    if console_errors:
        print("\nconsole errors:", file=sys.stderr)
        for item in console_errors[:10]:
            print(f"- {item}", file=sys.stderr)
        return 1

    print(f"\n{len(checks)} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
