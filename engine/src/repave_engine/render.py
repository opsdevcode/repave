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


@dataclass(frozen=True)
class RenderedFile:
    path: str
    content: str
    truncated: bool = False


def collect_rendered_files(
    output_dir: Path,
    *,
    max_files: int = 100,
    max_bytes: int = 32_768,
) -> tuple[RenderedFile, ...]:
    if not output_dir.exists():
        return ()

    files: list[RenderedFile] = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file():
            continue
        if len(files) >= max_files:
            break

        relative_path = path.relative_to(output_dir).as_posix()
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\0" in raw[:8192]:
            continue

        truncated = len(raw) > max_bytes
        content = raw[:max_bytes].decode("utf-8", errors="replace")
        files.append(RenderedFile(path=relative_path, content=content, truncated=truncated))

    return tuple(files)


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
