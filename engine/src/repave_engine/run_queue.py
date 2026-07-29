"""In-process async generation queue (Phase 1 durability)."""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repave_engine.auth_context import reset_acting_user, set_acting_user
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


class RunQueueFullError(RuntimeError):
    """Raised when the queue depth limit is reached."""


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
        self._refresh_metrics()

    @property
    def event_store(self) -> RunEventStore | None:
        return self._event_store

    def _emit_event(self, run_id: str, kind: str, payload: dict[str, Any] | None = None) -> None:
        if self._event_store is None:
            return
        self._event_store.append(run_id, kind, payload or {})

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

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
        self._executor.submit(self._run_worker, record.run_id, acting_user)
        self._refresh_metrics()
        return record

    def replay(self, run_id: str) -> RunRecord:
        record = self._store.get(run_id)
        if record is None:
            raise KeyError(run_id)
        if record.status not in (RunStatus.FAILED, RunStatus.DEAD_LETTER):
            raise ValueError("only failed or dead_letter runs can be replayed")
        self._store.update_status(run_id, RunStatus.QUEUED, result=None, error=None)
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
    db_path = config.db_path or (repo_root / "data" / "runs.sqlite")
    store = RunStore(db_path)
    event_store = build_run_event_store(db_path)
    return RunQueue(
        repo_root=repo_root,
        output_config=output_config,
        store=store,
        config=config,
        event_store=event_store,
    )
