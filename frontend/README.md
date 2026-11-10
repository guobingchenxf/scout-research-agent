# Scout Frontend

React + Vite + TypeScript UI for Scout.

## Pages

| Page | Purpose |
|---|---|
| Task | submit a question, choose mock/deepseek-flash planner |
| Run | live SSE timeline, run status, budgets |
| Evidence | plan coverage, evidence cards, conflicts, gaps |
| Report | Markdown report with citations; export `.md` |
| Eval | reads `reports/eval_*.json` summaries |
| Approvals | HITL records; approve/reject pending items |
| Sources | allowlist, API sources, capabilities, policy summary |

## Dev

Backend first:

```bash
cd ../backend
python -m scout.cli serve --host 127.0.0.1 --port 8000
```

Frontend:

```bash
cd ../frontend
npm install
npm run dev
```

Vite proxies `/v1` and `/health` to `http://127.0.0.1:8000`, so no CORS
configuration is needed in development.

## Build

```bash
npm run build
npm run preview
```

Verified in Phase 5: `npm install` (166 packages), `npm run build` (289 modules),
Vite dev + backend proxy + async run + SSE + eval summaries all return 200.

## API contract

- `POST /v1/runs` with `{question, planner, async_mode: true}` → `{run_id, status}`
- `GET /v1/runs/{id}` → run state/result
- `GET /v1/runs/{id}/events/stream` → SSE events
- `GET /v1/runs/{id}/approvals`
- `GET /v1/eval/summaries`
- `GET /v1/sources`
- `GET /v1/policies`

The UI never constructs citations or tool calls client-side; it renders the
backend's evidence and report.
