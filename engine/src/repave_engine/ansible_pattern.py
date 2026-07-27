from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, select_autoescape

from repave_engine.ansible_catalog import (
    load_ansible_catalog,
    role_pattern_by_id,
    role_patterns_for_platforms,
)
from repave_engine.ansible_platforms import parse_support_flag
from repave_engine.blueprint import Blueprint

ANSIBLE_ROOT = Path("ansible")


def blueprint_supports_role_patterns(blueprint: Blueprint) -> bool:
    return any(field.name == "role_pattern_source" for field in blueprint.inputs)


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


def normalize_role_pattern_inputs(
    blueprint: Blueprint,
    normalized: dict[str, Any],
    repo_root: Path,
) -> None:
    if not blueprint_supports_role_patterns(blueprint):
        return

    catalog = load_ansible_catalog(repo_root)
    support_linux, support_windows = _platform_flags(normalized)
    raw_pattern = str(normalized.get("role_pattern_source", "")).strip()
    if not raw_pattern:
        pattern_id = resolve_default_role_pattern(
            support_linux=support_linux,
            support_windows=support_windows,
        )
    else:
        pattern_id = raw_pattern

    pattern = role_pattern_by_id(catalog, pattern_id)
    if pattern is None:
        allowed = ", ".join(item.id for item in catalog.role_patterns)
        raise ValueError(f"Invalid role_pattern_source: {pattern_id!r}. Allowed values: {allowed}")

    allowed_patterns = role_patterns_for_platforms(
        catalog,
        support_linux=support_linux,
        support_windows=support_windows,
    )
    if pattern not in allowed_patterns:
        allowed = ", ".join(item.id for item in allowed_patterns)
        raise ValueError(
            f"Role pattern {pattern_id!r} is not valid for selected platforms. "
            f"Allowed patterns: {allowed}"
        )

    normalized["role_pattern_source"] = pattern_id
    normalized["_role_pattern_requires_collections"] = list(pattern.requires_collections)
    normalized["_role_pattern_omit_docker_molecule"] = pattern.omit_docker_molecule


def materialize_role_pattern(
    output_dir: Path,
    repo_root: Path,
    values: dict[str, Any],
) -> None:
    pattern_id = str(values.get("role_pattern_source", "linux-service")).strip()
    catalog = load_ansible_catalog(repo_root)
    pattern = role_pattern_by_id(catalog, pattern_id)
    if pattern is None or not pattern.files:
        return

    env = Environment(
        autoescape=select_autoescape(enabled_extensions=()),
        keep_trailing_newline=True,
    )
    pack_root = repo_root / ANSIBLE_ROOT
    for entry in pattern.files:
        source_path = pack_root / entry.source
        if not source_path.is_file():
            raise FileNotFoundError(f"Role pattern file missing: {source_path}")
        template = env.from_string(source_path.read_text(encoding="utf-8"))
        rendered = template.render(**values)
        dest_template = env.from_string(entry.dest)
        dest_rel = dest_template.render(**values)
        dest = output_dir / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(rendered, encoding="utf-8")


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
    (output_dir / "requirements.yml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def finalize_role_pattern_layout(output_dir: Path, values: dict[str, Any]) -> None:
    omit_docker = bool(values.get("_role_pattern_omit_docker_molecule", False))
    if omit_docker:
        docker_molecule = output_dir / "molecule" / "default" / "molecule.yml"
        if docker_molecule.is_file():
            docker_molecule.unlink()
