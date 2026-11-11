"""Environment-driven configuration for Scout."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, cast

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_ALLOWLIST = (
    "arxiv.org",
    "export.arxiv.org",
    "api.semanticscholar.org",
    "api.crossref.org",
    "api.github.com",
    "github.com",
    "raw.githubusercontent.com",
    "huggingface.co",
    "hf-mirror.com",
    "doi.org",
    "docs.vllm.ai",
    "docs.sglang.ai",
    "nvidia.github.io",
    "langchain-ai.github.io",
    "modelcontextprotocol.io",
)

LLMMode = Literal["mock", "live"]
EmbeddingProviderName = Literal["hash", "fastembed"]
SandboxBackend = Literal["disabled", "subprocess", "docker"]


def _env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_int(name: str, default: int) -> int:
    value = _env_str(name)
    return int(value) if value else default


def _env_float(name: str, default: float) -> float:
    value = _env_str(name)
    return float(value) if value else default


def _env_bool(name: str, default: bool) -> bool:
    value = _env_str(name).lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _resolve_path(value: str, root: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _env_sandbox(name: str, default: str) -> SandboxBackend:
    value = _env_str(name, default).lower()
    if value in {"disabled", "subprocess", "docker"}:
        return cast(SandboxBackend, value)
    return "disabled"


def _split_allowlist(value: str) -> tuple[str, ...]:
    items = tuple(item.strip().lower() for item in value.split(",") if item.strip())
    return items or DEFAULT_ALLOWLIST


def _split_models(value: str) -> tuple[str, ...]:
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    return items or ("deepseek-flash",)


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _env_json_list(name: str) -> tuple[str, ...]:
    raw = _env_str(name)
    if not raw:
        return ()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} must be a JSON array of strings") from exc
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a JSON array of strings")
    return tuple(value)


@dataclass(frozen=True)
class ScoutConfig:
    """Runtime configuration.

    Paths in the environment are resolved against the project root, not the
    current working directory, so `python -m scout.cli` behaves the same from
    `backend/` or the repository root.
    """

    project_root: Path = PROJECT_ROOT
    db_path: Path = PROJECT_ROOT / "data" / "scout.db"
    corpus_dir: Path = PROJECT_ROOT / "corpus"
    index_dir: Path = PROJECT_ROOT / "corpus" / "index"
    static_dir: Path = PROJECT_ROOT / "frontend" / "dist"
    reports_dir: Path = PROJECT_ROOT / "reports"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    model_planner: str = "deepseek-flash"
    model_synthesis: str = "deepseek-flash"
    model_judge: str = "deepseek-flash"
    allowed_models: tuple[str, ...] = ("deepseek-flash",)
    llm_mode: LLMMode = "mock"
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 2
    llm_backoff_seconds: float = 0.5
    enable_synthesis: bool = False
    cost_input_per_1k: float = 0.0
    cost_output_per_1k: float = 0.0

    embedding_provider: EmbeddingProviderName = "hash"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dim: int = 384

    max_steps: int = 25
    token_budget: int = 60_000
    cost_budget_usd: float = 0.50
    request_timeout_seconds: float = 30.0
    max_response_bytes: int = 5_000_000

    verify_dns: bool = True
    allow_http_local: bool = False
    sandbox_backend: SandboxBackend = "disabled"
    sandbox_timeout_seconds: float = 10.0
    sandbox_image: str = "python:3.10-slim"
    max_sandbox_output: int = 10_000

    require_auth: bool = False
    api_key: str = ""
    source_allowlist: tuple[str, ...] = DEFAULT_ALLOWLIST

    # Acquisition paths. All are opt-in: the default service stays offline.
    mcp_command: str = ""
    mcp_args: tuple[str, ...] = ()
    mcp_timeout_seconds: float = 30.0
    rpa_enabled: bool = False
    gui_enabled: bool = False
    gui_allowed_hosts: tuple[str, ...] = ()
    gui_browser_channel: str = ""

    # Optional Engram memory layer. Empty URL keeps memory disabled.
    engram_url: str = ""
    engram_api_key: str = ""
    engram_user_id: str = "scout"
    engram_tenant_id: str = ""
    engram_top_k: int = 5
    engram_token_budget: int = 800
    engram_timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> ScoutConfig:
        load_dotenv(env_file or PROJECT_ROOT / ".env", override=False)
        root = PROJECT_ROOT
        allowlist = _split_allowlist(
            _env_str("SCOUT_SOURCE_ALLOWLIST", ",".join(DEFAULT_ALLOWLIST))
        )
        return cls(
            project_root=root,
            db_path=_resolve_path(_env_str("SCOUT_DB_PATH", "./data/scout.db"), root),
            corpus_dir=_resolve_path(_env_str("SCOUT_CORPUS_DIR", "./corpus"), root),
            index_dir=_resolve_path(_env_str("SCOUT_INDEX_DIR", "./corpus/index"), root),
            static_dir=_resolve_path(
                _env_str("SCOUT_STATIC_DIR", "./frontend/dist"), root
            ),
            reports_dir=_resolve_path(_env_str("SCOUT_REPORTS_DIR", "./reports"), root),
            deepseek_api_key=_env_str("DEEPSEEK_API_KEY"),
            deepseek_base_url=_env_str("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            model_planner=_env_str("DEEPSEEK_MODEL_PLANNER", "deepseek-flash"),
            model_synthesis=_env_str("DEEPSEEK_MODEL_SYNTHESIS", "deepseek-flash"),
            model_judge=_env_str("DEEPSEEK_MODEL_JUDGE", "deepseek-flash"),
            allowed_models=_split_models(
                _env_str("SCOUT_ALLOWED_MODELS", "deepseek-flash")
            ),
            llm_mode=_env_str("SCOUT_LLM_MODE", "mock").lower() == "live" and "live" or "mock",
            llm_timeout_seconds=_env_float("SCOUT_LLM_TIMEOUT_SECONDS", 60.0),
            llm_max_retries=_env_int("SCOUT_LLM_MAX_RETRIES", 2),
            llm_backoff_seconds=_env_float("SCOUT_LLM_BACKOFF_SECONDS", 0.5),
            enable_synthesis=_env_bool("SCOUT_ENABLE_SYNTHESIS", False),
            cost_input_per_1k=_env_float("SCOUT_COST_INPUT_PER_1K", 0.0),
            cost_output_per_1k=_env_float("SCOUT_COST_OUTPUT_PER_1K", 0.0),
            embedding_provider=_env_str("SCOUT_EMBEDDING_PROVIDER", "hash").lower() == "fastembed" and "fastembed" or "hash",
            embedding_model=_env_str("SCOUT_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5"),
            embedding_dim=_env_int("SCOUT_EMBEDDING_DIM", 384),
            max_steps=_env_int("SCOUT_MAX_STEPS", 25),
            token_budget=_env_int("SCOUT_TOKEN_BUDGET", 60_000),
            cost_budget_usd=_env_float("SCOUT_COST_BUDGET_USD", 0.50),
            request_timeout_seconds=_env_float("SCOUT_REQUEST_TIMEOUT_SECONDS", 30.0),
            max_response_bytes=_env_int("SCOUT_MAX_RESPONSE_BYTES", 5_000_000),
            verify_dns=_env_bool("SCOUT_VERIFY_DNS", True),
            allow_http_local=_env_bool("SCOUT_ALLOW_HTTP_LOCAL", False),
            sandbox_backend=_env_sandbox("SCOUT_SANDBOX_BACKEND", "disabled"),
            sandbox_timeout_seconds=_env_float("SCOUT_SANDBOX_TIMEOUT_SECONDS", 10.0),
            sandbox_image=_env_str("SCOUT_SANDBOX_IMAGE", "python:3.10-slim"),
            max_sandbox_output=_env_int("SCOUT_MAX_SANDBOX_OUTPUT", 10_000),
            require_auth=_env_bool("SCOUT_REQUIRE_AUTH", False),
            api_key=_env_str("SCOUT_API_KEY"),
            source_allowlist=allowlist,
            mcp_command=_env_str("SCOUT_MCP_COMMAND"),
            mcp_args=_env_json_list("SCOUT_MCP_ARGS"),
            mcp_timeout_seconds=_env_float("SCOUT_MCP_TIMEOUT_SECONDS", 30.0),
            rpa_enabled=_env_bool("SCOUT_RPA_ENABLED", False),
            gui_enabled=_env_bool("SCOUT_GUI_ENABLED", False),
            gui_allowed_hosts=_split_csv(_env_str("SCOUT_GUI_ALLOWED_HOSTS")),
            gui_browser_channel=_env_str("SCOUT_GUI_BROWSER_CHANNEL"),
            engram_url=_env_str("SCOUT_ENGRAM_URL"),
            engram_api_key=_env_str("SCOUT_ENGRAM_API_KEY"),
            engram_user_id=_env_str("SCOUT_ENGRAM_USER_ID", "scout"),
            engram_tenant_id=_env_str("SCOUT_ENGRAM_TENANT_ID"),
            engram_top_k=_env_int("SCOUT_ENGRAM_TOP_K", 5),
            engram_token_budget=_env_int("SCOUT_ENGRAM_TOKEN_BUDGET", 800),
            engram_timeout_seconds=_env_float("SCOUT_ENGRAM_TIMEOUT_SECONDS", 10.0),
        )

    def with_overrides(self, **kwargs: object) -> ScoutConfig:
        return replace(self, **kwargs)  # type: ignore[arg-type]

    def model_allowed(self, model: str) -> bool:
        return model in self.allowed_models

    def public_dict(self) -> dict[str, object]:
        """A redacted view safe to log or expose."""

        return {
            "project_root": str(self.project_root),
            "db_path": str(self.db_path),
            "corpus_dir": str(self.corpus_dir),
            "index_dir": str(self.index_dir),
            "static_dir": str(self.static_dir),
            "reports_dir": str(self.reports_dir),
            "deepseek_base_url": self.deepseek_base_url,
            "model_planner": self.model_planner,
            "model_synthesis": self.model_synthesis,
            "model_judge": self.model_judge,
            "allowed_models": list(self.allowed_models),
            "enable_synthesis": self.enable_synthesis,
            "llm_mode": self.llm_mode,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "max_steps": self.max_steps,
            "token_budget": self.token_budget,
            "cost_budget_usd": self.cost_budget_usd,
            "verify_dns": self.verify_dns,
            "allow_http_local": self.allow_http_local,
            "sandbox_backend": self.sandbox_backend,
            "source_allowlist": list(self.source_allowlist),
            "mcp_enabled": bool(self.mcp_command),
            "rpa_enabled": self.rpa_enabled,
            "gui_enabled": self.gui_enabled,
            "engram_enabled": bool(self.engram_url),
            "require_auth": self.require_auth,
            "api_key_configured": bool(self.deepseek_api_key),
        }
