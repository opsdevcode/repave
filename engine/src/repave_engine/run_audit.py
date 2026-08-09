"""Audit records for async portal runs (run queue terminal states)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from repave_engine.audit import AuditRecord, append_audit_record
from repave_engine.audit_history import initial_artifact_version_for_audit
from repave_engine.publish_idempotency import publish_message_succeeded
from repave_engine.settings import load_audit_config


def record_async_run_audit(
    repo_root: Path,
    *,
    run_id: str,
    blueprint_name: str,
    blueprint_version: str,
    module_name: str,
    dry_run: bool,
    gates_outcome: str,
    repository_url: str | None,
    acting_user: str,
    pr_message: str = "",
    error: str | None = None,
    duration_seconds: float | None = None,
    event: str = "generation",
) -> None:
    """Append one generation audit row for a finished async run."""
    try:
        audit_cfg = load_audit_config(repo_root)
    except ValueError:
        return
    if audit_cfg is None or not audit_cfg.enabled:
        return

    publish_ok = dry_run or publish_message_succeeded(pr_message)
    extra: dict[str, Any] = {
        "run_id": run_id,
        "artifact_version": initial_artifact_version_for_audit(),
    }
    if duration_seconds is not None:
        extra["duration_seconds"] = round(duration_seconds, 3)
    if not dry_run:
        extra["publish_succeeded"] = publish_ok
    if error:
        extra["error"] = error
    if pr_message and not publish_ok:
        extra["publish_error"] = pr_message

    append_audit_record(
        audit_cfg.file,
        AuditRecord(
            event=event,
            blueprint_name=blueprint_name,
            blueprint_version=blueprint_version,
            module_name=module_name,
            dry_run=dry_run,
            gates_outcome=gates_outcome,
            repository_url=repository_url,
            acting_user=acting_user,
            extra=extra,
        ),
        repo_root=repo_root,
    )
