from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from helpers import make_blueprint
from repave_engine.blueprint import CheckovPolicyPack, validate_inputs
from repave_engine.provenance import (
    build_provenance_document,
    validate_provenance_file,
    write_provenance_file,
)


def test_build_provenance_document_includes_terraform_module(
    repo_root: Path, terraform_blueprint
) -> None:
    values = validate_inputs(
        terraform_blueprint,
        {
            "module_name": "networking-vnet",
            "description": "Networking module",
            "cloud_provider": "aws",
            "provider_services": "ec2,s3",
            "policy_profile": "estate-default",
        },
        repo_root=repo_root,
    )

    document = build_provenance_document(terraform_blueprint, values)

    assert document["apiVersion"] == "repave.dev/v1beta1"
    assert document["kind"] == "GoldenPathArtifact"
    assert document["metadata"]["name"] == "networking-vnet"
    assert document["spec"]["artifactType"] == "terraform-module"
    assert document["spec"]["blueprint"]["name"] == "terraform-module-generic"
    assert document["spec"]["standard"]["source"] == "standards/terraform-standards"
    assert document["spec"]["standard"]["version"] == "1.1.0"
    assert document["spec"]["opa"]["policy_version"] == "1.0.0"
    assert document["spec"]["governance"]["baseline_source"] == (
        "standards/policy/governance-baseline.md"
    )
    policy = document["spec"]["policy"]
    assert policy["profile"] == "estate-default"
    assert policy["pack_source"] == "repave-default"
    assert "checkov:CKV2_REPAVE_1" in policy["enabled_rules"]
    assert document["spec"]["terraformModule"]["cloud_provider"] == "aws"
    assert document["spec"]["terraformModule"]["provider_services"] == ["ec2", "s3"]
    assert document["spec"]["checkov"]["policies_source"] == "policy/checkov/policies"
    ci = document["spec"]["ci"]
    assert "terraform-test" in ci["gates"]
    assert ci["workflow"] == ".github/workflows/terraform-gates.yml"
    assert ci["toolchain"]["terraform"] == "1.9.8"


def test_build_provenance_document_includes_ansible_role(
    ansible_blueprint,
    ansible_sample_inputs,
) -> None:
    document = build_provenance_document(
        ansible_blueprint,
        validate_inputs(ansible_blueprint, ansible_sample_inputs),
    )

    assert document["spec"]["artifactType"] == "ansible-role"
    assert document["metadata"]["name"] == "acme.webserver"
    assert document["spec"]["ansibleRole"]["role_name"] == "webserver"
    assert document["spec"]["ansibleRole"]["namespace"] == "acme"
    assert document["spec"]["ansibleRole"]["min_ansible_version"] == "2.18"
    assert document["spec"]["ansibleRole"]["target_platforms"] == (
        "Debian:bookworm,EL:9,Ubuntu:jammy"
    )
    assert document["spec"]["ansibleLint"]["pack_version"] == "1.0.0"
    assert "terraformModule" not in document["spec"]
    assert "checkov" not in document["spec"]


def test_write_provenance_file_creates_repave_yaml(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    blueprint = make_blueprint(
        tmp_path,
        gates=("docs-drift", "provenance-drift"),
        provenance_file="repave.yaml",
        checkov_policies=CheckovPolicyPack(
            policies_source="policy/checkov/policies",
            policy_version="1.2.0",
        ),
    )

    output_dir = tmp_path / "module"
    output_dir.mkdir()
    path = write_provenance_file(
        output_dir,
        blueprint,
        {"module_name": "example", "cloud_provider": "aws", "provider_services": "s3"},
        filename="repave.yaml",
    )

    assert path == output_dir / "repave.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["kind"] == "GoldenPathArtifact"
    validate_provenance_file(path, repo_root)


def test_validate_provenance_file_rejects_missing_file(tmp_path: Path, repo_root: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Provenance file missing"):
        validate_provenance_file(tmp_path / "repave.yaml", repo_root)


def test_build_provenance_document_honors_fixed_generated_at(
    terraform_blueprint, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REPAVE_PROVENANCE_GENERATED_AT", "1970-01-01T00:00:00+00:00")
    document = build_provenance_document(
        terraform_blueprint,
        {
            "module_name": "example",
            "description": "Example",
            "cloud_provider": "aws",
            "provider_services": "s3",
        },
    )
    assert document["spec"]["generation"]["generated_at"] == "1970-01-01T00:00:00+00:00"


def test_require_provenance_for_publish_missing_file(
    tmp_path: Path, terraform_blueprint, repo_root: Path
) -> None:
    from repave_engine.provenance import require_provenance_for_publish

    with pytest.raises(FileNotFoundError, match="Provenance file missing"):
        require_provenance_for_publish(tmp_path, terraform_blueprint, repo_root=repo_root)


def test_require_provenance_for_publish_validates_schema(
    tmp_path: Path, terraform_blueprint, repo_root: Path
) -> None:
    from repave_engine.provenance import require_provenance_for_publish, write_provenance_file

    values = {
        "module_name": "example",
        "description": "Example",
        "cloud_provider": "aws",
        "provider_services": "s3",
    }
    write_provenance_file(
        tmp_path,
        terraform_blueprint,
        values,
        filename=terraform_blueprint.provenance_file or "repave.yaml",
    )
    path = require_provenance_for_publish(tmp_path, terraform_blueprint, repo_root=repo_root)
    assert path.name == "repave.yaml"


def test_publish_after_gates_requires_provenance(
    terraform_blueprint,
    sample_inputs,
    output_config,
    staging_root,
    repo_root: Path,
) -> None:
    from repave_engine.pipeline import _publish_after_gates
    from repave_engine.render import RenderResult
    from repave_engine.target_repo import resolve_module_repository

    normalized = dict(sample_inputs)
    module_name = normalized["module_name"]
    module_repository = resolve_module_repository(
        module_name=module_name,
        config=output_config,
        name_template=terraform_blueprint.output_repo_name_template,
        template_values=normalized,
    )
    render_result = RenderResult(output_dir=staging_root, values=normalized)
    (staging_root / "main.tf").write_text("# stub\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="Provenance file missing"):
        _publish_after_gates(
            blueprint=terraform_blueprint,
            render_result=render_result,
            module_repository=module_repository,
            normalized=normalized,
            dry_run=False,
            github_token=None,
            on_event=None,
            publish_idempotency=None,
            repo_root=repo_root,
        )
