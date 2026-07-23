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
def sample_inputs() -> dict[str, str]:
    return {
        "module_name": "example",
        "description": "Example module generated in tests",
        "cloud_provider": "aws",
        "provider_services": "s3,vpc",
    }
