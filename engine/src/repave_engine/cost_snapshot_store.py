"""Persist and read per-entity cost actuals for library trend sparklines."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from repave_engine.cost_actuals import CostActualsSummary
from repave_engine.jsonl_lock import append_jsonl_line

logger = logging.getLogger(__name__)

_MAX_SCAN = 2000
_DEFAULT_SLOTS = 8


@dataclass(frozen=True)
class CostSnapshotEntry:
    entity_id: str
    captured_at: str
    currency: str
    amount_30d: str

    def amount_float(self) -> float | None:
        try:
            return float(Decimal(self.amount_30d))
        except (InvalidOperation, ValueError):
            return None

    def to_public_dict(self) -> dict[str, str]:
        return {
            "entity_id": self.entity_id,
            "captured_at": self.captured_at,
            "currency": self.currency,
            "amount_30d": self.amount_30d,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _same_utc_day(left: str, right: str) -> bool:
    for value in (left, right):
        if not value:
            return False
    try:
        left_dt = datetime.fromisoformat(left.replace("Z", "+00:00"))
        right_dt = datetime.fromisoformat(right.replace("Z", "+00:00"))
    except ValueError:
        return left[:10] == right[:10]
    return left_dt.date() == right_dt.date()


def snapshot_from_dict(payload: dict[str, object]) -> CostSnapshotEntry | None:
    entity_id = str(payload.get("entity_id", "")).strip()
    amount = str(payload.get("amount_30d", "")).strip()
    if not entity_id or not amount:
        return None
    return CostSnapshotEntry(
        entity_id=entity_id,
        captured_at=str(payload.get("captured_at", "")).strip(),
        currency=str(payload.get("currency", "USD")).strip() or "USD",
        amount_30d=amount,
    )


def append_cost_snapshot(
    path: Path,
    entry: CostSnapshotEntry,
    *,
    repo_root: Path | None = None,
) -> None:
    payload = entry.to_public_dict()
    line = json.dumps(payload, separators=(",", ":"))
    created_at = entry.captured_at or _utc_now()
    if repo_root is not None:
        from repave_engine.durability_store import load_durability_store_settings
        from repave_engine.sql_store import append_cost_snapshot_line, connect

        settings = load_durability_store_settings(repo_root)
        if settings is not None:
            with connect(settings.database) as conn:
                append_cost_snapshot_line(
                    conn,
                    entry.entity_id,
                    payload,
                    created_at=created_at,
                )
                conn.commit()
            if not settings.export_jsonl:
                return
    append_jsonl_line(path, line, store="cost_snapshots")


def read_entity_cost_snapshots(
    path: Path,
    entity_id: str,
    *,
    repo_root: Path | None = None,
    limit: int = _DEFAULT_SLOTS,
) -> tuple[CostSnapshotEntry, ...]:
    safe_limit = max(1, min(limit, 32))
    if repo_root is not None:
        from repave_engine.durability_store import load_durability_store_settings
        from repave_engine.sql_store import connect, scan_entity_cost_snapshots

        settings = load_durability_store_settings(repo_root)
        if settings is not None:
            try:
                with connect(settings.database) as conn:
                    payloads = scan_entity_cost_snapshots(
                        conn,
                        entity_id=entity_id,
                        max_rows=safe_limit,
                    )
            except OSError as exc:
                logger.warning("Cost snapshot SQL read failed: %s", exc)
            else:
                snapshots = [
                    snap
                    for payload in reversed(payloads)
                    if (snap := snapshot_from_dict(payload)) is not None
                ]
                return tuple(snapshots[-safe_limit:])
    if not path.is_file():
        return ()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.warning("Cost snapshot read failed (%s): %s", path, exc)
        return ()
    matches: list[CostSnapshotEntry] = []
    for line in reversed(lines[-_MAX_SCAN:]):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        entry = snapshot_from_dict(payload)
        if entry is None or entry.entity_id != entity_id:
            continue
        matches.append(entry)
        if len(matches) >= safe_limit:
            break
    matches.reverse()
    return tuple(matches)


def latest_entity_cost_snapshot(
    path: Path,
    entity_id: str,
    *,
    repo_root: Path | None = None,
) -> CostSnapshotEntry | None:
    snapshots = read_entity_cost_snapshots(
        path,
        entity_id,
        repo_root=repo_root,
        limit=1,
    )
    return snapshots[-1] if snapshots else None


def read_latest_cost_snapshots(
    path: Path,
    *,
    repo_root: Path | None = None,
) -> dict[str, CostSnapshotEntry]:
    """Return the newest snapshot per entity_id."""
    if repo_root is not None:
        from repave_engine.durability_store import load_durability_store_settings
        from repave_engine.sql_store import connect, scan_latest_cost_snapshots

        settings = load_durability_store_settings(repo_root)
        if settings is not None:
            try:
                with connect(settings.database) as conn:
                    payloads = scan_latest_cost_snapshots(conn, max_entities=_MAX_SCAN)
            except OSError as exc:
                logger.warning("Cost snapshot SQL latest read failed: %s", exc)
            else:
                out: dict[str, CostSnapshotEntry] = {}
                for payload in payloads:
                    entry = snapshot_from_dict(payload)
                    if entry is not None:
                        out[entry.entity_id] = entry
                return out
    if not path.is_file():
        return {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.warning("Cost snapshot read failed (%s): %s", path, exc)
        return {}
    latest: dict[str, CostSnapshotEntry] = {}
    for line in lines[-_MAX_SCAN:]:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        entry = snapshot_from_dict(payload)
        if entry is None:
            continue
        latest[entry.entity_id] = entry
    return latest


def capture_cost_snapshots(
    path: Path,
    entries: Sequence[tuple[str, CostActualsSummary]],
    *,
    captured_at: str | None = None,
    repo_root: Path | None = None,
) -> int:
    """Append one snapshot per entity when amount changed or no snapshot exists today."""
    timestamp = captured_at or _utc_now()
    written = 0
    for entity_id, actuals in entries:
        normalized_id = entity_id.strip()
        if not normalized_id:
            continue
        latest = latest_entity_cost_snapshot(path, normalized_id, repo_root=repo_root)
        if (
            latest is not None
            and _same_utc_day(latest.captured_at, timestamp)
            and latest.amount_30d == actuals.amount_30d
            and latest.currency == actuals.currency
        ):
            continue
        append_cost_snapshot(
            path,
            CostSnapshotEntry(
                entity_id=normalized_id,
                captured_at=timestamp,
                currency=actuals.currency,
                amount_30d=actuals.amount_30d,
            ),
            repo_root=repo_root,
        )
        written += 1
    return written


def normalize_cost_sparkline_heights(
    amounts: Sequence[float],
    *,
    min_height: int = 14,
    max_height: int = 100,
) -> tuple[int, ...]:
    if not amounts:
        return ()
    if len(amounts) == 1:
        return (max_height,)
    low = min(amounts)
    high = max(amounts)
    if high <= low:
        return tuple(max_height for _ in amounts)
    span = high - low
    return tuple(
        int(min_height + (max_height - min_height) * ((amount - low) / span)) for amount in amounts
    )


def build_cost_sparkline(
    snapshots: Sequence[CostSnapshotEntry],
    *,
    slots: int = _DEFAULT_SLOTS,
) -> tuple[int, ...]:
    amounts = [value for snap in snapshots if (value := snap.amount_float()) is not None]
    if not amounts:
        return ()
    heights = normalize_cost_sparkline_heights(amounts[-slots:])
    if len(heights) < slots:
        heights = (0,) * (slots - len(heights)) + heights
    return heights


def cost_sparkline_detail(
    snapshots: Sequence[CostSnapshotEntry],
    *,
    currency: str,
) -> str:
    if not snapshots:
        return ""
    oldest = snapshots[0]
    newest = snapshots[-1]
    return (
        f"L30D trend ({len(snapshots)} points): "
        f"{currency} {oldest.amount_30d} → {currency} {newest.amount_30d}"
    )
