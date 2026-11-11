"""Scout command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .acquisition.factory import build_acquisition_router
from .agent.loop import AgentLoop
from .agent.planner import LLMPlanner, MockPlanner, Planner
from .agent.reflector import Reflector
from .agent.synthesis import Synthesizer
from .agent.tools import AutoHuman, ToolContext, ToolRegistry
from .audit import AuditLogger
from .baseline import SingleShotRAG
from .config import ScoutConfig
from .corpus import ingest_corpus, load_manifest
from .hitl import ApprovalGate
from .llm import LLMClient
from .memory import build_memory_client
from .policy.allowlist import AllowlistPolicy
from .policy.capability import PolicyEngine
from .policy.injection import InjectionDetector
from .policy.types import Capability
from .retrieval import build_index_from_store
from .sandbox.python_sandbox import make_sandbox
from .storage import SQLiteStore


def _print(payload: Any) -> None:
    # The Windows console may be GBK; ASCII-escaped JSON always prints.
    print(json.dumps(payload, ensure_ascii=True, indent=2, default=str))


def _store(config: ScoutConfig) -> SQLiteStore:
    return SQLiteStore(config.db_path)


def _index(config: ScoutConfig, store: SQLiteStore):
    return build_index_from_store(
        store,
        embedding_provider=config.embedding_provider,
        embedding_model=config.embedding_model,
        embedding_dim=config.embedding_dim,
    )


def _llm(config: ScoutConfig, live: bool) -> LLMClient | None:
    if not live:
        return None
    if not config.deepseek_api_key:
        raise SystemExit("DEEPSEEK_API_KEY is empty; set it in .env or use --live=false")
    return LLMClient(
        config.deepseek_base_url,
        config.deepseek_api_key,
        timeout=config.llm_timeout_seconds,
        max_retries=config.llm_max_retries,
        backoff=config.llm_backoff_seconds,
    )


def cmd_init(args: argparse.Namespace, config: ScoutConfig) -> int:
    for path in (config.db_path.parent, config.corpus_dir, config.index_dir):
        Path(path).mkdir(parents=True, exist_ok=True)
    store = _store(config)
    try:
        _print(
            {
                "ok": True,
                "db_path": str(config.db_path),
                "documents": store.count_documents(),
                "chunks": store.count_chunks(),
                "config": config.public_dict(),
            }
        )
    finally:
        store.close()
    return 0


def cmd_ingest(args: argparse.Namespace, config: ScoutConfig) -> int:
    store = _store(config)
    try:
        documents, chunks = ingest_corpus(store, config.corpus_dir)
        _print(
            {
                "ok": True,
                "ingested_documents": documents,
                "ingested_chunks": chunks,
                "total_documents": store.count_documents(),
                "total_chunks": store.count_chunks(),
            }
        )
    finally:
        store.close()
    return 0


def cmd_index(args: argparse.Namespace, config: ScoutConfig) -> int:
    store = _store(config)
    try:
        manifest = load_manifest(config.corpus_dir)
        index = _index(config, store)
        _print(
            {
                "ok": True,
                "manifest_documents": len(manifest.documents),
                "documents": len(index.documents),
                "chunks": len(index.chunks),
                "embedding_provider": config.embedding_provider,
                "embedding_dim": int(index.embeddings.shape[1]) if index.embeddings.size else 0,
            }
        )
    finally:
        store.close()
    return 0


def cmd_search(args: argparse.Namespace, config: ScoutConfig) -> int:
    store = _store(config)
    try:
        index = _index(config, store)
        hits = index.search(args.query, k=args.k)
        _print([hit.model_dump(mode="json") for hit in hits])
    finally:
        store.close()
    return 0


def cmd_baseline(args: argparse.Namespace, config: ScoutConfig) -> int:
    store = _store(config)
    try:
        index = _index(config, store)
        llm = _llm(config, args.live)
        baseline = SingleShotRAG(
            index,
            llm,
            model=config.model_planner,
            top_k=args.k,
            language=args.language,
            cost_input_per_1k=config.cost_input_per_1k,
            cost_output_per_1k=config.cost_output_per_1k,
        )
        try:
            result = baseline.run(args.question)
            _print(result.model_dump(mode="json"))
        finally:
            if llm is not None:
                llm.close()
    finally:
        store.close()
    return 0


def cmd_run(args: argparse.Namespace, config: ScoutConfig) -> int:
    store = _store(config)
    router = build_acquisition_router(config)
    memory = build_memory_client(config)
    try:
        index = _index(config, store)
        if not index.chunks:
            raise SystemExit("corpus is empty; run `scout ingest` first")
        planner: Planner
        if args.planner == "deepseek":
            if not config.deepseek_api_key:
                raise SystemExit("DEEPSEEK_API_KEY is empty; use --planner mock")
            if not config.model_allowed(config.model_planner):
                raise SystemExit(
                    f"model is not allowed: {config.model_planner}; "
                    f"allowed={config.allowed_models}"
                )
            llm = LLMClient(
                config.deepseek_base_url,
                config.deepseek_api_key,
                timeout=config.llm_timeout_seconds,
                max_retries=config.llm_max_retries,
                backoff=config.llm_backoff_seconds,
            )
            planner = LLMPlanner(llm, config.model_planner)
        else:
            llm = None
            planner = MockPlanner()
        allowlist = AllowlistPolicy(
            config.source_allowlist,
            verify_dns=config.verify_dns,
            allow_http_local=config.allow_http_local,
        )
        capabilities = {
            Capability.SOURCES_READ,
            Capability.REPORT_EXPORT,
            Capability.MEMORY_READ,
        }
        if config.sandbox_backend != "disabled":
            capabilities.add(Capability.SANDBOX_EXEC)
        human = AutoHuman()
        tools = ToolRegistry(
            ToolContext(
                store=store,
                index=index,
                router=router,
                human=human,
                python_runner=make_sandbox(
                    config.sandbox_backend,
                    image=config.sandbox_image,
                    timeout=config.sandbox_timeout_seconds,
                ),
                policy=PolicyEngine(capabilities, allowlist=allowlist),
                audit=AuditLogger(store),
                injection=InjectionDetector(),
                hitl=ApprovalGate(store, human),
                max_read_chars=args.max_read_chars,
            )
        )
        loop = AgentLoop(
            config,
            store,
            planner,
            tools,
            Reflector(store),
            synthesizer=Synthesizer(llm, config.model_planner) if llm is not None else None,
            trace_directory=str(config.db_path.parent / "traces"),
            memory=memory,
        )
        try:
            result = loop.run(args.question)
            _print(result.model_dump(mode="json"))
        finally:
            if llm is not None:
                llm.close()
    finally:
        router.close()
        if memory is not None:
            memory.close()
        store.close()
    return 0


def cmd_eval(args: argparse.Namespace, config: ScoutConfig) -> int:
    from .eval.report import render_markdown, write_markdown
    from .eval.runner import EvalRunner
    from .eval.tasks import default_tasks_path, load_tasks, validate_task_evidence

    tasks = load_tasks(args.tasks or default_tasks_path())
    store = _store(config)
    try:
        index = _index(config, store)
        if not index.chunks:
            raise SystemExit("corpus is empty; run `scout ingest` first")
        issues = validate_task_evidence(tasks, store)
        if issues and not args.allow_invalid:
            _print({"ok": False, "issues": issues})
            return 1
        runner = EvalRunner(config, store, index, tasks)
        categories = {
            item.strip() for item in (args.category or "").split(",") if item.strip()
        }
        results = runner.run(
            system=args.system,
            planner=args.planner,
            limit=args.limit,
            categories=categories or None,
            split=args.split,
        )
        summary = runner.summary(results)
        report = render_markdown(
            results,
            tasks,
            summary,
            system=args.system,
            planner=args.planner,
        )
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = config.project_root / out_path
        write_markdown(out_path, report)
        summary_path = out_path.with_suffix(".json")
        summary_path.write_text(
            json.dumps(
                {
                    "system": args.system,
                    "planner": args.planner,
                    "split": args.split,
                    "summary": summary,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        details_path = out_path.with_suffix(".details.json")
        details_path.write_text(
            json.dumps(
                [result.model_dump(mode="json") for result in results],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        _print(
            {
                "ok": True,
                "system": args.system,
                "planner": args.planner,
                "split": args.split,
                "summary": summary,
                "report": str(out_path),
                "summary_json": str(summary_path),
                "details_json": str(details_path),
                "issues": issues,
            }
        )
    finally:
        store.close()
    return 0


def cmd_trace(args: argparse.Namespace, config: ScoutConfig) -> int:
    store = _store(config)
    try:
        events = store.list_events(args.run_id)
        _print([event.model_dump(mode="json") for event in events])
    finally:
        store.close()
    return 0


def cmd_stats(args: argparse.Namespace, config: ScoutConfig) -> int:
    store = _store(config)
    try:
        manifest = load_manifest(config.corpus_dir)
        _print(
            {
                "db_path": str(config.db_path),
                "documents": store.count_documents(),
                "chunks": store.count_chunks(),
                "manifest_documents": len(manifest.documents),
                "manifest_path": str(config.corpus_dir / "manifest.json"),
            }
        )
    finally:
        store.close()
    return 0


def cmd_verify_ledger(args: argparse.Namespace, config: ScoutConfig) -> int:
    store = _store(config)
    try:
        ok, broken_id = store.verify_audit()
        _print({"ok": ok, "broken_id": broken_id})
    finally:
        store.close()
    return 0


def cmd_serve(args: argparse.Namespace, config: ScoutConfig) -> int:
    import uvicorn

    uvicorn.run(
        "scout.api:get_app",
        factory=True,
        host=args.host,
        port=args.port,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scout", description="Scout research agent CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create data/corpus directories and the SQLite schema")
    init.set_defaults(func=cmd_init)

    ingest = sub.add_parser("ingest", help="load corpus/manifest.json into SQLite")
    ingest.set_defaults(func=cmd_ingest)

    index = sub.add_parser("index", help="build the hybrid index and print stats")
    index.set_defaults(func=cmd_index)

    search = sub.add_parser("search", help="run a retrieval query")
    search.add_argument("--query", required=True)
    search.add_argument("--k", type=int, default=8)
    search.set_defaults(func=cmd_search)

    baseline = sub.add_parser("baseline", help="run the single-shot RAG baseline")
    baseline.add_argument("--question", required=True)
    baseline.add_argument("--k", type=int, default=6)
    baseline.add_argument("--language", default="zh", choices=["zh", "en"])
    baseline.add_argument(
        "--live",
        action="store_true",
        help="call DeepSeek; without this flag the baseline is extractive and offline",
    )
    baseline.set_defaults(func=cmd_baseline)

    run = sub.add_parser("run", help="run the agent loop")
    run.add_argument("--question", required=True)
    run.add_argument("--planner", default="mock", choices=["mock", "deepseek"])
    run.add_argument("--max-read-chars", type=int, default=6000)
    run.set_defaults(func=cmd_run)

    trace = sub.add_parser("trace", help="print a run's trace events")
    trace.add_argument("--run-id", required=True)
    trace.set_defaults(func=cmd_trace)

    eval_parser = sub.add_parser("eval", help="run the evaluation suite")
    eval_parser.add_argument("--tasks", default=None)
    eval_parser.add_argument(
        "--system",
        default="scout",
        choices=["scout", "single_shot_rag", "react_no_reflect"],
    )
    eval_parser.add_argument("--planner", default="mock", choices=["mock", "deepseek"])
    eval_parser.add_argument("--limit", type=int, default=None)
    eval_parser.add_argument("--category", default="")
    eval_parser.add_argument("--split", default="all", choices=["all", "dev", "heldout"])
    eval_parser.add_argument("--out", default="reports/eval.md")
    eval_parser.add_argument("--allow-invalid", action="store_true")
    eval_parser.set_defaults(func=cmd_eval)

    stats = sub.add_parser("stats", help="print corpus and store counts")
    stats.set_defaults(func=cmd_stats)

    verify = sub.add_parser("verify-ledger", help="verify the audit hash chain")
    verify.set_defaults(func=cmd_verify_ledger)

    serve = sub.add_parser("serve", help="start the FastAPI server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=cmd_serve)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = ScoutConfig.from_env()
    return int(args.func(args, config))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
