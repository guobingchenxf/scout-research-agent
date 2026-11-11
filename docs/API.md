# Scout API

Base URL in development: `http://127.0.0.1:8000`. Interactive OpenAPI docs:
`/docs`.

Authentication: when `SCOUT_REQUIRE_AUTH=true`, send `X-API-Key: <key>` on
every `/v1/*` request. `/health` is public.

## Runs

### `POST /v1/runs`

Create a research run. Set `async_mode=true` to return immediately and follow the
SSE stream; otherwise the request blocks until the run finishes.

```bash
curl -X POST http://127.0.0.1:8000/v1/runs \
  -H "Content-Type: application/json" \
  -d '{
    "question": "vLLM 和 SGLang 在 KV cache 管理上的差异是什么？",
    "planner": "mock",
    "async_mode": true
  }'
```

```json
{"run_id": "f1453c1cd03f405fb40f83d318aacf5a", "status": "running"}
```

`planner` is `mock` or `deepseek`. In `async_mode=false`, the response is the
full `RunResult` with `report` and `state`.

### `GET /v1/runs/{run_id}`

Run status, result, report and final state.

### `GET /v1/runs/{run_id}/events`

All recorded events as JSON.

### `GET /v1/runs/{run_id}/events/stream`

Server-Sent Events. Event names: `run_started`, `plan`, `tool_result`,
`reflect`, `budget_exhausted`, `run_failed`, `run_finished`.

`plan` events include `tokens` and `cost_usd` for the planner call.

### `GET /v1/runs/{run_id}/trace/view`

Standalone HTML trace viewer. Shows every event, its payload, per-plan tokens
and cost, and the run status.

## Approvals

### `GET /v1/runs/{run_id}/approvals`

HITL records for the run.

### `POST /v1/runs/{run_id}/approvals/{approval_id}`

```json
{"decision": "approve", "decided_by": "ui", "note": "ok"}
```

## Evaluation

### `GET /v1/eval/summaries`

Reads `reports/eval_*.json` and returns the summary payloads plus the file name.
The frontend evaluation dashboard uses this endpoint.

## Sources and policy

### `GET /v1/sources`

Allowlist, API source names, sandbox backend, DNS verification flag.

### `GET /v1/policies`

Redacted config plus the current capability set.

## Health

### `GET /health`

```json
{"ok": true, "documents": 306, "chunks": 1244, "llm_mode": "mock", "sandbox_backend": "disabled"}
```

## Errors

| Status | Meaning |
|---|---|
| 400 | invalid request / model not allowed / missing provider key |
| 401 | missing or invalid API key |
| 404 | run, approval or source not found |
| 500 | unexpected server error |

## Notes

- `deepseek-v4-pro` is rejected by `SCOUT_ALLOWED_MODELS`; only
  `deepseek-flash` is allowed by default.
- Runs write to SQLite. Do not run host CLI evals against the same database
  while the Docker container is running.
