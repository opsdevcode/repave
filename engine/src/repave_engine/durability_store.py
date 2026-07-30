"""Resolve durability SQL settings and JSONL export mirrors."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from repave_engine.execution_mode import (
    ExecutionMode,
    execution_mode_from_env,
    parse_execution_mode,
)
from repave_engine.sql_store import DatabaseConfig, load_database_config, parse_database_url
from repave_engine.worker_mode import WorkerMode, parse_worker_mode


@dataclass(frozen=True)
class DurabilityStoreSettings:
    """Phase 2 unified SQL store (audit, fleet, runs) plus optional JSONL export."""

    database: DatabaseConfig
    export_jsonl: bool = True
    external_workers: bool = False
    execution_mode: ExecutionMode = ExecutionMode.INPROCESS
    worker_mode: WorkerMode = WorkerMode.INLINE


@dataclass(frozen=True)
class DurabilityRuntimeSettings:
    execution_mode: ExecutionMode = ExecutionMode.INPROCESS
    external_workers: bool = False
    worker_mode: WorkerMode = WorkerMode.INLINE


def _resolve_durability_runtime(
    block: object,
) -> DurabilityRuntimeSettings:
    execution_mode = ExecutionMode.INPROCESS
    external_workers = False
    worker_mode = WorkerMode.INLINE
    if isinstance(block, dict):
        worker_raw = str(block.get("worker_mode", "inline")).strip().lower()
        if worker_raw:
            worker_mode = parse_worker_mode(worker_raw)
        if worker_mode in (WorkerMode.EXTERNAL, WorkerMode.JOB):
            external_workers = True
            execution_mode = ExecutionMode.WORKER
        mode_raw = block.get("execution_mode")
        if mode_raw is not None:
            execution_mode = parse_execution_mode(str(mode_raw))

    env_workers = os.environ.get("REPAVE_EXTERNAL_WORKERS", "").strip().lower()
    if env_workers in ("1", "true", "yes"):
        external_workers = True
        execution_mode = ExecutionMode.WORKER

    env_mode = execution_mode_from_env()
    if env_mode is not None:
        execution_mode = env_mode
        if execution_mode == ExecutionMode.WORKER:
            external_workers = True

    env_job = os.environ.get("REPAVE_RUN_JOBS", "").strip().lower()
    if env_job in ("1", "true", "yes"):
        worker_mode = WorkerMode.JOB
        external_workers = True
        execution_mode = ExecutionMode.WORKER

    return DurabilityRuntimeSettings(
        execution_mode=execution_mode,
        external_workers=external_workers,
        worker_mode=worker_mode,
    )


def load_durability_runtime(repo_root: Path) -> DurabilityRuntimeSettings:
    from repave_engine.settings import _load_config_file

    block = _load_config_file(repo_root / "repave.config.yaml").get("durability")
    return _resolve_durability_runtime(block)


def load_durability_store_settings(repo_root: Path) -> DurabilityStoreSettings | None:
    db = load_database_config(repo_root)
    if db is None:
        return None

    from repave_engine.settings import _load_config_file

    block = _load_config_file(repo_root / "repave.config.yaml").get("durability")
    export_jsonl = True
    runtime = _resolve_durability_runtime(block)
    if isinstance(block, dict):
        raw_export = block.get("export_jsonl", True)
        if not isinstance(raw_export, bool):
            raise ValueError("durability.export_jsonl must be a boolean")
        export_jsonl = raw_export

    return DurabilityStoreSettings(
        database=db,
        export_jsonl=export_jsonl,
        external_workers=runtime.external_workers,
        execution_mode=runtime.execution_mode,
        worker_mode=runtime.worker_mode,
    )


def resolve_runs_database(
    repo_root: Path,
    *,
    runs_db: Path,
    store_settings: DurabilityStoreSettings | None,
) -> DatabaseConfig:
    if store_settings is not None:
        return store_settings.database
    return parse_database_url(f"sqlite:///{runs_db}", repo_root=repo_root)
