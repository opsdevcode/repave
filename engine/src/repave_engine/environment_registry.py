"""Append-only JSONL registry of vended environments (ADR 003 Phase 3 slice 3)."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from repave_engine.environment_record import (
    EnvironmentRecord,
    entity_id_for_environment,
    expires_at_from_ttl,
    resolve_ttl_hours,
)
from repave_engine.jsonl_lock import append_jsonl_line

if TYPE_CHECKING:
    from repave_engine.environment_vend import EnvironmentVendResult

logger = logging.getLogger(__name__)

EVENT_REGISTER = "register"
EVENT_DECOMMISSION = "decommission"

_MAX_FILE_BYTES = 8_000_000


class EnvironmentRegistryError(ValueError):
    """Expected failure writing or reading the environment registry."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_environment_record_from_vend(
    *,
    vend_result: EnvironmentVendResult,
    payload: dict[str, Any],
    run_id: str,
    acting_user: str,
    ttl_hours: int | None,
) -> EnvironmentRecord:
    inputs_raw = payload.get("inputs", {})
    inputs = inputs_raw if isinstance(inputs_raw, dict) else {}
    stack_name = str(inputs.get("stack_name", "")).strip()
    if not stack_name:
        raise EnvironmentRegistryError("inputs.stack_name is required to register an environment")
    cloud_provider = str(inputs.get("cloud_provider", "aws")).strip() or "aws"
    environment_tier = str(inputs.get("environment", "dev")).strip() or "dev"
    vended_at = _now()
    status = "pending" if vend_result.draft else "active"
    return EnvironmentRecord(
        stack_name=stack_name,
        entity_id=entity_id_for_environment(cloud_provider=cloud_provider, stack_name=stack_name),
        cloud_provider=cloud_provider,
        environment_tier=environment_tier,
        owner=vend_result.owner or str(payload.get("owner", "")).strip(),
        env_class=vend_result.env_class
        or str(payload.get("class", "sandbox")).strip()
        or "sandbox",
        blueprint_name=vend_result.blueprint,
        blueprint_version=vend_result.blueprint_version,
        gitops_repo=vend_result.gitops_repo,
        gitops_path=vend_result.gitops_path,
        git_branch=vend_result.git_branch,
        pull_request_url=vend_result.pull_request_url,
        pull_request_number=vend_result.pull_request_number,
        gates_outcome=vend_result.gates_outcome,
        source_entity_id=str(payload.get("entity_id", "")).strip(),
        run_id=run_id,
        vended_by=acting_user.strip() or "unknown",
        vended_at=vended_at,
        expires_at=expires_at_from_ttl(ttl_hours=ttl_hours, vended_at=vended_at),
        status=status,
    )


def append_environment_event(path: Path, record: EnvironmentRecord, event: str) -> None:
    if event not in (EVENT_REGISTER, EVENT_DECOMMISSION):
        raise EnvironmentRegistryError(f"unknown environment registry event {event!r}")
    payload = record.to_event(event)
    line = json.dumps(payload, separators=(",", ":"))
    try:
        append_jsonl_line(path, line, store="environment_registry")
    except OSError as exc:
        raise EnvironmentRegistryError(
            f"environment registry write failed ({path}): {exc}"
        ) from exc


def _fold_environment_payloads(payloads: list[dict[str, Any]]) -> tuple[EnvironmentRecord, ...]:
    current: dict[str, EnvironmentRecord] = {}
    for payload in payloads:
        event = str(payload.get("event", "")).strip()
        stack_name = str(payload.get("stack_name", "")).strip()
        if not stack_name:
            continue
        if event == EVENT_DECOMMISSION:
            current.pop(stack_name, None)
            continue
        if event != EVENT_REGISTER:
            continue
        entry = EnvironmentRecord.from_event(payload)
        if entry is not None:
            current[stack_name] = entry
    return tuple(sorted(current.values(), key=lambda item: item.stack_name))


def read_environments(path: Path) -> tuple[EnvironmentRecord, ...]:
    """Return currently registered environments. Never raises."""
    if not path.is_file():
        return ()
    try:
        if path.stat().st_size > _MAX_FILE_BYTES:
            logger.warning("Environment registry %s is unusually large; reading anyway", path)
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        logger.warning("Environment registry unreadable (%s): %s", path, exc)
        return ()

    payloads: list[dict[str, Any]] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return _fold_environment_payloads(payloads)


def register_environment(path: Path, record: EnvironmentRecord) -> EnvironmentRecord:
    """Register or update a vended environment (last write wins per stack_name)."""
    if not record.stack_name:
        raise EnvironmentRegistryError("stack_name is required to register an environment")
    stamped = replace(
        record,
        vended_at=record.vended_at or _now(),
    )
    append_environment_event(path, stamped, EVENT_REGISTER)
    return stamped


def decommission_environment(path: Path, record: EnvironmentRecord) -> None:
    """Remove an environment from the registry (append-only decommission event)."""
    if not record.stack_name:
        raise EnvironmentRegistryError("stack_name is required to decommission an environment")
    append_environment_event(path, record, EVENT_DECOMMISSION)


def register_environment_from_vend(
    path: Path,
    *,
    vend_result: EnvironmentVendResult,
    payload: dict[str, Any],
    run_id: str,
    acting_user: str,
    default_ttl_hours: int = 0,
    ttl_hours_by_class: tuple[tuple[str, int], ...] = (),
) -> EnvironmentRecord:
    env_class = vend_result.env_class or str(payload.get("class", "sandbox")).strip() or "sandbox"
    ttl_hours = resolve_ttl_hours(
        env_class,
        default_ttl_hours=default_ttl_hours,
        ttl_hours_by_class=ttl_hours_by_class,
    )
    record = build_environment_record_from_vend(
        vend_result=vend_result,
        payload=payload,
        run_id=run_id,
        acting_user=acting_user,
        ttl_hours=ttl_hours,
    )
    return register_environment(path, record)
