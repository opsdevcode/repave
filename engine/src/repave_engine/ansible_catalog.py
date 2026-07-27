from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ANSIBLE_CATALOG_REL = Path("ansible/catalog.json")


@dataclass(frozen=True)
class AnsiblePatternFile:
    source: str
    dest: str


@dataclass(frozen=True)
class AnsiblePattern:
    id: str
    label: str
    description: str
    platform: str
    files: tuple[AnsiblePatternFile, ...]
    requires_collections: tuple[str, ...]
    omit_docker_molecule: bool = False


# Back-compat aliases for role-specific call sites
RolePatternFile = AnsiblePatternFile
RolePattern = AnsiblePattern


@dataclass(frozen=True)
class FormPreset:
    decision_fields: tuple[str, ...]


@dataclass(frozen=True)
class AnsibleCatalog:
    version: str
    defaults: dict[str, str]
    role_patterns: tuple[AnsiblePattern, ...]
    playbook_patterns: tuple[AnsiblePattern, ...]
    form_presets: dict[str, FormPreset]


def _parse_pattern_list(raw_list: object) -> tuple[AnsiblePattern, ...]:
    if not isinstance(raw_list, list):
        return ()
    patterns: list[AnsiblePattern] = []
    for raw in raw_list:
        if not isinstance(raw, dict) or "id" not in raw:
            continue
        files: list[AnsiblePatternFile] = []
        for entry in raw.get("files", []):
            if not isinstance(entry, dict):
                continue
            files.append(
                AnsiblePatternFile(
                    source=str(entry["source"]),
                    dest=str(entry["dest"]),
                )
            )
        collections_raw = raw.get("requires_collections", [])
        collections: list[str] = []
        if isinstance(collections_raw, list):
            collections = [str(item).strip() for item in collections_raw if str(item).strip()]
        patterns.append(
            AnsiblePattern(
                id=str(raw["id"]),
                label=str(raw.get("label", raw["id"])),
                description=str(raw.get("description", "")),
                platform=str(raw.get("platform", "any")).strip().lower(),
                files=tuple(files),
                requires_collections=tuple(collections),
                omit_docker_molecule=bool(raw.get("omit_docker_molecule", False)),
            )
        )
    return tuple(patterns)


def load_ansible_catalog(repo_root: Path) -> AnsibleCatalog:
    path = repo_root / ANSIBLE_CATALOG_REL
    if not path.is_file():
        raise FileNotFoundError(f"Ansible catalog missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    defaults_raw = data.get("defaults", {})
    defaults = (
        {str(k): str(v) for k, v in defaults_raw.items()} if isinstance(defaults_raw, dict) else {}
    )

    form_presets: dict[str, FormPreset] = {}
    raw_presets = data.get("form_presets", {})
    if isinstance(raw_presets, dict):
        for blueprint_name, preset_raw in raw_presets.items():
            if not isinstance(preset_raw, dict):
                continue
            fields_raw = preset_raw.get("decision_fields", [])
            fields = tuple(str(item) for item in fields_raw if str(item).strip())
            form_presets[str(blueprint_name)] = FormPreset(decision_fields=fields)

    return AnsibleCatalog(
        version=str(data.get("version", "0")),
        defaults=defaults,
        role_patterns=_parse_pattern_list(data.get("role_patterns", [])),
        playbook_patterns=_parse_pattern_list(data.get("playbook_patterns", [])),
        form_presets=form_presets,
    )


def pattern_by_id(patterns: tuple[AnsiblePattern, ...], pattern_id: str) -> AnsiblePattern | None:
    for pattern in patterns:
        if pattern.id == pattern_id:
            return pattern
    return None


def role_pattern_by_id(catalog: AnsibleCatalog, pattern_id: str) -> AnsiblePattern | None:
    return pattern_by_id(catalog.role_patterns, pattern_id)


def playbook_pattern_by_id(catalog: AnsibleCatalog, pattern_id: str) -> AnsiblePattern | None:
    return pattern_by_id(catalog.playbook_patterns, pattern_id)


def patterns_for_platforms(
    patterns: tuple[AnsiblePattern, ...],
    *,
    support_linux: bool,
    support_windows: bool,
) -> tuple[AnsiblePattern, ...]:
    items: list[AnsiblePattern] = []
    for pattern in patterns:
        if pattern.platform == "any":
            items.append(pattern)
            continue
        if pattern.platform == "linux" and support_linux:
            items.append(pattern)
            continue
        if pattern.platform == "windows" and support_windows:
            items.append(pattern)
    return tuple(items)


def role_patterns_for_platforms(
    catalog: AnsibleCatalog,
    *,
    support_linux: bool,
    support_windows: bool,
) -> tuple[AnsiblePattern, ...]:
    return patterns_for_platforms(
        catalog.role_patterns,
        support_linux=support_linux,
        support_windows=support_windows,
    )


def playbook_patterns_for_platforms(
    catalog: AnsibleCatalog,
    *,
    support_linux: bool,
    support_windows: bool,
) -> tuple[AnsiblePattern, ...]:
    return patterns_for_platforms(
        catalog.playbook_patterns,
        support_linux=support_linux,
        support_windows=support_windows,
    )


def form_preset_for_blueprint(catalog: AnsibleCatalog, blueprint_name: str) -> FormPreset | None:
    return catalog.form_presets.get(blueprint_name)


def _pattern_payload(pattern: AnsiblePattern) -> dict[str, Any]:
    return {
        "id": pattern.id,
        "label": pattern.label,
        "description": pattern.description,
        "platform": pattern.platform,
        "requires_collections": list(pattern.requires_collections),
    }


def catalog_for_api(
    catalog: AnsibleCatalog,
    *,
    defaults: dict[str, str] | None = None,
    support_linux: bool = True,
    support_windows: bool = False,
    blueprint_name: str | None = None,
) -> dict[str, Any]:
    preset = form_preset_for_blueprint(catalog, blueprint_name) if blueprint_name else None
    payload: dict[str, Any] = {
        "version": catalog.version,
        "defaults": defaults or dict(catalog.defaults),
        "form_preset": (
            {"decision_fields": list(preset.decision_fields)} if preset is not None else None
        ),
        "role_patterns": [],
        "playbook_patterns": [],
    }
    if blueprint_name == "ansible-role-generic":
        role_items = role_patterns_for_platforms(
            catalog,
            support_linux=support_linux,
            support_windows=support_windows,
        )
        payload["role_patterns"] = [_pattern_payload(item) for item in role_items]
    elif blueprint_name == "ansible-playbook-project":
        playbook_items = playbook_patterns_for_platforms(
            catalog,
            support_linux=support_linux,
            support_windows=support_windows,
        )
        payload["playbook_patterns"] = [_pattern_payload(item) for item in playbook_items]
    return payload


ansible_catalog_for_api = catalog_for_api
