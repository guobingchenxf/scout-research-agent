#!/usr/bin/env python
"""Exercise the opt-in acquisition paths against real services.

Runs three read-only checks and prints a markdown table:

- MCP: a real stdio MCP server (`uvx mcp-server-fetch`) fetching a docs page;
- RPA: the fixed GitHub README workflow;
- GUI: the read-only Playwright fallback against an allowlisted docs page.

Requirements: `uvx` on PATH, Playwright installed (`pip install -e '.[gui]'`),
and a browser. On Windows, `--gui-channel msedge` uses the installed Edge.

This script performs network requests. It does not write to the corpus or DB.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from scout.acquisition.gui.reader import GuiError, PlaywrightGuiReader
from scout.acquisition.mcp_client import StdioMcpClient
from scout.acquisition.router import AcquisitionRouter
from scout.acquisition.rpa.workflows import RpaRunner
from scout.config import ScoutConfig
from scout.policy.allowlist import AllowlistPolicy
from scout.sandbox.gui_sandbox import GuiSandbox


def _describe(result: Any, elapsed_ms: float) -> dict[str, Any]:
    document = result.documents[0] if result.documents else None
    return {
        "method": result.method.value if result.method else None,
        "ok": document is not None,
        "error": result.error,
        "docs": len(result.documents),
        "doc_id": document.id if document else None,
        "doc_ids": [item.id for item in result.documents],
        "titles": [item.title for item in result.documents],
        "title": document.title if document else None,
        "chars": len(document.text) if document else 0,
        "preview": (document.text[:180].replace("\n", " ") if document else ""),
        "elapsed_ms": round(elapsed_ms, 1),
    }


def check_mcp(config: ScoutConfig, url: str, timeout: float) -> dict[str, Any]:
    client = StdioMcpClient("uvx", ["mcp-server-fetch"], timeout=timeout).start()
    router = AcquisitionRouter(config, api_sources=[], mcp_client=client)
    started = time.perf_counter()
    try:
        result = router.read(url)
        return {**_describe(result, (time.perf_counter() - started) * 1000), "path": "mcp"}
    finally:
        router.close()


def check_mcp_search(
    config: ScoutConfig, query: str, k: int, timeout: float
) -> dict[str, Any]:
    client = StdioMcpClient("uvx", ["arxiv-mcp-server"], timeout=timeout).start()
    router = AcquisitionRouter(config, api_sources=[], mcp_client=client)
    started = time.perf_counter()
    try:
        result = router.search(query, k=k)
        return {
            **_describe(result, (time.perf_counter() - started) * 1000),
            "path": "mcp-search",
        }
    finally:
        router.close()


def check_rpa(config: ScoutConfig, url: str) -> dict[str, Any]:
    router = AcquisitionRouter(config, api_sources=[], rpa_runner=RpaRunner())
    started = time.perf_counter()
    try:
        result = router.read(url)
        return {**_describe(result, (time.perf_counter() - started) * 1000), "path": "rpa"}
    finally:
        router.close()


def check_gui(
    config: ScoutConfig, url: str, channel: str | None, timeout_ms: int
) -> dict[str, Any]:
    allowlist = AllowlistPolicy(
        config.source_allowlist,
        verify_dns=config.verify_dns,
        allow_http_local=config.allow_http_local,
    )
    reader = PlaywrightGuiReader(
        timeout_ms=timeout_ms,
        allowed_hosts=set(config.source_allowlist),
        channel=channel,
    )
    gui = GuiSandbox(allowlist, reader)
    router = AcquisitionRouter(config, api_sources=[], gui_reader=gui)
    started = time.perf_counter()
    try:
        result = router.read(url)
        return {**_describe(result, (time.perf_counter() - started) * 1000), "path": "gui"}
    finally:
        router.close()


def check_gui_denied(config: ScoutConfig) -> dict[str, Any]:
    allowlist = AllowlistPolicy(
        config.source_allowlist,
        verify_dns=config.verify_dns,
        allow_http_local=config.allow_http_local,
    )
    gui = GuiSandbox(
        allowlist,
        PlaywrightGuiReader(allowed_hosts={"docs.vllm.ai"}),
    )
    try:
        gui.read("https://example.com/")
    except GuiError as exc:
        return {"path": "gui-deny", "ok": True, "error": str(exc)}
    return {"path": "gui-deny", "ok": False, "error": "non-allowlisted host was accepted"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mcp-url", default="https://docs.vllm.ai/en/latest/")
    parser.add_argument("--mcp-query", default="PagedAttention KV cache")
    parser.add_argument("--rpa-url", default="https://github.com/vllm-project/vllm")
    parser.add_argument("--gui-url", default="https://docs.vllm.ai/en/latest/")
    parser.add_argument("--gui-channel", default="msedge")
    parser.add_argument("--gui-timeout-ms", type=int, default=30_000)
    parser.add_argument("--mcp-timeout", type=float, default=90.0)
    parser.add_argument("--json", default="")
    args = parser.parse_args()

    config = ScoutConfig.from_env()
    results: list[dict[str, Any]] = []

    for name, fn in (
        ("mcp", lambda: check_mcp(config, args.mcp_url, args.mcp_timeout)),
        (
            "mcp-search",
            lambda: check_mcp_search(
                config, args.mcp_query, 3, args.mcp_timeout
            ),
        ),
        ("rpa", lambda: check_rpa(config, args.rpa_url)),
        ("gui", lambda: check_gui(config, args.gui_url, args.gui_channel, args.gui_timeout_ms)),
        ("gui-deny", lambda: check_gui_denied(config)),
    ):
        print(f"[{name}] running...", flush=True)
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001 - report, don't abort the suite
            result = {"path": name, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
        result["check"] = name
        results.append(result)
        status = "ok" if result.get("ok") else "FAIL"
        print(
            f"[{name}] {status} method={result.get('method')} "
            f"chars={result.get('chars', 0)} error={result.get('error') or ''}",
            flush=True,
        )

    print()
    print("| path | ok | method | docs | title | chars | elapsed ms |")
    print("|---|---|---|---:|---|---:|---:|")
    for result in results:
        title = (result.get("title") or "").replace("|", "\\|")[:60]
        print(
            f"| {result['check']} | {result.get('ok')} | {result.get('method') or '-'} "
            f"| {result.get('docs', 0)} | {title or '-'} | {result.get('chars', 0)} "
            f"| {result.get('elapsed_ms', '-')} |"
        )

    if args.json:
        Path(args.json).write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nwrote {args.json}")

    return 0 if all(result.get("ok") for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
