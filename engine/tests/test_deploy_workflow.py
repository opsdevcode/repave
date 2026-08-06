from __future__ import annotations

import re
from pathlib import Path

import pytest

from repave_engine.blueprint import load_blueprint
from repave_engine.deploy_workflow import (
    deploy_pipeline_enabled,
    render_deploy_oidc_doc,
    render_deploy_workflow,
    validate_deploy_inputs,
)

_SHA = re.compile(r"[0-9a-f]{40}")
_USES = re.compile(r"uses:\s*([A-Za-z0-9._/-]+)@([^\s#]+)")


def test_deploy_pipeline_disabled_by_default() -> None:
    assert not deploy_pipeline_enabled({"enable_deploy_pipeline": "false"})
    assert not deploy_pipeline_enabled({})


def test_validate_deploy_inputs_requires_gitops_for_helm(repo_root: Path) -> None:
    blueprint = load_blueprint(repo_root / "blueprints" / "helm-chart-generic", repo_root=repo_root)
    with pytest.raises(ValueError, match="gitops_repo"):
        validate_deploy_inputs(
            blueprint,
            {
                "enable_deploy_pipeline": "true",
                "deploy_environment": "dev",
                "gitops_engine": "argocd",
            },
        )


def test_validate_deploy_inputs_requires_registry_for_app(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "app-service-generic", repo_root=repo_root
    )
    with pytest.raises(ValueError, match="container_registry"):
        validate_deploy_inputs(
            blueprint,
            {"enable_deploy_pipeline": "true", "deploy_environment": "dev"},
        )


def test_render_helm_deploy_workflow_pins_actions(repo_root: Path) -> None:
    blueprint = load_blueprint(repo_root / "blueprints" / "helm-chart-generic", repo_root=repo_root)
    payload = {
        "enable_deploy_pipeline": "true",
        "deploy_environment": "staging",
        "gitops_repo": "acme/gitops-staging-api",
        "gitops_manifest_path": "apps/release.yaml",
        "gitops_engine": "argocd",
        "chart_name": "api",
        "owner": "platform-engineering",
    }
    text = render_deploy_workflow(blueprint, payload)
    assert "promote-gitops" in text
    assert "acme/gitops-staging-api" in text
    assert "REPAVE_GITOPS_APP_TOKEN" in text
    assert "targetRevision" in text
    for repository, ref in _USES.findall(text):
        assert _SHA.fullmatch(ref), f"{repository}@{ref} must be a commit SHA pin"


def test_render_app_deploy_workflow_uses_oidc(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "app-service-generic", repo_root=repo_root
    )
    payload = {
        "enable_deploy_pipeline": "true",
        "deploy_environment": "dev",
        "container_registry": "ghcr.io/acme",
        "service_name": "checkout-api",
    }
    text = render_deploy_workflow(blueprint, payload)
    assert "id-token: write" in text
    assert "ghcr.io/acme/checkout-api" in text
    assert "docker/build-push-action" in text
    for repository, ref in _USES.findall(text):
        assert _SHA.fullmatch(ref), f"{repository}@{ref} must be a commit SHA pin"


def test_write_deploy_workflow_creates_files(
    repo_root: Path,
    output_config,
    staging_root,
    tmp_path: Path,
) -> None:
    from repave_engine.pipeline import generate_from_blueprint

    blueprint = load_blueprint(repo_root / "blueprints" / "helm-chart-generic", repo_root=repo_root)
    result = generate_from_blueprint(
        blueprint,
        {
            "chart_name": "api",
            "owner": "platform-engineering",
            "app_name": "api",
            "description": "HTTP API",
            "image_repository": "ghcr.io/acme/api",
            "enable_deploy_pipeline": "true",
            "deploy_environment": "dev",
            "gitops_repo": "acme/gitops-dev-api",
            "gitops_engine": "argocd",
        },
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )
    output_dir = result.render.output_dir
    deploy = output_dir / ".github" / "workflows" / "repave-deploy.yml"
    doc = output_dir / "docs" / "DEPLOY-OIDC.md"
    assert deploy.is_file()
    assert doc.is_file()
    assert "permissions:" in deploy.read_text(encoding="utf-8")
    oidc = render_deploy_oidc_doc(
        blueprint,
        {
            "enable_deploy_pipeline": "true",
            "deploy_environment": "dev",
            "gitops_repo": "acme/gitops-dev-api",
            "gitops_engine": "argocd",
            "chart_name": "api",
            "owner": "platform-engineering",
        },
    )
    assert "GitHub App" in oidc
