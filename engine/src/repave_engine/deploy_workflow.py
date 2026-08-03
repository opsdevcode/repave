"""GitHub Actions deploy workflow generation for app and Helm golden paths (v1.80)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from repave_engine.blueprint import Blueprint
from repave_engine.ci_action_pins import action_pins

_TEMPLATES = Path(__file__).resolve().parent / "templates" / "ci"

_DEPLOY_ARTIFACT_TYPES = frozenset({"app-service", "helm-chart"})


def deploy_pipeline_enabled(payload: dict[str, Any]) -> bool:
    return str(payload.get("enable_deploy_pipeline", "false")).strip().lower() == "true"


def _require(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise ValueError(f"enable_deploy_pipeline requires input {key!r}")
    return value


def validate_deploy_inputs(blueprint: Blueprint, payload: dict[str, Any]) -> None:
    if not deploy_pipeline_enabled(payload):
        return
    if blueprint.artifact_type not in _DEPLOY_ARTIFACT_TYPES:
        raise ValueError(
            f"deploy pipeline is not supported for artifact type {blueprint.artifact_type!r}"
        )
    _require(payload, "deploy_environment")
    if blueprint.artifact_type == "helm-chart":
        _require(payload, "gitops_repo")
        engine = _require(payload, "gitops_engine")
        if engine not in ("argocd", "flux"):
            raise ValueError("gitops_engine must be argocd or flux when deploy pipeline is enabled")
    if blueprint.artifact_type == "app-service":
        _require(payload, "container_registry")


def deploy_workflow_relpath() -> str:
    return ".github/workflows/repave-deploy.yml"


def _deploy_context(blueprint: Blueprint, payload: dict[str, Any]) -> dict[str, Any]:
    chart_name = str(payload.get("chart_name", "")).strip()
    service_name = str(payload.get("service_name", "")).strip() or chart_name
    manifest_path = str(payload.get("gitops_manifest_path", "apps/release.yaml")).strip()
    return {
        "deploy_environment": str(payload.get("deploy_environment", "dev")).strip(),
        "gitops_repo": str(payload.get("gitops_repo", "")).strip(),
        "gitops_manifest_path": manifest_path or "apps/release.yaml",
        "gitops_engine": str(payload.get("gitops_engine", "argocd")).strip(),
        "container_registry": str(payload.get("container_registry", "")).strip().rstrip("/"),
        "service_name": service_name,
        "chart_name": chart_name,
        "runtime": str(payload.get("runtime", "python")).strip(),
        "actions": action_pins(),
    }


def render_deploy_workflow(blueprint: Blueprint, payload: dict[str, Any]) -> str:
    validate_deploy_inputs(blueprint, payload)
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        autoescape=select_autoescape(default_for_string=False),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    if blueprint.artifact_type == "helm-chart":
        template = env.get_template("repave-deploy-helm.yml.jinja")
    elif blueprint.artifact_type == "app-service":
        template = env.get_template("repave-deploy-app.yml.jinja")
    else:
        raise ValueError(
            f"unsupported artifact type for deploy workflow: {blueprint.artifact_type}"
        )
    return template.render(**_deploy_context(blueprint, payload))


def render_deploy_oidc_doc(blueprint: Blueprint, payload: dict[str, Any]) -> str:
    validate_deploy_inputs(blueprint, payload)
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        autoescape=select_autoescape(default_for_string=False),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("deploy-oidc-trust.md.jinja")
    ctx = _deploy_context(blueprint, payload)
    ctx["artifact_type"] = blueprint.artifact_type
    return template.render(**ctx)


def write_deploy_workflow(
    output_dir: Path, blueprint: Blueprint, payload: dict[str, Any]
) -> Path | None:
    if not deploy_pipeline_enabled(payload):
        return None
    validate_deploy_inputs(blueprint, payload)
    target = output_dir / deploy_workflow_relpath()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_deploy_workflow(blueprint, payload), encoding="utf-8")
    doc_path = output_dir / "docs" / "DEPLOY-OIDC.md"
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(render_deploy_oidc_doc(blueprint, payload), encoding="utf-8")
    return target


__all__ = [
    "deploy_pipeline_enabled",
    "deploy_workflow_relpath",
    "render_deploy_oidc_doc",
    "render_deploy_workflow",
    "validate_deploy_inputs",
    "write_deploy_workflow",
]
