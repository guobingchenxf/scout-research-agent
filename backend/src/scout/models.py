"""Pydantic models shared by the agent, storage, API and evaluation harness."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SourceType(str, Enum):
    PAPER = "paper"
    OFFICIAL_DOC = "official_doc"
    CODE_REPO = "code_repo"
    MODEL_CARD = "model_card"
    BENCHMARK = "benchmark"
    BLOG = "blog"
    WEB = "web"


class TrustLevel(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    UNTRUSTED = "untrusted"


class RetrievalMethod(str, Enum):
    API = "api"
    MCP = "mcp"
    RPA = "rpa"
    GUI = "gui"
    LOCAL = "local"


class RunStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    WAITING_HUMAN = "waiting_human"
    FINISHED = "finished"
    FAILED = "failed"
    ESCALATED = "escalated"


class SupportType(str, Enum):
    DIRECT = "direct"
    INDIRECT = "indirect"
    CONFLICTING = "conflicting"


class EvalCategory(str, Enum):
    FACT = "fact"
    MULTI_HOP = "multi_hop"
    COMPARISON = "comparison"
    PROCEDURE = "procedure"
    CONFLICT = "conflict"
    ABSTENTION = "abstention"


class SourceDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    url: str
    source_type: SourceType
    trust: TrustLevel = TrustLevel.SECONDARY
    retrieval_method: RetrievalMethod = RetrievalMethod.LOCAL
    license: str | None = None
    published_at: str | None = None
    fetched_at: str = Field(default_factory=utc_now)
    content_hash: str = ""
    text: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class Chunk(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    doc_id: str
    ordinal: int
    text: str
    token_count: int = 0


class SearchHit(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_id: str
    chunk_id: str
    score: float
    snippet: str
    title: str = ""
    url: str = ""
    trust: TrustLevel = TrustLevel.SECONDARY
    retrieval_method: RetrievalMethod = RetrievalMethod.LOCAL


class AcquisitionResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    documents: list[SourceDocument] = Field(default_factory=list)
    hits: list[SearchHit] = Field(default_factory=list)
    method: RetrievalMethod = RetrievalMethod.LOCAL
    policy_verdict: str = "allowed"
    error: str | None = None


class Evidence(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    claim: str
    doc_id: str
    span: str
    quote: str
    trust: TrustLevel = TrustLevel.SECONDARY
    support: SupportType = SupportType.DIRECT
    retrieval_method: RetrievalMethod = RetrievalMethod.LOCAL
    content_hash: str = ""


class Citation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    evidence_id: str = ""
    doc_id: str
    span: str = ""
    quote: str = ""
    url: str = ""


class Claim(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    text: str
    citations: list[Citation] = Field(default_factory=list)
    support: SupportType = SupportType.DIRECT


class SubQuestion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    text: str
    status: str = "pending"


class Coverage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str = "pending"
    evidence_ids: list[str] = Field(default_factory=list)


class Conflict(BaseModel):
    model_config = ConfigDict(extra="ignore")

    claim_a: str
    claim_b: str
    reason: str = ""


class Gap(BaseModel):
    model_config = ConfigDict(extra="ignore")

    subquestion_id: str
    reason: str = ""
    attempts: int = 0


class Reflection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sufficient: bool = False
    coverage_ratio: float = 0.0
    unresolved_gaps: list[Gap] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    force_finish: bool = False


class Budget(BaseModel):
    model_config = ConfigDict(extra="ignore")

    steps: int = 0
    tokens: int = 0
    cost_usd: float = 0.0
    deadline: str | None = None


class ResearchState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question: str
    constraints: dict[str, Any] = Field(default_factory=dict)
    plan: list[SubQuestion] = Field(default_factory=list)
    coverage: dict[str, Coverage] = Field(default_factory=dict)
    evidence_board: list[Evidence] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    budget: Budget = Field(default_factory=Budget)
    history: list[dict[str, Any]] = Field(default_factory=list)
    approvals: list[dict[str, Any]] = Field(default_factory=list)


class ToolName(str, Enum):
    SEARCH = "search"
    READ = "read"
    PYTHON = "python"
    ASK_HUMAN = "ask_human"
    FINISH = "finish"


class PlannerDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tool: ToolName
    arguments: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="ignore")

    call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    call_id: str
    ok: bool
    output: Any = None
    error: str | None = None
    latency_ms: float = 0.0
    tokens: int = 0
    cost_usd: float = 0.0


class Event(BaseModel):
    model_config = ConfigDict(extra="ignore")

    seq: int
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    ts: str = Field(default_factory=utc_now)


class Run(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    question: str
    constraints: dict[str, Any] = Field(default_factory=dict)
    status: RunStatus = RunStatus.CREATED
    created_at: str = Field(default_factory=utc_now)
    ended_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class Approval(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    run_id: str
    question: str
    risk: str = "irreversible_write"
    options: list[str] = Field(default_factory=list)
    decision: str | None = None
    decided_by: str | None = None
    note: str = ""
    created_at: str = Field(default_factory=utc_now)
    decided_at: str | None = None


class EvalTask(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    category: EvalCategory
    difficulty: int = 1
    question: str
    constraints: dict[str, Any] = Field(default_factory=dict)
    gold_answer: str
    gold_evidence: list[dict[str, Any]] = Field(default_factory=list)
    required_citations: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    max_steps: int = 20
    max_cost_usd: float = 0.10
    expected_hitl: bool = False
    require_conflict: bool = True


class EvalResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    task_id: str
    passed: bool
    answer: str = ""
    citation_support_rate: float = 0.0
    metrics: dict[str, float] = Field(default_factory=dict)
    failure_category: str | None = None
    cost_usd: float = 0.0
    latency_ms: float = 0.0


class Report(BaseModel):
    model_config = ConfigDict(extra="ignore")

    answer: str
    claims: list[Claim] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    confidence: float = 0.0
    markdown: str = ""


class BaselineResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    hits: list[SearchHit] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)
    cost_usd: float = 0.0
    mode: str = "extractive"


class RunResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_id: str
    status: RunStatus
    report: Report
    state: ResearchState
    steps: int = 0
    tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None
