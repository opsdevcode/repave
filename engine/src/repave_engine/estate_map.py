"""Estate map tiles: fleet freshness and audit sparklines for the portal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

from repave_engine.audit_history import AuditHistoryEntry
from repave_engine.entity_catalog import entity_id_for_repo_url
from repave_engine.fleet import normalize_repo_url

FreshnessLevel = Literal["fresh", "aging", "drift", "error", "unknown"]
SparkValue = Literal[0, 1, 2]  # 0=fail, 1=pass, 2=empty slot


@dataclass(frozen=True)
class EstateTile:
    repo_url: str
    title: str
    owner: str
    blueprint_name: str
    blueprint_label: str
    operator_phase: str
    freshness: FreshnessLevel
    freshness_detail: str
    registered_at: str
    sparkline: tuple[SparkValue, ...]
    entity_id: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "repo_url": self.repo_url,
            "title": self.title,
            "owner": self.owner,
            "blueprint_name": self.blueprint_name,
            "blueprint_label": self.blueprint_label,
            "operator_phase": self.operator_phase,
            "freshness": self.freshness,
            "freshness_detail": self.freshness_detail,
            "registered_at": self.registered_at,
            "sparkline": list(self.sparkline),
            "entity_id": self.entity_id,
        }


def _repo_tail(repo_url: str) -> str:
    normalized = normalize_repo_url(repo_url)
    path = urlparse(normalized).path.strip("/")
    return path.split("/")[-1] if path else normalized


def _freshness_for_row(row: dict[str, Any]) -> tuple[FreshnessLevel, str]:
    phase = str(row.get("operator_phase", "")).strip()
    if phase == "Error":
        return "error", str(row.get("operator_message", "")).strip() or "Operator error"
    if phase == "OutOfDate":
        return "drift", str(row.get("operator_message", "")).strip() or "Pins out of date"
    if phase == "Ready":
        return "fresh", str(row.get("operator_message", "")).strip() or "Operator in sync"
    if phase:
        return "aging", phase
    return "unknown", "Operator status not configured"


def _audit_sparkline(
    entries: tuple[AuditHistoryEntry, ...],
    *,
    repo_url: str,
    title: str,
    slots: int = 8,
) -> tuple[SparkValue, ...]:
    normalized = normalize_repo_url(repo_url)
    tail = _repo_tail(repo_url)
    relevant: list[SparkValue] = []
    for entry in entries:
        url_match = entry.repository_url and normalize_repo_url(entry.repository_url) == normalized
        name_match = bool(entry.module_name) and entry.module_name in {title, tail}
        if not url_match and not name_match:
            continue
        value: SparkValue = 1 if entry.gates_outcome == "passed" else 0
        relevant.append(value)
        if len(relevant) >= slots:
            break
    relevant.reverse()
    if not relevant:
        empty: SparkValue = 2
        return tuple([empty] * slots)
    empty_slot: SparkValue = 2
    padded: list[SparkValue] = [empty_slot] * (slots - len(relevant)) + relevant
    return tuple(padded[-slots:])


def build_estate_tiles(
    fleet_rows: list[dict[str, Any]],
    *,
    audit_entries: tuple[AuditHistoryEntry, ...] = (),
    sparkline_slots: int = 8,
) -> list[EstateTile]:
    tiles: list[EstateTile] = []
    for row in fleet_rows:
        repo_url = str(row.get("repo_url", "")).strip()
        if not repo_url:
            continue
        title = _repo_tail(repo_url)
        blueprint = str(row.get("blueprint_name", "")).strip()
        version = str(row.get("blueprint_version", "")).strip()
        label = f"{blueprint}@{version}" if blueprint and version else blueprint or "—"
        freshness, detail = _freshness_for_row(row)
        tiles.append(
            EstateTile(
                repo_url=repo_url,
                title=title,
                owner=str(row.get("owner", "")).strip(),
                blueprint_name=blueprint,
                blueprint_label=label,
                operator_phase=str(row.get("operator_phase", "")).strip(),
                freshness=freshness,
                freshness_detail=detail,
                registered_at=str(row.get("registered_at", "")).strip(),
                sparkline=_audit_sparkline(
                    audit_entries,
                    repo_url=repo_url,
                    title=title,
                    slots=sparkline_slots,
                ),
                entity_id=entity_id_for_repo_url(repo_url),
            )
        )
    return sorted(tiles, key=lambda item: item.title.lower())
