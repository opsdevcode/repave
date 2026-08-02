"""Fleet-wide pin drift estimates from registry pins vs catalog targets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from repave_engine.blueprint import Blueprint
from repave_engine.fleet import FleetEntry


@dataclass(frozen=True)
class FleetRepoDriftRow:
    repo_url: str
    owner: str
    blueprint_version: str
    standard_version: str
    catalog_blueprint_version: str
    catalog_standard_version: str
    behind: bool
    pin_fields: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_url": self.repo_url,
            "owner": self.owner,
            "blueprint_version": self.blueprint_version,
            "standard_version": self.standard_version,
            "catalog_blueprint_version": self.catalog_blueprint_version,
            "catalog_standard_version": self.catalog_standard_version,
            "behind": self.behind,
            "pin_fields": list(self.pin_fields),
        }


@dataclass(frozen=True)
class BlueprintDriftSummary:
    blueprint_name: str
    catalog_version: str
    catalog_standard_version: str
    governed_count: int
    current_count: int
    behind_count: int
    behind_repos: tuple[FleetRepoDriftRow, ...]
    estimate_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "blueprint_name": self.blueprint_name,
            "catalog_version": self.catalog_version,
            "catalog_standard_version": self.catalog_standard_version,
            "governed_count": self.governed_count,
            "current_count": self.current_count,
            "behind_count": self.behind_count,
            "behind_repos": [row.to_dict() for row in self.behind_repos],
            "estimate_only": self.estimate_only,
        }


def _entry_behind(entry: FleetEntry, blueprint: Blueprint) -> tuple[bool, tuple[str, ...]]:
    fields: list[str] = []
    if entry.blueprint_version and entry.blueprint_version != blueprint.version:
        fields.append("blueprint_version")
    if entry.standard_version and entry.standard_version != blueprint.standard_version:
        fields.append("standard_version")
    if entry.standard_source and entry.standard_source != blueprint.standard_source:
        fields.append("standard_source")
    if not entry.blueprint_version and not entry.standard_version:
        fields.append("pins_unrecorded")
    return bool(fields), tuple(fields)


def estimate_fleet_drift(
    entries: tuple[FleetEntry, ...] | list[FleetEntry],
    blueprints: list[Blueprint],
) -> tuple[BlueprintDriftSummary, ...]:
    by_name = {bp.name: bp for bp in blueprints}
    grouped: dict[str, list[FleetEntry]] = {}
    for entry in entries:
        grouped.setdefault(entry.blueprint_name, []).append(entry)

    summaries: list[BlueprintDriftSummary] = []
    for blueprint_name in sorted(grouped):
        catalog = by_name.get(blueprint_name)
        if catalog is None:
            continue
        rows: list[FleetRepoDriftRow] = []
        behind_rows: list[FleetRepoDriftRow] = []
        current = 0
        for entry in grouped[blueprint_name]:
            behind, pin_fields = _entry_behind(entry, catalog)
            row = FleetRepoDriftRow(
                repo_url=entry.repo_url,
                owner=entry.owner,
                blueprint_version=entry.blueprint_version,
                standard_version=entry.standard_version,
                catalog_blueprint_version=catalog.version,
                catalog_standard_version=catalog.standard_version,
                behind=behind,
                pin_fields=pin_fields,
            )
            rows.append(row)
            if behind:
                behind_rows.append(row)
            else:
                current += 1
        summaries.append(
            BlueprintDriftSummary(
                blueprint_name=blueprint_name,
                catalog_version=catalog.version,
                catalog_standard_version=catalog.standard_version,
                governed_count=len(rows),
                current_count=current,
                behind_count=len(behind_rows),
                behind_repos=tuple(behind_rows),
            )
        )
    return tuple(summaries)
