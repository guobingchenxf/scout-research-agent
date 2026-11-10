"""Capability-based tool policy."""

from __future__ import annotations

from .allowlist import AllowlistPolicy
from .types import Capability, PolicyDecision

_TOOL_CAPABILITY: dict[str, Capability | None] = {
    "search": Capability.SOURCES_READ,
    "read": Capability.SOURCES_READ,
    "python": Capability.SANDBOX_EXEC,
    "ask_human": None,
    "finish": Capability.REPORT_EXPORT,
    # Reserved for future write tools; policy tests cover the approval path.
    "write": Capability.SOURCES_WRITE,
    "memory_write": Capability.MEMORY_WRITE,
}

_WRITE_CAPABILITIES = {Capability.SOURCES_WRITE, Capability.MEMORY_WRITE}


class PolicyEngine:
    def __init__(
        self,
        capabilities: set[Capability] | None = None,
        *,
        allowlist: AllowlistPolicy | None = None,
    ) -> None:
        self.capabilities = capabilities or {
            Capability.SOURCES_READ,
            Capability.REPORT_EXPORT,
        }
        self.allowlist = allowlist

    def grant(self, capability: Capability) -> None:
        self.capabilities.add(capability)

    def revoke(self, capability: Capability) -> None:
        self.capabilities.discard(capability)

    def check_tool(self, tool: str, arguments: dict[str, object]) -> PolicyDecision:
        if tool == "ask_human":
            return PolicyDecision(allowed=True, reason="human interaction is always allowed")
        capability = _TOOL_CAPABILITY.get(tool)
        if capability is None:
            return PolicyDecision(
                allowed=False,
                reason=f"unknown tool: {tool}",
            )
        if capability not in self.capabilities:
            if capability in _WRITE_CAPABILITIES:
                return PolicyDecision(
                    allowed=False,
                    requires_approval=True,
                    reason=f"human approval required for {capability.value}",
                    capability=capability,
                )
            return PolicyDecision(
                allowed=False,
                reason=f"capability not granted: {capability.value}",
                capability=capability,
            )

        if tool == "read" and self.allowlist is not None:
            reference = str(arguments.get("source_id") or arguments.get("url") or "")
            if reference.startswith(("http://", "https://")):
                verdict = self.allowlist.check(reference)
                if not verdict.allowed:
                    return PolicyDecision(
                        allowed=False,
                        reason=verdict.reason,
                        capability=capability,
                    )
        return PolicyDecision(
            allowed=True,
            reason=f"{capability.value} granted",
            capability=capability,
        )

    def check_url(self, url: str) -> PolicyDecision:
        if self.allowlist is None:
            return PolicyDecision(allowed=False, reason="no allowlist configured")
        verdict = self.allowlist.check(url)
        return PolicyDecision(
            allowed=verdict.allowed,
            reason=verdict.reason,
            capability=Capability.SOURCES_READ,
        )
