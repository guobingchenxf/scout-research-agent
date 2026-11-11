"""FastAPI surface for Scout.

Synchronous runs keep the original CLI/test contract. `async_mode=true` creates
a run and returns immediately; clients follow `/events/stream` (SSE) or poll
`/v1/runs/{id}`.
"""

from __future__ import annotations

import hmac
import json
import threading
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .acquisition.router import AcquisitionRouter
from .agent.loop import AgentLoop
from .agent.planner import LLMPlanner, MockPlanner, Planner
from .agent.reflector import Reflector
from .agent.synthesis import Synthesizer
from .agent.tools import AutoHuman, ToolContext, ToolRegistry
from .audit import AuditLogger
from .config import ScoutConfig
from .hitl import ApprovalGate
from .llm import LLMClient
from .models import Run, RunStatus
from .policy.allowlist import AllowlistPolicy
from .policy.capability import PolicyEngine
from .policy.injection import InjectionDetector
from .policy.types import Capability
from .retrieval import build_index_from_store
from .sandbox.python_sandbox import make_sandbox
from .storage import SQLiteStore
from .viewer import render_trace_html


class RunRequest(BaseModel):
    question: str = Field(min_length=2)
    constraints: dict[str, Any] = Field(default_factory=dict)
    planner: Literal["mock", "deepseek"] = "mock"
    async_mode: bool = False


class ApprovalDecision(BaseModel):
    decision: str
    note: str = ""
    decided_by: str = "ui"


def create_app(config: ScoutConfig | None = None) -> FastAPI:
    config = config or ScoutConfig.from_env()
    store = SQLiteStore(config.db_path)
    index = build_index_from_store(
        store,
        embedding_provider=config.embedding_provider,
        embedding_model=config.embedding_model,
        embedding_dim=config.embedding_dim,
    )
    router = AcquisitionRouter(config)
    reflector = Reflector(store)
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
    policy = PolicyEngine(capabilities, allowlist=allowlist)
    injection = InjectionDetector()
    python_runner = make_sandbox(
        config.sandbox_backend,
        image=config.sandbox_image,
        timeout=config.sandbox_timeout_seconds,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            router.close()
            store.close()

    app = FastAPI(title="Scout", version="0.1.0", lifespan=lifespan)
    app.state.config = config
    app.state.store = store
    app.state.index = index
    app.state.router = router
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _auth(request: Request, call_next: Any) -> Any:
        if config.require_auth and request.url.path.startswith("/v1/"):
            supplied = request.headers.get("X-API-Key", "")
            if not config.api_key or not hmac.compare_digest(supplied, config.api_key):
                return JSONResponse(
                    status_code=401,
                    content={"error": "unauthorized", "detail": "invalid API key"},
                )
        return await call_next(request)

    def _make_loop(
        planner_name: str,
    ) -> tuple[AgentLoop, LLMClient | None]:
        if planner_name == "deepseek" and not config.deepseek_api_key:
            raise HTTPException(status_code=400, detail="DEEPSEEK_API_KEY is not configured")
        if planner_name == "deepseek" and not config.model_allowed(config.model_planner):
            raise HTTPException(
                status_code=400,
                detail=f"model is not allowed: {config.model_planner}",
            )
        llm: LLMClient | None = None
        planner: Planner
        if planner_name == "deepseek":
            llm = LLMClient(
                config.deepseek_base_url,
                config.deepseek_api_key,
                timeout=config.llm_timeout_seconds,
                max_retries=config.llm_max_retries,
                backoff=config.llm_backoff_seconds,
            )
            planner = LLMPlanner(llm, config.model_planner)
        else:
            planner = MockPlanner()

        tools = ToolRegistry(
            ToolContext(
                store=store,
                index=index,
                router=router,
                human=human,
                python_runner=python_runner,
                policy=policy,
                audit=AuditLogger(store),
                injection=injection,
                hitl=ApprovalGate(store, human),
                max_read_chars=6000,
            )
        )
        loop = AgentLoop(
            config,
            store,
            planner,
            tools,
            reflector,
            synthesizer=Synthesizer(llm, config.model_planner) if llm is not None else None,
            trace_directory=str(config.db_path.parent / "traces"),
        )
        return loop, llm

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "documents": store.count_documents(),
            "chunks": store.count_chunks(),
            "llm_mode": config.llm_mode,
            "sandbox_backend": config.sandbox_backend,
        }

    @app.post("/v1/runs")
    def create_run(payload: RunRequest) -> dict[str, Any]:
        loop, llm = _make_loop(payload.planner)
        try:
            if not payload.async_mode:
                result = loop.run(payload.question, constraints=payload.constraints)
                return result.model_dump(mode="json")

            run_id = uuid.uuid4().hex
            store.create_run(
                Run(
                    id=run_id,
                    question=payload.question,
                    constraints=payload.constraints,
                    status=RunStatus.RUNNING,
                )
            )

            def worker() -> None:
                try:
                    loop.run(
                        payload.question,
                        constraints=payload.constraints,
                        run_id=run_id,
                        create_run=False,
                    )
                finally:
                    if llm is not None:
                        llm.close()

            threading.Thread(target=worker, daemon=True).start()
            return {"run_id": run_id, "status": "running"}
        except Exception:
            if llm is not None:
                llm.close()
            raise

    @app.get("/v1/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return run.model_dump(mode="json")

    @app.get("/v1/runs/{run_id}/events")
    def get_events(run_id: str) -> list[dict[str, Any]]:
        return [event.model_dump(mode="json") for event in store.list_events(run_id)]

    @app.get("/v1/runs/{run_id}/trace/view", response_class=HTMLResponse)
    def trace_view(run_id: str) -> HTMLResponse:
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return HTMLResponse(render_trace_html(store.list_events(run_id), run))

    @app.get("/v1/runs/{run_id}/events/stream")
    def stream_events(run_id: str) -> StreamingResponse:
        if store.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")

        def generator():
            last_seq = 0
            while True:
                for event in store.list_events(run_id):
                    if event.seq <= last_seq:
                        continue
                    last_seq = event.seq
                    payload = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
                    yield f"event: {event.type}\ndata: {payload}\n\n"
                run = store.get_run(run_id)
                if run is not None and run.status.value not in {"created", "running"}:
                    break
                time.sleep(0.5)

        return StreamingResponse(generator(), media_type="text/event-stream")

    @app.get("/v1/runs/{run_id}/approvals")
    def get_approvals(run_id: str) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in store.list_approvals(run_id)]

    @app.post("/v1/runs/{run_id}/approvals/{approval_id}")
    def decide_approval(
        run_id: str,
        approval_id: str,
        payload: ApprovalDecision,
    ) -> dict[str, Any]:
        if store.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        updated = store.decide_approval(
            approval_id,
            payload.decision,
            payload.decided_by,
            payload.note,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="approval not found or already decided")
        return {"ok": True, "approval_id": approval_id, "decision": payload.decision}

    @app.get("/v1/eval/summaries")
    def eval_summaries() -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for path in sorted(config.reports_dir.glob("eval_*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            payload["file"] = path.name
            results.append(payload)
        return results

    @app.get("/v1/sources")
    def sources() -> dict[str, Any]:
        return {
            "allowlist": list(config.source_allowlist),
            "api_sources": [source.name for source in router.api_sources],
            "sandbox_backend": config.sandbox_backend,
            "verify_dns": config.verify_dns,
        }

    @app.get("/v1/policies")
    def policies() -> dict[str, Any]:
        return {
            "config": config.public_dict(),
            "capabilities": sorted(item.value for item in policy.capabilities),
        }

    if config.static_dir.exists():
        app.mount("/", StaticFiles(directory=str(config.static_dir), html=True), name="ui")

    return app


def get_app() -> FastAPI:
    return create_app(ScoutConfig.from_env())
