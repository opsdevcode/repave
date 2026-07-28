"""Portal and API presentation for fleet registry rows."""

from __future__ import annotations

from typing import Any

from repave_engine.fleet import FleetEntry
from repave_engine.fleet_manifests import resource_name
from repave_engine.fleet_operator_status import FleetOperatorStatus


def fleet_row(
    entry: FleetEntry,
    *,
    operator: FleetOperatorStatus | None = None,
    namespace: str = "default",
) -> dict[str, Any]:
    manifest_name = resource_name(entry.repo_url)
    row: dict[str, Any] = {
        **entry.to_dict(),
        "manifest_name": manifest_name,
        "manifest_namespace": namespace,
    }
    if operator is None:
        row["operator_phase"] = ""
        row["operator_message"] = ""
        row["remediation_pr_url"] = ""
        return row
    row["operator_phase"] = operator.phase or ""
    row["operator_message"] = operator.message or ""
    row["remediation_pr_url"] = operator.remediation_pr_url or ""
    if operator.resource_name:
        row["manifest_name"] = operator.resource_name
    if operator.namespace:
        row["manifest_namespace"] = operator.namespace
    return row


def build_fleet_rows(
    entries: tuple[FleetEntry, ...] | list[FleetEntry],
    *,
    operator_by_url: dict[str, FleetOperatorStatus] | None = None,
    namespace: str = "default",
) -> list[dict[str, Any]]:
    lookup = operator_by_url or {}
    return [
        fleet_row(entry, operator=lookup.get(entry.repo_url), namespace=namespace)
        for entry in entries
    ]
