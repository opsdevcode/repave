from __future__ import annotations

import pytest

from repave_engine.durability_store import _resolve_durability_runtime
from repave_engine.execution_mode import ExecutionMode, parse_execution_mode
from repave_engine.worker_mode import WorkerMode


def test_parse_execution_mode_worker_aliases() -> None:
    assert parse_execution_mode("worker") == ExecutionMode.WORKER
    assert parse_execution_mode("external") == ExecutionMode.WORKER


def test_resolve_durability_runtime_worker_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REPAVE_EXTERNAL_WORKERS", raising=False)
    monkeypatch.delenv("REPAVE_EXECUTION_MODE", raising=False)
    monkeypatch.delenv("REPAVE_RUN_JOBS", raising=False)
    runtime = _resolve_durability_runtime({"worker_mode": "external"})
    assert runtime.execution_mode == ExecutionMode.WORKER
    assert runtime.external_workers is True
    assert runtime.worker_mode.value == "external"


def test_resolve_durability_runtime_job_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REPAVE_EXTERNAL_WORKERS", raising=False)
    monkeypatch.delenv("REPAVE_EXECUTION_MODE", raising=False)
    monkeypatch.delenv("REPAVE_RUN_JOBS", raising=False)
    runtime = _resolve_durability_runtime({"worker_mode": "job"})
    assert runtime.execution_mode == ExecutionMode.WORKER
    assert runtime.external_workers is True
    assert runtime.worker_mode == WorkerMode.JOB


def test_resolve_durability_runtime_env_execution_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPAVE_EXECUTION_MODE", "worker")
    runtime = _resolve_durability_runtime({})
    assert runtime.execution_mode == ExecutionMode.WORKER
