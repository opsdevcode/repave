from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, select_autoescape

from repave_engine.blueprint import Blueprint
from repave_engine.observability_catalog import (
    load_observability_catalog,
    monitor_pack_by_id,
    monitor_packs_for_backend,
)
from repave_engine.safe_paths import confined_join, trusted_path

OBSERVABILITY_ROOT = Path("observability")


def blueprint_supports_monitor_packs(blueprint: Blueprint) -> bool:
    return any(field.name == "monitor_pack_source" for field in blueprint.inputs)


def normalize_monitor_pack_inputs(
    blueprint: Blueprint,
    normalized: dict[str, Any],
    repo_root: Path,
) -> None:
    if not blueprint_supports_monitor_packs(blueprint):
        return

    catalog = load_observability_catalog(repo_root)
    backend = str(normalized.get("backend", "datadog")).strip()
    pack_id = str(
        normalized.get(
            "monitor_pack_source",
            catalog.defaults.get("monitor_pack_source", "repave-red-starter"),
        )
    ).strip()
    pack = monitor_pack_by_id(catalog, pack_id)
    if pack is None:
        allowed = ", ".join(item.id for item in catalog.monitor_packs)
        raise ValueError(f"Invalid monitor_pack_source: {pack_id!r}. Allowed values: {allowed}")
    if pack.backend not in ("any", backend):
        allowed = ", ".join(item.id for item in monitor_packs_for_backend(catalog, backend))
        raise ValueError(
            f"Monitor pack {pack_id!r} is not valid for backend {backend!r}. "
            f"Allowed packs: {allowed}"
        )
    normalized["monitor_pack_source"] = pack_id


def materialize_monitor_pack(
    output_dir: Path,
    repo_root: Path,
    values: dict[str, Any],
) -> None:
    pack_id = str(values.get("monitor_pack_source", "repave-red-starter")).strip()
    catalog = load_observability_catalog(repo_root)
    pack = monitor_pack_by_id(catalog, pack_id)
    if pack is None or not pack.files:
        return

    output_dir = trusted_path(output_dir)
    repo_root = trusted_path(repo_root)
    env = Environment(
        autoescape=select_autoescape(enabled_extensions=()),
        keep_trailing_newline=True,
    )
    pack_root = confined_join(repo_root, OBSERVABILITY_ROOT)
    for entry in pack.files:
        source_path = confined_join(pack_root, entry.source)
        if not source_path.is_file():
            raise FileNotFoundError(f"Monitor pack file missing: {source_path}")
        template = env.from_string(source_path.read_text(encoding="utf-8"))
        rendered = template.render(**values)
        dest = confined_join(output_dir, entry.dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(rendered, encoding="utf-8")


def write_monitor_pack_terraform(output_dir: Path, *, backend: str) -> None:
    from repave_engine.monitor_pack_terraform import write_monitor_pack_terraform as _write

    _write(output_dir, backend=backend)
