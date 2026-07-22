from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from copier import run_copy

from repave_engine.blueprint import Blueprint


@dataclass(frozen=True)
class RenderResult:
    output_dir: Path
    values: dict[str, Any]


def render_blueprint(
    blueprint: Blueprint,
    values: dict[str, Any],
    output_dir: Path,
    *,
    overwrite: bool = True,
) -> RenderResult:
    if blueprint.template_engine != "copier":
        raise ValueError(f"Unsupported template engine: {blueprint.template_engine}")

    template_dir = blueprint.template_dir
    if not template_dir.exists():
        raise FileNotFoundError(f"Template directory not found: {template_dir}")

    if output_dir.exists():
        if overwrite:
            shutil.rmtree(output_dir)
        else:
            raise FileExistsError(f"Output directory already exists: {output_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        **values,
        "_repave_blueprint_name": blueprint.name,
        "_repave_blueprint_version": blueprint.version,
        "_repave_standard_source": blueprint.standard_source,
        "_repave_standard_version": blueprint.standard_version,
    }

    run_copy(
        src_path=str(template_dir),
        dst_path=str(output_dir),
        data=payload,
        overwrite=True,
        defaults=True,
        unsafe=True,
    )

    return RenderResult(output_dir=output_dir, values=payload)
