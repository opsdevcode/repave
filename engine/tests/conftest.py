from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.blueprint import Blueprint, load_blueprint


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def terraform_blueprint(repo_root: Path) -> Blueprint:
    return load_blueprint(repo_root / "blueprints" / "terraform-module-generic", repo_root)


@pytest.fixture
def sample_inputs() -> dict[str, str]:
    return {
        "module_name": "example",
        "description": "Example module generated in tests",
    }
