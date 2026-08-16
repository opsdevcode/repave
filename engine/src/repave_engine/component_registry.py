"""Append-only JSONL registry of vended components (ADR 013)."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from repave_engine.component_record import ComponentRecord, entity_id_for_component
from repave_engine.jsonl_lock import append_jsonl_line

if TYPE_CHECKING:
    from repave_engine.component_vend import ComponentVendResult

logger = logging.getLogger(__name__)

EVENT_REGISTER = "register"
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
) -> ComponentRecord:
    inputs_raw = payload.get("inputs", {})
    inputs = inputs_raw if isinstance(inputs_raw, dict) else {}
    name = str(inputs.get("stack_name", "")).strip() or vend_result.name
    kind = vend_result.kind
    if not name or not kind:
        raise ComponentRegistryError("name and kind are required to register a component")
    cloud_provider = str(inputs.get("cloud_provider", "aws")).strip() or "aws"
    environment_tier = str(inputs.get("environment", "dev")).strip() or "dev"
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
        vended_at=_now(),
        status="pending" if vend_result.draft else "active",
    )


def append_component_event(path: Path, record: ComponentRecord, event: str) -> None:
    if event != EVENT_REGISTER:
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
        if event != EVENT_REGISTER:
            continue
        entry = ComponentRecord.from_event(payload)
        if entry is not None:
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


def register_component_from_vend(
    path: Path,
    *,
    vend_result: ComponentVendResult,
    payload: dict[str, Any],
    run_id: str,
    acting_user: str,
) -> ComponentRecord:
    record = build_component_record_from_vend(
        vend_result=vend_result,
        payload=payload,
        run_id=run_id,
        acting_user=acting_user,
    )
    return register_component(path, record)
