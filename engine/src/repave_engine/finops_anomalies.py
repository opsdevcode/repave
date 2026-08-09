"""WoW / MoM cost anomaly detection on snapshot series (v1.94)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from repave_engine.audit import AuditRecord, append_audit_record
from repave_engine.cost_snapshot_store import CostSnapshotEntry, read_entity_cost_snapshots
from repave_engine.entity_catalog import CatalogEntity
from repave_engine.settings import CostAnomalyConfig, PortalConfig, load_audit_config

logger = logging.getLogger(__name__)

AnomalyKind = Literal["wow", "mom"]


@dataclass(frozen=True)
class CostAnomaly:
    entity_id: str
    display_name: str
    owner: str
    kind: AnomalyKind
    currency: str
    baseline_amount: float
    current_amount: float
    change_pct: float
    threshold_pct: float
    baseline_at: str
    current_at: str

    def to_public_dict(self) -> dict[str, object]:
        return {
            "entity_id": self.entity_id,
            "display_name": self.display_name,
            "owner": self.owner,
            "kind": self.kind,
            "currency": self.currency,
            "baseline_amount": f"{self.baseline_amount:.2f}",
            "current_amount": f"{self.current_amount:.2f}",
            "change_pct": round(self.change_pct, 2),
            "threshold_pct": self.threshold_pct,
            "baseline_at": self.baseline_at,
            "current_at": self.current_at,
        }


def _parse_snapshot_time(captured_at: str) -> datetime | None:
    text = captured_at.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _pct_increase(current: float, baseline: float) -> float | None:
    if baseline <= 0:
        if current <= 0:
            return None
        return 100.0
    return ((current - baseline) / baseline) * 100.0


def _baseline_snapshot(
    snapshots: Sequence[CostSnapshotEntry],
    *,
    latest: CostSnapshotEntry,
    days_back: int,
    tolerance_days: int,
) -> CostSnapshotEntry | None:
    latest_dt = _parse_snapshot_time(latest.captured_at)
    if latest_dt is None:
        return None
    target = latest_dt - timedelta(days=days_back)
    best: CostSnapshotEntry | None = None
    best_delta: float | None = None
    for snap in snapshots:
        snap_dt = _parse_snapshot_time(snap.captured_at)
        if snap_dt is None or snap_dt >= latest_dt:
            continue
        delta_days = abs((snap_dt - target).total_seconds()) / 86400.0
        if delta_days > tolerance_days:
            continue
        if best_delta is None or delta_days < best_delta:
            best = snap
            best_delta = delta_days
    return best


def detect_entity_cost_anomalies(
    entity: CatalogEntity,
    snapshots: Sequence[CostSnapshotEntry],
    config: CostAnomalyConfig,
) -> tuple[CostAnomaly, ...]:
    if not config.enabled or len(snapshots) < 2:
        return ()
    latest = snapshots[-1]
    current = latest.amount_float()
    if current is None:
        return ()
    anomalies: list[CostAnomaly] = []
    checks: tuple[tuple[AnomalyKind, int, int, float], ...] = (
        ("wow", 7, 3, config.wow_threshold_pct),
        ("mom", 28, 7, config.mom_threshold_pct),
    )
    for kind, days_back, tolerance_days, threshold in checks:
        baseline_snap = _baseline_snapshot(
            snapshots,
            latest=latest,
            days_back=days_back,
            tolerance_days=tolerance_days,
        )
        if baseline_snap is None:
            continue
        baseline_amount = baseline_snap.amount_float()
        if baseline_amount is None:
            continue
        change_pct = _pct_increase(current, baseline_amount)
        if change_pct is None or change_pct < threshold:
            continue
        anomalies.append(
            CostAnomaly(
                entity_id=entity.entity_id,
                display_name=entity.display_name,
                owner=entity.owner,
                kind=kind,
                currency=latest.currency or "USD",
                baseline_amount=baseline_amount,
                current_amount=current,
                change_pct=change_pct,
                threshold_pct=threshold,
                baseline_at=baseline_snap.captured_at,
                current_at=latest.captured_at,
            )
        )
    return tuple(anomalies)


def _record_anomaly_audit(
    repo_root: Path,
    anomaly: CostAnomaly,
) -> None:
    try:
        audit_cfg = load_audit_config(repo_root)
    except ValueError:
        return
    if audit_cfg is None or not audit_cfg.enabled:
        return
    append_audit_record(
        audit_cfg.file,
        AuditRecord(
            event="finops_anomaly",
            blueprint_name="finops",
            blueprint_version="",
            module_name=anomaly.display_name,
            dry_run=False,
            gates_outcome="n/a",
            repository_url=None,
            acting_user="system",
            extra=anomaly.to_public_dict(),
        ),
        repo_root=repo_root,
    )


def evaluate_finops_anomalies(
    entities: Sequence[CatalogEntity],
    portal_config: PortalConfig,
    *,
    repo_root: Path,
    notify: bool = True,
    audit: bool = True,
) -> tuple[CostAnomaly, ...]:
    if not portal_config.cost_anomalies.enabled:
        return ()
    if portal_config.cost_snapshots_file is None:
        return ()
    found: list[CostAnomaly] = []
    for entity in entities:
        snapshots = read_entity_cost_snapshots(
            portal_config.cost_snapshots_file,
            entity.entity_id,
            repo_root=repo_root,
            limit=32,
        )
        entity_anomalies = detect_entity_cost_anomalies(
            entity,
            snapshots,
            portal_config.cost_anomalies,
        )
        for anomaly in entity_anomalies:
            if audit:
                _record_anomaly_audit(repo_root, anomaly)
            found.append(anomaly)
    if notify and found:
        from repave_engine.notifications import notify_finops_anomalies

        notify_finops_anomalies(repo_root, tuple(found))
    return tuple(found)
