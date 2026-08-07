from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repave_engine.blueprint import Blueprint
from repave_engine.policy_catalog import (
    PolicyRule,
    load_policy_catalog,
    resolve_profile_rule_ids,
    rules_for_artifact,
)
from repave_engine.settings import GateOverrides

POLICY_SELECTION_FILENAME = ".repave/policy-selection.json"


@dataclass(frozen=True)
class PolicySelection:
    profile: str
    pack_source: str
    enabled_rules: tuple[str, ...]
    checkov_skip_checks: tuple[str, ...]
    opa_rego_files: tuple[str, ...]
    azure_definition_files: tuple[str, ...]
    pack_versions: dict[str, str]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "pack_source": self.pack_source,
            "enabled_rules": list(self.enabled_rules),
            "checkov_skip_checks": list(self.checkov_skip_checks),
            "opa_rego_files": list(self.opa_rego_files),
            "azure_definition_files": list(self.azure_definition_files),
            "pack_versions": dict(self.pack_versions),
        }


def blueprint_supports_policy_customization(blueprint: Blueprint) -> bool:
    if blueprint_policy_optional(blueprint):
        return False
    return any(field.name == "policy_profile" for field in blueprint.inputs)


def blueprint_policy_optional(blueprint: Blueprint) -> bool:
    return any(field.name == "enable_policy" for field in blueprint.inputs)


def blueprint_supports_optional_policy(blueprint: Blueprint) -> bool:
    return blueprint_policy_optional(blueprint) and any(
        field.name == "policy_profile" for field in blueprint.inputs
    )


def policy_pack_enabled(values: dict[str, Any]) -> bool:
    return str(values.get("enable_policy", "false")).strip().lower() == "true"


def policy_input_defaults(blueprint: Blueprint) -> dict[str, str]:
    """Blueprint-declared defaults for policy pack source and profile."""
    defaults = {
        "policy_pack_source": "repave-default",
        "policy_profile": "estate-default",
        "enable_policy": "false",
    }
    for field in blueprint.inputs:
        if field.name in defaults and field.default not in (None, ""):
            defaults[field.name] = str(field.default)
    return defaults


def _parse_custom_rules(raw: Any) -> tuple[str, ...]:
    if raw in (None, ""):
        return ()
    if isinstance(raw, str):
        parts = [part.strip() for part in raw.split(",") if part.strip()]
        return tuple(sorted(set(parts)))
    if isinstance(raw, list):
        return tuple(sorted({str(item).strip() for item in raw if str(item).strip()}))
    return ()


def normalize_policy_inputs(
    blueprint: Blueprint,
    normalized: dict[str, Any],
    repo_root: Path,
    *,
    gate_overrides: GateOverrides | None = None,
) -> PolicySelection | None:
    if not blueprint_supports_policy_customization(
        blueprint
    ) and not blueprint_supports_optional_policy(blueprint):
        return None

    if blueprint_policy_optional(blueprint) and not policy_pack_enabled(normalized):
        normalized["enable_policy"] = "false"
        normalized.pop("_policy_selection", None)
        return None

    if blueprint_policy_optional(blueprint):
        normalized["enable_policy"] = "true"

    catalog = load_policy_catalog(repo_root)
    profile = str(normalized.get("policy_profile", "estate-default")).strip()
    pack_source = str(normalized.get("policy_pack_source", "repave-default")).strip()
    custom_rules = _parse_custom_rules(normalized.get("policy_rules"))

    pack_ids = {entry["id"] for entry in catalog.pack_sources if "id" in entry}
    if pack_source not in pack_ids:
        allowed = ", ".join(sorted(pack_ids))
        raise ValueError(f"Invalid policy_pack_source {pack_source!r}. Allowed: {allowed}")

    enabled_ids = resolve_profile_rule_ids(
        catalog,
        profile=profile,
        artifact_type=blueprint.artifact_type,
        custom_rules=custom_rules,
    )
    applicable = {rule.id: rule for rule in rules_for_artifact(catalog, blueprint.artifact_type)}

    _validate_platform_skips(enabled_ids, applicable, gate_overrides)

    checkov_skips: list[str] = []
    opa_files: list[str] = []
    azure_files: list[str] = []
    for rule_id, rule in applicable.items():
        if rule_id in enabled_ids:
            if rule.family == "opa" and rule.rego_file:
                opa_files.append(rule.rego_file)
            if rule.family == "azure" and rule.definition_file:
                azure_files.append(rule.definition_file)
        elif rule.family == "checkov" and rule.checkov_id:
            checkov_skips.append(rule.checkov_id)

    pack_versions: dict[str, str] = {}
    if blueprint.checkov_policies is not None:
        pack_versions["checkov"] = blueprint.checkov_policies.policy_version
    if blueprint.opa_policies is not None:
        pack_versions["opa"] = blueprint.opa_policies.policy_version
    if blueprint.azure_policy_pack is not None:
        pack_versions["azure"] = blueprint.azure_policy_pack.policy_version

    selection = PolicySelection(
        profile=profile,
        pack_source=pack_source,
        enabled_rules=tuple(sorted(enabled_ids)),
        checkov_skip_checks=tuple(sorted(set(checkov_skips))),
        opa_rego_files=tuple(sorted(set(opa_files))),
        azure_definition_files=tuple(sorted(set(azure_files))),
        pack_versions=pack_versions,
    )
    normalized["policy_profile"] = profile
    normalized["policy_pack_source"] = pack_source
    normalized["policy_rules"] = ",".join(custom_rules) if custom_rules else ""
    normalized["_policy_selection"] = selection
    return selection


def _validate_platform_skips(
    enabled_ids: set[str],
    applicable: dict[str, PolicyRule],
    gate_overrides: GateOverrides | None,
) -> None:
    if gate_overrides is None:
        return
    for skip_id in gate_overrides.checkov_skip_checks:
        for rule in applicable.values():
            if rule.checkov_id == skip_id and rule.required:
                raise ValueError(
                    f"Platform skip_checks includes required rule {skip_id!r}; "
                    "remove it from repave.config.yaml gates.checkov.skip_checks"
                )
    for rule_id in gate_overrides.blocked_policy_rule_skips:
        if rule_id not in applicable:
            continue
        if rule_id not in enabled_ids:
            raise ValueError(
                f"Policy rule {rule_id!r} is required by platform gates.policy.required_rules"
            )


def write_policy_selection_file(output_dir: Path, selection: PolicySelection) -> Path:
    path = output_dir / POLICY_SELECTION_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(selection.to_json_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def load_policy_selection_file(output_dir: Path) -> PolicySelection | None:
    path = output_dir / POLICY_SELECTION_FILENAME
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return PolicySelection(
        profile=str(data.get("profile", "estate-default")),
        pack_source=str(data.get("pack_source", "repave-default")),
        enabled_rules=tuple(str(item) for item in data.get("enabled_rules", [])),
        checkov_skip_checks=tuple(str(item) for item in data.get("checkov_skip_checks", [])),
        opa_rego_files=tuple(str(item) for item in data.get("opa_rego_files", [])),
        azure_definition_files=tuple(str(item) for item in data.get("azure_definition_files", [])),
        pack_versions={str(k): str(v) for k, v in (data.get("pack_versions") or {}).items()},
    )


def policy_provenance_block(selection: PolicySelection | None) -> dict[str, Any] | None:
    if selection is None:
        return None
    return {
        "profile": selection.profile,
        "pack_source": selection.pack_source,
        "enabled_rules": list(selection.enabled_rules),
        "pack_versions": dict(selection.pack_versions),
    }


def diff_policy_provenance(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> tuple[str, ...]:
    notes: list[str] = []
    before = before or {}
    after = after or {}
    if before.get("profile") != after.get("profile"):
        notes.append(
            f"Policy profile: {before.get('profile', '(none)')} → {after.get('profile', '(none)')}"
        )
    before_rules = set(before.get("enabled_rules") or [])
    after_rules = set(after.get("enabled_rules") or [])
    added = sorted(after_rules - before_rules)
    removed = sorted(before_rules - after_rules)
    if added:
        notes.append(f"Policy rules enabled: {', '.join(added)}")
    if removed:
        notes.append(f"Policy rules disabled: {', '.join(removed)}")
    before_versions = before.get("pack_versions") or {}
    after_versions = after.get("pack_versions") or {}
    for key in sorted(set(before_versions) | set(after_versions)):
        if before_versions.get(key) != after_versions.get(key):
            notes.append(
                f"Policy pack {key}: {before_versions.get(key)!r} → {after_versions.get(key)!r}"
            )
    return tuple(notes)
