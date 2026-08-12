"""Policy waiver records with enforced expiry (v3 foundation slice)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class WaiverStatus(StrEnum):
    ACTIVE = "active"
    EXPIRING = "expiring"
    EXPIRED = "expired"
    MISSING = "missing"


class Clock(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True)
class FrozenClock:
    """Injectable clock for tests."""

    instant: datetime

    def now(self) -> datetime:
        return self.instant


@dataclass(frozen=True)
class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(frozen=True)
class WaiverRecord:
    waiver_id: str
    gate_id: str
    expires_at: datetime
    entity_id: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class WaiverEvaluation:
    status: WaiverStatus
    record: WaiverRecord | None
    message: str = ""


def _parse_expires(raw: str) -> datetime:
    text = raw.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_waivers(path: Path) -> tuple[WaiverRecord, ...]:
    """Load waiver records from a JSONL file. Missing file returns empty."""
    if not path.is_file():
        return ()
    records: list[WaiverRecord] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in waivers file {path} line {line_no}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"waivers line {line_no} in {path} must be a JSON object")
        waiver_id = str(payload.get("waiver_id") or payload.get("id") or "").strip()
        gate_id = str(payload.get("gate_id") or "").strip()
        expires_raw = payload.get("expires_at") or payload.get("expires")
        if not waiver_id or not gate_id or not expires_raw:
            raise ValueError(
                f"waivers line {line_no} in {path} requires waiver_id, gate_id, and expires_at"
            )
        entity_raw = payload.get("entity_id")
        entity_id = str(entity_raw).strip() if entity_raw else None
        reason = str(payload.get("reason") or "").strip()
        records.append(
            WaiverRecord(
                waiver_id=waiver_id,
                gate_id=gate_id,
                expires_at=_parse_expires(str(expires_raw)),
                entity_id=entity_id or None,
                reason=reason,
            )
        )
    return tuple(records)


def evaluate_waiver(
    *,
    gate_id: str,
    waivers: tuple[WaiverRecord, ...],
    clock: Clock | None = None,
    entity_id: str | None = None,
    warn_days: int = 7,
) -> WaiverEvaluation:
    """Return waiver status for a gate/entity pair. Expired waivers do not pass."""
    now = (clock or SystemClock()).now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    matches = [
        record
        for record in waivers
        if record.gate_id == gate_id and (record.entity_id is None or record.entity_id == entity_id)
    ]
    if not matches:
        return WaiverEvaluation(WaiverStatus.MISSING, None, "no waiver on file")

    record = max(matches, key=lambda item: item.expires_at)
    if record.expires_at <= now:
        return WaiverEvaluation(
            WaiverStatus.EXPIRED,
            record,
            f"waiver {record.waiver_id} expired at {record.expires_at.isoformat()}",
        )

    warn_cutoff = now + timedelta(days=warn_days)
    if record.expires_at <= warn_cutoff:
        return WaiverEvaluation(
            WaiverStatus.EXPIRING,
            record,
            f"waiver {record.waiver_id} expires at {record.expires_at.isoformat()}",
        )

    return WaiverEvaluation(WaiverStatus.ACTIVE, record, "")


def waiver_blocks_gate(evaluation: WaiverEvaluation) -> bool:
    """True when the gate must fail — expired or missing when enforcement is on."""
    return evaluation.status in {WaiverStatus.EXPIRED, WaiverStatus.MISSING}
