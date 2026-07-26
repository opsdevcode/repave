from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

POLICY_CATALOG_REL = Path("policy/catalog.json")

POLICY_CUSTOMIZABLE_ARTIFACTS = frozenset(
    {
        "terraform-module",
        "terraform-environment-stack",
        "opa-policy",
        "azure-policy",
        "checkov-policy",
    }
)


@dataclass(frozen=True)
class PolicyRule:
    id: str
    family: str
    title: str
    artifact_types: tuple[str, ...]
    required: bool
    removable: bool
    checkov_id: str | None = None
    rego_file: str | None = None
    definition_file: str | None = None


@dataclass(frozen=True)
class PolicyCatalog:
    version: str
    profiles: dict[str, dict[str, Any]]
    pack_sources: tuple[dict[str, str], ...]
    rules: tuple[PolicyRule, ...]


def load_policy_catalog(repo_root: Path) -> PolicyCatalog:
    path = repo_root / POLICY_CATALOG_REL
    if not path.is_file():
        raise FileNotFoundError(f"Policy catalog missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    rules: list[PolicyRule] = []
    for raw in data.get("rules", []):
        if not isinstance(raw, dict):
            continue
        rules.append(
            PolicyRule(
                id=str(raw["id"]),
                family=str(raw["family"]),
                title=str(raw.get("title", raw["id"])),
                artifact_types=tuple(str(item) for item in raw.get("artifact_types", [])),
                required=bool(raw.get("required", False)),
                removable=bool(raw.get("removable", True)),
                checkov_id=str(raw["checkov_id"]) if raw.get("checkov_id") else None,
                rego_file=str(raw["rego_file"]) if raw.get("rego_file") else None,
                definition_file=str(raw["definition_file"]) if raw.get("definition_file") else None,
            )
        )
    profiles = cast(dict[str, dict[str, Any]], data.get("profiles", {}))
    pack_sources: list[dict[str, str]] = []
    for item in data.get("pack_sources", []):
        if not isinstance(item, dict) or "id" not in item:
            continue
        entry: dict[str, str] = {"id": str(item["id"])}
        for key in ("label", "description", "default_profile", "reference_url"):
            if key in item and item[key] is not None:
                entry[key] = str(item[key])
        artifact_types = item.get("artifact_types")
        if isinstance(artifact_types, list):
            entry["artifact_types"] = ",".join(str(t) for t in artifact_types)
        pack_sources.append(entry)
    pack_sources_tuple = tuple(pack_sources)
    return PolicyCatalog(
        version=str(data.get("version", "1.0.0")),
        profiles=profiles,
        pack_sources=pack_sources_tuple,
        rules=tuple(rules),
    )


def rules_for_artifact(catalog: PolicyCatalog, artifact_type: str) -> tuple[PolicyRule, ...]:
    return tuple(rule for rule in catalog.rules if artifact_type in rule.artifact_types)


def pack_sources_for_artifact(
    catalog: PolicyCatalog,
    artifact_type: str,
) -> tuple[dict[str, str], ...]:
    selected: list[dict[str, str]] = []
    for pack in catalog.pack_sources:
        raw = pack.get("artifact_types", "").strip()
        if not raw:
            selected.append(pack)
            continue
        if artifact_type in {part.strip() for part in raw.split(",") if part.strip()}:
            selected.append(pack)
    return tuple(selected)


def _match_includes(pattern: str, rule_id: str, family: str) -> bool:
    if pattern == rule_id:
        return True
    if pattern.endswith(":*"):
        prefix = pattern[:-1]
        return rule_id.startswith(prefix)
    return fnmatch.fnmatch(rule_id, pattern)


def resolve_profile_rule_ids(
    catalog: PolicyCatalog,
    *,
    profile: str,
    artifact_type: str,
    custom_rules: tuple[str, ...] = (),
) -> set[str]:
    if profile not in catalog.profiles:
        raise ValueError(f"Unknown policy profile: {profile!r}")

    applicable = {rule.id: rule for rule in rules_for_artifact(catalog, artifact_type)}
    if profile == "custom":
        enabled = {rule_id for rule_id in custom_rules if rule_id in applicable}
        for rule_id, rule in applicable.items():
            if rule.required:
                enabled.add(rule_id)
        if not enabled:
            raise ValueError("policy_rules must include at least one rule when profile is custom")
        return enabled

    includes = catalog.profiles[profile].get("includes", [])
    if not isinstance(includes, list):
        includes = []
    resolved: set[str] = set()
    for rule_id, rule in applicable.items():
        for pattern in includes:
            if isinstance(pattern, str) and _match_includes(pattern, rule_id, rule.family):
                resolved.add(rule_id)
                break
    for rule_id, rule in applicable.items():
        if rule.required:
            resolved.add(rule_id)
    return resolved


def enabled_rule_ids_for_profile(
    catalog: PolicyCatalog,
    *,
    profile: str,
    artifact_type: str,
    custom_rules: tuple[str, ...] = (),
) -> set[str]:
    """Rule IDs checked on the blueprint form for the given profile."""
    try:
        return resolve_profile_rule_ids(
            catalog,
            profile=profile,
            artifact_type=artifact_type,
            custom_rules=custom_rules,
        )
    except ValueError:
        return {rule.id for rule in rules_for_artifact(catalog, artifact_type) if rule.required}


def catalog_for_api(
    catalog: PolicyCatalog,
    artifact_type: str,
    *,
    defaults: dict[str, str] | None = None,
) -> dict[str, Any]:
    rules = rules_for_artifact(catalog, artifact_type)
    packs = pack_sources_for_artifact(catalog, artifact_type)
    if not packs:
        packs = catalog.pack_sources
    return {
        "version": catalog.version,
        "defaults": defaults or {},
        "profiles": {
            key: {
                "label": value.get("label", key),
                "description": value.get("description", ""),
                "includes": list(value.get("includes", []))
                if isinstance(value.get("includes"), list)
                else [],
            }
            for key, value in catalog.profiles.items()
        },
        "pack_sources": list(packs),
        "rules": [
            {
                "id": rule.id,
                "family": rule.family,
                "title": rule.title,
                "required": rule.required,
                "removable": rule.removable,
            }
            for rule in rules
        ],
    }
