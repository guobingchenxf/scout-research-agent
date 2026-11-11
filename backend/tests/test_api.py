from __future__ import annotations

import json

from fastapi.testclient import TestClient

from scout.api import create_app
from scout.config import ScoutConfig


def _config(tmp_path, **overrides):
    values = {
        "db_path": tmp_path / "api.db",
        "corpus_dir": tmp_path,
        "index_dir": tmp_path,
        "max_steps": 2,
        "token_budget": 10_000,
        "cost_budget_usd": 1.0,
        "require_auth": False,
    }
    values.update(overrides)
    return ScoutConfig(**values)


def test_health_and_run_endpoints(tmp_path) -> None:
    app = create_app(_config(tmp_path))
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["ok"] is True

        response = client.post(
            "/v1/runs",
            json={"question": "What is PagedAttention?", "planner": "mock"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["run_id"]
        assert payload["report"]["answer"] == "INSUFFICIENT_EVIDENCE"

        run = client.get(f"/v1/runs/{payload['run_id']}")
        assert run.status_code == 200
        assert run.json()["status"] == "escalated"

        events = client.get(f"/v1/runs/{payload['run_id']}/events")
        assert events.status_code == 200
        assert isinstance(events.json(), list)

        trace = client.get(f"/v1/runs/{payload['run_id']}/trace/view")
        assert trace.status_code == 200
        assert "Scout trace" in trace.text or "run" in trace.text


def test_eval_summaries_skips_details_files(tmp_path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "eval_ok.json").write_text(
        json.dumps({"summary": {"tasks": 1}}), encoding="utf-8"
    )
    (reports / "eval_ok.details.json").write_text(
        json.dumps([{"task_id": "x"}]), encoding="utf-8"
    )
    app = create_app(_config(tmp_path, reports_dir=reports))
    with TestClient(app) as client:
        response = client.get("/v1/eval/summaries")
        assert response.status_code == 200
        assert [item["file"] for item in response.json()] == ["eval_ok.json"]


def test_auth_required(tmp_path) -> None:
    app = create_app(
        _config(tmp_path, require_auth=True, api_key="secret", max_steps=1)
    )
    with TestClient(app) as client:
        unauthorized = client.post(
            "/v1/runs",
            json={"question": "What is PagedAttention?"},
        )
        assert unauthorized.status_code == 401

        authorized = client.post(
            "/v1/runs",
            json={"question": "What is PagedAttention?"},
            headers={"X-API-Key": "secret"},
        )
        assert authorized.status_code == 200
