from __future__ import annotations

import time
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from portal_moved import assert_surface_moved
from repave_engine.api import create_app


@pytest.fixture
def async_client(repo_root, output_config, monkeypatch):
    monkeypatch.setenv("REPAVE_ASYNC_GENERATION", "1")
    monkeypatch.setenv("REPAVE_RUNS_DB", str(repo_root / "data" / "test-runs.sqlite"))
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    yield client
    queue = client.app.state.run_queue
    if queue is not None:
        queue.close()


def test_async_generate_returns_202(async_client) -> None:
    fake = {
        "blueprint": "terraform-module-generic",
        "gates_outcome": "passed",
        "gates_passed": True,
        "gates": [],
        "rendered_files": 0,
        "output_dir": "/tmp/out",
    }
    with patch("repave_engine.run_queue.run_generate_api", return_value=fake):
        submit = async_client.post(
            "/api/v1/generate",
            json={
                "blueprint": "terraform-module-generic",
                "inputs": {"module_name": "demo"},
                "dry_run": True,
                "async": True,
                "client_request_id": f"api-test-{uuid.uuid4()}",
            },
        )
        assert submit.status_code in (200, 202)
        run_id = submit.json()["run_id"]
        deadline = time.time() + 5.0
        while time.time() < deadline:
            poll = async_client.get(f"/api/v1/runs/{run_id}")
            assert poll.status_code == 200
            if poll.json()["status"] == "succeeded":
                assert poll.json()["result"]["gates_outcome"] == "passed"
                return
            time.sleep(0.05)
        pytest.fail("run did not complete")


def test_async_disabled_without_config(tmp_path, output_config, monkeypatch) -> None:
    monkeypatch.delenv("REPAVE_ASYNC_GENERATION", raising=False)
    monkeypatch.delenv("REPAVE_RUNS_DB", raising=False)
    client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))
    response = client.post(
        "/api/v1/generate",
        json={"blueprint": "x", "inputs": {}, "async": True},
    )
    assert response.status_code == 503


def test_list_runs_filters_by_status(async_client) -> None:
    fake = {
        "blueprint": "terraform-module-generic",
        "gates_outcome": "passed",
        "gates_passed": True,
        "gates": [],
        "rendered_files": 0,
        "output_dir": "/tmp/out",
    }
    with patch("repave_engine.run_queue.run_generate_api", return_value=fake):
        submit = async_client.post(
            "/api/v1/runs",
            json={
                "blueprint": "terraform-module-generic",
                "inputs": {"module_name": "demo"},
                "dry_run": True,
                "client_request_id": f"list-test-{uuid.uuid4()}",
            },
        )
        assert submit.status_code == 202
        run_id = submit.json()["run_id"]
        deadline = time.time() + 5.0
        while time.time() < deadline:
            listed = async_client.get("/api/v1/runs?status=succeeded&limit=10")
            assert listed.status_code == 200
            runs = listed.json()["runs"]
            if any(item["run_id"] == run_id for item in runs):
                return
            time.sleep(0.05)
        pytest.fail("run did not appear in succeeded list")


def test_runs_index_lists_recent_runs(async_client) -> None:
    fake = {
        "blueprint": "terraform-module-generic",
        "gates_outcome": "passed",
        "gates_passed": True,
        "gates": [],
        "rendered_files": 0,
        "output_dir": "/tmp/out",
    }
    with patch("repave_engine.run_queue.run_generate_api", return_value=fake):
        submit = async_client.post(
            "/api/v1/runs",
            json={
                "blueprint": "terraform-module-generic",
                "inputs": {"module_name": "demo"},
                "dry_run": True,
                "client_request_id": f"portal-runs-{uuid.uuid4()}",
            },
        )
        assert submit.status_code == 202
        run_id = submit.json()["run_id"]
        deadline = time.time() + 5.0
        while time.time() < deadline:
            listed = async_client.get("/api/v1/runs?limit=10")
            assert listed.status_code == 200
            if any(row.get("run_id") == run_id for row in listed.json().get("runs", [])):
                page = async_client.get("/runs")
                assert_surface_moved(page, "runs")
                assert "data-runs-index" not in page.text
                return
            time.sleep(0.05)
        pytest.fail("run did not appear in API list")
