"""Append-only JSONL registry of vended components (ADR 013)."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from repave_engine.component_record import (
    ComponentRecord,
    entity_id_for_component,
    resolve_component_ttl_hours,
)
from repave_engine.environment_record import expires_at_from_ttl
from repave_engine.jsonl_lock import append_jsonl_line

if TYPE_CHECKING:
    from repave_engine.component_vend import ComponentVendResult

logger = logging.getLogger(__name__)

EVENT_REGISTER = "register"
EVENT_DECOMMISSION = "decommission"
_MAX_FILE_BYTES = 8_000_000


class ComponentRegistryError(ValueError):
    """Expected failure writing or reading the component registry."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_component_record_from_vend(
    *,
    vend_result: ComponentVendResult,
    payload: dict[str, Any],
    run_id: str,
    acting_user: str,
    ttl_hours: int | None = None,
) -> ComponentRecord:
    inputs_raw = payload.get("inputs", {})
    inputs = inputs_raw if isinstance(inputs_raw, dict) else {}
    name = str(inputs.get("stack_name", "")).strip() or vend_result.name
    kind = vend_result.kind
    if not name or not kind:
        raise ComponentRegistryError("name and kind are required to register a component")
    cloud_provider = str(inputs.get("cloud_provider", "aws")).strip() or "aws"
    environment_tier = str(inputs.get("environment", "dev")).strip() or "dev"
    vended_at = _now()
    return ComponentRecord(
        name=name,
        kind=kind,
        entity_id=entity_id_for_component(kind=kind, name=name),
        cloud_provider=cloud_provider,
        environment_tier=environment_tier,
        owner=vend_result.owner or str(payload.get("owner", "")).strip(),
        blueprint_name=vend_result.blueprint,
        blueprint_version=vend_result.blueprint_version,
        gitops_repo=vend_result.gitops_repo,
        gitops_path=vend_result.gitops_path,
        git_branch=vend_result.git_branch,
        pull_request_url=vend_result.pull_request_url,
        pull_request_number=vend_result.pull_request_number,
        gates_outcome=vend_result.gates_outcome,
        run_id=run_id,
        vended_by=acting_user.strip() or "unknown",
        vended_at=vended_at,
        status="pending" if vend_result.draft else "active",
        expires_at=expires_at_from_ttl(ttl_hours=ttl_hours, vended_at=vended_at),
    )


def append_component_event(path: Path, record: ComponentRecord, event: str) -> None:
    if event not in (EVENT_REGISTER, EVENT_DECOMMISSION):
        raise ComponentRegistryError(f"unknown component registry event {event!r}")
    line = json.dumps(record.to_event(event), separators=(",", ":"))
    try:
        append_jsonl_line(path, line, store="component_registry")
    except OSError as exc:
        raise ComponentRegistryError(f"component registry write failed ({path}): {exc}") from exc


def _fold_component_payloads(payloads: list[dict[str, Any]]) -> tuple[ComponentRecord, ...]:
    current: dict[str, ComponentRecord] = {}
    for payload in payloads:
        event = str(payload.get("event", "")).strip()
        entry = ComponentRecord.from_event(payload)
        if entry is None:
            continue
        if event == EVENT_DECOMMISSION:
            current.pop(entry.entity_id, None)
            continue
        if event != EVENT_REGISTER:
            continue
        current[entry.entity_id] = entry
    return tuple(sorted(current.values(), key=lambda item: item.entity_id))


def read_components(path: Path) -> tuple[ComponentRecord, ...]:
    """Return currently registered components. Never raises."""
    if not path.is_file():
        return ()
    try:
        if path.stat().st_size > _MAX_FILE_BYTES:
            logger.warning("Component registry %s is unusually large; reading anyway", path)
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        logger.warning("Component registry unreadable (%s): %s", path, exc)
        return ()
    payloads: list[dict[str, Any]] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            payloads.append(loaded)
    return _fold_component_payloads(payloads)


def register_component(path: Path, record: ComponentRecord) -> ComponentRecord:
    if not record.name or not record.kind:
        raise ComponentRegistryError("name and kind are required to register a component")
    stamped = replace(record, vended_at=record.vended_at or _now())
    append_component_event(path, stamped, EVENT_REGISTER)
    return stamped


def decommission_component(path: Path, record: ComponentRecord) -> None:
    """Remove a component from the registry (append-only decommission event)."""
    if not record.name or not record.kind:
        raise ComponentRegistryError("name and kind are required to decommission a component")
    append_component_event(path, record, EVENT_DECOMMISSION)


def mark_component_expired(
    path: Path,
    record: ComponentRecord,
    *,
    pull_request_url: str,
    pull_request_number: int,
    git_branch: str,
) -> ComponentRecord:
    """Keep the component in the catalog with expired status and a decommission PR."""
    updated = replace(
        record,
        status="expired",
        pull_request_url=pull_request_url.strip(),
        pull_request_number=pull_request_number,
        git_branch=git_branch.strip() or record.git_branch,
    )
    return register_component(path, updated)


def register_component_from_vend(
    path: Path,
    *,
    vend_result: ComponentVendResult,
    payload: dict[str, Any],
    run_id: str,
    acting_user: str,
    default_ttl_hours: int = 0,
    ttl_hours_by_kind: tuple[tuple[str, int], ...] = (),
) -> ComponentRecord:
    ttl_hours = resolve_component_ttl_hours(
        vend_result.kind,
        default_ttl_hours=default_ttl_hours,
        ttl_hours_by_kind=ttl_hours_by_kind,
    )
    record = build_component_record_from_vend(
        vend_result=vend_result,
        payload=payload,
        run_id=run_id,
        acting_user=acting_user,
        ttl_hours=ttl_hours,
    )
    return register_component(path, record)
