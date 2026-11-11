"""Tests for opt-in acquisition path wiring."""

from __future__ import annotations

from scout.acquisition.factory import build_acquisition_router
from scout.config import ScoutConfig
from scout.sandbox import GuiSandbox


def test_default_router_stays_offline():
    router = build_acquisition_router(ScoutConfig())
    try:
        assert router.mcp_client is None
        assert router.rpa_runner is None
        assert router.gui_reader is None
    finally:
        router.close()


def test_rpa_and_gui_are_wired_when_enabled():
    router = build_acquisition_router(
        ScoutConfig(
            rpa_enabled=True,
            gui_enabled=True,
            gui_allowed_hosts=("docs.vllm.ai",),
        )
    )
    try:
        assert router.rpa_runner is not None
        assert isinstance(router.gui_reader, GuiSandbox)
    finally:
        router.close()


def test_mcp_start_failure_degrades_to_next_path(monkeypatch):
    def boom(*args: object, **kwargs: object) -> None:
        raise OSError("server not found")

    monkeypatch.setattr("scout.acquisition.factory.StdioMcpClient", boom)
    router = build_acquisition_router(ScoutConfig(mcp_command="missing-mcp"))
    try:
        assert router.mcp_client is None
    finally:
        router.close()


def test_config_parses_opt_in_paths(monkeypatch):
    monkeypatch.setenv("SCOUT_MCP_COMMAND", "uvx")
    monkeypatch.setenv("SCOUT_MCP_ARGS", '["mcp-server-fetch", "--ignore-robots-txt"]')
    monkeypatch.setenv("SCOUT_MCP_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("SCOUT_RPA_ENABLED", "true")
    monkeypatch.setenv("SCOUT_GUI_ENABLED", "true")
    monkeypatch.setenv("SCOUT_GUI_ALLOWED_HOSTS", "docs.vllm.ai, modelcontextprotocol.io")
    monkeypatch.setenv("SCOUT_GUI_BROWSER_CHANNEL", "msedge")

    config = ScoutConfig.from_env()

    assert config.mcp_command == "uvx"
    assert config.mcp_args == ("mcp-server-fetch", "--ignore-robots-txt")
    assert config.mcp_timeout_seconds == 12
    assert config.rpa_enabled is True
    assert config.gui_enabled is True
    assert config.gui_allowed_hosts == (
        "docs.vllm.ai",
        "modelcontextprotocol.io",
    )
    assert config.gui_browser_channel == "msedge"


def test_config_rejects_invalid_mcp_args(monkeypatch):
    monkeypatch.setenv("SCOUT_MCP_ARGS", "not-json")

    try:
        ScoutConfig.from_env()
    except ValueError as exc:
        assert "SCOUT_MCP_ARGS" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected ValueError")
