from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from repave_engine.blueprint import artifact_family, load_blueprint, validate_inputs
from repave_engine.governance import missing_governance_gates
from repave_engine.pipeline import generate_from_blueprint

ARGOCD_INPUTS = {
    "service_name": "checkout-api",
    "environment": "dev",
    "gitops_engine": "argocd",
    "chart_repo_url": "https://charts.example.com",
    "chart_name": "checkout-api",
    "chart_version": "1.2.3",
    "target_namespace": "checkout",
    "sync_policy": "manual",
    "destination_server": "https://kubernetes.default.svc",
    "argocd_project": "platform",
}
FLUX_INPUTS = {
    **ARGOCD_INPUTS,
    "gitops_engine": "flux",
    "flux_source_name": "example-charts",
    "flux_source_namespace": "flux-system",
}


@pytest.fixture
def gitops_blueprint(repo_root: Path):
    return load_blueprint(
        repo_root / "blueprints" / "gitops-deployment-generic",
        repo_root=repo_root,
    )


def test_gitops_deployment_family_is_gitops() -> None:
    assert artifact_family("gitops-deployment") == "gitops"


def test_blueprint_declares_pin_and_policy_gates(gitops_blueprint) -> None:
    assert gitops_blueprint.artifact_type == "gitops-deployment"
    assert "opa" in gitops_blueprint.gates
    assert "yamllint" in gitops_blueprint.gates
    assert missing_governance_gates(gitops_blueprint) == []
    chart = next(field for field in gitops_blueprint.inputs if field.name == "chart_name")
    assert chart.advanced is False
    destination = next(
        field for field in gitops_blueprint.inputs if field.name == "destination_server"
    )
    assert destination.advanced is True


def test_argocd_inputs_fall_back_to_in_cluster_defaults(gitops_blueprint) -> None:
    normalized = validate_inputs(gitops_blueprint, {**ARGOCD_INPUTS, "destination_server": ""})
    assert normalized["destination_server"] == "https://kubernetes.default.svc"


def test_floating_chart_version_is_rejected_by_enum_free_input(gitops_blueprint) -> None:
    # chart_version has no enum; the pin rule is enforced by the opa gate on the manifest,
    # so validation must accept the value and let the gate fail it.
    normalized = validate_inputs(gitops_blueprint, {**ARGOCD_INPUTS, "chart_version": "latest"})
    assert normalized["chart_version"] == "latest"


def test_flux_requires_source_name(gitops_blueprint) -> None:
    with pytest.raises(ValueError, match="flux_source_name"):
        validate_inputs(gitops_blueprint, {**FLUX_INPUTS, "flux_source_name": ""})


@pytest.mark.slow
def test_generate_argocd_application_dry_run(
    gitops_blueprint,
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    result = generate_from_blueprint(
        gitops_blueprint,
        dict(ARGOCD_INPUTS),
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )

    output_dir = result.render.output_dir
    manifest = yaml.safe_load((output_dir / "apps" / "release.yaml").read_text(encoding="utf-8"))
    assert manifest["kind"] == "Application"
    assert manifest["metadata"]["name"] == "checkout-api-dev"
    assert manifest["spec"]["source"]["targetRevision"] == "1.2.3"
    assert manifest["spec"]["project"] == "platform"
    assert manifest["spec"]["destination"]["namespace"] == "checkout"
    # Manual sync must not opt into automated reconciliation.
    assert "automated" not in manifest["spec"]["syncPolicy"]
    assert not (output_dir / "apps" / "kustomization.yaml").exists()

    spec = yaml.safe_load((output_dir / "repave.yaml").read_text(encoding="utf-8"))["spec"]
    assert spec["artifactType"] == "gitops-deployment"
    assert spec["gitopsDeployment"]["chart_version"] == "1.2.3"
    assert spec["gitopsDeployment"]["sync_policy"] == "manual"
    assert all(g.passed or g.skipped for g in result.gates)


@pytest.mark.slow
def test_generate_argocd_automated_sync_declares_prune_and_self_heal(
    gitops_blueprint,
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    result = generate_from_blueprint(
        gitops_blueprint,
        {**ARGOCD_INPUTS, "sync_policy": "automated"},
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )

    manifest = yaml.safe_load(
        (result.render.output_dir / "apps" / "release.yaml").read_text(encoding="utf-8")
    )
    automated = manifest["spec"]["syncPolicy"]["automated"]
    assert automated["prune"] is True
    assert automated["selfHeal"] is True
    assert all(g.passed or g.skipped for g in result.gates)


@pytest.mark.slow
@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"chart_version": "latest"}, "exact chart version"),
        ({"chart_repo_url": "git@github.com:acme/charts.git"}, "https:// or oci:// URL"),
        ({"argocd_project": "default"}, "implicit default project"),
    ],
)
def test_opa_gate_rejects_unpinned_or_unscoped_manifests(
    gitops_blueprint,
    repo_root: Path,
    output_config,
    staging_root,
    overrides: dict[str, str],
    expected: str,
) -> None:
    result = generate_from_blueprint(
        gitops_blueprint,
        {**ARGOCD_INPUTS, **overrides},
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )

    opa = next(gate for gate in result.gates if gate.name == "opa")
    if opa.skipped:
        pytest.skip("conftest not installed")
    assert not opa.passed
    assert expected in opa.message


@pytest.mark.slow
def test_generate_flux_helm_release_dry_run(
    gitops_blueprint,
    repo_root: Path,
    output_config,
    staging_root,
) -> None:
    result = generate_from_blueprint(
        gitops_blueprint,
        dict(FLUX_INPUTS),
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
        repo_root=repo_root,
    )

    output_dir = result.render.output_dir
    manifest = yaml.safe_load((output_dir / "apps" / "release.yaml").read_text(encoding="utf-8"))
    assert manifest["kind"] == "HelmRelease"
    chart = manifest["spec"]["chart"]["spec"]
    assert chart["version"] == "1.2.3"
    assert chart["sourceRef"]["name"] == "example-charts"
    assert manifest["spec"]["targetNamespace"] == "checkout"
    assert manifest["spec"]["storageNamespace"] == "checkout"
    assert (output_dir / "apps" / "kustomization.yaml").is_file()

    spec = yaml.safe_load((output_dir / "repave.yaml").read_text(encoding="utf-8"))["spec"]
    assert spec["gitopsDeployment"]["gitops_engine"] == "flux"
    assert spec["gitopsDeployment"]["flux_source_name"] == "example-charts"
    assert all(g.passed or g.skipped for g in result.gates)
