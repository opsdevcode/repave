from __future__ import annotations

from pathlib import Path

from repave_engine.blueprint import (
    Blueprint,
    BlueprintCatalogGroup,
    artifact_family,
    group_blueprints_by_artifact,
)


def _bp(name: str, artifact_type: str) -> Blueprint:
    return Blueprint(
        path=Path(f"/tmp/{name}"),
        name=name,
        version="1.0.0",
        description=f"{name} desc",
        artifact_type=artifact_type,
        standard_source="standards",
        standard_version="0.1.0",
        inputs=(),
        template_engine="copier",
        template_path="template",
        gates=("fmt", "checkov"),
        output_type="git-repo",
        output_repo_name_template="{name}",
        output_title_template="{name}",
    )


def test_artifact_family_groups_terraform_types() -> None:
    assert artifact_family("terraform-module") == "terraform"
    assert artifact_family("terraform-environment-stack") == "terraform"


def test_group_blueprints_by_artifact_collapses_families() -> None:
    groups = group_blueprints_by_artifact(
        [
            _bp("playbook-a", "ansible-playbook-project"),
            _bp("collection-a", "ansible-collection"),
            _bp("role-a", "ansible-role"),
            _bp("env-stack", "terraform-environment-stack"),
            _bp("tf-b", "terraform-module"),
            _bp("tf-a", "terraform-module"),
        ]
    )

    assert [group.family for group in groups] == ["terraform", "ansible"]
    assert groups[0].title == "Terraform"
    assert [bp.name for bp in groups[0].blueprints] == ["tf-a", "tf-b", "env-stack"]
    assert groups[1].title == "Ansible"
    assert [bp.name for bp in groups[1].blueprints] == ["role-a", "collection-a", "playbook-a"]
    assert isinstance(groups[0], BlueprintCatalogGroup)


def test_group_blueprints_policy_family_groups_opa_and_azure() -> None:
    groups = group_blueprints_by_artifact(
        [
            _bp("azure-policy-generic", "azure-policy"),
            _bp("opa-policy-generic", "opa-policy"),
            _bp("tf-a", "terraform-module"),
        ]
    )

    assert [group.family for group in groups] == ["terraform", "policy"]
    policy = groups[1]
    assert policy.title == "Policy"
    assert [bp.name for bp in policy.blueprints] == ["opa-policy-generic", "azure-policy-generic"]


def test_artifact_family_groups_policy_types() -> None:
    assert artifact_family("opa-policy") == "policy"
    assert artifact_family("azure-policy") == "policy"


def test_group_blueprints_unknown_type_appended() -> None:
    groups = group_blueprints_by_artifact([_bp("helm-x", "helm-chart")])

    assert len(groups) == 1
    assert groups[0].family == "helm-chart"
    assert groups[0].title == "Helm Chart"
