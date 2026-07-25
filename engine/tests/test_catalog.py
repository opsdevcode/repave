from __future__ import annotations

from pathlib import Path

from repave_engine.blueprint import (
    Blueprint,
    BlueprintCatalogGroup,
    group_blueprints_by_artifact,
)


def _bp(name: str, artifact_type: str) -> Blueprint:
    return Blueprint(
        path=Path(f"/tmp/{name}"),
        name=name,
        version="1.0.0",
        description=f"{name} desc",
        artifact_type=artifact_type,
        standard_source="examples/standards",
        standard_version="0.1.0",
        inputs=(),
        template_engine="copier",
        template_path="template",
        gates=("fmt", "checkov"),
        output_type="git-repo",
        output_repo_name_template="{name}",
        output_title_template="{name}",
    )


def test_group_blueprints_by_artifact_orders_known_types() -> None:
    groups = group_blueprints_by_artifact(
        [
            _bp("role-a", "ansible-role"),
            _bp("tf-b", "terraform-module"),
            _bp("tf-a", "terraform-module"),
        ]
    )

    assert [group.artifact_type for group in groups] == [
        "terraform-module",
        "ansible-role",
    ]
    assert groups[0].title == "Terraform"
    assert [bp.name for bp in groups[0].blueprints] == ["tf-b", "tf-a"]
    assert groups[1].title == "Ansible"
    assert isinstance(groups[0], BlueprintCatalogGroup)


def test_group_blueprints_unknown_type_appended() -> None:
    groups = group_blueprints_by_artifact([_bp("helm-x", "helm-chart")])

    assert len(groups) == 1
    assert groups[0].artifact_type == "helm-chart"
    assert groups[0].title == "Helm Chart"
