"""Discover observability golden-path repos for portal service inventory."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, cast

import yaml

from repave_engine.observability_catalog import (
    CatalogService,
    ObservabilityCatalog,
    load_observability_catalog,
)


@dataclass(frozen=True)
class InventoryService:
    id: str
    label: str
    organization: str
    team: str
    description: str
    runbook_url: str = ""
    repo_name: str = ""
    source_kind: str = "discovered"

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    def to_catalog_service(self) -> CatalogService:
        return CatalogService(
            id=self.id,
            label=self.label,
            organization=self.organization,
            team=self.team,
            description=self.description,
            runbook_url=self.runbook_url,
        )


def _load_repave_spec(repo_dir: Path) -> dict[str, Any] | None:
    path = repo_dir / "repave.yaml"
    if not path.is_file():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    spec = data.get("spec")
    return cast(dict[str, Any], spec) if isinstance(spec, dict) else None


def _observability_from_spec(spec: dict[str, Any]) -> dict[str, Any] | None:
    if spec.get("artifactType") != "observability":
        return None
    block = spec.get("observability")
    return cast(dict[str, Any], block) if isinstance(block, dict) else None


def _repo_name_matches_observability(name: str) -> bool:
    return name.startswith("observability-") or name.startswith("dashboards-")


def list_inventory_services(modules_root: Path) -> list[InventoryService]:
    """Scan modules_root for observability artifact repos (observability-* / dashboards-*)."""
    services: list[InventoryService] = []
    if not modules_root.is_dir():
        return services

    for entry in sorted(modules_root.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        if not _repo_name_matches_observability(name):
            continue
        spec = _load_repave_spec(entry)
        if spec is None:
            continue
        obs = _observability_from_spec(spec)
        if obs is None:
            continue
        service_id = str(obs.get("service_name", "")).strip()
        if not service_id:
            continue
        organization = str(obs.get("organization", "")).strip() or "platform"
        team = str(obs.get("team", "")).strip() or "platform"
        runbook = str(obs.get("runbook_url", "")).strip()
        label = service_id.replace("-", " ").replace("_", " ").title()
        services.append(
            InventoryService(
                id=service_id,
                label=label,
                organization=organization,
                team=team,
                description=f"Discovered from {name} (repave.yaml)",
                runbook_url=runbook,
                repo_name=name,
                source_kind="discovered",
            )
        )
    return services


def merge_catalog_services(
    catalog: ObservabilityCatalog,
    discovered: list[InventoryService],
) -> tuple[CatalogService, ...]:
    """Catalog entries win on id conflict; append discovered-only services."""
    by_id: dict[str, CatalogService] = {svc.id: svc for svc in catalog.services}
    for item in discovered:
        if item.id in by_id:
            continue
        by_id[item.id] = item.to_catalog_service()
    return tuple(by_id[service_id] for service_id in sorted(by_id))


def load_merged_observability_catalog(
    repo_root: Path,
    modules_root: Path | None,
) -> tuple[ObservabilityCatalog, frozenset[str]]:
    base = load_observability_catalog(repo_root)
    catalog_ids = frozenset(svc.id for svc in base.services)
    merged = catalog_with_merged_services(base, modules_root)
    return merged, catalog_ids


def catalog_with_merged_services(
    catalog: ObservabilityCatalog,
    modules_root: Path | None,
) -> ObservabilityCatalog:
    if modules_root is None or not modules_root.is_dir():
        return catalog
    merged = merge_catalog_services(catalog, list_inventory_services(modules_root))
    return replace(catalog, services=merged)


def services_inventory_json(
    modules_root: Path,
    catalog: ObservabilityCatalog,
    *,
    merge: bool = True,
) -> dict[str, Any]:
    discovered = list_inventory_services(modules_root)
    catalog_ids = {svc.id for svc in catalog.services}
    if merge:
        merged = merge_catalog_services(catalog, discovered)
        services_payload = [
            {
                "id": svc.id,
                "label": svc.label,
                "organization": svc.organization,
                "team": svc.team,
                "description": svc.description,
                "runbook_url": svc.runbook_url,
                "source_kind": "catalog" if svc.id in catalog_ids else "discovered",
            }
            for svc in merged
        ]
    else:
        services_payload = [item.to_json() for item in discovered]
    return {
        "modules_root": str(modules_root),
        "merge_catalog": merge,
        "services": services_payload,
        "discovered_count": len(discovered),
    }
