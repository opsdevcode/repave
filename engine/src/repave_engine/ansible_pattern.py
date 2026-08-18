from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, select_autoescape

from repave_engine.ansible_catalog import (
    AnsiblePattern,
    collection_sample_pattern_by_id,
    load_ansible_catalog,
    pattern_by_id,
    patterns_for_platforms,
    playbook_pattern_by_id,
    role_pattern_by_id,
)
from repave_engine.ansible_platforms import parse_support_flag
from repave_engine.blueprint import Blueprint
from repave_engine.safe_paths import confined_join, trusted_path

ANSIBLE_ROOT = Path("ansible")


def blueprint_supports_role_patterns(blueprint: Blueprint) -> bool:
    return any(field.name == "role_pattern_source" for field in blueprint.inputs)


def blueprint_supports_playbook_patterns(blueprint: Blueprint) -> bool:
    return any(field.name == "playbook_pattern_source" for field in blueprint.inputs)


def blueprint_supports_collection_sample_patterns(blueprint: Blueprint) -> bool:
    return any(field.name == "sample_role_pattern_source" for field in blueprint.inputs)


def _platform_flags(normalized: dict[str, Any]) -> tuple[bool, bool]:
    support_linux = parse_support_flag(normalized.get("support_linux"), default=True)
    support_windows = parse_support_flag(normalized.get("support_windows"), default=False)
    platforms = str(normalized.get("target_platforms", "")).strip()
    if platforms:
        parts = [part.strip() for part in platforms.split(",") if part.strip()]
        has_windows = any(part.startswith("Windows:") for part in parts)
        has_linux = any(not part.startswith("Windows:") for part in parts)
        if has_windows and not has_linux:
            return False, True
        if has_linux and not has_windows:
            return True, False
    return support_linux, support_windows


def resolve_default_role_pattern(
    *,
    support_linux: bool,
    support_windows: bool,
) -> str:
    if support_windows and not support_linux:
        return "windows-service"
    if support_linux:
        return "linux-service"
    return "repave-baseline"


def resolve_default_playbook_pattern(
    *,
    support_linux: bool,
    support_windows: bool,
) -> str:
    if support_windows and not support_linux:
        return "windows-update-baseline"
    if support_linux:
        return "linux-patch-baseline"
    return "repave-baseline"


def _normalize_pattern_source(
    *,
    field_name: str,
    patterns: tuple[AnsiblePattern, ...],
    default_resolver: Callable[..., str],
    support_linux: bool,
    support_windows: bool,
    normalized: dict[str, Any],
    collections_key: str,
    omit_docker_key: str | None,
) -> None:
    raw_pattern = str(normalized.get(field_name, "")).strip()
    if not raw_pattern:
        pattern_id = default_resolver(
            support_linux=support_linux,
            support_windows=support_windows,
        )
    else:
        pattern_id = raw_pattern

    pattern = pattern_by_id(patterns, pattern_id)
    if pattern is None:
        allowed = ", ".join(item.id for item in patterns)
        raise ValueError(f"Invalid {field_name}: {pattern_id!r}. Allowed values: {allowed}")

    allowed_patterns = patterns_for_platforms(
        patterns,
        support_linux=support_linux,
        support_windows=support_windows,
    )
    if pattern not in allowed_patterns:
        allowed = ", ".join(item.id for item in allowed_patterns)
        raise ValueError(
            f"Pattern {pattern_id!r} is not valid for selected platforms. "
            f"Allowed patterns: {allowed}"
        )

    normalized[field_name] = pattern_id
    normalized[collections_key] = list(pattern.requires_collections)
    if omit_docker_key is not None:
        normalized[omit_docker_key] = pattern.omit_docker_molecule


def normalize_role_pattern_inputs(
    blueprint: Blueprint,
    normalized: dict[str, Any],
    repo_root: Path,
) -> None:
    if not blueprint_supports_role_patterns(blueprint):
        return

    catalog = load_ansible_catalog(repo_root)
    support_linux, support_windows = _platform_flags(normalized)
    _normalize_pattern_source(
        field_name="role_pattern_source",
        patterns=catalog.role_patterns,
        default_resolver=resolve_default_role_pattern,
        support_linux=support_linux,
        support_windows=support_windows,
        normalized=normalized,
        collections_key="_role_pattern_requires_collections",
        omit_docker_key="_role_pattern_omit_docker_molecule",
    )


def normalize_playbook_pattern_inputs(
    blueprint: Blueprint,
    normalized: dict[str, Any],
    repo_root: Path,
) -> None:
    if not blueprint_supports_playbook_patterns(blueprint):
        return

    catalog = load_ansible_catalog(repo_root)
    support_linux, support_windows = _platform_flags(normalized)
    _normalize_pattern_source(
        field_name="playbook_pattern_source",
        patterns=catalog.playbook_patterns,
        default_resolver=resolve_default_playbook_pattern,
        support_linux=support_linux,
        support_windows=support_windows,
        normalized=normalized,
        collections_key="_playbook_pattern_requires_collections",
        omit_docker_key=None,
    )
    pattern_id = str(normalized.get("playbook_pattern_source", "")).strip()
    if pattern_id == "pinned-roles-rollout":
        pinned = normalized.get("pinned_roles")
        if not isinstance(pinned, list) or not pinned:
            raise ValueError(
                "Playbook pattern 'pinned-roles-rollout' requires at least one pinned Galaxy role"
            )


def _materialize_pattern(
    output_dir: Path,
    repo_root: Path,
    values: dict[str, Any],
    pattern: AnsiblePattern | None,
) -> None:
    if pattern is None or not pattern.files:
        return

    output_dir = trusted_path(output_dir)
    repo_root = trusted_path(repo_root)
    env = Environment(
        autoescape=select_autoescape(enabled_extensions=()),
        keep_trailing_newline=True,
    )
    pack_root = confined_join(repo_root, ANSIBLE_ROOT)
    for entry in pattern.files:
        source_path = confined_join(pack_root, entry.source)
        if not source_path.is_file():
            raise FileNotFoundError(f"Ansible pattern file missing: {source_path}")
        template = env.from_string(source_path.read_text(encoding="utf-8"))
        rendered = template.render(**values)
        dest_template = env.from_string(entry.dest)
        dest_rel = dest_template.render(**values)
        dest = confined_join(output_dir, dest_rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(rendered, encoding="utf-8")


def materialize_role_pattern(
    output_dir: Path,
    repo_root: Path,
    values: dict[str, Any],
) -> None:
    pattern_id = str(values.get("role_pattern_source", "linux-service")).strip()
    catalog = load_ansible_catalog(repo_root)
    pattern = role_pattern_by_id(catalog, pattern_id)
    _materialize_pattern(output_dir, repo_root, values, pattern)


def materialize_playbook_pattern(
    output_dir: Path,
    repo_root: Path,
    values: dict[str, Any],
) -> None:
    pattern_id = str(values.get("playbook_pattern_source", "linux-patch-baseline")).strip()
    catalog = load_ansible_catalog(repo_root)
    pattern = playbook_pattern_by_id(catalog, pattern_id)
    _materialize_pattern(output_dir, repo_root, values, pattern)


def write_ansible_requirements_yml(output_dir: Path, values: dict[str, Any]) -> None:
    raw = values.get("_role_pattern_requires_collections", [])
    collections: list[str] = []
    if isinstance(raw, list):
        collections = sorted({str(item).strip() for item in raw if str(item).strip()})
    lines = ["---", "collections:"]
    if collections:
        for name in collections:
            lines.append(f"  - name: {name}")
    else:
        lines[-1] = "collections: []"
    confined_join(trusted_path(output_dir), "requirements.yml").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def merge_playbook_requirements_collections(output_dir: Path, values: dict[str, Any]) -> None:
    raw = values.get("_playbook_pattern_requires_collections", [])
    collections: list[str] = []
    if isinstance(raw, list):
        collections = sorted({str(item).strip() for item in raw if str(item).strip()})
    if not collections:
        return
    path = confined_join(trusted_path(output_dir), "requirements.yml")
    if not path.is_file():
        return
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        data = {}
    existing_raw = data.get("collections")
    existing: list[str] = []
    if isinstance(existing_raw, list):
        for item in existing_raw:
            if isinstance(item, dict) and item.get("name"):
                existing.append(str(item["name"]).strip())
            elif isinstance(item, str) and item.strip():
                existing.append(item.strip())
    merged = sorted(set(existing) | set(collections))
    data["collections"] = [{"name": name} for name in merged]
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def finalize_role_pattern_layout(output_dir: Path, values: dict[str, Any]) -> None:
    omit_docker = bool(values.get("_role_pattern_omit_docker_molecule", False))
    if omit_docker:
        docker_molecule = confined_join(
            trusted_path(output_dir), "molecule", "default", "molecule.yml"
        )
        if docker_molecule.is_file():
            docker_molecule.unlink()


def _sample_role_name(values: dict[str, Any]) -> str:
    name = str(values.get("sample_role_name", "sample")).strip()
    return name or "sample"


def normalize_collection_sample_pattern_inputs(
    blueprint: Blueprint,
    normalized: dict[str, Any],
    repo_root: Path,
) -> None:
    if not blueprint_supports_collection_sample_patterns(blueprint):
        return

    sample_name = _sample_role_name(normalized)
    normalized["sample_role_name"] = sample_name
    normalized["role_name"] = sample_name

    catalog = load_ansible_catalog(repo_root)
    support_linux, support_windows = _platform_flags(normalized)
    _normalize_pattern_source(
        field_name="sample_role_pattern_source",
        patterns=catalog.collection_sample_patterns,
        default_resolver=resolve_default_role_pattern,
        support_linux=support_linux,
        support_windows=support_windows,
        normalized=normalized,
        collections_key="_collection_sample_requires_collections",
        omit_docker_key=None,
    )


def materialize_collection_sample_pattern(
    output_dir: Path,
    repo_root: Path,
    values: dict[str, Any],
) -> None:
    pattern_id = str(values.get("sample_role_pattern_source", "linux-service")).strip()
    catalog = load_ansible_catalog(repo_root)
    pattern = collection_sample_pattern_by_id(catalog, pattern_id)
    render_values = dict(values)
    render_values["role_name"] = _sample_role_name(values)
    render_values["sample_role_name"] = render_values["role_name"]
    _materialize_pattern(output_dir, repo_root, render_values, pattern)


def merge_collection_galaxy_dependencies(output_dir: Path, values: dict[str, Any]) -> None:
    raw = values.get("_collection_sample_requires_collections", [])
    collections: list[str] = []
    if isinstance(raw, list):
        collections = sorted({str(item).strip() for item in raw if str(item).strip()})
    if not collections:
        return
    path = confined_join(trusted_path(output_dir), "galaxy.yml")
    if not path.is_file():
        return
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        data = {}
    deps_raw = data.get("dependencies")
    deps: dict[str, str] = dict(deps_raw) if isinstance(deps_raw, dict) else {}
    for name in collections:
        deps.setdefault(name, ">=1.0.0")
    data["dependencies"] = deps
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def finalize_collection_sample_role_layout(output_dir: Path, values: dict[str, Any]) -> None:
    import shutil

    sample = _sample_role_name(values)
    output_dir = trusted_path(output_dir)
    placeholder = confined_join(output_dir, "roles", "sample")
    target = confined_join(output_dir, "roles", sample)
    if sample != "sample" and placeholder.is_dir() and placeholder != target:
        shutil.rmtree(placeholder)
