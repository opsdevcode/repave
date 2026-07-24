from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from helpers import make_blueprint
from repave_engine.blueprint import CheckovPolicyPack
from repave_engine.provenance import (
    build_provenance_document,
    validate_provenance_file,
    write_provenance_file,
)


def test_build_provenance_document_includes_terraform_module(terraform_blueprint) -> None:
    values = {
        "module_name": "networking-vnet",
        "cloud_provider": "aws",
        "provider_services": "ec2, s3",
    }

    document = build_provenance_document(terraform_blueprint, values)

    assert document["apiVersion"] == "repave.dev/v1beta1"
    assert document["kind"] == "GoldenPathArtifact"
    assert document["metadata"]["name"] == "networking-vnet"
    assert document["spec"]["artifactType"] == "terraform-module"
    assert document["spec"]["blueprint"]["name"] == "terraform-module-generic"
    assert document["spec"]["standard"]["source"] == "examples/standards"
    assert document["spec"]["terraformModule"]["cloud_provider"] == "aws"
    assert document["spec"]["terraformModule"]["provider_services"] == ["ec2", "s3"]
    assert document["spec"]["checkov"]["policies_source"] == "examples/checkov/policies"


def test_build_provenance_document_includes_ansible_role(
    ansible_blueprint,
    ansible_sample_inputs,
) -> None:
    document = build_provenance_document(ansible_blueprint, ansible_sample_inputs)

    assert document["spec"]["artifactType"] == "ansible-role"
    assert document["metadata"]["name"] == "acme.webserver"
    assert document["spec"]["ansibleRole"]["role_name"] == "webserver"
    assert document["spec"]["ansibleRole"]["namespace"] == "acme"
    assert document["spec"]["ansibleRole"]["min_ansible_version"] == "2.15"
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
            policies_source="examples/checkov/policies",
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
