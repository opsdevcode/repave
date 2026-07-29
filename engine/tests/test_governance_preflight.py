from __future__ import annotations

from repave_engine.blueprint import load_blueprint
from repave_engine.governance_preflight import build_blueprint_preflight
from repave_engine.settings import OutputConfig


def test_build_blueprint_preflight_includes_repo_and_gates(repo_root) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "terraform-module-generic",
        repo_root,
    )
    output = OutputConfig(github_org="acme", modules_root=repo_root / "modules")
    preflight = build_blueprint_preflight(blueprint, output_config=output)
    assert preflight.gate_count == len(blueprint.gates)
    assert preflight.example_repo_name
    assert "terraform-standards" in preflight.standard_label
