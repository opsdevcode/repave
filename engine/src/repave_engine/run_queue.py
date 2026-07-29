"""In-process async generation queue (Phase 1 durability)."""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repave_engine.auth_context import reset_acting_user, set_acting_user
from repave_engine.durability_store import load_durability_store_settings, resolve_runs_database
from repave_engine.generate_api import run_generate_api
from repave_engine.metrics import (
    record_run_queue_depth,
    record_run_terminal,
)
from repave_engine.run_events import RunEventStore, build_run_event_store
from repave_engine.run_store import RunRecord, RunStatus, RunStore
from repave_engine.settings import OutputConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunQueueConfig:
    max_concurrent_runs: int = 2
    queue_max_depth: int = 32
    db_path: Path | None = None
    external_workers: bool = False


class RunQueueFullError(RuntimeError):
    """Raised when the queue depth limit is reached."""


class RunQueueShuttingDownError(RuntimeError):
    """Raised when the queue is draining for shutdown."""


class RunQueue:
    def __init__(
        self,
        *,
        repo_root: Path,
        output_config: OutputConfig,
        store: RunStore,
        config: RunQueueConfig,
        event_store: RunEventStore | None = None,
    ) -> None:
        self._repo_root = repo_root
        self._output_config = output_config
        self._store = store
        self._config = config
        self._event_store = event_store
        self._executor = ThreadPoolExecutor(max_workers=config.max_concurrent_runs)
        self._accepting = True
        self._external_workers = config.external_workers
        self._refresh_metrics()

    @property
    def event_store(self) -> RunEventStore | None:
        return self._event_store

    def _emit_event(self, run_id: str, kind: str, payload: dict[str, Any] | None = None) -> None:
        if self._event_store is None:
            return
        self._event_store.append(run_id, kind, payload or {})

    def stop_accepting(self) -> None:
        self._accepting = False

    def drain(self, timeout: float) -> bool:
        """Wait for queued and running jobs to finish. Returns True if the queue emptied."""
        self._accepting = False
        deadline = time.monotonic() + max(0.0, timeout)
        while time.monotonic() < deadline:
            if self._queue_depth() == 0:
                return True
            time.sleep(0.25)
        return self._queue_depth() == 0

    def close(self, *, wait: bool = True) -> None:
        self._accepting = False
        self._executor.shutdown(wait=wait, cancel_futures=not wait)

    def _refresh_metrics(self) -> None:
        queued = self._store.count_by_status(RunStatus.QUEUED)
        running = self._store.count_by_status(RunStatus.RUNNING)
        record_run_queue_depth(queued + running)

    def _queue_depth(self) -> int:
        return self._store.count_by_status(RunStatus.QUEUED, RunStatus.RUNNING)

    def submit(
        self,
        *,
        blueprint_name: str,
        inputs: dict[str, Any],
        dry_run: bool,
        acting_user: str,
        client_request_id: str | None = None,
    ) -> RunRecord:
        if not self._accepting:
            raise RunQueueShuttingDownError("async generation queue is shutting down")

        if client_request_id:
            existing = self._store.get_by_client_request_id(client_request_id)
            if existing is not None:
                return existing

        if self._queue_depth() >= self._config.queue_max_depth:
            raise RunQueueFullError(
                f"Queue full ({self._config.queue_max_depth} in-flight runs max)"
            )

        payload = {"blueprint": blueprint_name, "inputs": inputs, "dry_run": dry_run}
        record = self._store.create_run(
            blueprint_name=blueprint_name,
            dry_run=dry_run,
            payload=payload,
            acting_user=acting_user,
            client_request_id=client_request_id or None,
        )
        if not self._external_workers:
            self._executor.submit(self._run_worker, record.run_id, acting_user)
        self._refresh_metrics()
        return record

    def claim_and_process(self) -> bool:
        """Claim one queued run and execute it (external worker loop)."""
        record = self._store.claim_next_queued()
        if record is None:
            return False
        self.process_run(record.run_id, record.acting_user)
        return True

    def process_run(self, run_id: str, acting_user: str) -> None:
        """Execute one run (external worker / Kubernetes Job entrypoint)."""
        self._run_worker(run_id, acting_user)

    def replay(self, run_id: str) -> RunRecord:
        record = self._store.get(run_id)
        if record is None:
            raise KeyError(run_id)
        if record.status not in (RunStatus.FAILED, RunStatus.DEAD_LETTER):
            raise ValueError("only failed or dead_letter runs can be replayed")
        self._store.update_status(run_id, RunStatus.QUEUED, result=None, error=None)
        if not self._external_workers:
            self._executor.submit(self._run_worker, run_id, record.acting_user)
        self._refresh_metrics()
        updated = self._store.get(run_id)
        if updated is None:
            raise RuntimeError(f"run row missing after replay queue: {run_id}")
        return updated

    def get(self, run_id: str) -> RunRecord | None:
        return self._store.get(run_id)

    def queue_depth(self) -> int:
        return self._queue_depth()

    def _run_worker(self, run_id: str, acting_user: str) -> None:
        token = set_acting_user(acting_user)
        try:
            self._store.update_status(run_id, RunStatus.RUNNING)
            self._refresh_metrics()
            record = self._store.get(run_id)
            if record is None:
                return
            self._emit_event(
                run_id,
                "run_started",
                {"blueprint": record.blueprint_name, "dry_run": record.dry_run},
            )
            inputs_raw = record.payload.get("inputs", {})
            if not isinstance(inputs_raw, dict):
                inputs_raw = {}

            def on_event(kind: str, payload: dict[str, Any]) -> None:
                self._emit_event(run_id, kind, payload)

            github_token = None if record.dry_run else os.environ.get("GITHUB_TOKEN")
            try:
                result = run_generate_api(
                    repo_root=self._repo_root,
                    output_config=self._output_config,
                    blueprint_name=record.blueprint_name,
                    inputs=inputs_raw,
                    dry_run=record.dry_run,
                    github_token=github_token,
                    on_event=on_event,
                )
            except Exception as exc:
                logger.exception("async run %s failed", run_id)
                self._store.update_status(
                    run_id,
                    RunStatus.DEAD_LETTER,
                    error=str(exc),
                )
                self._emit_event(run_id, "run_failed", {"error": str(exc)})
                record_run_terminal("dead_letter", record.blueprint_name)
            else:
                self._store.update_status(
                    run_id,
                    RunStatus.SUCCEEDED,
                    result=result,
                )
                outcome = str(result.get("gates_outcome", "unknown"))
                self._emit_event(
                    run_id,
                    "run_finished",
                    {"status": "succeeded", "gates_outcome": outcome},
                )
                record_run_terminal(outcome, record.blueprint_name)
        finally:
            reset_acting_user(token)
            self._refresh_metrics()


def build_run_queue(
    repo_root: Path,
    output_config: OutputConfig,
    config: RunQueueConfig,
) -> RunQueue:
    store_settings = load_durability_store_settings(repo_root)
    db_path = config.db_path or (repo_root / "data" / "runs.sqlite")
    db_cfg = resolve_runs_database(
        repo_root,
        runs_db=db_path,
        store_settings=store_settings,
    )
    external = config.external_workers or (
        store_settings.external_workers if store_settings is not None else False
    )
    queue_config = RunQueueConfig(
        max_concurrent_runs=config.max_concurrent_runs,
        queue_max_depth=config.queue_max_depth,
        db_path=config.db_path,
        external_workers=external,
    )
    store = RunStore(db_cfg)
    event_store = build_run_event_store(db_cfg)
    return RunQueue(
        repo_root=repo_root,
        output_config=output_config,
        store=store,
        config=queue_config,
        event_store=event_store,
    )
