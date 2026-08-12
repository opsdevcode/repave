from __future__ import annotations

from pathlib import Path

from helpers import make_blueprint
from repave_engine.blueprint import InputField, load_blueprint, validate_inputs
from repave_engine.guided_identity import (
    apply_guided_identity,
    humanize_identity,
    render_guided_from,
    slugify_identity,
)


def test_slugify_identity_joins_comma_lists() -> None:
    assert slugify_identity("ec2,s3") == "ec2-s3"
    assert slugify_identity("aws_s3_bucket") == "aws-s3-bucket"
    assert slugify_identity("linux-service", separator="_") == "linux_service"
    assert slugify_identity("ghcr.io/acme/payments") == "payments"


def test_humanize_identity_lists_and_slugs() -> None:
    assert humanize_identity("ec2,s3") == "ec2, s3"
    assert humanize_identity("linux-service") == "linux service"


def test_render_guided_from_skips_empty_placeholders() -> None:
    assert render_guided_from("{provider_services}", {}, slug=True) == ""
    assert (
        render_guided_from(
            "{cloud_provider} Terraform module covering {provider_services}.",
            {"cloud_provider": "aws", "provider_services": "ec2,s3"},
            slug=False,
        )
        == "aws Terraform module covering ec2, s3."
    )


def test_apply_guided_identity_fills_empty_fields() -> None:
    blueprint = make_blueprint(
        Path("/tmp/guided-identity"),
        create_template=False,
        inputs=(
            InputField("module_name", "string", True, guided_from="{provider_services}"),
            InputField(
                "description",
                "string",
                True,
                guided_from="{cloud_provider} module for {provider_services}.",
            ),
            InputField("cloud_provider", "string", True),
            InputField("provider_services", "string", True),
        ),
    )
    values: dict[str, str] = {
        "cloud_provider": "aws",
        "provider_services": "ec2,s3",
        "module_name": "",
        "description": "",
    }
    apply_guided_identity(blueprint, values)
    assert values["module_name"] == "ec2-s3"
    assert values["description"] == "aws module for ec2, s3."


def test_apply_guided_identity_skips_optional_empty_fields() -> None:
    blueprint = make_blueprint(
        Path("/tmp/guided-identity-optional"),
        create_template=False,
        inputs=(
            InputField(
                "description",
                "string",
                False,
                default="",
                guided_from="{visibility} GitHub repository.",
            ),
            InputField("visibility", "string", True, default="private"),
        ),
    )
    values: dict[str, str] = {"visibility": "private", "description": ""}
    apply_guided_identity(blueprint, values)
    assert values["description"] == ""


def test_apply_guided_identity_keeps_explicit_overrides() -> None:
    blueprint = make_blueprint(
        Path("/tmp/guided-identity-override"),
        create_template=False,
        inputs=(
            InputField("module_name", "string", True, guided_from="{provider_services}"),
            InputField("provider_services", "string", True),
        ),
    )
    values = {"module_name": "custom-vpc", "provider_services": "ec2,s3"}
    apply_guided_identity(blueprint, values)
    assert values["module_name"] == "custom-vpc"


def test_validate_inputs_fills_terraform_identity(terraform_blueprint) -> None:
    values = validate_inputs(
        terraform_blueprint,
        {
            "cloud_provider": "aws",
            "provider_services": "ec2,s3",
            "owner": "platform-engineering",
        },
    )
    assert values["module_name"] == "ec2-s3"
    assert values["description"] == "aws Terraform module covering ec2, s3."


def test_validate_inputs_fills_ansible_identity_from_pattern(
    repo_root: Path,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "ansible-role-generic",
        repo_root=repo_root,
    )
    values = validate_inputs(
        blueprint,
        {
            "namespace": "acme",
            "support_linux": "true",
            "support_windows": "false",
        },
        repo_root=repo_root,
    )
    assert values["role_pattern_source"] == "linux-service"
    assert values["role_name"] == "linux_service"
    assert values["description"] == "acme Ansible role (linux service)."


def test_validate_inputs_fills_app_service_identity(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "app-service-generic",
        repo_root=repo_root,
    )
    values = validate_inputs(
        blueprint,
        {"owner": "group:platform"},
        repo_root=repo_root,
    )
    assert values["service_name"] == "python-http-api"
    assert values["description"] == "python http api application service."
