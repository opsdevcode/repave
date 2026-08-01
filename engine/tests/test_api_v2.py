from __future__ import annotations

import time
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from repave_engine.api import create_app


def test_api_v2_metadata(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/api/v2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["api_version"] == "v2"
    assert "engine_version" in payload
    assert "POST /api/v2/upgrades/plan" in payload["endpoints"]
    assert "POST /api/v2/runs" in payload["endpoints"]
    assert "GET /api/v2/runs" in payload["endpoints"]


def test_api_v2_upgrades_plan(repo_root, output_config, tmp_path) -> None:
    fixture = repo_root / "operator" / "testdata" / "modules" / "terraform-minimal"
    if not fixture.is_dir():
        pytest.skip("operator fixture not present")

    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/api/v2/upgrades/plan",
        json={
            "target_repo": str(fixture),
            "staging_root": str(tmp_path / "staging"),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["blueprint_name"] == "terraform-module-generic"
    assert payload["changed_file_count"] > 0
    assert "summary" in payload
    assert "added" in payload
    assert "modified" in payload
    assert "removed" in payload


def test_api_v2_upgrades_plan_requires_target_repo(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post("/api/v2/upgrades/plan", json={})

    assert response.status_code == 400
    assert "target_repo" in response.json()["detail"]


@pytest.fixture
def async_v2_client(repo_root, output_config, monkeypatch):
    monkeypatch.setenv("REPAVE_ASYNC_GENERATION", "1")
    monkeypatch.setenv("REPAVE_RUNS_DB", str(repo_root / "data" / "test-v2-runs.sqlite"))
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    yield client
    queue = client.app.state.run_queue
    if queue is not None:
        queue.close()


def test_api_v2_runs_submit(async_v2_client) -> None:
    fake = {
        "blueprint": "terraform-module-generic",
        "gates_outcome": "passed",
        "gates_passed": True,
        "gates": [],
        "rendered_files": 0,
        "output_dir": "/tmp/out",
    }
    with patch("repave_engine.run_queue.run_generate_api", return_value=fake):
        submit = async_v2_client.post(
            "/api/v2/runs",
            json={
                "blueprint": "terraform-module-generic",
                "inputs": {"module_name": "demo"},
                "dry_run": True,
                "client_request_id": f"v2-api-{uuid.uuid4()}",
            },
        )
        assert submit.status_code == 202
        run_id = submit.json()["run_id"]
        deadline = time.time() + 5.0
        while time.time() < deadline:
            poll = async_v2_client.get(f"/api/v2/runs/{run_id}")
            assert poll.status_code == 200
            if poll.json()["status"] == "succeeded":
                assert poll.json()["result"]["gates_outcome"] == "passed"
                return
            time.sleep(0.05)
        pytest.fail("v2 run did not complete")


def test_api_v2_runs_list_filters_by_status(async_v2_client) -> None:
    fake = {
        "blueprint": "terraform-module-generic",
        "gates_outcome": "passed",
        "gates_passed": True,
        "gates": [],
        "rendered_files": 0,
        "output_dir": "/tmp/out",
    }
    with patch("repave_engine.run_queue.run_generate_api", return_value=fake):
        submit = async_v2_client.post(
            "/api/v2/runs",
            json={
                "blueprint": "terraform-module-generic",
                "inputs": {"module_name": "demo"},
                "dry_run": True,
                "client_request_id": f"v2-list-{uuid.uuid4()}",
            },
        )
        assert submit.status_code == 202
        run_id = submit.json()["run_id"]
        deadline = time.time() + 5.0
        while time.time() < deadline:
            listed = async_v2_client.get("/api/v2/runs?status=succeeded&limit=10")
            assert listed.status_code == 200
            runs = listed.json()["runs"]
            if any(item["run_id"] == run_id for item in runs):
                return
            time.sleep(0.05)
        pytest.fail("v2 run did not appear in succeeded list")


def test_api_v2_generate_async_matches_runs(async_v2_client) -> None:
    fake = {
        "blueprint": "terraform-module-generic",
        "gates_outcome": "passed",
        "gates_passed": True,
        "gates": [],
        "rendered_files": 0,
        "output_dir": "/tmp/out",
    }
    with patch("repave_engine.run_queue.run_generate_api", return_value=fake):
        response = async_v2_client.post(
            "/api/v2/generate",
            json={
                "blueprint": "terraform-module-generic",
                "inputs": {"module_name": "demo"},
                "dry_run": True,
                "async": True,
                "client_request_id": f"v2-gen-{uuid.uuid4()}",
            },
        )
        assert response.status_code in (200, 202)
        assert "run_id" in response.json()
