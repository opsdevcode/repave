from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from repave_engine.readiness import (
    evaluate_readiness,
    gate_toolchain_required,
    path_writable,
)


def test_path_writable(tmp_path) -> None:
    assert path_writable(tmp_path / "nested") is True


def test_evaluate_readiness_modules_root(tmp_path) -> None:
    modules = tmp_path / "modules"
    report = evaluate_readiness(
        modules_root=modules,
        runs_db=None,
        shutting_down=False,
        auth_service_enabled=False,
        require_session_secret=False,
        github_token_configured=False,
    )
    assert report.ready is True
    assert report.checks["modules_root_writable"] is True


def test_evaluate_readiness_shutting_down(tmp_path) -> None:
    report = evaluate_readiness(
        modules_root=tmp_path,
        runs_db=None,
        shutting_down=True,
        auth_service_enabled=False,
        require_session_secret=False,
        github_token_configured=False,
    )
    assert report.ready is False
    assert report.checks["not_shutting_down"] is False


def test_gate_toolchain_not_required_for_decomposed_portal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("REPAVE_EXTERNAL_WORKERS", "1")
    monkeypatch.setenv("REPAVE_IMAGE_GATE_TOOLCHAIN", "0")
    assert gate_toolchain_required() is False

    report = evaluate_readiness(
        modules_root=tmp_path,
        runs_db=None,
        shutting_down=False,
        auth_service_enabled=False,
        require_session_secret=False,
        github_token_configured=False,
    )
    assert report.ready is True
    assert "gate_tools" not in report.checks
    assert "runtime" in report.details


def test_run_queue_drain_waits_for_worker(tmp_path) -> None:
    from repave_engine.run_queue import RunQueue, RunQueueConfig
    from repave_engine.run_store import RunStatus, RunStore
    from repave_engine.settings import OutputConfig

    store = RunStore(tmp_path / "runs.sqlite")
    output = OutputConfig(github_org="example", modules_root=tmp_path / "modules")
    queue = RunQueue(
        repo_root=tmp_path,
        output_config=output,
        store=store,
        config=RunQueueConfig(max_concurrent_runs=1, queue_max_depth=4),
    )
    started = time.time()

    def slow_generate(**_kwargs):
        time.sleep(0.3)
        return {
            "blueprint": "terraform-module-generic",
            "gates_outcome": "passed",
            "gates_passed": True,
            "gates": [],
            "rendered_files": 1,
            "output_dir": str(tmp_path / "out"),
        }

    with patch("repave_engine.run_queue.run_generate_api", side_effect=slow_generate):
        record = queue.submit(
            blueprint_name="terraform-module-generic",
            inputs={"module_name": "demo"},
            dry_run=True,
            acting_user="tester",
        )
        assert queue.drain(timeout=5.0) is True
        terminal = store.get(record.run_id)
        assert terminal is not None
        assert terminal.status == RunStatus.SUCCEEDED
    assert time.time() - started >= 0.25
    queue.close()
