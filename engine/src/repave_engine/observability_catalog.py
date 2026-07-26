from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

OBSERVABILITY_CATALOG_REL = Path("observability/catalog.json")


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
class ObservabilityCatalog:
    version: str
    defaults: dict[str, str]
    notification_sources: tuple[NotificationSource, ...]


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
    defaults_raw = data.get("defaults", {})
    defaults: dict[str, str] = {}
    if isinstance(defaults_raw, dict):
        for key in ("notification_source", "notification_target"):
            if key in defaults_raw and defaults_raw[key] is not None:
                defaults[key] = str(defaults_raw[key])
    return ObservabilityCatalog(
        version=str(data.get("version", "1.0.0")),
        defaults=defaults,
        notification_sources=tuple(sources),
    )


def source_by_id(
    catalog: ObservabilityCatalog,
    source_id: str,
) -> NotificationSource | None:
    for source in catalog.notification_sources:
        if source.id == source_id:
            return source
    return None


def target_ids_for_source(catalog: ObservabilityCatalog, source_id: str) -> set[str]:
    source = source_by_id(catalog, source_id)
    if source is None:
        return set()
    return {target.id for target in source.targets}


def catalog_for_api(
    catalog: ObservabilityCatalog,
    *,
    defaults: dict[str, str] | None = None,
) -> dict[str, Any]:
    merged = {**catalog.defaults, **(defaults or {})}
    return {
        "version": catalog.version,
        "defaults": merged,
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
    }
