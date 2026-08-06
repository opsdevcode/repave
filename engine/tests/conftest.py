from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.blueprint import Blueprint, load_blueprint
from repave_engine.settings import OutputConfig


@pytest.fixture(autouse=True)
def _clear_repave_output_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests independent of developer shell REPAVE_* exports (see settings precedence)."""
    monkeypatch.delenv("REPAVE_GITHUB_ORG", raising=False)
    monkeypatch.delenv("REPAVE_MODULES_ROOT", raising=False)


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def terraform_blueprint(repo_root: Path) -> Blueprint:
    return load_blueprint(
        repo_root / "blueprints" / "terraform-module-generic", repo_root=repo_root
    )


@pytest.fixture
def ansible_blueprint(repo_root: Path) -> Blueprint:
    return load_blueprint(repo_root / "blueprints" / "ansible-role-generic", repo_root=repo_root)


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
        "owner": "platform-engineering",
    }


@pytest.fixture
def env_stack_inputs() -> dict[str, str]:
    return {
        "stack_name": "platform",
        "description": "Example environment stack",
        "cloud_provider": "aws",
        "environment": "dev",
        "owner": "platform-engineering",
        "pinned_modules": (
            '[{"name":"foundation","source":"./modules/_example","repo_name":"_example"}]'
        ),
    }


@pytest.fixture
def ansible_playbook_sample_inputs() -> dict[str, str]:
    return {
        "project_name": "baseline",
        "description": "Example playbook project",
        "min_ansible_version": "2.18",
        "environment": "dev",
        "pinned_roles": "[]",
    }


@pytest.fixture
def sample_inputs() -> dict[str, str]:
    return {
        "module_name": "example",
        "description": "Example module generated in tests",
        "cloud_provider": "aws",
        "provider_services": "ec2,s3",
        "owner": "platform-engineering",
        "cost_center": "CC-100",
    }


@pytest.fixture
def ansible_sample_inputs() -> dict[str, str]:
    return {
        "role_name": "webserver",
        "namespace": "acme",
        "description": "Example webserver role generated in tests",
        "min_ansible_version": "2.18",
        "support_linux": "true",
        "support_windows": "false",
        "windows_server_generation": "2022",
        "target_platforms_advanced": "",
    }
