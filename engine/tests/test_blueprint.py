from __future__ import annotations

import json
from pathlib import Path

import pytest

from helpers import make_blueprint
from repave_engine.blueprint import (
    InputField,
    list_blueprints,
    load_blueprint,
    validate_inputs,
)
from repave_engine.provider_catalog import load_provider_catalog


def test_load_terraform_module_blueprint(terraform_blueprint) -> None:
    assert terraform_blueprint.name == "terraform-module-generic"
    assert terraform_blueprint.version == "0.11.0"
    assert terraform_blueprint.artifact_type == "terraform-module"
    assert terraform_blueprint.standard_source == "standards/terraform-standards"
    assert terraform_blueprint.standard_version == "1.1.0"
    assert terraform_blueprint.opa_policies is not None
    assert terraform_blueprint.opa_policies.policy_version == "1.0.0"
    assert terraform_blueprint.provenance_file == "repave.yaml"
    assert terraform_blueprint.checkov_policies is not None
    assert terraform_blueprint.checkov_policies.policies_source == "policy/checkov/policies"
    assert terraform_blueprint.checkov_policies.policy_version == "1.2.0"
    assert terraform_blueprint.checkov_gate.external_checks_dir == "policy/checkov"
    assert terraform_blueprint.checkov_gate.config_file == ".checkov.yml"
    assert "terraform-fmt" in terraform_blueprint.gates
    assert "secrets" in terraform_blueprint.gates
    assert "provenance-drift" in terraform_blueprint.gates
    cloud_provider = next(
        field for field in terraform_blueprint.inputs if field.name == "cloud_provider"
    )
    assert cloud_provider.enum == ("aws", "azure", "gcp")
    assert (
        terraform_blueprint.output_title_template
        == "Bootstrap {cloud_provider} module {module_name} ({provider_services})"
    )


def test_validate_required_inputs(terraform_blueprint) -> None:
    with pytest.raises(ValueError, match="Missing required input"):
        validate_inputs(terraform_blueprint, {"module_name": "example"})

    values = validate_inputs(
        terraform_blueprint,
        {
            "module_name": "example",
            "description": "Example module",
            "cloud_provider": "aws",
            "provider_services": "ec2,s3",
        },
    )
    assert values["module_name"] == "example"
    assert values["provider_services"] == "ec2,s3"
    assert "provider_service_scope" in values
    assert "provider_service_scope_summary" in values


def test_validate_rejects_unknown_inputs(terraform_blueprint) -> None:
    with pytest.raises(ValueError, match="Unknown input fields"):
        validate_inputs(
            terraform_blueprint,
            {
                "module_name": "example",
                "description": "Example module",
                "cloud_provider": "aws",
                "provider_services": "s3",
                "unexpected": "nope",
            },
        )


def test_validate_applies_defaults(tmp_path: Path) -> None:
    blueprint = make_blueprint(
        tmp_path,
        inputs=(
            InputField("module_name", "string", True, "Module name"),
            InputField("environment", "string", False, "Environment", default="dev"),
        ),
    )

    values = validate_inputs(blueprint, {"module_name": "example"})
    assert values["environment"] == "dev"


def test_validate_rejects_invalid_cloud_provider(terraform_blueprint) -> None:
    with pytest.raises(ValueError, match="Invalid value for cloud_provider"):
        validate_inputs(
            terraform_blueprint,
            {
                "module_name": "example",
                "description": "Example module",
                "cloud_provider": "oracle",
                "provider_services": "s3",
            },
        )


def test_validate_rejects_invalid_provider_services(terraform_blueprint) -> None:
    with pytest.raises(ValueError, match="Invalid provider_services for aws"):
        validate_inputs(
            terraform_blueprint,
            {
                "module_name": "example",
                "description": "Example module",
                "cloud_provider": "aws",
                "provider_services": "blob_storage",
            },
        )


def test_validate_basic_with_additional_provider_service_scope(terraform_blueprint) -> None:
    values = validate_inputs(
        terraform_blueprint,
        {
            "module_name": "example",
            "description": "Example module",
            "cloud_provider": "aws",
            "provider_services": "s3",
            "provider_service_scope": (
                '{"s3":{"mode":"basic","additional_resources":["bucket_acl"]}}'
            ),
        },
    )
    assert "bucket_acl" in values["provider_service_scope"]
    assert "basic capabilities + additional" in values["provider_service_scope_summary"]


def test_validate_custom_provider_service_scope(terraform_blueprint) -> None:
    values = validate_inputs(
        terraform_blueprint,
        {
            "module_name": "example",
            "description": "Example module",
            "cloud_provider": "aws",
            "provider_services": "s3",
            "provider_service_scope": (
                '{"s3":{"mode":"custom","resources":["bucket_acl","bucket"]}}'
            ),
        },
    )
    assert "bucket_acl" in values["provider_service_scope"]
    assert "custom resources" in values["provider_service_scope_summary"]


def test_validate_normalizes_provider_services(terraform_blueprint) -> None:
    values = validate_inputs(
        terraform_blueprint,
        {
            "module_name": "example",
            "description": "Example module",
            "cloud_provider": "aws",
            "provider_services": " s3 , ec2 ",
        },
    )
    assert values["provider_services"] == "ec2,s3"


def test_load_provider_catalog(terraform_blueprint) -> None:
    catalog = load_provider_catalog(terraform_blueprint.path)
    assert len(catalog["aws"]) >= 200
    assert len(catalog["azure"]) >= 100
    assert len(catalog["gcp"]) >= 150
    assert "resources" in catalog["aws"]["s3"]
    assert "basic" in catalog["aws"]["s3"]
    assert "bucket" in catalog["aws"]["s3"]["resources"]


def test_list_blueprints(repo_root: Path) -> None:
    blueprints = list_blueprints(repo_root / "blueprints")
    names = [bp.name for bp in blueprints]
    assert "terraform-module-generic" in names
    assert "terraform-module-resource" in names
    assert "terraform-environment-stack" in names
    assert "ansible-role-generic" in names
    assert "ansible-playbook-project" in names
    assert "ansible-collection-generic" in names
    assert "opa-policy-generic" in names
    assert "azure-policy-generic" in names
    assert "checkov-policy-generic" in names


def test_load_checkov_policy_generic_blueprint(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "checkov-policy-generic",
        repo_root,
    )
    assert blueprint.artifact_type == "checkov-policy"
    assert "checkov" in blueprint.gates
    assert blueprint.checkov_policies is not None
    assert blueprint.checkov_gate.scan_dir == "tests/fixtures/pass"


def test_load_opa_policy_generic_blueprint(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "opa-policy-generic",
        repo_root,
    )
    assert blueprint.artifact_type == "opa-policy"
    assert "opa" in blueprint.gates
    assert "secrets" in blueprint.gates
    assert blueprint.opa_gate.policies_dir == "policy"


def test_load_azure_policy_generic_blueprint(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "azure-policy-generic",
        repo_root,
    )
    assert blueprint.artifact_type == "azure-policy"
    assert "azure-policy" in blueprint.gates
    assert blueprint.azure_policy_pack is not None


def test_load_ansible_collection_generic_blueprint(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "ansible-collection-generic",
        repo_root,
    )
    assert blueprint.name == "ansible-collection-generic"
    assert blueprint.artifact_type == "ansible-collection"
    assert blueprint.standard_source == "standards/ansible/collection-standard.md"
    assert blueprint.output_repo_name_template.startswith("ansible-collection-")


def test_build_provenance_document_ansible_collection(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "ansible-collection-generic",
        repo_root,
    )
    from repave_engine.provenance import build_provenance_document

    document = build_provenance_document(
        blueprint,
        {
            "namespace": "acme",
            "collection_name": "platform",
            "description": "Shared platform modules",
            "min_ansible_version": "2.18",
        },
    )
    assert document["spec"]["artifactType"] == "ansible-collection"
    assert document["metadata"]["name"] == "acme.platform"
    assert document["spec"]["ansibleCollection"]["collection_name"] == "platform"


def test_load_ansible_playbook_project_blueprint(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "ansible-playbook-project",
        repo_root,
    )
    assert blueprint.name == "ansible-playbook-project"
    assert blueprint.artifact_type == "ansible-playbook-project"
    assert blueprint.output_repo_name_template.startswith("ansible-playbook-")


def test_build_provenance_document_ansible_playbook_project(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "ansible-playbook-project",
        repo_root,
    )
    from repave_engine.provenance import build_provenance_document

    document = build_provenance_document(
        blueprint,
        {
            "project_name": "baseline",
            "description": "Core playbooks",
            "min_ansible_version": "2.18",
            "environment": "dev",
        },
    )
    assert document["spec"]["artifactType"] == "ansible-playbook-project"
    assert document["spec"]["ansiblePlaybookProject"]["project_name"] == "baseline"


def test_validate_ansible_playbook_pinned_roles(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "ansible-playbook-project",
        repo_root,
    )
    normalized = validate_inputs(
        blueprint,
        {
            "project_name": "baseline",
            "description": "Core playbooks",
            "min_ansible_version": "2.18",
            "environment": "dev",
            "pinned_roles": '[{"galaxy_name":"acme.web","version":"1.0.0","src":"https://github.com/acme/ansible-role-web","repo_name":"ansible-role-web"}]',
        },
    )
    assert len(normalized["pinned_roles"]) == 1
    assert normalized["pinned_roles"][0]["galaxy_name"] == "acme.web"


def test_build_provenance_document_ansible_playbook_pinned_roles(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "ansible-playbook-project",
        repo_root,
    )
    from repave_engine.provenance import build_provenance_document

    document = build_provenance_document(
        blueprint,
        {
            "project_name": "baseline",
            "description": "Core playbooks",
            "min_ansible_version": "2.18",
            "environment": "dev",
            "pinned_roles": [
                {
                    "galaxy_name": "acme.web",
                    "version": "1.0.0",
                    "src": "https://github.com/acme/ansible-role-web",
                    "repo_name": "ansible-role-web",
                }
            ],
        },
    )
    pinned = document["spec"]["ansiblePlaybookProject"]["pinned_roles"]
    assert pinned[0]["version"] == "1.0.0"


def test_load_terraform_module_resource_blueprint(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "terraform-module-resource",
        repo_root,
    )
    assert blueprint.name == "terraform-module-resource"
    assert blueprint.version == "0.4.0"
    assert blueprint.standard_source == "standards/terraform-standards"
    assert blueprint.standard_version == "1.1.0"
    assert blueprint.terraform_layout == "single-resource"
    assert blueprint.output_repo_name_template.startswith("tfm-")
    input_names = {field.name for field in blueprint.inputs}
    assert {"provider_service", "provider_resource"}.issubset(input_names)


def test_validate_single_resource_inputs(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "terraform-module-resource",
        repo_root,
    )
    normalized = validate_inputs(
        blueprint,
        {
            "module_name": "acme-bucket",
            "description": "S3 bucket module",
            "cloud_provider": "aws",
            "provider_service": "s3",
            "provider_resource": "bucket",
        },
        repo_root=repo_root,
    )
    assert normalized["provider_services"] == "s3"
    scope = json.loads(normalized["provider_service_scope"])
    assert scope["s3"]["resources"] == ["bucket"]


def test_load_terraform_environment_stack_blueprint(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "terraform-environment-stack",
        repo_root,
    )
    assert blueprint.name == "terraform-environment-stack"
    assert blueprint.artifact_type == "terraform-environment-stack"
    assert blueprint.output_repo_name_template.startswith("env-")


def test_build_provenance_document_environment_stack(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "terraform-environment-stack",
        repo_root,
    )
    from repave_engine.provenance import build_provenance_document

    document = build_provenance_document(
        blueprint,
        {
            "stack_name": "platform",
            "description": "Core platform stack",
            "cloud_provider": "aws",
            "environment": "dev",
            "pinned_modules": [
                {"name": "foundation", "source": "./modules/_example", "repo_name": "_example"},
            ],
        },
    )
    assert document["spec"]["artifactType"] == "terraform-environment-stack"
    stack = document["spec"]["terraformEnvironmentStack"]
    assert stack["stack_name"] == "platform"
    assert stack["pinned_modules"][0]["source"] == "./modules/_example"


def test_validate_environment_stack_pinned_modules(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "terraform-environment-stack",
        repo_root,
    )
    normalized = validate_inputs(
        blueprint,
        {
            "stack_name": "platform",
            "description": "Core platform stack",
            "cloud_provider": "aws",
            "environment": "dev",
            "pinned_modules": (
                '[{"name":"foundation","source":"./modules/_example","repo_name":"_example"}]'
            ),
        },
    )
    assert len(normalized["pinned_modules"]) == 1
    assert normalized["pinned_modules"][0]["name"] == "foundation"


def test_load_ansible_role_blueprint(ansible_blueprint) -> None:
    assert ansible_blueprint.name == "ansible-role-generic"
    assert ansible_blueprint.version == "0.3.0"
    assert ansible_blueprint.artifact_type == "ansible-role"
    assert ansible_blueprint.standard_source == "standards/ansible"
    assert ansible_blueprint.standard_version == "1.0.0"
    assert ansible_blueprint.provenance_file == "repave.yaml"
    assert ansible_blueprint.checkov_policies is None
    assert ansible_blueprint.ansible_lint_pack is not None
    assert ansible_blueprint.ansible_lint_pack.pack_source == "policy/ansible-lint/pack"
    assert ansible_blueprint.ansible_lint_pack.pack_version == "1.0.0"
    assert "yamllint" in ansible_blueprint.gates
    assert "ansible-lint" in ansible_blueprint.gates
    assert "secrets" in ansible_blueprint.gates
    assert "molecule" in ansible_blueprint.gates
    assert "provenance-drift" in ansible_blueprint.gates
    assert ansible_blueprint.output_repo_name_template == "ansible-role-{role_name}"
    advanced = next(
        field for field in ansible_blueprint.inputs if field.name == "target_platforms_advanced"
    )
    assert advanced.multi is True
    assert "Windows:2022" in advanced.enum
    assert "Ubuntu:jammy" in advanced.enum
    linux = next(field for field in ansible_blueprint.inputs if field.name == "support_linux")
    assert linux.default == "true"
    min_ansible = next(
        field for field in ansible_blueprint.inputs if field.name == "min_ansible_version"
    )
    assert min_ansible.default == "2.18"
    assert min_ansible.enum[0] == "2.18"
    assert "2.15" in min_ansible.enum


def test_validate_ansible_target_platforms_linux_defaults(ansible_blueprint) -> None:
    values = validate_inputs(
        ansible_blueprint,
        {
            "role_name": "webserver",
            "namespace": "acme",
            "description": "Example",
            "min_ansible_version": "2.15",
            "support_linux": "true",
            "support_windows": "false",
            "windows_server_generation": "2022",
            "target_platforms_advanced": "",
        },
    )
    assert values["target_platforms"] == "Debian:bookworm,EL:9,Ubuntu:jammy"


def test_validate_ansible_target_platforms_advanced_override(ansible_blueprint) -> None:
    values = validate_inputs(
        ansible_blueprint,
        {
            "role_name": "webserver",
            "namespace": "acme",
            "description": "Example",
            "min_ansible_version": "2.15",
            "support_linux": "false",
            "support_windows": "false",
            "windows_server_generation": "2022",
            "target_platforms_advanced": "Ubuntu:jammy,Windows:2022,EL:9",
        },
    )
    assert values["target_platforms"] == "EL:9,Ubuntu:jammy,Windows:2022"


def test_validate_rejects_unknown_target_platform_advanced(ansible_blueprint) -> None:
    with pytest.raises(ValueError, match="Invalid value\\(s\\) for target_platforms_advanced"):
        validate_inputs(
            ansible_blueprint,
            {
                "role_name": "webserver",
                "namespace": "acme",
                "description": "Example",
                "min_ansible_version": "2.15",
                "support_linux": "true",
                "support_windows": "false",
                "windows_server_generation": "2022",
                "target_platforms_advanced": "NotAPlatform:1",
            },
        )


def test_validate_ansible_role_inputs(ansible_blueprint, ansible_sample_inputs) -> None:
    values = validate_inputs(ansible_blueprint, ansible_sample_inputs)
    assert values["role_name"] == "webserver"
    assert values["namespace"] == "acme"
    assert "Debian:bookworm" in values["target_platforms"]
    assert "provider_service_scope" not in values


def test_list_blueprints_empty_dir(tmp_path: Path) -> None:
    assert list_blueprints(tmp_path / "missing") == []


def test_load_blueprint_missing_file(tmp_path: Path, repo_root: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Blueprint not found"):
        load_blueprint(tmp_path / "missing" / "blueprint.yaml", repo_root)


def test_validate_rejects_invalid_enum_value(tmp_path: Path) -> None:
    blueprint = make_blueprint(
        tmp_path,
        inputs=(
            InputField("module_name", "string", True, "Module name"),
            InputField(
                "environment",
                "string",
                True,
                "Environment",
                enum=("dev", "prod"),
            ),
        ),
    )

    with pytest.raises(ValueError, match="Invalid value for environment"):
        validate_inputs(blueprint, {"module_name": "example", "environment": "staging"})


def test_validate_rejects_empty_provider_services(terraform_blueprint) -> None:
    with pytest.raises(ValueError, match="at least one service"):
        validate_inputs(
            terraform_blueprint,
            {
                "module_name": "example",
                "description": "Example module",
                "cloud_provider": "aws",
                "provider_services": "  , ",
            },
        )


def test_load_observability_blueprint(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "observability-as-code-generic",
        repo_root,
    )
    assert blueprint.artifact_type == "observability"
    assert "promtool" in blueprint.gates
    assert "grafana-dashboard" in blueprint.gates
    assert "datadog-monitor" in blueprint.gates
    assert "terraform-validate" in blueprint.gates
    assert "yamllint" in blueprint.gates
    assert blueprint.output_repo_name_template.startswith("observability-")


def test_build_provenance_document_observability(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "observability-as-code-generic",
        repo_root,
    )
    from repave_engine.provenance import build_provenance_document

    document = build_provenance_document(
        blueprint,
        {
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout alerts",
            "backend": "prometheus",
            "output_mode": "native",
            "notification_source": "repave-estate-oncall",
            "notification_target": "pagerduty-payments",
            "runbook_url": "https://wiki.example.com/runbooks/checkout",
            "slo_target_percent": "99.9",
        },
    )
    assert document["spec"]["artifactType"] == "observability"
    obs = document["spec"]["observability"]
    assert obs["service_name"] == "checkout"
    assert obs["notification_source"] == "repave-estate-oncall"
    assert obs["notification_target"] == "pagerduty-payments"
    assert obs["slo_target_percent"] == "99.9"


def test_load_dashboards_as_code_blueprint(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "dashboards-as-code-generic",
        repo_root,
    )
    assert blueprint.artifact_type == "observability"
    assert "grafana-dashboard" in blueprint.gates
    assert "datadog-dashboard" in blueprint.gates
    assert blueprint.output_repo_name_template.startswith("dashboards-")


def test_build_provenance_document_dashboards(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "dashboards-as-code-generic",
        repo_root,
    )
    from repave_engine.provenance import build_provenance_document

    document = build_provenance_document(
        blueprint,
        {
            "service_name": "checkout",
            "organization": "platform",
            "team": "payments",
            "description": "Checkout dashboards",
            "backend": "grafana",
            "output_mode": "native",
            "environment": "prod",
            "observability_focus": "dashboards",
            "datasource_uid": "prometheus",
            "notification_source": "repave-estate-oncall",
            "notification_target": "pagerduty-platform-primary",
        },
    )
    obs = document["spec"]["observability"]
    assert obs["focus"] == "dashboards"
    assert obs["environment"] == "prod"
    assert obs["datasource_uid"] == "prometheus"
    assert "runbook_url" not in obs


def test_load_blueprint_rejects_invalid_schema(tmp_path: Path, repo_root: Path) -> None:
    import jsonschema

    blueprint_dir = tmp_path / "invalid-blueprint"
    blueprint_dir.mkdir()
    (blueprint_dir / "blueprint.yaml").write_text(
        "\n".join(
            [
                "apiVersion: repave.dev/v1alpha1",
                "kind: Blueprint",
                "metadata:",
                "  name: invalid",
                "  version: 0.0.1",
                "spec:",
                "  standard:",
                "    source: standards",
                "    version: 0.4.0",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(jsonschema.ValidationError):
        load_blueprint(blueprint_dir, repo_root)
