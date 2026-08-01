"""Shared async run submission helpers (blueprint or bundle targets)."""

from __future__ import annotations

from typing import Any

from repave_engine.run_queue import RunQueue
from repave_engine.run_store import RunRecord


def parse_run_target(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    blueprint_name = str(payload.get("blueprint", "")).strip()
    bundle_name = str(payload.get("bundle", "")).strip()
    if blueprint_name and bundle_name:
        raise ValueError("provide only one of blueprint or bundle")
    if not blueprint_name and not bundle_name:
        raise ValueError("blueprint or bundle is required")
    return blueprint_name or None, bundle_name or None


def submit_async_run(
    queue: RunQueue,
    *,
    payload: dict[str, Any],
    acting_user: str,
    client_request_id: str | None = None,
) -> RunRecord:
    blueprint_name, bundle_name = parse_run_target(payload)
    inputs_raw = payload.get("inputs", {})
    if not isinstance(inputs_raw, dict):
        raise ValueError("inputs must be an object")
    dry_run = bool(payload.get("dry_run", True))
    return queue.submit(
        blueprint_name=blueprint_name,
        bundle_name=bundle_name,
        inputs=inputs_raw,
        dry_run=dry_run,
        acting_user=acting_user,
        client_request_id=client_request_id,
    )


def is_bundle_run(record: RunRecord) -> bool:
    return bool(record.payload.get("bundle"))
