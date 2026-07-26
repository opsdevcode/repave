"""OPA policy golden path plan_demo fixture wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.blueprint import load_blueprint
from repave_engine.gates import run_gates
from repave_engine.render import render_blueprint


@pytest.mark.parametrize(
    "plan_demo,expect_opa_pass",
    [("pass", True), ("destructive_delete", False)],
)
def test_opa_policy_plan_demo_fixture(
    repo_root: Path,
    tmp_path: Path,
    plan_demo: str,
    expect_opa_pass: bool,
) -> None:
    blueprint = load_blueprint(repo_root / "blueprints" / "opa-policy-generic", repo_root)
    values = {
        "policy_name": "demo",
        "organization": "platform",
        "description": "Demo OPA policy pack",
        "plan_demo": plan_demo,
    }
    output = tmp_path / "out"
    render_blueprint(blueprint, values, output)
    fixtures = output / "tests" / "fixtures"
    if plan_demo == "destructive_delete":
        assert (fixtures / "plan-destructive-delete.json").is_file()
        assert not (fixtures / "plan-create-only.json").is_file()
    else:
        assert (fixtures / "plan-create-only.json").is_file()

    results = {gate.name: gate for gate in run_gates(output, blueprint.gates, blueprint=blueprint)}
    opa = results.get("opa")
    assert opa is not None
    if not expect_opa_pass:
        if opa.skipped and "conftest" in opa.message:
            pytest.skip("conftest not installed")
        assert opa.passed is False
        assert "Publish blocked" in opa.message or "destructive" in opa.message.lower()
    else:
        assert opa.passed is True or opa.skipped
