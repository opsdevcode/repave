from __future__ import annotations

from pathlib import Path
from typing import Any

from repave_engine.blueprint import Blueprint
from repave_engine.observability_catalog import (
    load_observability_catalog,
    source_by_id,
    target_ids_for_source,
)


def blueprint_supports_observability_notifications(blueprint: Blueprint) -> bool:
    return any(field.name == "notification_source" for field in blueprint.inputs)


def observability_input_defaults(blueprint: Blueprint, repo_root: Path) -> dict[str, str]:
    catalog = load_observability_catalog(repo_root)
    defaults = dict(catalog.defaults)
    for field in blueprint.inputs:
        if field.name in defaults and field.default not in (None, ""):
            defaults[field.name] = str(field.default)
    source_id = defaults.get("notification_source", "")
    source = source_by_id(catalog, source_id)
    if source and source.targets:
        target_default = defaults.get("notification_target", "")
        if target_default not in {t.id for t in source.targets}:
            defaults["notification_target"] = source.targets[0].id
    return defaults


def normalize_observability_inputs(
    blueprint: Blueprint,
    normalized: dict[str, Any],
    repo_root: Path,
) -> None:
    if not blueprint_supports_observability_notifications(blueprint):
        return

    catalog = load_observability_catalog(repo_root)
    form_defaults = observability_input_defaults(blueprint, repo_root)

    source_id = str(
        normalized.get("notification_source", form_defaults["notification_source"])
    ).strip()
    source = source_by_id(catalog, source_id)
    if source is None:
        allowed = ", ".join(item.id for item in catalog.notification_sources)
        raise ValueError(f"Invalid notification_source: {source_id!r}. Allowed values: {allowed}")
    normalized["notification_source"] = source_id

    target_id = str(
        normalized.get("notification_target", form_defaults["notification_target"])
    ).strip()
    allowed_targets = target_ids_for_source(catalog, source_id)
    if target_id not in allowed_targets:
        allowed = ", ".join(sorted(allowed_targets))
        raise ValueError(
            f"Invalid notification_target: {target_id!r} for source {source_id!r}. "
            f"Allowed values: {allowed}"
        )
    normalized["notification_target"] = target_id
