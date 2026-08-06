"""Persist and read DX metrics snapshots (JSONL + optional SQL)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from repave_engine.audit_history import AuditHistoryEntry, read_recent_audit_entries
from repave_engine.dx_metrics import (
    DxMetricsSnapshot,
    build_dx_metrics_snapshot,
    collect_eligible_repo_urls,
)
from repave_engine.fleet import read_fleet
from repave_engine.jsonl_lock import append_jsonl_line
from repave_engine.settings import (
    load_audit_config,
    load_fleet_config,
    load_platform_metrics_config,
)

logger = logging.getLogger(__name__)

_MAX_SNAPSHOT_SCAN = 500


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def snapshot_from_dict(payload: dict[str, Any]) -> DxMetricsSnapshot | None:
    try:
        funnels_raw = payload.get("funnels") or []
        friction_raw = payload.get("friction") or []
        from repave_engine.dx_metrics import BlueprintFriction, BlueprintFunnel

        funnels = tuple(
            BlueprintFunnel(
                blueprint_name=str(item.get("blueprint_name", "")),
                plans=int(item.get("plans", 0)),
                applies=int(item.get("applies", 0)),
                passed_applies=int(item.get("passed_applies", 0)),
                conversion_ratio=float(item.get("conversion_ratio", 0.0)),
            )
            for item in funnels_raw
            if isinstance(item, dict)
        )
        friction = tuple(
            BlueprintFriction(
                blueprint_name=str(item.get("blueprint_name", "")),
                total=int(item.get("total", 0)),
                failed=int(item.get("failed", 0)),
                fail_ratio=float(item.get("fail_ratio", 0.0)),
            )
            for item in friction_raw
            if isinstance(item, dict)
        )
        bypass_raw = payload.get("bypass_repos") or []
        return DxMetricsSnapshot(
            captured_at=str(payload.get("captured_at", "")),
            audit_available=bool(payload.get("audit_available")),
            fleet_enabled=bool(payload.get("fleet_enabled")),
            eligible_count=int(payload.get("eligible_count", 0)),
            governed_count=int(payload.get("governed_count", 0)),
            adoption_ratio=(
                float(payload["adoption_ratio"])
                if payload.get("adoption_ratio") is not None
                else None
            ),
            bypass_repos=tuple(str(item) for item in bypass_raw),
            plan_count=int(payload.get("plan_count", 0)),
            apply_count=int(payload.get("apply_count", 0)),
            plan_apply_ratio=(
                float(payload["plan_apply_ratio"])
                if payload.get("plan_apply_ratio") is not None
                else None
            ),
            funnels=funnels,
            time_to_first_artifact_seconds_p50=(
                float(payload["time_to_first_artifact_seconds_p50"])
                if payload.get("time_to_first_artifact_seconds_p50") is not None
                else None
            ),
            time_to_first_artifact_seconds_p90=(
                float(payload["time_to_first_artifact_seconds_p90"])
                if payload.get("time_to_first_artifact_seconds_p90") is not None
                else None
            ),
            service_creation_seconds_p50=(
                float(payload["service_creation_seconds_p50"])
                if payload.get("service_creation_seconds_p50") is not None
                else None
            ),
            service_creation_seconds_p90=(
                float(payload["service_creation_seconds_p90"])
                if payload.get("service_creation_seconds_p90") is not None
                else None
            ),
            friction=friction,
            baseline_adoption_ratio=(
                float(payload["baseline_adoption_ratio"])
                if payload.get("baseline_adoption_ratio") is not None
                else None
            ),
            baseline_plan_apply_ratio=(
                float(payload["baseline_plan_apply_ratio"])
                if payload.get("baseline_plan_apply_ratio") is not None
                else None
            ),
            eligible_source=str(payload.get("eligible_source", "fleet")),
            message=str(payload.get("message", "")),
        )
    except (TypeError, ValueError, KeyError) as exc:
        logger.warning("Skipping invalid DX metrics snapshot: %s", exc)
        return None


def append_dx_metrics_snapshot(
    path: Path,
    snapshot: DxMetricsSnapshot,
    *,
    repo_root: Path | None = None,
) -> None:
    payload = snapshot.to_public_dict()
    created_at = snapshot.captured_at or _utc_now()
    if repo_root is not None:
        from repave_engine.durability_store import load_durability_store_settings
        from repave_engine.sql_store import append_dx_metrics_snapshot_line, connect

        settings = load_durability_store_settings(repo_root)
        if settings is not None:
            with connect(settings.database) as conn:
                append_dx_metrics_snapshot_line(conn, payload, created_at=created_at)
                conn.commit()
            if not settings.export_jsonl:
                return
    line = json.dumps(payload, separators=(",", ":"))
    append_jsonl_line(path, line, store="dx_metrics")


def read_dx_metrics_snapshots(
    path: Path,
    *,
    repo_root: Path | None = None,
    limit: int = 30,
) -> tuple[DxMetricsSnapshot, ...]:
    safe_limit = max(1, min(limit, 200))
    payloads: list[dict[str, Any]] = []
    if repo_root is not None:
        from repave_engine.durability_store import load_durability_store_settings
        from repave_engine.sql_store import connect, scan_dx_metrics_snapshots

        settings = load_durability_store_settings(repo_root)
        if settings is not None:
            try:
                with connect(settings.database) as conn:
                    payloads = scan_dx_metrics_snapshots(conn, max_rows=_MAX_SNAPSHOT_SCAN)
            except OSError as exc:
                logger.warning("DX metrics SQL read failed: %s", exc)
            else:
                snapshots = [
                    snap
                    for payload in payloads
                    if (snap := snapshot_from_dict(payload)) is not None
                ]
                return tuple(snapshots[:safe_limit])

    if not path.is_file():
        return ()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.warning("DX metrics snapshot read failed (%s): %s", path, exc)
        return ()
    for line in reversed(lines[-_MAX_SNAPSHOT_SCAN:]):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    snapshots = [snap for payload in payloads if (snap := snapshot_from_dict(payload)) is not None]
    return tuple(snapshots[:safe_limit])


def capture_dx_metrics(
    repo_root: Path,
    *,
    github_token: str | None = None,
    persist: bool = True,
) -> DxMetricsSnapshot:
    """Build a live snapshot from audit + fleet + optional GitHub search."""
    metrics_cfg = load_platform_metrics_config(repo_root)
    fleet_cfg = load_fleet_config(repo_root)
    audit_cfg = load_audit_config(repo_root)

    fleet_enabled = bool(fleet_cfg is not None and fleet_cfg.enabled)
    fleet_entries = (
        read_fleet(fleet_cfg.file, repo_root=repo_root) if fleet_enabled and fleet_cfg else ()
    )

    audit_available = bool(audit_cfg is not None and audit_cfg.enabled)
    audit_entries: tuple[AuditHistoryEntry, ...] = ()
    if audit_available and audit_cfg is not None:
        audit_entries = read_recent_audit_entries(
            audit_cfg.file,
            limit=5000,
            repo_root=repo_root,
        )

    orgs = metrics_cfg.github_orgs if metrics_cfg else ()
    topics = metrics_cfg.github_topics if metrics_cfg else ()
    search_limit = metrics_cfg.search_limit if metrics_cfg else 100
    eligible_urls, eligible_source, message = collect_eligible_repo_urls(
        github_orgs=orgs,
        github_topics=topics,
        token=github_token,
        search_limit=search_limit,
    )

    snapshot = build_dx_metrics_snapshot(
        captured_at=_utc_now(),
        fleet_entries=fleet_entries,
        eligible_urls=eligible_urls,
        audit_entries=audit_entries,
        audit_available=audit_available,
        fleet_enabled=fleet_enabled,
        eligible_source=eligible_source,
        baseline_adoption_ratio=(metrics_cfg.baseline_adoption_ratio if metrics_cfg else None),
        baseline_plan_apply_ratio=(metrics_cfg.baseline_plan_apply_ratio if metrics_cfg else None),
        message=message,
    )

    if persist and metrics_cfg is not None and metrics_cfg.enabled:
        try:
            append_dx_metrics_snapshot(
                metrics_cfg.snapshot_file,
                snapshot,
                repo_root=repo_root,
            )
        except OSError as exc:
            logger.warning("Failed to persist DX metrics snapshot: %s", exc)

    from repave_engine.metrics import record_dx_metrics

    record_dx_metrics(snapshot)
    return snapshot
