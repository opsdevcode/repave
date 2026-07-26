from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

OBSERVABILITY_CATALOG_REL = Path("observability/catalog.json")


@dataclass(frozen=True)
class CatalogOption:
    id: str
    label: str
    description: str = ""


@dataclass(frozen=True)
class CatalogTeam:
    id: str
    label: str
    organization: str
    description: str = ""


@dataclass(frozen=True)
class CatalogService:
    id: str
    label: str
    organization: str
    team: str
    description: str
    runbook_url: str = ""


@dataclass(frozen=True)
class GrafanaDatasource:
    uid: str
    label: str
    type: str


@dataclass(frozen=True)
class CatalogRunbook:
    id: str
    label: str
    url: str


@dataclass(frozen=True)
class SloTargetOption:
    id: str
    label: str
    value: str


@dataclass(frozen=True)
class NotificationTarget:
    id: str
    label: str
    description: str


@dataclass(frozen=True)
class NotificationSource:
    id: str
    label: str
    description: str
    provider: str
    targets: tuple[NotificationTarget, ...]
    reference_url: str | None = None


@dataclass(frozen=True)
class DashboardPackFile:
    source: str
    dest: str


@dataclass(frozen=True)
class DashboardPack:
    id: str
    label: str
    description: str
    backend: str
    files: tuple[DashboardPackFile, ...]
    reference_url: str | None = None
    license: str | None = None


@dataclass(frozen=True)
class FormPreset:
    decision_fields: tuple[str, ...]


@dataclass(frozen=True)
class ObservabilityCatalog:
    version: str
    defaults: dict[str, str]
    organizations: tuple[CatalogOption, ...]
    teams: tuple[CatalogTeam, ...]
    environments: tuple[CatalogOption, ...]
    services: tuple[CatalogService, ...]
    grafana_datasources: tuple[GrafanaDatasource, ...]
    runbooks: tuple[CatalogRunbook, ...]
    slo_targets: tuple[SloTargetOption, ...]
    notification_sources: tuple[NotificationSource, ...]
    dashboard_packs: tuple[DashboardPack, ...]
    form_presets: dict[str, FormPreset]


def _load_options(raw_list: object) -> tuple[CatalogOption, ...]:
    if not isinstance(raw_list, list):
        return ()
    items: list[CatalogOption] = []
    for raw in raw_list:
        if not isinstance(raw, dict) or "id" not in raw:
            continue
        items.append(
            CatalogOption(
                id=str(raw["id"]),
                label=str(raw.get("label", raw["id"])),
                description=str(raw.get("description", "")),
            )
        )
    return tuple(items)


def load_observability_catalog(repo_root: Path) -> ObservabilityCatalog:
    path = repo_root / OBSERVABILITY_CATALOG_REL
    if not path.is_file():
        raise FileNotFoundError(f"Observability catalog missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    sources: list[NotificationSource] = []
    for raw in data.get("notification_sources", []):
        if not isinstance(raw, dict) or "id" not in raw:
            continue
        targets: list[NotificationTarget] = []
        for item in raw.get("targets", []):
            if not isinstance(item, dict) or "id" not in item:
                continue
            targets.append(
                NotificationTarget(
                    id=str(item["id"]),
                    label=str(item.get("label", item["id"])),
                    description=str(item.get("description", "")),
                )
            )
        sources.append(
            NotificationSource(
                id=str(raw["id"]),
                label=str(raw.get("label", raw["id"])),
                description=str(raw.get("description", "")),
                provider=str(raw.get("provider", "")),
                targets=tuple(targets),
                reference_url=str(raw["reference_url"]) if raw.get("reference_url") else None,
            )
        )
    packs: list[DashboardPack] = []
    for raw in data.get("dashboard_packs", []):
        if not isinstance(raw, dict) or "id" not in raw:
            continue
        files: list[DashboardPackFile] = []
        for item in raw.get("files", []):
            if not isinstance(item, dict):
                continue
            if "source" not in item or "dest" not in item:
                continue
            files.append(
                DashboardPackFile(
                    source=str(item["source"]),
                    dest=str(item["dest"]),
                )
            )
        packs.append(
            DashboardPack(
                id=str(raw["id"]),
                label=str(raw.get("label", raw["id"])),
                description=str(raw.get("description", "")),
                backend=str(raw.get("backend", "any")),
                files=tuple(files),
                reference_url=str(raw["reference_url"]) if raw.get("reference_url") else None,
                license=str(raw["license"]) if raw.get("license") else None,
            )
        )
    teams: list[CatalogTeam] = []
    for raw in data.get("teams", []):
        if not isinstance(raw, dict) or "id" not in raw:
            continue
        teams.append(
            CatalogTeam(
                id=str(raw["id"]),
                label=str(raw.get("label", raw["id"])),
                organization=str(raw.get("organization", "")),
                description=str(raw.get("description", "")),
            )
        )
    services: list[CatalogService] = []
    for raw in data.get("services", []):
        if not isinstance(raw, dict) or "id" not in raw:
            continue
        services.append(
            CatalogService(
                id=str(raw["id"]),
                label=str(raw.get("label", raw["id"])),
                organization=str(raw.get("organization", "")),
                team=str(raw.get("team", "")),
                description=str(raw.get("description", "")),
                runbook_url=str(raw.get("runbook_url", "")),
            )
        )
    datasources: list[GrafanaDatasource] = []
    for raw in data.get("grafana_datasources", []):
        if not isinstance(raw, dict) or "uid" not in raw:
            continue
        datasources.append(
            GrafanaDatasource(
                uid=str(raw["uid"]),
                label=str(raw.get("label", raw["uid"])),
                type=str(raw.get("type", "prometheus")),
            )
        )
    runbooks: list[CatalogRunbook] = []
    for raw in data.get("runbooks", []):
        if not isinstance(raw, dict) or "id" not in raw or "url" not in raw:
            continue
        runbooks.append(
            CatalogRunbook(
                id=str(raw["id"]),
                label=str(raw.get("label", raw["id"])),
                url=str(raw["url"]),
            )
        )
    slo_options: list[SloTargetOption] = []
    for raw in data.get("slo_targets", []):
        if not isinstance(raw, dict) or "id" not in raw:
            continue
        slo_options.append(
            SloTargetOption(
                id=str(raw["id"]),
                label=str(raw.get("label", raw["id"])),
                value=str(raw.get("value", "")),
            )
        )
    defaults_raw = data.get("defaults", {})
    defaults: dict[str, str] = {}
    if isinstance(defaults_raw, dict):
        for key, value in defaults_raw.items():
            if value is not None:
                defaults[str(key)] = str(value)
    form_presets: dict[str, FormPreset] = {}
    raw_presets = data.get("form_presets", {})
    if isinstance(raw_presets, dict):
        for blueprint_name, preset_raw in raw_presets.items():
            if not isinstance(preset_raw, dict):
                continue
            fields_raw = preset_raw.get("decision_fields", [])
            if not isinstance(fields_raw, list):
                continue
            form_presets[str(blueprint_name)] = FormPreset(
                decision_fields=tuple(str(item) for item in fields_raw)
            )
    return ObservabilityCatalog(
        version=str(data.get("version", "1.0.0")),
        defaults=defaults,
        organizations=_load_options(data.get("organizations")),
        teams=tuple(teams),
        environments=_load_options(data.get("environments")),
        services=tuple(services),
        grafana_datasources=tuple(datasources),
        runbooks=tuple(runbooks),
        slo_targets=tuple(slo_options),
        notification_sources=tuple(sources),
        dashboard_packs=tuple(packs),
        form_presets=form_presets,
    )


def form_preset_for_blueprint(
    catalog: ObservabilityCatalog,
    blueprint_name: str,
) -> FormPreset | None:
    return catalog.form_presets.get(blueprint_name)


def catalog_has_field_options(catalog: ObservabilityCatalog) -> bool:
    return bool(catalog.organizations and catalog.teams and catalog.services)


def source_by_id(
    catalog: ObservabilityCatalog,
    source_id: str,
) -> NotificationSource | None:
    for source in catalog.notification_sources:
        if source.id == source_id:
            return source
    return None


def service_by_id(catalog: ObservabilityCatalog, service_id: str) -> CatalogService | None:
    for service in catalog.services:
        if service.id == service_id:
            return service
    return None


def teams_for_organization(
    catalog: ObservabilityCatalog,
    organization_id: str,
) -> tuple[CatalogTeam, ...]:
    return tuple(team for team in catalog.teams if team.organization == organization_id)


def target_ids_for_source(catalog: ObservabilityCatalog, source_id: str) -> set[str]:
    source = source_by_id(catalog, source_id)
    if source is None:
        return set()
    return {target.id for target in source.targets}


def dashboard_pack_by_id(catalog: ObservabilityCatalog, pack_id: str) -> DashboardPack | None:
    for pack in catalog.dashboard_packs:
        if pack.id == pack_id:
            return pack
    return None


def dashboard_packs_for_backend(
    catalog: ObservabilityCatalog,
    backend: str,
) -> tuple[DashboardPack, ...]:
    selected: list[DashboardPack] = []
    for pack in catalog.dashboard_packs:
        if pack.backend in ("any", backend):
            selected.append(pack)
    return tuple(selected)


def _options_payload(options: tuple[CatalogOption, ...]) -> list[dict[str, str]]:
    return [
        {"id": item.id, "label": item.label, "description": item.description} for item in options
    ]


def _dashboard_pack_payload(pack: DashboardPack) -> dict[str, Any]:
    return {
        "id": pack.id,
        "label": pack.label,
        "description": pack.description,
        "backend": pack.backend,
        "reference_url": pack.reference_url,
        "license": pack.license,
        "file_count": len(pack.files),
        "files": [{"source": item.source, "dest": item.dest} for item in pack.files],
    }


def catalog_for_api(
    catalog: ObservabilityCatalog,
    *,
    defaults: dict[str, str] | None = None,
    backend: str | None = None,
    blueprint_name: str | None = None,
) -> dict[str, Any]:
    merged = {**catalog.defaults, **(defaults or {})}
    if backend:
        merged.setdefault("backend", backend)
    preset = form_preset_for_blueprint(catalog, blueprint_name) if blueprint_name else None
    return {
        "version": catalog.version,
        "defaults": merged,
        "form_preset": (
            {"decision_fields": list(preset.decision_fields)} if preset is not None else None
        ),
        "organizations": _options_payload(catalog.organizations),
        "teams": [
            {
                "id": team.id,
                "label": team.label,
                "organization": team.organization,
                "description": team.description,
            }
            for team in catalog.teams
        ],
        "environments": _options_payload(catalog.environments),
        "services": [
            {
                "id": service.id,
                "label": service.label,
                "organization": service.organization,
                "team": service.team,
                "description": service.description,
                "runbook_url": service.runbook_url,
            }
            for service in catalog.services
        ],
        "grafana_datasources": [
            {"uid": item.uid, "label": item.label, "type": item.type}
            for item in catalog.grafana_datasources
        ],
        "runbooks": [
            {"id": item.id, "label": item.label, "url": item.url} for item in catalog.runbooks
        ],
        "slo_targets": [
            {"id": item.id, "label": item.label, "value": item.value}
            for item in catalog.slo_targets
        ],
        "notification_sources": [
            {
                "id": source.id,
                "label": source.label,
                "description": source.description,
                "provider": source.provider,
                "reference_url": source.reference_url,
                "targets": [
                    {
                        "id": target.id,
                        "label": target.label,
                        "description": target.description,
                    }
                    for target in source.targets
                ],
            }
            for source in catalog.notification_sources
        ],
        "dashboard_packs": [_dashboard_pack_payload(pack) for pack in catalog.dashboard_packs],
    }
