from __future__ import annotations

from pathlib import Path

from helpers import make_blueprint
from repave_engine.infracost_policy import effective_gate_names
from repave_engine.settings import GateOverrides, InfracostGatePolicy


def test_effective_gate_names_unchanged_when_not_required(tmp_path: Path) -> None:
    blueprint = make_blueprint(
        tmp_path,
        gates=("terraform-fmt", "tflint", "secrets"),
        create_template=False,
    )
    names = effective_gate_names(blueprint, GateOverrides())
    assert names == ("terraform-fmt", "tflint", "secrets")


def test_effective_gate_names_injects_infracost_after_tflint(tmp_path: Path) -> None:
    blueprint = make_blueprint(
        tmp_path,
        gates=("terraform-fmt", "tflint", "secrets"),
        create_template=False,
    )
    overrides = GateOverrides(infracost=InfracostGatePolicy(required=True))
    names = effective_gate_names(blueprint, overrides)
    assert names == ("terraform-fmt", "tflint", "infracost", "secrets")


def test_effective_gate_names_skips_non_terraform_blueprints(tmp_path: Path) -> None:
    blueprint = make_blueprint(
        tmp_path,
        gates=("docs-drift", "secrets"),
        artifact_type="docs",
        create_template=False,
    )
    overrides = GateOverrides(infracost=InfracostGatePolicy(required=True))
    assert effective_gate_names(blueprint, overrides) == ("docs-drift", "secrets")


def test_effective_gate_names_idempotent_when_already_present(tmp_path: Path) -> None:
    blueprint = make_blueprint(
        tmp_path,
        gates=("terraform-fmt", "infracost"),
        create_template=False,
    )
    overrides = GateOverrides(infracost=InfracostGatePolicy(required=True))
    assert effective_gate_names(blueprint, overrides) == ("terraform-fmt", "infracost")
