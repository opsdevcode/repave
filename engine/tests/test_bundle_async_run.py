from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from repave_engine.api import create_app
from repave_engine.generate_api import bundle_result_from_stored_run
from repave_engine.run_queue import RunQueue, RunQueueConfig
from repave_engine.run_store import RunRecord, RunStatus, RunStore
from repave_engine.run_submit import is_bundle_run, parse_run_target, submit_async_run
from repave_engine.settings import OutputConfig

SERVICE_STACK_INPUTS = {
    "service_name": "async-bundle",
    "description": "Async bundle test",
    "owner": "group:platform",
    "organization": "platform",
    "team": "payments",
    "port": "8080",
    "runtime": "python",
    "catalog_lifecycle": "experimental",
}


def _fake_bundle_result() -> dict[str, object]:
    return {
        "kind": "bundle",
        "bundle": "service-stack",
        "bundle_version": "0.1.0",
        "dry_run": True,
        "gates_outcome": "passed",
        "gates_passed": True,
        "gates": [],
        "shared_inputs": dict(SERVICE_STACK_INPUTS),
        "members": [
            {
                "member_id": "app",
                "blueprint": "app-service-generic",
                "blueprint_version": "0.1.0",
                "dry_run": True,
                "gates_outcome": "passed",
                "gates_passed": True,
                "gates": [
                    {"name": "dockerfile-lint", "passed": True, "skipped": False, "message": "ok"},
                ],
                "rendered_files": 1,
                "output_dir": "/tmp/app",
            },
        ],
    }


def test_parse_run_target_rejects_both_blueprint_and_bundle() -> None:
    with pytest.raises(ValueError, match="only one"):
        parse_run_target({"blueprint": "demo", "bundle": "service-stack"})


def test_parse_run_target_accepts_bundle() -> None:
    assert parse_run_target({"bundle": "service-stack"}) == (None, "service-stack")


def test_is_bundle_run() -> None:
    record = RunRecord(
        run_id="run-1",
        status=RunStatus.QUEUED,
        blueprint_name="service-stack",
        dry_run=True,
        client_request_id=None,
        acting_user="tester",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        payload={"bundle": "service-stack", "inputs": {}, "dry_run": True},
    )
    assert is_bundle_run(record) is True


def test_run_store_public_dict_exposes_bundle() -> None:
    record = RunRecord(
        run_id="run-1",
        status=RunStatus.QUEUED,
        blueprint_name="service-stack",
        dry_run=True,
        client_request_id=None,
        acting_user="tester",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        payload={"bundle": "service-stack", "inputs": {}, "dry_run": True},
    )
    public = record.to_public_dict()
    assert public["bundle"] == "service-stack"
    assert "blueprint" not in public


def test_run_queue_executes_bundle_job(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite")
    output = OutputConfig(
        github_org="example",
        modules_root=tmp_path / "modules",
    )
    queue = RunQueue(
        repo_root=tmp_path,
        output_config=output,
        store=store,
        config=RunQueueConfig(max_concurrent_runs=1, queue_max_depth=4),
    )
    fake_result = _fake_bundle_result()
    with patch("repave_engine.run_queue.run_bundle_api", return_value=fake_result):
        record = queue.submit(
            bundle_name="service-stack",
            inputs=SERVICE_STACK_INPUTS,
            dry_run=True,
            acting_user="tester",
            client_request_id="bundle-job-1",
        )
        run_id = record.run_id
        deadline = time.time() + 5.0
        terminal = None
        while time.time() < deadline:
            terminal = store.get(run_id)
            if terminal and terminal.status in (
                RunStatus.SUCCEEDED,
                RunStatus.FAILED,
                RunStatus.DEAD_LETTER,
            ):
                break
            time.sleep(0.05)
        assert terminal is not None
        assert terminal.status == RunStatus.SUCCEEDED
        assert terminal.result is not None
        assert terminal.result.get("kind") == "bundle"
        assert terminal.payload.get("bundle") == "service-stack"
    queue.close()


def test_submit_async_run_bundle(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite")
    output = OutputConfig(
        github_org="example",
        modules_root=tmp_path / "modules",
    )
    queue = RunQueue(
        repo_root=tmp_path,
        output_config=output,
        store=store,
        config=RunQueueConfig(
            max_concurrent_runs=1,
            queue_max_depth=4,
            external_workers=True,
            enqueue_only=True,
        ),
    )
    record = submit_async_run(
        queue,
        payload={
            "bundle": "service-stack",
            "inputs": SERVICE_STACK_INPUTS,
            "dry_run": True,
        },
        acting_user="tester",
    )
    assert record.payload["bundle"] == "service-stack"
    assert record.to_public_dict()["bundle"] == "service-stack"
    queue.close()


def test_bundle_result_from_stored_run(repo_root: Path) -> None:
    record = RunRecord(
        run_id="run-bundle",
        status=RunStatus.SUCCEEDED,
        blueprint_name="service-stack",
        dry_run=True,
        client_request_id=None,
        acting_user="tester",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        payload={"bundle": "service-stack", "inputs": SERVICE_STACK_INPUTS, "dry_run": True},
        result={
            "kind": "bundle",
            "bundle": "service-stack",
            "shared_inputs": SERVICE_STACK_INPUTS,
            "members": [
                {
                    "member_id": "app",
                    "blueprint": "app-service-generic",
                    "output_dir": "/tmp/app",
                    "gates": [
                        {
                            "name": "dockerfile-lint",
                            "passed": True,
                            "skipped": False,
                            "message": "ok",
                        },
                    ],
                    "rendered_files": [
                        {"path": "Dockerfile", "content": "FROM python\n", "truncated": False},
                    ],
                },
            ],
        },
    )
    output = OutputConfig(github_org="test-org", modules_root=repo_root / "modules")
    rebuilt = bundle_result_from_stored_run(
        record=record,
        repo_root=repo_root,
        output_config=output,
    )
    assert rebuilt is not None
    assert rebuilt.bundle.name == "service-stack"
    assert len(rebuilt.members) == 1
    assert rebuilt.members[0].result.blueprint.name == "app-service-generic"
    assert rebuilt.members[0].result.rendered_files[0].path == "Dockerfile"


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


def test_portal_bundle_generate_enqueues_in_worker_mode(worker_client) -> None:
    with patch("repave_engine.run_queue.run_bundle_api") as mock_bundle:
        response = worker_client.post(
            "/generate",
            data={
                "bundle_name": "service-stack",
                "dry_run": "true",
                **SERVICE_STACK_INPUTS,
            },
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/runs/")
    mock_bundle.assert_not_called()


def test_api_v2_async_bundle_generate_in_worker_mode(worker_client) -> None:
    with patch("repave_engine.run_queue.run_bundle_api") as mock_bundle:
        mock_bundle.return_value = _fake_bundle_result()
        response = worker_client.post(
            "/api/v2/runs",
            json={
                "bundle": "service-stack",
                "inputs": SERVICE_STACK_INPUTS,
                "dry_run": True,
            },
        )
    assert response.status_code == 202
    body = response.json()
    assert body["bundle"] == "service-stack"
    assert "run_id" in body
