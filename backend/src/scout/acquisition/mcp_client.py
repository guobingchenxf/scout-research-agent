"""Minimal MCP (Model Context Protocol) client.

The standard transport is JSON-RPC 2.0 over stdio. `MockMcpClient` is used in
tests and offline demos; `StdioMcpClient` can talk to a real MCP server.
"""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class McpError(Exception):
    pass


class McpTool(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class McpClientProtocol(Protocol):
    def list_tools(self) -> list[McpTool]: ...

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...

    def close(self) -> None: ...


class MockMcpClient:
    def __init__(self, tools: dict[str, Callable[[dict[str, Any]], Any]] | None = None) -> None:
        self.tools = tools or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def list_tools(self) -> list[McpTool]:
        return [
            McpTool(name=name, description=f"mock tool {name}", input_schema={})
            for name in self.tools
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((name, arguments))
        if name not in self.tools:
            raise McpError(f"unknown MCP tool: {name}")
        return self.tools[name](arguments)

    def close(self) -> None:
        return None


class StdioMcpClient:
    """Spawn an MCP server and speak JSON-RPC over stdin/stdout."""

    def __init__(
        self,
        command: str,
        args: Sequence[str] = (),
        *,
        timeout: float = 15.0,
    ) -> None:
        self.command = command
        self.args = list(args)
        self.timeout = timeout
        self._process: subprocess.Popen[str] | None = None
        self._messages: queue.Queue[dict[str, Any]] = queue.Queue()
        self._reader: threading.Thread | None = None
        self._next_id = 1
        self._lock = threading.Lock()

    def start(self) -> StdioMcpClient:
        self._process = subprocess.Popen(
            [self.command, *self.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "scout", "version": "0.1.0"},
            },
        )
        self._notify("notifications/initialized", {})
        return self

    def _read_loop(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        for line in self._process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict):
                self._messages.put(message)

    def _send(self, payload: dict[str, Any]) -> None:
        if self._process is None or self._process.stdin is None:
            raise McpError("MCP client is not started")
        with self._lock:
            self._process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self._process.stdin.flush()

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _request(self, method: str, params: dict[str, Any]) -> Any:
        request_id = self._next_id
        self._next_id += 1
        self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                message = self._messages.get(timeout=remaining)
            except queue.Empty:
                break
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise McpError(str(message["error"]))
            return message.get("result")
        raise McpError(f"MCP request timed out: {method}")

    def list_tools(self) -> list[McpTool]:
        result = self._request("tools/list", {})
        tools = result.get("tools", []) if isinstance(result, dict) else []
        return [
            McpTool(
                name=str(tool.get("name", "")),
                description=str(tool.get("description", "")),
                input_schema=tool.get("inputSchema") or {},
            )
            for tool in tools
            if isinstance(tool, dict) and tool.get("name")
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return self._request("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> None:
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
