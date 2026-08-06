"""Persist and read platform feedback events (JSONL + optional SQL)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from repave_engine.feedback import (
    FeedbackEvent,
    FeedbackRollup,
    build_feedback_event,
    build_feedback_rollup,
)
from repave_engine.jsonl_lock import append_jsonl_line
from repave_engine.settings import load_platform_metrics_config

logger = logging.getLogger(__name__)

_MAX_EVENT_SCAN = 2000


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def event_from_dict(payload: dict[str, Any]) -> FeedbackEvent | None:
    try:
        tags_raw = payload.get("friction_tags") or []
        return build_feedback_event(
            submitted_at=str(payload.get("submitted_at", "")),
            csat=int(payload.get("csat", 0)),
            friction_tags=tuple(str(item) for item in tags_raw),
            comment=str(payload.get("comment", "")),
            blueprint_name=str(payload.get("blueprint_name", "")),
            blueprint_version=str(payload.get("blueprint_version", "")),
            dry_run=bool(payload.get("dry_run")),
            gates_outcome=str(payload.get("gates_outcome", "")),
            acting_user=str(payload.get("acting_user", "")),
            run_id=str(payload.get("run_id", "")),
            surface=str(payload.get("surface", "")),
        )
    except (TypeError, ValueError) as exc:
        logger.warning("Skipping invalid feedback event: %s", exc)
        return None


def append_feedback_event(
    path: Path,
    event: FeedbackEvent,
    *,
    repo_root: Path | None = None,
) -> None:
    payload = event.to_public_dict()
    created_at = event.submitted_at or _utc_now()
    if repo_root is not None:
        from repave_engine.durability_store import load_durability_store_settings
        from repave_engine.sql_store import append_feedback_event_line, connect

        settings = load_durability_store_settings(repo_root)
        if settings is not None:
            with connect(settings.database) as conn:
                append_feedback_event_line(conn, payload, created_at=created_at)
                conn.commit()
            if not settings.export_jsonl:
                return
    line = json.dumps(payload, separators=(",", ":"))
    append_jsonl_line(path, line, store="feedback")


def read_feedback_events(
    path: Path,
    *,
    repo_root: Path | None = None,
    limit: int = 100,
) -> tuple[FeedbackEvent, ...]:
    safe_limit = max(1, min(limit, 500))
    payloads: list[dict[str, Any]] = []
    if repo_root is not None:
        from repave_engine.durability_store import load_durability_store_settings
        from repave_engine.sql_store import connect, scan_feedback_events

        settings = load_durability_store_settings(repo_root)
        if settings is not None:
            try:
                with connect(settings.database) as conn:
                    payloads = scan_feedback_events(conn, max_rows=_MAX_EVENT_SCAN)
            except OSError as exc:
                logger.warning("Feedback SQL read failed: %s", exc)
            else:
                events = [
                    event for payload in payloads if (event := event_from_dict(payload)) is not None
                ]
                return tuple(events[:safe_limit])

    if not path.is_file():
        return ()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.warning("Feedback event read failed (%s): %s", path, exc)
        return ()
    for line in reversed(lines[-_MAX_EVENT_SCAN:]):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    events = [event for payload in payloads if (event := event_from_dict(payload)) is not None]
    return tuple(events[:safe_limit])


def load_feedback_rollup(
    repo_root: Path,
    *,
    limit: int = 500,
) -> tuple[FeedbackRollup, tuple[FeedbackEvent, ...]]:
    metrics_cfg = load_platform_metrics_config(repo_root)
    if metrics_cfg is None:
        return FeedbackRollup(
            event_count=0,
            csat_average=None,
            csat_counts=(),
            friction_tags=(),
            by_blueprint=(),
            by_surface=(),
            by_gates_outcome=(),
        ), ()
    events = read_feedback_events(
        metrics_cfg.feedback_file,
        repo_root=repo_root,
        limit=limit,
    )
    return build_feedback_rollup(events), events
