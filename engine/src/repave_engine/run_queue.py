"""In-process async generation queue (Phase 1 durability)."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from repave_engine.artifact_store import ArtifactStore, resolve_artifact_store
from repave_engine.auth_context import reset_acting_user, set_acting_user
from repave_engine.durability_store import (
    load_durability_runtime,
    load_durability_store_settings,
    resolve_runs_database,
)
from repave_engine.execution_mode import ExecutionMode
from repave_engine.generate_api import run_bundle_api, run_generate_api
from repave_engine.github_auth import resolve_github_access_token
from repave_engine.metrics import (
    record_run_queue_depth,
    record_run_terminal,
)
from repave_engine.publish_idempotency import PublishIdempotencyContext, PublishIdempotencyStore
from repave_engine.run_events import RunEventStore, build_run_event_store
from repave_engine.run_job_dispatcher import RunJobDispatcher, build_run_job_dispatcher
from repave_engine.run_store import RunRecord, RunStatus, RunStore
from repave_engine.settings import OutputConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunQueueConfig:
    max_concurrent_runs: int = 2
    queue_max_depth: int = 32
    db_path: Path | None = None
    external_workers: bool = False
    enqueue_only: bool = False
    use_claim_workers: bool = False
    max_attempts: int = 3
    stale_run_seconds: int = 3600
    retry_base_seconds: int = 5


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
        artifact_store: ArtifactStore | None = None,
        publish_store: PublishIdempotencyStore | None = None,
        job_dispatcher: RunJobDispatcher | None = None,
    ) -> None:
        self._repo_root = repo_root
        self._output_config = output_config
        self._store = store
        self._config = config
        self._event_store = event_store
        self._artifact_store = artifact_store or resolve_artifact_store(repo_root)
        self._publish_store = publish_store
        self._job_dispatcher = job_dispatcher
        self._enqueue_only = config.enqueue_only or config.external_workers
        self._use_claim_workers = config.use_claim_workers
        self._executor: ThreadPoolExecutor | None = None
        if not self._enqueue_only:
            self._executor = ThreadPoolExecutor(max_workers=config.max_concurrent_runs)
        self._accepting = True
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
        if self._executor is not None:
            self._executor.shutdown(wait=wait, cancel_futures=not wait)

    def _refresh_metrics(self) -> None:
        self._reclaim_stale()
        queued = self._store.count_by_status(RunStatus.QUEUED)
        running = self._store.count_by_status(RunStatus.RUNNING)
        record_run_queue_depth(queued + running)

    def _reclaim_stale(self) -> None:
        if self._config.stale_run_seconds <= 0:
            return
        self._store.reclaim_stale_runs(
            stale_after_seconds=self._config.stale_run_seconds,
            max_attempts=self._config.max_attempts,
        )

    def _retry_delay_seconds(self, attempt_count: int) -> int:
        base = max(1, self._config.retry_base_seconds)
        exponent = max(0, attempt_count - 1)
        return int(min(300, base * (2**exponent)))

    def _schedule_retry(self, run_id: str, *, attempt_count: int, error: str) -> None:
        delay = self._retry_delay_seconds(attempt_count)
        next_at = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
        self._store.schedule_retry(
            run_id,
            attempt_count=attempt_count,
            error=error,
            next_attempt_at=next_at,
        )
        self._emit_event(
            run_id,
            "run_retry_scheduled",
            {"attempt_count": attempt_count, "next_attempt_at": next_at, "error": error},
        )

    def _queue_depth(self) -> int:
        return self._store.count_by_status(RunStatus.QUEUED, RunStatus.RUNNING)

    def _schedule_execution(self, *, acting_user: str, run_id: str | None = None) -> None:
        if self._enqueue_only or self._executor is None:
            return
        if self._use_claim_workers:
            self._executor.submit(self.claim_and_process)
        elif run_id is not None:
            self._executor.submit(self._run_worker, run_id, acting_user)

    def _dispatch_run(self, *, run_id: str, acting_user: str) -> None:
        if self._job_dispatcher is not None:
            try:
                self._job_dispatcher.dispatch(run_id)
            except Exception as exc:
                logger.exception("failed to dispatch run Job for %s", run_id)
                self._store.update_status(
                    run_id,
                    RunStatus.DEAD_LETTER,
                    error=f"job dispatch: {exc}",
                )
                self._emit_event(run_id, "run_failed", {"error": str(exc)})
                raise
            return
        self._schedule_execution(acting_user=acting_user, run_id=run_id)

    def submit(
        self,
        *,
        blueprint_name: str | None = None,
        bundle_name: str | None = None,
        inputs: dict[str, Any],
        dry_run: bool,
        acting_user: str,
        client_request_id: str | None = None,
    ) -> RunRecord:
        if not self._accepting:
            raise RunQueueShuttingDownError("async generation queue is shutting down")

        if blueprint_name and bundle_name:
            raise ValueError("provide only one of blueprint_name or bundle_name")
        if not blueprint_name and not bundle_name:
            raise ValueError("blueprint_name or bundle_name is required")

        if client_request_id:
            existing = self._store.get_by_client_request_id(client_request_id)
            if existing is not None:
                return existing

        if self._queue_depth() >= self._config.queue_max_depth:
            raise RunQueueFullError(
                f"Queue full ({self._config.queue_max_depth} in-flight runs max)"
            )

        target_name = bundle_name or blueprint_name or ""
        if bundle_name:
            payload: dict[str, Any] = {
                "bundle": bundle_name,
                "inputs": inputs,
                "dry_run": dry_run,
            }
        else:
            payload = {"blueprint": blueprint_name, "inputs": inputs, "dry_run": dry_run}
        record = self._store.create_run(
            blueprint_name=target_name,
            dry_run=dry_run,
            payload=payload,
            acting_user=acting_user,
            client_request_id=client_request_id or None,
        )
        self._dispatch_run(run_id=record.run_id, acting_user=acting_user)
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
        self._store.reset_for_replay(run_id)
        self._dispatch_run(run_id=run_id, acting_user=record.acting_user)
        self._refresh_metrics()
        updated = self._store.get(run_id)
        if updated is None:
            raise RuntimeError(f"run row missing after replay queue: {run_id}")
        return updated

    def get(self, run_id: str) -> RunRecord | None:
        return self._store.get(run_id)

    def list_runs(
        self,
        *,
        status: RunStatus | None = None,
        limit: int = 50,
    ) -> list[RunRecord]:
        return self._store.list_runs(status=status, limit=limit)

    def queue_depth(self) -> int:
        return self._queue_depth()

    def _run_worker(self, run_id: str, acting_user: str) -> None:
        token = set_acting_user(acting_user)
        try:
            if self._use_claim_workers:
                record = self._store.get(run_id)
                if record is None or record.status != RunStatus.RUNNING:
                    return
            else:
                self._store.update_status(run_id, RunStatus.RUNNING)
                self._refresh_metrics()
                record = self._store.get(run_id)
                if record is None:
                    return
            self._emit_event(
                run_id,
                "run_started",
                {
                    "blueprint": record.payload.get("blueprint") or None,
                    "bundle": record.payload.get("bundle") or None,
                    "dry_run": record.dry_run,
                },
            )
            inputs_raw = record.payload.get("inputs", {})
            if not isinstance(inputs_raw, dict):
                inputs_raw = {}

            def on_event(kind: str, payload: dict[str, Any]) -> None:
                self._emit_event(run_id, kind, payload)

            github_token = None if record.dry_run else resolve_github_access_token()
            artifact_dir = self._artifact_store.local_staging_dir(self._repo_root, run_id)
            publish_ctx = PublishIdempotencyContext(
                store=self._publish_store,
                run_id=run_id,
                client_request_id=record.client_request_id,
            )
            try:
                bundle_name = str(record.payload.get("bundle", "")).strip()
                if bundle_name:
                    result = run_bundle_api(
                        repo_root=self._repo_root,
                        output_config=self._output_config,
                        bundle_name=bundle_name,
                        inputs=inputs_raw,
                        dry_run=record.dry_run,
                        github_token=github_token,
                        on_event=on_event,
                        staging_root=artifact_dir,
                    )
                else:
                    result = run_generate_api(
                        repo_root=self._repo_root,
                        output_config=self._output_config,
                        blueprint_name=record.blueprint_name,
                        inputs=inputs_raw,
                        dry_run=record.dry_run,
                        github_token=github_token,
                        on_event=on_event,
                        staging_root=artifact_dir,
                        publish_idempotency=publish_ctx,
                    )
            except Exception as exc:
                logger.exception("async run %s failed", run_id)
                record = self._store.get(run_id)
                attempt = (record.attempt_count if record else 0) + 1
                if attempt >= self._config.max_attempts:
                    self._store.update_status(
                        run_id,
                        RunStatus.DEAD_LETTER,
                        error=str(exc),
                        clear_next_attempt=True,
                    )
                    self._emit_event(run_id, "run_failed", {"error": str(exc)})
                    record_run_terminal("dead_letter", record.blueprint_name if record else "")
                else:
                    self._schedule_retry(run_id, attempt_count=attempt, error=str(exc))
                    if not self._enqueue_only and self._executor is not None:
                        self._executor.submit(
                            self._wait_and_retry,
                            run_id,
                            record.acting_user if record else acting_user,
                            attempt,
                        )
            else:
                artifact_fields = self._artifact_store.persist_run_artifacts(run_id, artifact_dir)
                merged = {**result, **artifact_fields}
                self._store.update_status(
                    run_id,
                    RunStatus.SUCCEEDED,
                    result=merged,
                )
                outcome = str(merged.get("gates_outcome", "unknown"))
                self._emit_event(
                    run_id,
                    "run_finished",
                    {"status": "succeeded", "gates_outcome": outcome},
                )
                record_run_terminal(outcome, record.blueprint_name)
        finally:
            reset_acting_user(token)
            self._refresh_metrics()

    def _wait_and_retry(self, run_id: str, acting_user: str, attempt_count: int) -> None:
        delay = self._retry_delay_seconds(attempt_count)
        time.sleep(delay)
        current = self._store.get(run_id)
        if current is None or current.status != RunStatus.QUEUED:
            return
        self._run_worker(run_id, acting_user)


def build_run_queue(
    repo_root: Path,
    output_config: OutputConfig,
    config: RunQueueConfig,
) -> RunQueue:
    store_settings = load_durability_store_settings(repo_root)
    runtime = load_durability_runtime(repo_root)
    db_path = config.db_path or (repo_root / "data" / "runs.sqlite")
    db_cfg = resolve_runs_database(
        repo_root,
        runs_db=db_path,
        store_settings=store_settings,
    )
    enqueue_only = (
        config.enqueue_only
        or config.external_workers
        or runtime.external_workers
        or runtime.execution_mode == ExecutionMode.WORKER
    )
    use_claim_workers = db_cfg.dialect == "postgresql" and runtime.worker_mode.value != "job"
    queue_config = RunQueueConfig(
        max_concurrent_runs=config.max_concurrent_runs,
        queue_max_depth=config.queue_max_depth,
        db_path=config.db_path,
        external_workers=enqueue_only,
        enqueue_only=enqueue_only,
        use_claim_workers=use_claim_workers,
        max_attempts=config.max_attempts,
        stale_run_seconds=config.stale_run_seconds,
        retry_base_seconds=config.retry_base_seconds,
    )
    store = RunStore(db_cfg)
    event_store = build_run_event_store(db_cfg)
    publish_store = PublishIdempotencyStore(db_cfg)
    job_dispatcher = build_run_job_dispatcher(repo_root, worker_mode=runtime.worker_mode)
    return RunQueue(
        repo_root=repo_root,
        output_config=output_config,
        store=store,
        config=queue_config,
        event_store=event_store,
        publish_store=publish_store,
        job_dispatcher=job_dispatcher,
    )
