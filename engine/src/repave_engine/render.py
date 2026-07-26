from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from copier import run_copy
from jinja2 import Environment, FileSystemLoader, select_autoescape

from repave_engine import __version__
from repave_engine.backstage_catalog import write_backstage_catalog_if_enabled
from repave_engine.blueprint import Blueprint, _find_repo_root
from repave_engine.gates import is_gate_artifact_path
from repave_engine.policy_selection import (
    PolicySelection,
    write_policy_selection_file,
)


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
    seen_stems: set[str] = set()
    for service, entry in sorted(scope.items()):
        if not isinstance(entry, dict):
            raise ValueError(f"provider_service_scope entry for {service!r} must be an object")
        for resource in sorted(entry.get("resources", [])):
            resource_name = str(resource).strip()
            if not resource_name:
                continue
            file_stem = f"{service}_{resource_name}"
            if file_stem in seen_stems:
                continue
            seen_stems.add(file_stem)
            items.append(
                ScopedResource(
                    service=service,
                    resource=resource_name,
                    file_stem=file_stem,
                )
            )
    return items


def collect_rendered_files(
    output_dir: Path,
    *,
    artifact_type: str = "terraform-module",
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
        if is_gate_artifact_path(relative_path, artifact_type=artifact_type):
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
        "_repave_engine_version": __version__,
    }

    run_copy(
        src_path=str(template_dir),
        dst_path=str(output_dir),
        data=payload,
        overwrite=True,
        defaults=True,
        unsafe=True,
    )
    write_backstage_catalog_if_enabled(output_dir, blueprint, payload)
    if blueprint.name == "dashboards-as-code-generic":
        backend = str(payload.get("backend", "grafana"))
        output_mode = str(payload.get("output_mode", "native"))
        _prune_dashboard_backend_outputs(output_dir, backend)
        from repave_engine.dashboard_pack import (
            materialize_dashboard_pack,
            write_dashboard_pack_terraform,
        )

        materialize_dashboard_pack(output_dir, _find_repo_root(blueprint.path), payload)
        mode = output_mode.strip().lower()
        if mode == "terraform":
            from repave_engine.observability_catalog import (
                dashboard_pack_by_id,
                load_observability_catalog,
            )

            pack_id = str(payload.get("dashboard_pack_source", "")).strip()
            catalog = load_observability_catalog(_find_repo_root(blueprint.path))
            pack = dashboard_pack_by_id(catalog, pack_id)
            if pack is not None and pack.files:
                for tf_name in ("dashboard.tf", "datadog_dashboard.tf"):
                    tf_path = output_dir / tf_name
                    if tf_path.is_file():
                        tf_path.unlink()
                write_dashboard_pack_terraform(output_dir, backend=backend)
            else:
                _prune_dashboard_terraform_starter_files(output_dir, backend=backend)
                pack_tf = output_dir / "dashboard_packs.tf"
                if pack_tf.is_file():
                    pack_tf.unlink()
    if blueprint.name == "observability-as-code-generic":
        _prune_observability_backend_outputs(
            output_dir,
            backend=str(payload.get("backend", "prometheus")),
            output_mode=str(payload.get("output_mode", "native")),
        )
    _write_scoped_resource_files(output_dir, blueprint, payload, scoped_resources)
    selection = payload.get("_policy_selection")
    policy_selection = selection if isinstance(selection, PolicySelection) else None
    if policy_selection is not None:
        write_policy_selection_file(output_dir, policy_selection)
    _copy_checkov_policies(output_dir, blueprint)
    if policy_selection is not None:
        _apply_checkov_skip_config(output_dir, blueprint, policy_selection.checkov_skip_checks)
    _copy_opa_policies(output_dir, blueprint, policy_selection)
    _copy_azure_policy_definitions(output_dir, blueprint, policy_selection)
    _copy_ansible_lint_pack(output_dir, blueprint)
    if blueprint.provenance_file:
        from repave_engine.provenance import write_provenance_file

        write_provenance_file(
            output_dir,
            blueprint,
            payload,
            filename=blueprint.provenance_file,
        )
        from repave_engine.provenance_readme import sync_readme_provenance_section

        sync_readme_provenance_section(output_dir, blueprint, payload)

        from repave_engine.ci_workflow import write_ci_workflow

        write_ci_workflow(output_dir, blueprint)
        _append_yamllint_workflow_ignore(output_dir)

    return RenderResult(output_dir=output_dir, values=payload)


def _append_yamllint_workflow_ignore(output_dir: Path) -> None:
    """GitHub Actions workflow YAML is validated in CI, not repo yamllint."""
    config = output_dir / ".yamllint"
    if not config.is_file():
        return
    text = config.read_text(encoding="utf-8")
    if ".github/workflows" in text:
        return
    block = "\nignore: |\n  .github/workflows/\n"
    config.write_text(text.rstrip() + block, encoding="utf-8")


def _prune_dashboard_backend_outputs(output_dir: Path, backend: str) -> None:
    """Keep only the selected dashboard backend directory (Grafana vs Datadog)."""
    normalized = backend.strip().lower()
    if normalized == "grafana":
        target = output_dir / "datadog"
    elif normalized == "datadog":
        target = output_dir / "grafana"
    else:
        return
    if target.is_dir():
        shutil.rmtree(target)


_OBSERVABILITY_TF_BY_BACKEND: dict[str, frozenset[str]] = {
    "datadog": frozenset({"monitors.tf"}),
    "grafana": frozenset({"dashboard.tf"}),
    "prometheus": frozenset({"prometheus_rules.tf", "alertmanager.tf"}),
    "otel": frozenset({"otel_collector.tf"}),
}
_OBSERVABILITY_TF_ROOT = frozenset(
    {"versions.tf", "variables.tf", "providers.tf", "dashboard_packs.tf"}
)
_ALL_OBSERVABILITY_TF = (
    frozenset(
        {
            "monitors.tf",
            "dashboard.tf",
            "prometheus_rules.tf",
            "alertmanager.tf",
            "otel_collector.tf",
            "dashboard_packs.tf",
        }
    )
    | _OBSERVABILITY_TF_ROOT
)


def _prune_observability_backend_outputs(
    output_dir: Path,
    *,
    backend: str,
    output_mode: str,
) -> None:
    """Keep native trees for the selected backend, or Terraform-only layout."""
    mode = output_mode.strip().lower()
    selected = backend.strip().lower()

    if mode == "terraform":
        for name in ("prometheus", "grafana", "datadog", "otel"):
            path = output_dir / name
            if path.is_dir():
                shutil.rmtree(path)
        keep = _OBSERVABILITY_TF_BY_BACKEND.get(selected, frozenset()) | _OBSERVABILITY_TF_ROOT
        for tf_name in _ALL_OBSERVABILITY_TF:
            if tf_name in keep:
                continue
            tf_path = output_dir / tf_name
            if tf_path.is_file():
                tf_path.unlink()
        return

    for tf_name in _ALL_OBSERVABILITY_TF:
        tf_path = output_dir / tf_name
        if tf_path.is_file():
            tf_path.unlink()

    backend_dirs = ("prometheus", "grafana", "datadog", "otel")
    for name in backend_dirs:
        if name == selected:
            continue
        path = output_dir / name
        if path.is_dir():
            shutil.rmtree(path)


def _prune_dashboard_terraform_starter_files(output_dir: Path, *, backend: str) -> None:
    """Drop copier starter TF when pack Terraform will be generated."""
    normalized = backend.strip().lower()
    if normalized == "grafana":
        for tf_name in ("datadog_dashboard.tf",):
            tf_path = output_dir / tf_name
            if tf_path.is_file():
                tf_path.unlink()
    elif normalized == "datadog":
        for tf_name in ("dashboard.tf",):
            tf_path = output_dir / tf_name
            if tf_path.is_file():
                tf_path.unlink()


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


def _apply_checkov_skip_config(
    output_dir: Path,
    blueprint: Blueprint,
    skip_checks: tuple[str, ...],
) -> None:
    if not skip_checks or blueprint.checkov_policies is None:
        return
    config_path = output_dir / blueprint.checkov_gate.config_file
    data: dict[str, Any] = {}
    if config_path.is_file():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    existing = data.get("skip-check", [])
    if not isinstance(existing, list):
        existing = []
    merged = sorted({str(item) for item in existing} | set(skip_checks))
    data["skip-check"] = merged
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _copy_named_files(source_dir: Path, destination: Path, filenames: tuple[str, ...]) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        src = source_dir / name
        if not src.is_file():
            raise FileNotFoundError(f"Policy file missing in pack: {src}")
        shutil.copy2(src, destination / name)


def _copy_opa_policies(
    output_dir: Path,
    blueprint: Blueprint,
    selection: PolicySelection | None,
) -> None:
    if blueprint.opa_policies is None:
        return

    repo_root = _find_repo_root(blueprint.path)
    source_dir = repo_root / blueprint.opa_policies.policies_source
    if not source_dir.is_dir():
        raise FileNotFoundError(f"OPA policy pack not found: {source_dir}")

    destination = output_dir / blueprint.opa_gate.policies_dir
    if destination.exists():
        shutil.rmtree(destination)
    if selection is not None and selection.opa_rego_files:
        _copy_named_files(source_dir, destination, selection.opa_rego_files)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, destination)


def _copy_azure_policy_definitions(
    output_dir: Path,
    blueprint: Blueprint,
    selection: PolicySelection | None,
) -> None:
    if blueprint.azure_policy_pack is None:
        return

    repo_root = _find_repo_root(blueprint.path)
    source_dir = repo_root / blueprint.azure_policy_pack.definitions_source
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Azure policy definitions not found: {source_dir}")

    destination = output_dir / blueprint.azure_policy_gate.definitions_dir
    if destination.exists():
        shutil.rmtree(destination)
    if selection is not None and selection.azure_definition_files:
        _copy_named_files(source_dir, destination, selection.azure_definition_files)
        return
    shutil.copytree(source_dir, destination)


def _copy_ansible_lint_pack(output_dir: Path, blueprint: Blueprint) -> None:
    if blueprint.ansible_lint_pack is None:
        return

    repo_root = _find_repo_root(blueprint.path)
    source_dir = repo_root / blueprint.ansible_lint_pack.pack_source
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Ansible lint pack not found: {source_dir}")

    for item in source_dir.iterdir():
        if not item.is_file():
            continue
        shutil.copy2(item, output_dir / item.name)
