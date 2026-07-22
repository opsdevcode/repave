from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.blueprint import load_blueprint, validate_inputs


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_load_terraform_module_blueprint() -> None:
    blueprint = load_blueprint(
        REPO_ROOT / "blueprints" / "terraform-module-generic",
        REPO_ROOT,
    )
    assert blueprint.name == "terraform-module-generic"
    assert blueprint.version == "0.1.0"
    assert "terraform-fmt" in blueprint.gates


def test_validate_required_inputs() -> None:
    blueprint = load_blueprint(
        REPO_ROOT / "blueprints" / "terraform-module-generic",
        REPO_ROOT,
    )
    with pytest.raises(ValueError, match="Missing required input"):
        validate_inputs(blueprint, {"module_name": "example"})

    values = validate_inputs(
        blueprint,
        {"module_name": "example", "description": "Example module"},
    )
    assert values["module_name"] == "example"
