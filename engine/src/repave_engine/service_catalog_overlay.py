"""Enrich CatalogEntity with ownership, dependencies, maturity, and initiatives."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from repave_engine.entity_catalog import CATALOG_FILENAME, CatalogEntity
from repave_engine.initiatives import (
    Initiative,
    InitiativeEntityStatus,
    evaluate_initiative_for_entity,
    read_initiatives,
)
from repave_engine.maturity_rubric import MaturityRubric, evaluate_maturity, load_maturity_rubric
from repave_engine.settings import ServiceCatalogConfig
from repave_engine.yaml_util import load_yaml_mapping_soft


def team_slug_from_owner(owner: str, *, default_team: str = "platform") -> str:
    text = owner.strip()
    if not text:
        return default_team.strip() or "platform"
    lowered = text.lower()
    for prefix in ("group:", "team:", "user:"):
        if lowered.startswith(prefix):
            rest = text[len(prefix) :].strip()
            if "/" in rest:
                rest = rest.rsplit("/", 1)[-1]
            slug = re.sub(r"[^a-z0-9._-]+", "-", rest.lower()).strip("-")
            return slug or default_team
    if "@" in text:
        local = text.split("@", 1)[0]
        slug = re.sub(r"[^a-z0-9._-]+", "-", local.lower()).strip("-")
        return slug or default_team
    slug = re.sub(r"[^a-z0-9._-]+", "-", lowered).strip("-")
    return slug or default_team


def _parse_depends_on(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        item = raw.strip()
        return (item,) if item else ()
    if not isinstance(raw, list):
        return ()
    out: list[str] = []
    for entry in raw:
        if isinstance(entry, str) and entry.strip():
            out.append(entry.strip())
        elif isinstance(entry, dict):
            name = str(entry.get("name", "")).strip()
            if name:
                out.append(name)
    return tuple(out)


def extract_catalog_overlay_fields(repo_dir: Path | None) -> dict[str, Any]:
    """Read on-call and dependsOn from local catalog-info.yaml / repave.yaml."""
    if repo_dir is None or not repo_dir.is_dir():
        return {"oncall": "", "dependencies": (), "workload_profile": ""}
    oncall = ""
    dependencies: tuple[str, ...] = ()
    workload_profile = ""
    catalog = load_yaml_mapping_soft(repo_dir / CATALOG_FILENAME)
    if catalog is not None:
        metadata = catalog.get("metadata")
        if isinstance(metadata, dict):
            annotations = metadata.get("annotations")
            if isinstance(annotations, dict):
                oncall = str(annotations.get("repave.dev/oncall", "")).strip()
                if not workload_profile:
                    workload_profile = str(
                        annotations.get("repave.dev/workload-profile", "")
                    ).strip()
        spec = catalog.get("spec")
        if isinstance(spec, dict):
            dependencies = _parse_depends_on(spec.get("dependsOn"))
    repave = load_yaml_mapping_soft(repo_dir / "repave.yaml")
    if repave is not None:
        spec = repave.get("spec")
        if isinstance(spec, dict):
            if not oncall:
                oncall = str(spec.get("oncall", "")).strip()
            inputs = spec.get("inputs")
            if isinstance(inputs, dict) and not workload_profile:
                workload_profile = str(inputs.get("workload_profile", "")).strip()
            if not dependencies:
                dependencies = _parse_depends_on(spec.get("dependsOn"))
    return {
        "oncall": oncall,
        "dependencies": dependencies,
        "workload_profile": workload_profile,
    }


def enrich_entity_with_overlay(
    entity: CatalogEntity,
    *,
    config: ServiceCatalogConfig,
    rubric: MaturityRubric,
    initiatives: tuple[Initiative, ...] = (),
) -> CatalogEntity:
    fields = extract_catalog_overlay_fields(entity.local_path)
    oncall = fields["oncall"] or entity.oncall
    dependencies = fields["dependencies"] or entity.dependencies
    workload_profile = fields["workload_profile"] or entity.workload_profile
    team_slug = team_slug_from_owner(entity.owner, default_team=config.default_team)
    patched = replace(
        entity,
        oncall=oncall,
        team_slug=team_slug,
        dependencies=dependencies,
        workload_profile=workload_profile,
    )
    maturity = evaluate_maturity(patched, rubric)
    active = [item for item in initiatives if item.active]
    statuses = [
        evaluate_initiative_for_entity(item, patched, maturity=maturity, rubric=rubric)
        for item in active
    ]
    badges = tuple(status.title for status in statuses if not status.passed) + tuple(
        status.title for status in statuses if status.passed
    )
    # Prefer failing initiatives first, then passing — cap for library chips.
    unique_badges: list[str] = []
    for title in badges:
        if title not in unique_badges:
            unique_badges.append(title)
        if len(unique_badges) >= 4:
            break
    return replace(
        patched,
        maturity_level=maturity.level,
        maturity_label=maturity.label,
        maturity_passing=maturity.passing,
        maturity_total=maturity.total,
        initiative_badges=tuple(unique_badges),
    )


def enrich_catalog_entities_with_overlay(
    entities: list[CatalogEntity],
    config: ServiceCatalogConfig | None,
) -> list[CatalogEntity]:
    if config is None or not config.enabled:
        return entities
    rubric = load_maturity_rubric(config.maturity_rubric)
    initiatives = read_initiatives(config.initiatives) if config.initiatives else ()
    return [
        enrich_entity_with_overlay(
            entity,
            config=config,
            rubric=rubric,
            initiatives=initiatives,
        )
        for entity in entities
    ]


def filter_entities_for_user(
    entities: list[CatalogEntity],
    *,
    email: str = "",
    owner_filter: str = "",
    default_team: str = "platform",
) -> list[CatalogEntity]:
    """Select services for the developer hub."""
    if owner_filter.strip():
        needle = owner_filter.strip().lower()
        return [
            item
            for item in entities
            if needle in item.owner.lower()
            or needle == item.team_slug.lower()
            or needle in team_slug_from_owner(item.owner, default_team=default_team)
        ]
    if not email.strip():
        # Auth off: prefer default team, else all entities.
        team = default_team.strip().lower()
        matched = [
            item
            for item in entities
            if team in item.owner.lower() or item.team_slug.lower() == team
        ]
        return matched or list(entities)
    email_l = email.strip().lower()
    local = email_l.split("@", 1)[0]
    return [
        item
        for item in entities
        if email_l in item.owner.lower()
        or local in item.owner.lower()
        or local == item.team_slug.lower()
    ]


def filter_entities_by_team(
    entities: list[CatalogEntity],
    team_slug: str,
    *,
    default_team: str = "platform",
) -> list[CatalogEntity]:
    needle = team_slug.strip().lower()
    if not needle:
        return list(entities)
    return [
        item
        for item in entities
        if item.team_slug.lower() == needle
        or needle in item.owner.lower()
        or team_slug_from_owner(item.owner, default_team=default_team) == needle
    ]


def entity_initiative_statuses(
    entity: CatalogEntity,
    config: ServiceCatalogConfig | None,
) -> list[InitiativeEntityStatus]:
    if config is None or not config.enabled:
        return []
    rubric = load_maturity_rubric(config.maturity_rubric)
    initiatives = read_initiatives(config.initiatives) if config.initiatives else ()
    maturity = evaluate_maturity(entity, rubric)
    return [
        evaluate_initiative_for_entity(item, entity, maturity=maturity, rubric=rubric)
        for item in initiatives
        if item.active
    ]


def maturity_distribution(entities: list[CatalogEntity]) -> dict[str, Any]:
    counts: dict[int, int] = {}
    for entity in entities:
        counts[entity.maturity_level] = counts.get(entity.maturity_level, 0) + 1
    return {
        "entity_count": len(entities),
        "by_level": [
            {"level": level, "count": counts.get(level, 0)} for level in sorted(counts.keys())
        ],
        "average_level": (
            sum(entity.maturity_level for entity in entities) / len(entities) if entities else 0.0
        ),
    }
