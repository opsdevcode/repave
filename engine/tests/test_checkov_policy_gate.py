from __future__ import annotations

from pathlib import Path

from repave_engine.blueprint import CheckovGateConfig, load_blueprint
from repave_engine.gate_registry import GateContext
from repave_engine.gate_runners import build_checkov_command, run_checkov
from repave_engine.pipeline import generate_from_blueprint
from repave_engine.settings import OutputConfig


def test_checkov_scan_dir_in_command(tmp_path: Path) -> None:
    fixture = tmp_path / "tests" / "fixtures" / "pass"
    fixture.mkdir(parents=True)
    (fixture / "versions.tf").write_text(
        'terraform { required_version = ">= 1.8.0, < 2.0.0" }\n',
        encoding="utf-8",
    )
    config = CheckovGateConfig(scan_dir="tests/fixtures/pass")
    cmd = build_checkov_command(tmp_path, config)
    assert str(fixture) in cmd[2]


def test_checkov_policy_generate_gate_passes(repo_root: Path, tmp_path: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "checkov-policy-generic", repo_root=repo_root
    )
    staging = tmp_path / "staging"
    output_config = OutputConfig(
        github_org="example",
        modules_root=tmp_path / "modules",
    )
    result = generate_from_blueprint(
        blueprint,
        {
            "policy_name": "estate",
            "organization": "platform",
            "description": "Estate Checkov pack",
        },
        output_config=output_config,
        dry_run=True,
        repo_root=repo_root,
        staging_root=staging,
    )
    out = result.render.output_dir
    policies_dir = out / "policy" / "checkov"
    assert policies_dir.is_dir()
    assert any(policies_dir.glob("*.py")) or any(policies_dir.glob("*.yaml"))
    assert (out / "tests" / "fixtures" / "pass" / "locals.tf").is_file()

    gate = run_checkov(GateContext(output_dir=out, blueprint=blueprint))
    if gate.skipped:
        return
    assert gate.passed, gate.message
