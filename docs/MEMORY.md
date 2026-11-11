# Engram memory adapter

> Scout's P1 memory integration: a research run reads relevant long-term
> memories before planning and writes a compact episodic memory after finishing.
> The memory layer is **Engram**, reached over its HTTP API, not imported as a
> library.

## Why this exists

Scout is stateless by design. That is good for reproducibility, but it means a
user's preferences and prior findings disappear every session. The adapter
closes that loop without turning memory into evidence:

- memory is injected as **context for planning** (which sources, which
  sub-questions, what was already tried);
- every claim still needs a `doc_id` returned by `search`/`read`;
- a memory outage never fails a run (fail-open).

## Contract

```text
run start   POST /v1/memories/search  -> context string -> ResearchState.memory_context
            -> LLM planner payload includes "memory_context"
run finish  POST /v1/memories         -> episodic memory, source_type=agent
            metadata: run_id, question, status, sources
```

- Only `status=finished` runs are written.
- The memory content is capped at 1,200 characters of the answer plus up to
  eight source doc ids.
- `idempotency_key` is `scout-run-<run_id>`, so retries do not duplicate.
- Search and write failures are logged and traced (`memory_error`), never raised.

## Enabling it

Start Engram (its own process and DB):

```bash
cd D:\\engram
uvicorn --factory engram.api:get_app --host 127.0.0.1 --port 8001
```

Point Scout at it:

```dotenv
SCOUT_ENGRAM_URL=http://127.0.0.1:8001
SCOUT_ENGRAM_USER_ID=scout
SCOUT_ENGRAM_TENANT_ID=
SCOUT_ENGRAM_API_KEY=
SCOUT_ENGRAM_TOP_K=5
SCOUT_ENGRAM_TOKEN_BUDGET=800
SCOUT_ENGRAM_TIMEOUT_SECONDS=10
```

`SCOUT_ENGRAM_URL` is the only switch; leave it empty to disable memory.

## Live verification

Environment: Engram on `127.0.0.1:8001` with a temporary demo DB, Scout's venv.

```bash
cd D:\\scout
python scripts/verify_engram.py --url http://127.0.0.1:8001
```

Recorded run:

| check | result |
|---|---|
| seed user preference written | `4f87bdbb…` |
| `search_context` for a vLLM/SGLang KV-cache question | returned the seed preference (259 chars in the Scout run) |
| `write_run` after a run | `8fd62131…` |
| search after write | returns the episodic "Research run: …" memory |

A Scout CLI run with `SCOUT_ENGRAM_URL` set produced these trace events:

```text
memory_search  {"chars": 259, "context": "Relevant long-term memories ... prefer official docs ..."}
memory_write   {"memory_id": "a45b597b...", "sources": ["..."]}
```

The planner prompt payload now contains `memory_context`, and the system prompt
tells the planner to treat it as a lead rather than evidence.

## Limits

- The adapter talks to Engram over HTTP; it does not embed Engram's Python
  package. The two projects remain independently deployable.
- Memory quality is only as good as the written answer. With the mock planner
  the written answer can be a raw document dump; use the live planner or a
  synthesis pass for useful episodic memory.
- Search uses Engram's hash embeddings by default; ranking is lexical-ish.
- Context grows as memories accumulate: the first recorded run injected 259
  chars, a later run on the same demo DB injected ~1.9k chars.
- This is a single-user adapter (`SCOUT_ENGRAM_USER_ID`). Multi-tenant routing
  is supported by setting `SCOUT_ENGRAM_TENANT_ID`, but Scout's own API is still
  loopback-oriented.
- The live check seeded a preference through the Engram API, not through Scout's
  UI. The in-run write path is real; preference authoring is still manual.
