"""Build an acquisition router with the paths enabled by configuration.

The default configuration stays offline: API adapters only. MCP, RPA and GUI
are opt-in so tests, CI and a plain `scout serve` never spawn subprocesses or
browsers unless the operator asks for them.
"""

from __future__ import annotations

import logging

from ..config import ScoutConfig
from ..policy.allowlist import AllowlistPolicy
from ..sandbox.gui_sandbox import GuiSandbox
from .gui.reader import PlaywrightGuiReader
from .mcp_client import StdioMcpClient
from .router import AcquisitionRouter
from .rpa.workflows import RpaRunner

logger = logging.getLogger(__name__)


def build_acquisition_router(config: ScoutConfig) -> AcquisitionRouter:
    mcp_client = None
    if config.mcp_command:
        try:
            mcp_client = StdioMcpClient(
                config.mcp_command,
                config.mcp_args,
                timeout=config.mcp_timeout_seconds,
            ).start()
        except Exception as exc:  # noqa: BLE001 - degrade to the next path
            logger.warning(
                "MCP server failed to start (%s); continuing without it", exc
            )

    rpa_runner = RpaRunner() if config.rpa_enabled else None

    gui_reader = None
    if config.gui_enabled:
        allowlist = AllowlistPolicy(
            config.source_allowlist,
            verify_dns=config.verify_dns,
            allow_http_local=config.allow_http_local,
        )
        gui_reader = GuiSandbox(
            allowlist,
            PlaywrightGuiReader(
                timeout_ms=int(config.request_timeout_seconds * 1000),
                allowed_hosts=set(
                    config.gui_allowed_hosts or config.source_allowlist
                ),
                channel=config.gui_browser_channel or None,
            ),
        )

    return AcquisitionRouter(
        config,
        mcp_client=mcp_client,
        rpa_runner=rpa_runner,
        gui_reader=gui_reader,
    )
