"""Shared JSON read models for estate and governance portal surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from repave_engine.audit_history import AuditHistoryEntry
from repave_engine.blueprint import blueprint_dir, load_blueprint
from repave_engine.estate_map import build_estate_tiles
from repave_engine.governance_annotations import build_governance_previews
from repave_engine.policy_catalog import enabled_rule_ids_for_profile, load_policy_catalog
from repave_engine.policy_selection import policy_input_defaults
from repave_engine.portal_context import (
    audit_portal_enabled,
    portal_fleet_context,
    portal_recent_activity,
)
from repave_engine.standards_diff import catalog_pin_diffs_for_blueprint, standards_diff_for_pin


class FleetRegistryUnavailableError(ValueError):
    """Fleet registry is not configured."""


def build_estate_read_model(repo_root: Path) -> dict[str, Any]:
    """Fleet estate tiles with optional audit sparklines."""
    enabled, fleet_repos, _namespace = portal_fleet_context(repo_root)
    if not enabled:
        raise FleetRegistryUnavailableError(
            "Fleet registry is not configured (set fleet.file or REPAVE_FLEET_FILE)"
        )
    audit_entries: tuple[AuditHistoryEntry, ...] = ()
    if audit_portal_enabled(repo_root):
        audit_entries = portal_recent_activity(repo_root, limit=80)
    tiles = build_estate_tiles(fleet_repos, audit_entries=audit_entries)
    return {
        "count": len(tiles),
        "tiles": [tile.to_public_dict() for tile in tiles],
    }


def build_governance_annotations_read_model(
    repo_root: Path,
    blueprint_name: str,
) -> dict[str, Any]:
    """Governance annotation previews for a blueprint form preflight."""
    blueprint = load_blueprint(blueprint_dir(repo_root, blueprint_name), repo_root=repo_root)
    standards = standards_diff_for_pin(
        repo_root,
        standard_source=blueprint.standard_source,
        pinned_version=blueprint.standard_version,
    )
    try:
        catalog = load_policy_catalog(repo_root)
    except FileNotFoundError:
        catalog = None
    policy_defaults = policy_input_defaults(blueprint)
    profile = policy_defaults.get("policy_profile", "estate-default")
    enabled_ids = (
        enabled_rule_ids_for_profile(
            catalog,
            profile=profile,
            artifact_type=blueprint.artifact_type,
        )
        if catalog is not None
        else frozenset()
    )
    policy_rules = (
        tuple(rule for rule in catalog.rules if rule.id in enabled_ids)
        if catalog is not None
        else ()
    )
    previews = build_governance_previews(repo_root, standards, policy_rules)
    pin_diffs = catalog_pin_diffs_for_blueprint(repo_root, blueprint)
    return {
        "blueprint": blueprint_name,
        "standard": standards.standard_source,
        "pinned_version": standards.pinned_version,
        "previews": [item.to_public_dict() for item in previews],
        "pin_diffs": [
            {
                "kind": item.kind,
                "label": item.label,
                "available": item.result.available,
                "has_changes": item.has_changes,
                "pinned_version": item.result.pinned_version,
                "source": item.result.standard_source,
                "changed_files": len(item.result.files),
                "reason": item.result.reason,
            }
            for item in pin_diffs
        ],
    }
