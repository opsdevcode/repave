from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from copier import run_copy
from jinja2 import Environment, FileSystemLoader, select_autoescape

from repave_engine.blueprint import Blueprint, _find_repo_root
from repave_engine.gates import is_gate_artifact_path


@dataclass(frozen=True)
class RenderResult:
    output_dir: Path
    values: dict[str, Any]


@dataclass(frozen=True)
class RenderedFile:
    path: str
    content: str
    truncated: bool = False


@dataclass(frozen=True)
class ScopedResource:
    service: str
    resource: str
    file_stem: str


def build_scoped_resources(scope_raw: Any) -> list[ScopedResource]:
    if scope_raw in (None, ""):
        return []
    scope = json.loads(scope_raw) if isinstance(scope_raw, str) else scope_raw
    if not isinstance(scope, dict):
        raise ValueError("provider_service_scope must decode to a JSON object")

    items: list[ScopedResource] = []
    for service, entry in sorted(scope.items()):
        if not isinstance(entry, dict):
            raise ValueError(f"provider_service_scope entry for {service!r} must be an object")
        for resource in sorted(entry.get("resources", [])):
            resource_name = str(resource).strip()
            if not resource_name:
                continue
            items.append(
                ScopedResource(
                    service=service,
                    resource=resource_name,
                    file_stem=f"{service}_{resource_name}",
                )
            )
    return items


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
        if is_gate_artifact_path(relative_path):
            continue
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

    scoped_resources = build_scoped_resources(values.get("provider_service_scope"))
    payload = {
        **values,
        "scoped_resources": [
            {
                "service": item.service,
                "resource": item.resource,
                "file_stem": item.file_stem,
            }
            for item in scoped_resources
        ],
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
    _write_scoped_resource_files(output_dir, blueprint, payload, scoped_resources)
    _copy_checkov_policies(output_dir, blueprint)

    return RenderResult(output_dir=output_dir, values=payload)


def _write_scoped_resource_files(
    output_dir: Path,
    blueprint: Blueprint,
    values: dict[str, Any],
    scoped_resources: list[ScopedResource],
) -> None:
    template_name = "resource.tf.jinja"
    partials_dir = blueprint.path / "partials"
    if not (partials_dir / template_name).exists() or not scoped_resources:
        return

    env = Environment(
        loader=FileSystemLoader(str(partials_dir)),
        autoescape=select_autoescape(enabled_extensions=()),
        keep_trailing_newline=True,
    )
    template = env.get_template(template_name)
    cloud_provider = str(values["cloud_provider"])

    for item in scoped_resources:
        content = template.render(
            service=item.service,
            resource=item.resource,
            file_stem=item.file_stem,
            cloud_provider=cloud_provider,
        )
        (output_dir / f"{item.file_stem}.tf").write_text(content, encoding="utf-8")


def _copy_checkov_policies(output_dir: Path, blueprint: Blueprint) -> None:
    if blueprint.checkov_policies is None:
        return

    repo_root = _find_repo_root(blueprint.path)
    source_dir = repo_root / blueprint.checkov_policies.policies_source
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Checkov policy pack not found: {source_dir}")

    destination = output_dir / blueprint.checkov_gate.external_checks_dir
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source_dir, destination)
