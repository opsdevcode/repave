from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from repave_engine.api import create_app
from repave_engine.execution_mode import SYNC_GENERATE_UNAVAILABLE_DETAIL
from repave_engine.run_queue import RunQueueConfig, build_run_queue


def _write_worker_config(repo_root) -> None:
    (repo_root / "repave.config.yaml").write_text(
        """
durability:
  async_generation: true
  execution_mode: worker
  database_url: sqlite:///data/repave.sqlite
audit:
  enabled: true
  file: data/audit/generation.jsonl
fleet:
  enabled: true
  file: data/fleet/registry.jsonl
""".strip()
        + "\n",
        encoding="utf-8",
    )


@pytest.fixture
def worker_client(repo_root, output_config, monkeypatch, tmp_path):
    monkeypatch.setenv("REPAVE_ASYNC_GENERATION", "1")
    monkeypatch.setenv("REPAVE_EXECUTION_MODE", "worker")
    monkeypatch.setenv("REPAVE_DATABASE_URL", f"sqlite:///{tmp_path}/worker.sqlite")
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    yield client
    queue = client.app.state.run_queue
    if queue is not None:
        queue.close()


def test_api_v1_sync_generate_rejected_in_worker_mode(worker_client) -> None:
    with patch("repave_engine.api_v1.router.run_generate_api") as mock_gen:
        response = worker_client.post(
            "/api/v1/generate",
            json={
                "blueprint": "terraform-module-generic",
                "inputs": {"module_name": "demo"},
                "dry_run": True,
            },
        )
    assert response.status_code == 409
    assert response.json()["detail"] == SYNC_GENERATE_UNAVAILABLE_DETAIL
    mock_gen.assert_not_called()


def test_api_v2_sync_generate_rejected_in_worker_mode(worker_client) -> None:
    with patch("repave_engine.api_v2.router.run_generate_api") as mock_gen:
        response = worker_client.post(
            "/api/v2/generate",
            json={
                "blueprint": "terraform-module-generic",
                "inputs": {"module_name": "demo"},
                "dry_run": True,
            },
        )
    assert response.status_code == 409
    assert response.json()["detail"] == SYNC_GENERATE_UNAVAILABLE_DETAIL
    mock_gen.assert_not_called()


def test_api_v1_async_generate_allowed_in_worker_mode(worker_client) -> None:
    with patch("repave_engine.run_queue.run_generate_api") as mock_gen:
        mock_gen.return_value = {
            "blueprint": "terraform-module-generic",
            "gates_outcome": "passed",
            "gates_passed": True,
            "gates": [],
            "rendered_files": 0,
            "output_dir": "/tmp/out",
        }
        response = worker_client.post(
            "/api/v1/generate",
            json={
                "blueprint": "terraform-module-generic",
                "inputs": {"module_name": "demo"},
                "dry_run": True,
                "async": True,
            },
        )
    assert response.status_code in (200, 202)
    assert "run_id" in response.json()


def test_portal_generate_enqueues_in_worker_mode(worker_client) -> None:
    with patch("repave_engine.run_queue.run_generate_api") as mock_gen:
        response = worker_client.post(
            "/generate",
            data={
                "blueprint_name": "terraform-module-generic",
                "module_name": "demo",
                "dry_run": "true",
            },
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/runs/")
    mock_gen.assert_not_called()


def test_build_run_queue_worker_mode_is_enqueue_only(
    tmp_path,
    output_config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import time

    monkeypatch.setenv("REPAVE_EXECUTION_MODE", "worker")
    monkeypatch.setenv("REPAVE_DATABASE_URL", f"sqlite:///{tmp_path}/data/repave.sqlite")
    queue = build_run_queue(
        tmp_path,
        output_config,
        RunQueueConfig(max_concurrent_runs=2, queue_max_depth=8),
    )
    try:
        with patch("repave_engine.run_queue.run_generate_api") as mock_gen:
            queue.submit(
                blueprint_name="terraform-module-generic",
                inputs={"module_name": "demo"},
                dry_run=True,
                acting_user="tester",
            )
            time.sleep(0.2)
            mock_gen.assert_not_called()
    finally:
        queue.close()


def test_worker_execution_mode_active_from_env(repo_root, monkeypatch: pytest.MonkeyPatch) -> None:
    from repave_engine.execution_mode import worker_execution_mode_active

    monkeypatch.setenv("REPAVE_EXECUTION_MODE", "worker")
    (repo_root / "repave.config.yaml").write_text("durability:\n  async_generation: true\n")
    assert worker_execution_mode_active(repo_root) is True
