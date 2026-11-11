# Live acquisition verification

> Date: 2026-11-11 · Windows 10 · Python 3.10 (`.venv`) · Node 24 · Microsoft Edge
>
> Scope: prove the opt-in acquisition paths actually run against real services,
> not only mocks. This is read-only: no corpus or DB writes, no LLM spend.

## What was run

```bash
cd D:\scout
python scripts/verify_live_acquisition.py --json reports/live_acquisition.json
```

The script disables the API adapters per check so the requested path is forced;
in normal operation the router tries **API → MCP → RPA → GUI** in that order.

| path | ok | method | document | chars | elapsed |
|---|---|---|---:|---:|---:|
| MCP fetch | ✅ | `mcp` | `https://docs.vllm.ai/en/latest/` | 4,589 | 0.57s |
| RPA GitHub README | ✅ | `rpa` | `docs:github:vllm-project/vllm` | 5,864 | 0.53s |
| GUI (Playwright) | ✅ | `gui` | `docs.vllm.ai` (title: vLLM) | 3,382 | 4.51s |
| GUI allowlist denial | ✅ | — | `example.com` rejected | 0 | — |

Raw output: `reports/live_acquisition.json` (gitignored; numbers above are the
recorded run).

## Path details

### MCP: official fetch server over stdio

`StdioMcpClient` starts the official Python MCP server:

```text
uvx mcp-server-fetch
```

It performs the MCP handshake (`initialize` → `notifications/initialized`),
calls `tools/list`, then `tools/call` for `fetch` on an allowlisted URL. The
returned document is normalized into `SourceDocument` with
`retrieval_method=mcp`. The server respects `robots.txt`; no ignore flag is
used.

### RPA: fixed GitHub workflow

`RpaRunner` matches the URL pattern and runs one known adapter
(`github_repo`), producing `docs:github:vllm-project/vllm` from the GitHub
README API. RPA is deliberately boring: a URL pattern maps to one handler, and
failure falls through to the next path

### GUI: read-only Playwright fallback

`PlaywrightGuiReader` launches headless Edge (`SCOUT_GUI_BROWSER_CHANNEL=msedge`),
navigates to the allowlisted page, and extracts only the title and `body` text.
It never clicks, types, submits forms, downloads, uploads, or reads the
clipboard. `GuiSandbox` re-checks the allowlist and scans the text for prompt
injection; a non-allowlisted host (`example.com`) is rejected.

## Enabling it

The default service stays offline. Opt in through `.env`:

```dotenv
SCOUT_MCP_COMMAND=uvx
SCOUT_MCP_ARGS=["mcp-server-fetch"]
SCOUT_MCP_TIMEOUT_SECONDS=30

SCOUT_RPA_ENABLED=true

SCOUT_GUI_ENABLED=true
SCOUT_GUI_ALLOWED_HOSTS=docs.vllm.ai,modelcontextprotocol.io
SCOUT_GUI_BROWSER_CHANNEL=msedge   # empty + `playwright install chromium` elsewhere
```

`scripts/verify_live_acquisition.py` can be used as a smoke test after changing
any of these settings.

## Limits

- MCP is wired for **fetch/read**; open-ended MCP **search** still needs a
  search-capable server. The current API adapters cover search.
- The MCP server is fetched by `uvx` on first use; the machine needs `uvx` and
  network access.
- GUI uses installed Edge on Windows. On Linux/CI, leave the channel empty and
  run `playwright install chromium`; headless Chromium adds a large download.
- GUI is a read-only fallback, not an interactive browser agent. It does not
  handle login walls, pagination, or JavaScript-only content beyond the initial
  page text.
- These checks hit live third-party sites; results depend on their current
  content and availability.
