from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from helpers import make_blueprint
from repave_engine.cost_estimate import (
    CostEstimate,
    cost_estimate_for_result,
    cost_estimate_from_gates,
    load_cost_estimate_file,
    parse_infracost_breakdown,
    write_cost_estimate_file,
)
from repave_engine.gate_registry import GateContext, GateResult
from repave_engine.gate_runners.terraform import run_infracost
from repave_engine.pipeline import GenerationResult
from repave_engine.render import RenderResult


def test_parse_infracost_breakdown() -> None:
    payload = {
        "currency": "USD",
        "totalMonthlyCost": "42.50",
        "totalHourlyCost": "0.058",
        "projects": [{"breakdown": {"resources": [{"name": "a"}, {"name": "b"}]}}],
    }
    estimate = parse_infracost_breakdown(payload)
    assert estimate is not None
    assert estimate.currency == "USD"
    assert estimate.monthly_cost == "42.50"
    assert estimate.resource_count == 2


def test_write_and_load_cost_estimate_file(tmp_path: Path) -> None:
    estimate = CostEstimate(
        currency="USD",
        monthly_cost="10",
        hourly_cost="0.01",
        resource_count=1,
        detail="Estimated USD 10/month across 1 resource(s)",
    )
    write_cost_estimate_file(tmp_path, estimate)
    loaded = load_cost_estimate_file(tmp_path)
    assert loaded == estimate


def test_cost_estimate_from_gates_message() -> None:
    gates = [
        GateResult(
            "infracost",
            True,
            False,
            "Estimated USD 99.00/month across 3 resource(s)",
        )
    ]
    estimate = cost_estimate_from_gates(gates)
    assert estimate is not None
    assert estimate.monthly_cost == "99.00"


def test_cost_estimate_for_result_prefers_file(tmp_path: Path) -> None:
    estimate = CostEstimate(
        currency="EUR",
        monthly_cost="5",
        hourly_cost="—",
        resource_count=0,
        detail="Estimated EUR 5/month",
    )
    write_cost_estimate_file(tmp_path, estimate)
    blueprint = make_blueprint(tmp_path, create_template=False)
    result = GenerationResult(
        blueprint=blueprint,
        render=RenderResult(output_dir=tmp_path, values={}),
        gates=[],
        module_repository=None,
        pr_plan=None,
        pr_message="",
    )
    loaded = cost_estimate_for_result(result)
    assert loaded is not None
    assert loaded.currency == "EUR"


def test_run_infracost_writes_estimate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "main.tf").write_text('resource "null_resource" "x" {}\n', encoding="utf-8")
    monkeypatch.setenv("INFRACOST_API_KEY", "test-key")
    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available", lambda name: name == "infracost"
    )
    monkeypatch.setattr("repave_engine.gate_runners.terraform_usable", lambda _path: True)

    plan_json = tmp_path / ".repave" / "infracost-plan" / "tfplan.json"
    plan_json.parent.mkdir(parents=True)
    plan_json.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "repave_engine.gate_runners.terraform._terraform_plan_json",
        lambda *_args, **_kwargs: plan_json,
    )

    payload = {
        "currency": "USD",
        "totalMonthlyCost": "12.34",
        "totalHourlyCost": "0.017",
        "projects": [],
    }

    def fake_run(cmd, cwd, *, extra_env=None, timeout=None):
        if cmd[:2] == ["infracost", "breakdown"]:
            return MagicMock(returncode=0, stdout=json.dumps(payload), stderr="")
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("repave_engine.gate_runners.run_command", fake_run)

    result = run_infracost(GateContext(output_dir=tmp_path))
    assert result.passed is True
    assert "12.34" in result.message
    assert load_cost_estimate_file(tmp_path) is not None
