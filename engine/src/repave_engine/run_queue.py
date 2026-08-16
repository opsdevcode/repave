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
from repave_engine.component_registry import ComponentRegistryError, register_component_from_vend
from repave_engine.component_vend import (
    is_component_vend_run as is_component_vend_payload,
)
from repave_engine.component_vend import (
    run_component_vend,
)
from repave_engine.durability_store import (
    load_durability_runtime,
    load_durability_store_settings,
    resolve_runs_database,
)
from repave_engine.environment_registry import (
    EnvironmentRegistryError,
    register_environment_from_vend,
)
from repave_engine.environment_vend import (
    DEFAULT_VEND_BLUEPRINT,
    run_environment_vend,
)
from repave_engine.environment_vend import (
    is_environment_vend_run as is_environment_vend_payload,
)
from repave_engine.execution_mode import ExecutionMode
from repave_engine.generate_api import run_bundle_api, run_generate_api
from repave_engine.github_auth import resolve_github_access_token
from repave_engine.live_plan import is_live_plan_run as is_live_plan_payload
from repave_engine.live_plan import run_live_plan
from repave_engine.live_plan_pr import PullRequestRef, attach_live_plan_to_pull_request
from repave_engine.metrics import (
    record_run_queue_depth,
    record_run_terminal,
)
from repave_engine.org_import_scan import is_org_scan_run as is_org_scan_payload
from repave_engine.org_import_scan import run_org_scan
from repave_engine.platform_runs import (
    is_environment_reclaim_run,
    is_fleet_drift_confirm_run,
    load_environment_reclaim_config,
    run_environment_reclaim,
    run_fleet_drift_confirm,
)
from repave_engine.publish_idempotency import (
    PublishIdempotencyContext,
    PublishIdempotencyStore,
    publish_message_succeeded,
)
from repave_engine.render import collect_rendered_files
from repave_engine.run_audit import record_async_run_audit
from repave_engine.run_events import TERMINAL_EVENT_KINDS, RunEventStore, build_run_event_store
from repave_engine.run_job_dispatcher import RunJobDispatcher, build_run_job_dispatcher
from repave_engine.run_store import RunRecord, RunStatus, RunStore
from repave_engine.settings import (
    OutputConfig,
    load_component_vending_config,
    load_environment_vending_config,
)

logger = logging.getLogger(__name__)

# Publish SSE can complete while the worker is still finalizing (notify/S3/OOM).
# After this age, refresh/poll may recover a dry-run from staging artifacts.
_STALLED_AFTER_PUBLISH_SECONDS = 20.0


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

    @property
    def repo_root(self) -> Path:
        return self._repo_root

    def _emit_event(self, run_id: str, kind: str, payload: dict[str, Any] | None = None) -> None:
        if self._event_store is None:
            return
        self._event_store.append(run_id, kind, payload or {})

    def _emit_run_audit(
        self,
        record: RunRecord,
        *,
        merged: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        kind = str(record.payload.get("kind", "")).strip()
        if kind in (
            "live_plan",
            "environment_vend",
            "component_vend",
            "environment_reclaim",
            "fleet_drift_confirm",
            "org_scan",
        ):
            return
        blueprint_name = record.blueprint_name or str(record.payload.get("bundle", "")).strip()
        if not blueprint_name:
            return
        event = "bundle_generation" if record.payload.get("bundle") else "generation"
        if merged is not None:
            blueprint_version = str(
                merged.get("blueprint_version") or merged.get("bundle_version") or ""
            )
            module_name = str(merged.get("module_name") or blueprint_name)
            gates_outcome = str(merged.get("gates_outcome", "unknown"))
            pr_message = str(merged.get("pr_message", ""))
            repository_url = merged.get("repository_url")
            if not isinstance(repository_url, str) or not repository_url.strip():
                repository_url = None
        else:
            blueprint_version = ""
            module_name = blueprint_name
            gates_outcome = "failed"
            pr_message = ""
            repository_url = None
        record_async_run_audit(
            self._repo_root,
            run_id=record.run_id,
            blueprint_name=blueprint_name,
            blueprint_version=blueprint_version,
            module_name=module_name,
            dry_run=record.dry_run,
            gates_outcome=gates_outcome,
            repository_url=repository_url,
            acting_user=record.acting_user,
            pr_message=pr_message,
            error=error,
            event=event,
        )

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
                record = self._store.get(run_id)
                secret_name = None
                if record is not None:
                    raw_secret = record.payload.get("live_plan_secret_name")
                    if isinstance(raw_secret, str) and raw_secret.strip():
                        secret_name = raw_secret.strip()
                self._job_dispatcher.dispatch(run_id, live_plan_secret_name=secret_name)
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
        kind: str | None = None,
        live_plan_secret_name: str | None = None,
        pull_request: dict[str, Any] | None = None,
        environment_vend: dict[str, Any] | None = None,
        component_vend: dict[str, Any] | None = None,
    ) -> RunRecord:
        if not self._accepting:
            raise RunQueueShuttingDownError("async generation queue is shutting down")

        run_kind = (kind or "").strip()
        if run_kind == "live_plan":
            if not blueprint_name:
                raise ValueError("live_plan runs require blueprint_name sentinel")
        elif run_kind == "environment_vend":
            if not blueprint_name:
                raise ValueError("environment_vend runs require blueprint_name sentinel")
        elif run_kind == "component_vend":
            if not blueprint_name:
                raise ValueError("component_vend runs require blueprint_name sentinel")
        elif run_kind in ("environment_reclaim", "fleet_drift_confirm", "org_scan"):
            if not blueprint_name:
                raise ValueError(f"{run_kind} runs require blueprint_name sentinel")
        elif blueprint_name and bundle_name:
            raise ValueError("provide only one of blueprint_name or bundle_name")
        elif not blueprint_name and not bundle_name:
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
        if run_kind == "live_plan":
            payload: dict[str, Any] = {
                "kind": "live_plan",
                "inputs": inputs,
                "dry_run": True,
            }
            if live_plan_secret_name:
                payload["live_plan_secret_name"] = live_plan_secret_name
            if pull_request:
                payload["pull_request"] = pull_request
        elif run_kind == "environment_vend":
            payload = {
                "kind": "environment_vend",
                "inputs": inputs,
                "dry_run": dry_run,
            }
            if environment_vend:
                payload.update(environment_vend)
        elif run_kind == "component_vend":
            payload = {
                "kind": "component_vend",
                "inputs": inputs,
                "dry_run": dry_run,
            }
            if component_vend:
                payload.update(component_vend)
        elif run_kind == "environment_reclaim":
            payload = {
                "kind": "environment_reclaim",
                "inputs": inputs,
                "dry_run": dry_run,
            }
        elif run_kind == "fleet_drift_confirm":
            payload = {
                "kind": "fleet_drift_confirm",
                "inputs": inputs,
                "dry_run": True,
            }
        elif run_kind == "org_scan":
            payload = {
                "kind": "org_scan",
                "inputs": inputs,
                "dry_run": True,
            }
        elif bundle_name:
            payload = {
                "bundle": bundle_name,
                "inputs": inputs,
                "dry_run": dry_run,
            }
        else:
            payload = {"blueprint": blueprint_name, "inputs": inputs, "dry_run": dry_run}
        record = self._store.create_run(
            blueprint_name=target_name,
            dry_run=dry_run if run_kind not in ("live_plan",) else True,
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
        record = self._store.get(run_id)
        if record is None:
            return None
        if record.status == RunStatus.RUNNING:
            recovered = self._recover_stalled_after_publish(record)
            if recovered is not None:
                return recovered
        return record

    def _recover_stalled_after_publish(self, record: RunRecord) -> RunRecord | None:
        """Finalize dry-runs stuck RUNNING after publish SSE (worker hang/crash)."""
        if not record.dry_run or self._event_store is None:
            return None
        try:
            updated = datetime.fromisoformat(record.updated_at.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - updated).total_seconds()
        except ValueError:
            return None
        if age < _STALLED_AFTER_PUBLISH_SECONDS:
            return None
        events = self._event_store.list_from(record.run_id, after_seq=0)
        if any(event.kind in TERMINAL_EVENT_KINDS for event in events):
            return None
        publish_done = any(
            event.kind == "stage_finished" and event.payload.get("stage") == "publish"
            for event in events
        )
        if not publish_done:
            return None
        artifact_dir = self._artifact_store.local_staging_dir(self._repo_root, record.run_id)
        if not artifact_dir.is_dir():
            logger.warning(
                "async run %s stalled after publish; staging missing at %s",
                record.run_id,
                artifact_dir,
            )
            return None
        gates: list[dict[str, Any]] = []
        for event in events:
            if event.kind != "gate_finished":
                continue
            gate_name = str(event.payload.get("gate", "")).strip()
            if not gate_name:
                continue
            gates.append(
                {
                    "name": gate_name,
                    "passed": bool(event.payload.get("passed")),
                    "skipped": bool(event.payload.get("skipped")),
                    "message": str(event.payload.get("message", "")),
                }
            )
        if not gates:
            return None
        rendered = collect_rendered_files(artifact_dir)
        pr_message = ""
        for event in reversed(events):
            if event.kind == "publish_finished":
                pr_message = str(event.payload.get("summary") or event.payload.get("detail") or "")
                break
        gates_passed = all(row["passed"] or row["skipped"] for row in gates)
        result: dict[str, Any] = {
            "blueprint": record.blueprint_name,
            "dry_run": True,
            "gates_outcome": "passed" if gates_passed else "failed",
            "gates_passed": gates_passed,
            "gates": gates,
            "output_dir": str(artifact_dir),
            "artifact_root": str(artifact_dir),
            "pr_message": pr_message or "Plan preview recovered after worker stall",
            "rendered_files": [
                {
                    "path": item.path,
                    "content": item.content,
                    "truncated": item.truncated,
                }
                for item in rendered
            ],
            "recovered_after_publish_stall": True,
        }
        logger.warning(
            "async run %s: recovering SUCCEEDED after publish stall (age=%.0fs, files=%d)",
            record.run_id,
            age,
            len(rendered),
        )
        self._store.update_status(record.run_id, RunStatus.SUCCEEDED, result=result)
        self._emit_event(
            record.run_id,
            "run_finished",
            {
                "status": "succeeded",
                "gates_outcome": result["gates_outcome"],
                "publish_succeeded": True,
                "recovered_after_publish_stall": True,
            },
        )
        record_run_terminal(str(result["gates_outcome"]), record.blueprint_name)
        return self._store.get(record.run_id)

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
                    "kind": record.payload.get("kind") or None,
                    "dry_run": record.dry_run,
                },
            )
            inputs_raw = record.payload.get("inputs", {})
            if not isinstance(inputs_raw, dict):
                inputs_raw = {}

            def on_event(kind: str, payload: dict[str, Any]) -> None:
                self._emit_event(run_id, kind, payload)

            github_token = (
                resolve_github_access_token()
                if (
                    (is_environment_vend_payload(record.payload) and not record.dry_run)
                    or (is_component_vend_payload(record.payload) and not record.dry_run)
                    or (is_environment_reclaim_run(record.payload) and not record.dry_run)
                    or is_org_scan_payload(record.payload)
                )
                else (None if record.dry_run else resolve_github_access_token())
            )
            artifact_dir = self._artifact_store.local_staging_dir(self._repo_root, run_id)
            publish_ctx = PublishIdempotencyContext(
                store=self._publish_store,
                run_id=run_id,
                client_request_id=record.client_request_id,
            )
            try:
                if is_live_plan_payload(record.payload):
                    entity_id = str(inputs_raw.get("entity_id", "")).strip()
                    target = str(inputs_raw.get("target", "")).strip()
                    policies_dir = str(
                        inputs_raw.get("policies_dir", "policy/opa/policies")
                    ).strip()
                    use_backend = bool(inputs_raw.get("use_backend", True))
                    on_event("live_plan_started", {"entity_id": entity_id, "target": target})
                    summary = run_live_plan(
                        repo_root=self._repo_root,
                        target=target,
                        entity_id=entity_id,
                        policies_dir=policies_dir,
                        use_backend=use_backend,
                    )
                    result = summary.to_public_dict()
                    pr_raw = record.payload.get("pull_request")
                    if isinstance(pr_raw, dict):
                        pr_ref = PullRequestRef.from_dict(pr_raw)
                        if pr_ref is not None:
                            pr_github_token = resolve_github_access_token()
                            attachment = attach_live_plan_to_pull_request(
                                pr_ref,
                                summary,
                                run_id=run_id,
                                github_token=pr_github_token,
                            )
                            result["pr_attachment"] = attachment.to_public_dict()
                            on_event(
                                "live_plan_pr_attachment",
                                {
                                    "attached": attachment.attached,
                                    "pull_request_url": attachment.pull_request_url,
                                },
                            )
                    on_event(
                        "live_plan_finished",
                        {
                            "gates_outcome": result.get("gates_outcome"),
                            "resource_add": summary.resource_add,
                            "resource_change": summary.resource_change,
                            "resource_destroy": summary.resource_destroy,
                        },
                    )
                elif is_environment_vend_payload(record.payload):
                    vend_blueprint = (
                        str(record.payload.get("blueprint", DEFAULT_VEND_BLUEPRINT)).strip()
                        or DEFAULT_VEND_BLUEPRINT
                    )
                    on_event(
                        "environment_vend_started",
                        {
                            "blueprint": vend_blueprint,
                            "gitops_path": str(record.payload.get("gitops_path", "")),
                        },
                    )
                    vend_result = run_environment_vend(
                        repo_root=self._repo_root,
                        output_config=self._output_config,
                        blueprint_name=vend_blueprint,
                        inputs=inputs_raw,
                        gitops_repo=str(record.payload.get("gitops_repo", "")),
                        gitops_path=str(record.payload.get("gitops_path", "")),
                        owner=str(record.payload.get("owner", "")),
                        env_class=str(record.payload.get("class", "sandbox")),
                        base_branch=str(record.payload.get("base_branch", "main")),
                        git_branch=str(record.payload.get("git_branch", "")),
                        dry_run=bool(record.payload.get("dry_run", record.dry_run)),
                        github_token=github_token,
                        on_event=on_event,
                    )
                    result = vend_result.to_public_dict()
                    if not record.dry_run:
                        vend_cfg = load_environment_vending_config(self._repo_root)
                        if vend_cfg is not None:
                            try:
                                env_record = register_environment_from_vend(
                                    vend_cfg.file,
                                    vend_result=vend_result,
                                    payload=record.payload,
                                    run_id=record.run_id,
                                    acting_user=record.acting_user,
                                    default_ttl_hours=vend_cfg.default_ttl_hours,
                                    ttl_hours_by_class=vend_cfg.ttl_hours_by_class,
                                )
                                result["catalog_entity_id"] = env_record.entity_id
                            except EnvironmentRegistryError as exc:
                                logger.warning(
                                    "environment registry write failed for run %s: %s",
                                    record.run_id,
                                    exc,
                                )
                    on_event(
                        "environment_vend_finished",
                        {
                            "gates_outcome": result.get("gates_outcome"),
                            "pull_request_url": result.get("pull_request_url"),
                        },
                    )
                elif is_component_vend_payload(record.payload):
                    vend_blueprint = (
                        str(record.payload.get("blueprint", "")).strip()
                        or "terraform-environment-stack"
                    )
                    component_kind = str(record.payload.get("component_kind", "")).strip()
                    component_name = str(record.payload.get("name", "")).strip()
                    on_event(
                        "component_vend_started",
                        {
                            "blueprint": vend_blueprint,
                            "kind": component_kind,
                            "gitops_path": str(record.payload.get("gitops_path", "")),
                        },
                    )
                    cmp_result = run_component_vend(
                        repo_root=self._repo_root,
                        output_config=self._output_config,
                        blueprint_name=vend_blueprint,
                        inputs=inputs_raw,
                        gitops_repo=str(record.payload.get("gitops_repo", "")),
                        gitops_path=str(record.payload.get("gitops_path", "")),
                        owner=str(record.payload.get("owner", "")),
                        component_kind=component_kind,
                        name=component_name,
                        base_branch=str(record.payload.get("base_branch", "main")),
                        git_branch=str(record.payload.get("git_branch", "")),
                        dry_run=bool(record.payload.get("dry_run", record.dry_run)),
                        github_token=github_token,
                        on_event=on_event,
                    )
                    result = cmp_result.to_public_dict()
                    if not record.dry_run:
                        cmp_cfg = load_component_vending_config(self._repo_root)
                        if cmp_cfg is not None:
                            try:
                                cmp_record = register_component_from_vend(
                                    cmp_cfg.file,
                                    vend_result=cmp_result,
                                    payload=record.payload,
                                    run_id=record.run_id,
                                    acting_user=record.acting_user,
                                    default_ttl_hours=cmp_cfg.default_ttl_hours,
                                    ttl_hours_by_kind=cmp_cfg.ttl_hours_by_kind,
                                )
                                result["catalog_entity_id"] = cmp_record.entity_id
                            except ComponentRegistryError as exc:
                                logger.warning(
                                    "component registry write failed for run %s: %s",
                                    record.run_id,
                                    exc,
                                )
                    on_event(
                        "component_vend_finished",
                        {
                            "gates_outcome": result.get("gates_outcome"),
                            "pull_request_url": result.get("pull_request_url"),
                        },
                    )
                elif is_environment_reclaim_run(record.payload):
                    on_event("environment_reclaim_started", {"dry_run": record.dry_run})
                    config = load_environment_reclaim_config(self._repo_root)
                    stack_name = str(inputs_raw.get("stack_name", "")).strip() or None
                    result = run_environment_reclaim(
                        self._repo_root,
                        config=config,
                        github_token=github_token,
                        dry_run=record.dry_run,
                        stack_name=stack_name,
                    )
                    on_event(
                        "environment_reclaim_finished",
                        {
                            "reclaimed_count": result.get("reclaimed_count"),
                            "skipped_count": result.get("skipped_count"),
                        },
                    )
                elif is_fleet_drift_confirm_run(record.payload):
                    repo_urls_raw = inputs_raw.get("repo_urls", [])
                    repo_urls: list[str] = []
                    if isinstance(repo_urls_raw, list):
                        repo_urls = [
                            str(item).strip() for item in repo_urls_raw if str(item).strip()
                        ]
                    on_event(
                        "fleet_drift_confirm_started",
                        {"repo_count": len(repo_urls)},
                    )
                    confirm = run_fleet_drift_confirm(
                        self._repo_root,
                        repo_urls=repo_urls,
                    )
                    result = confirm.to_public_dict()
                    on_event(
                        "fleet_drift_confirm_finished",
                        {
                            "confirmed_behind": confirm.confirmed_behind,
                            "confirmed_current": confirm.confirmed_current,
                        },
                    )
                elif is_org_scan_payload(record.payload):
                    if not github_token:
                        raise ValueError(
                            "GitHub credentials are not configured; set GITHUB_TOKEN or "
                            "GitHub App env vars to scan organization repositories"
                        )
                    result = run_org_scan(
                        self._repo_root,
                        token=github_token,
                        inputs=inputs_raw,
                        on_event=on_event,
                    )
                else:
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
                if record is not None and record.status == RunStatus.SUCCEEDED:
                    # Stall recovery (or a prior finalize) already committed success.
                    return
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
                    if record is not None:
                        self._emit_run_audit(record, error=str(exc))
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
                # Mark terminal before object-store upload so S3 hangs cannot leave
                # the run RUNNING after publish SSE already completed.
                if "artifact_root" not in result:
                    result = {**result, "artifact_root": str(artifact_dir)}
                logger.info(
                    "async run %s: generation complete — marking succeeded",
                    run_id,
                )
                self._store.update_status(
                    run_id,
                    RunStatus.SUCCEEDED,
                    result=result,
                )
                outcome = str(result.get("gates_outcome", "unknown"))
                pr_message = str(result.get("pr_message", ""))
                publish_ok = record.dry_run or publish_message_succeeded(pr_message)
                self._emit_event(
                    run_id,
                    "run_finished",
                    {
                        "status": "succeeded",
                        "gates_outcome": outcome,
                        "publish_succeeded": publish_ok,
                    },
                )
                record_run_terminal(outcome, record.blueprint_name)
                try:
                    artifact_fields = self._artifact_store.persist_run_artifacts(
                        run_id, artifact_dir
                    )
                    if artifact_fields:
                        merged = {**result, **artifact_fields}
                        self._store.update_status(
                            run_id,
                            RunStatus.SUCCEEDED,
                            result=merged,
                        )
                        result = merged
                except Exception:
                    logger.exception(
                        "async run %s: artifact persist failed (run already succeeded)",
                        run_id,
                    )
                self._emit_run_audit(record, merged=result)
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
