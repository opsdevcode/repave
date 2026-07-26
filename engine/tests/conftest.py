from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.blueprint import Blueprint, load_blueprint
from repave_engine.settings import OutputConfig


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def terraform_blueprint(repo_root: Path) -> Blueprint:
    return load_blueprint(repo_root / "blueprints" / "terraform-module-generic", repo_root)


@pytest.fixture
def ansible_blueprint(repo_root: Path) -> Blueprint:
    return load_blueprint(repo_root / "blueprints" / "ansible-role-generic", repo_root)


@pytest.fixture
def output_config(tmp_path: Path) -> OutputConfig:
    modules_root = tmp_path / "modules"
    modules_root.mkdir()
    return OutputConfig(github_org="example-org", modules_root=modules_root)


@pytest.fixture
def staging_root(tmp_path: Path) -> Path:
    path = tmp_path / "staging"
    path.mkdir()
    return path


@pytest.fixture
def resource_module_inputs() -> dict[str, str]:
    return {
        "module_name": "acme-bucket",
        "description": "Example S3 bucket module",
        "cloud_provider": "aws",
        "provider_service": "s3",
        "provider_resource": "bucket",
    }


@pytest.fixture
def env_stack_inputs() -> dict[str, str]:
    return {
        "stack_name": "platform",
        "description": "Example environment stack",
        "cloud_provider": "aws",
        "environment": "dev",
        "module_name": "foundation",
        "module_source": "./modules/_example",
        "module_version": "",
    }


@pytest.fixture
def sample_inputs() -> dict[str, str]:
    return {
        "module_name": "example",
        "description": "Example module generated in tests",
        "cloud_provider": "aws",
        "provider_services": "ec2,s3",
    }


@pytest.fixture
def ansible_sample_inputs() -> dict[str, str]:
    return {
        "role_name": "webserver",
        "namespace": "acme",
        "description": "Example webserver role generated in tests",
        "min_ansible_version": "2.18",
        "target_platforms": "Ubuntu:jammy",
    }
