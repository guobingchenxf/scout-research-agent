"""Shared policy types."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class Capability(str, Enum):
    SOURCES_READ = "sources:read"
    SOURCES_WRITE = "sources:write"
    SANDBOX_EXEC = "sandbox:exec"
    MEMORY_READ = "memory:read"
    MEMORY_WRITE = "memory:write"
    REPORT_EXPORT = "report:export"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")

    allowed: bool
    requires_approval: bool = False
    reason: str = ""
    capability: Capability | None = None
