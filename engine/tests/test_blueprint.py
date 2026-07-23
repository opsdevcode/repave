from __future__ import annotations

from pathlib import Path

import pytest

from helpers import make_blueprint
from repave_engine.blueprint import (
    InputField,
    list_blueprints,
    load_blueprint,
    load_license_catalog,
    load_provider_catalog,
    validate_inputs,
)


def test_load_terraform_module_blueprint(terraform_blueprint) -> None:
    assert terraform_blueprint.name == "terraform-module-generic"
    assert terraform_blueprint.version == "0.3.0"
    assert "terraform-fmt" in terraform_blueprint.gates
    cloud_provider = next(
        field for field in terraform_blueprint.inputs if field.name == "cloud_provider"
    )
    assert cloud_provider.enum == ("aws", "azure", "gcp")
    assert (
        terraform_blueprint.output_title_template
        == "Bootstrap {cloud_provider} module {module_name} ({provider_services})"
    )
    license_field = next(field for field in terraform_blueprint.inputs if field.name == "license")
    assert license_field.enum == ("none", "proprietary", "Apache-2.0", "MIT")
    assert license_field.default == "Apache-2.0"


def test_validate_required_inputs(terraform_blueprint) -> None:
    with pytest.raises(ValueError, match="Missing required input"):
        validate_inputs(terraform_blueprint, {"module_name": "example"})

    values = validate_inputs(
        terraform_blueprint,
        {
            "module_name": "example",
            "description": "Example module",
            "cloud_provider": "aws",
            "provider_services": "s3,vpc",
            "license": "Apache-2.0",
        },
    )
    assert values["module_name"] == "example"
    assert values["provider_services"] == "s3,vpc"


def test_validate_rejects_unknown_inputs(terraform_blueprint) -> None:
    with pytest.raises(ValueError, match="Unknown input fields"):
        validate_inputs(
            terraform_blueprint,
            {
                "module_name": "example",
                "description": "Example module",
                "cloud_provider": "aws",
                "provider_services": "s3",
                "license": "Apache-2.0",
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


def test_load_license_catalog(terraform_blueprint) -> None:
    catalog = load_license_catalog(terraform_blueprint)
    assert catalog["none"] == "No license"
    assert catalog["proprietary"] == "Proprietary software license"


def test_validate_rejects_invalid_cloud_provider(terraform_blueprint) -> None:
    with pytest.raises(ValueError, match="Invalid value for cloud_provider"):
        validate_inputs(
            terraform_blueprint,
            {
                "module_name": "example",
                "description": "Example module",
                "cloud_provider": "oracle",
                "provider_services": "s3",
                "license": "Apache-2.0",
            },
        )


def test_validate_rejects_invalid_license(terraform_blueprint) -> None:
    with pytest.raises(ValueError, match="Invalid value for license"):
        validate_inputs(
            terraform_blueprint,
            {
                "module_name": "example",
                "description": "Example module",
                "cloud_provider": "aws",
                "provider_services": "s3",
                "license": "GPL-3.0",
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
                "license": "Apache-2.0",
            },
        )


def test_validate_normalizes_provider_services(terraform_blueprint) -> None:
    values = validate_inputs(
        terraform_blueprint,
        {
            "module_name": "example",
            "description": "Example module",
            "cloud_provider": "aws",
            "provider_services": " vpc , s3 ",
            "license": "Apache-2.0",
        },
    )
    assert values["provider_services"] == "s3,vpc"


def test_load_provider_catalog(terraform_blueprint) -> None:
    catalog = load_provider_catalog(terraform_blueprint)
    assert "aws" in catalog
    assert "s3" in catalog["aws"]
    assert "vpc" in catalog["aws"]


def test_list_blueprints(repo_root: Path) -> None:
    blueprints = list_blueprints(repo_root / "blueprints")
    names = [bp.name for bp in blueprints]
    assert "terraform-module-generic" in names


def test_list_blueprints_empty_dir(tmp_path: Path) -> None:
    assert list_blueprints(tmp_path / "missing") == []


def test_load_blueprint_missing_file(tmp_path: Path, repo_root: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Blueprint not found"):
        load_blueprint(tmp_path / "missing" / "blueprint.yaml", repo_root)
