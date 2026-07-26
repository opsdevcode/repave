from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from helpers import make_blueprint
from repave_engine.blueprint import OpaGateConfig, OpaPolicyPack
from repave_engine.gate_registry import GateContext
from repave_engine.gate_runners import run_opa


def _opa_policy_pack_blueprint(tmp_path: Path):
    bp = make_blueprint(tmp_path, gates=("opa",), artifact_type="opa-policy")
    return replace(
        bp,
        opa_policies=OpaPolicyPack(
            policies_source="policy/opa/policies",
            policy_version="1.0.0",
        ),
        opa_gate=OpaGateConfig(policies_dir="policy", fixtures_dir="tests/fixtures"),
    )


def test_opa_skips_without_policy_config(tmp_path: Path) -> None:
    ctx = GateContext(output_dir=tmp_path, blueprint=None)
    result = run_opa(ctx)
    assert result.skipped is True
    assert "not configured" in result.message


def test_opa_skips_when_conftest_missing(tmp_path: Path) -> None:
    bp = _opa_policy_pack_blueprint(tmp_path)
    (tmp_path / "policy").mkdir()
    (tmp_path / "policy" / "sample.rego").write_text("package x\n", encoding="utf-8")
    fixtures = tmp_path / "tests" / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "input.json").write_text("{}", encoding="utf-8")

    with patch("repave_engine.gate_runners.tool_available", return_value=False):
        result = run_opa(GateContext(output_dir=tmp_path, blueprint=bp))
    assert result.skipped is True
    assert "conftest" in result.message


def test_opa_runs_conftest_on_fixtures(tmp_path: Path, monkeypatch) -> None:
    bp = _opa_policy_pack_blueprint(tmp_path)
    (tmp_path / "policy").mkdir()
    (tmp_path / "policy" / "sample.rego").write_text("package x\n", encoding="utf-8")
    fixtures = tmp_path / "tests" / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "input.json").write_text("{}", encoding="utf-8")

    captured: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], cwd: Path, **kwargs):
        captured["cmd"] = cmd
        return CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("repave_engine.gate_runners.tool_available", lambda _n: True)
    monkeypatch.setattr("repave_engine.gate_runners.run_command", fake_run)

    result = run_opa(GateContext(output_dir=tmp_path, blueprint=bp))
    assert result.passed is True
    assert captured["cmd"][:3] == ["conftest", "test", str(fixtures)]


def test_opa_evaluates_helm_rendered_manifests(tmp_path: Path, monkeypatch) -> None:
    bp = make_blueprint(tmp_path, gates=("opa",), artifact_type="helm-chart")
    bp = replace(
        bp,
        opa_policies=OpaPolicyPack(
            policies_source="policy/opa/policies",
            policy_version="1.0.0",
        ),
        opa_gate=OpaGateConfig(policies_dir="policy", fixtures_dir="tests/fixtures"),
    )
    chart_yaml = tmp_path / "Chart.yaml"
    chart_yaml.write_text("apiVersion: v2\nname: demo\nversion: 0.1.0\n", encoding="utf-8")
    (tmp_path / "policy").mkdir()
    (tmp_path / "policy" / "sample.rego").write_text("package x\n", encoding="utf-8")

    captured: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], cwd: Path, **kwargs):
        captured["cmd"] = cmd
        return CompletedProcess(cmd, 0, "kind: Deployment\nmetadata:\n  name: api\n", "")

    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda name: name in {"helm", "conftest"},
    )
    monkeypatch.setattr("repave_engine.gate_runners.run_command", fake_run)

    result = run_opa(GateContext(output_dir=tmp_path, blueprint=bp))
    assert result.passed is True
    assert captured["cmd"][0] == "conftest"
    assert "helm-rendered.yaml" in captured["cmd"][2]
