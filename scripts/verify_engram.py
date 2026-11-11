#!/usr/bin/env python
"""Live check for the Engram memory adapter.

Requires a running Engram API, e.g.:

    cd D:\\engram
    uvicorn --factory engram.api:get_app --host 127.0.0.1 --port 8001

This script writes one user preference memory and one Scout episodic run
memory, then reads both back through `scout.memory.EngramMemory`.
"""

from __future__ import annotations

import argparse
import sys

import httpx
from scout.memory.engram import EngramMemory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    parser.add_argument("--user-id", default="scout")
    args = parser.parse_args()

    base = args.url.rstrip("/")
    try:
        health = httpx.get(f"{base}/health", timeout=5.0)
        health.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - a clear message beats a traceback
        print(f"Engram is not reachable at {base}: {exc}", file=sys.stderr)
        return 1

    seed = (
        "For vLLM vs SGLang KV cache comparisons, prefer official docs "
        "(docs.vllm.ai, docs.sglang.ai) and read at least two distinct sources."
    )
    written = httpx.post(
        f"{base}/v1/memories",
        json={
            "user_id": args.user_id,
            "content": seed,
            "type": "semantic",
            "source_type": "user",
            "importance": 0.9,
            "metadata": {"kind": "preference", "demo": True},
        },
        timeout=10.0,
    )
    written.raise_for_status()
    print(f"seed memory: {written.json().get('id')}")

    memory = EngramMemory(base, user_id=args.user_id, top_k=5, token_budget=600)
    context = memory.search_context("vLLM 和 SGLang 在 KV cache 管理上的核心差异")
    print(f"search context: {len(context)} chars")
    print(context[:400])

    run_id = "engram-demo-run"
    memory_id = memory.write_run(
        question="vLLM 和 SGLang 在 KV cache 管理上的核心差异是什么？",
        answer="vLLM uses PagedAttention; SGLang uses RadixAttention.",
        run_id=run_id,
        sources=["arxiv:2309.06180", "docs:github:vllm-project/vllm"],
    )
    print(f"run memory: {memory_id}")
    after = memory.search_context(run_id)
    print(f"after-write context: {len(after)} chars")

    ok = (
        seed.split(",")[0] in context
        and bool(memory_id)
        and "Research run" in after
    )
    print("result:", "ok" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
