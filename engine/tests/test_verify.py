from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from repave_engine.blueprint import validate_inputs
from repave_engine.cli import build_parser, cmd_verify
from repave_engine.render import render_blueprint
from repave_engine.verify import VerifyError, verify_repository, verify_repository_outcome


def test_parser_exposes_verify() -> None:
    args = build_parser().parse_args(["verify", "/tmp/module"])
    assert args.func is cmd_verify
    assert args.format == "text"
    assert args.require_run is False


def test_verify_clone_fails_for_unreachable_host(capsys) -> None:
    args = argparse.Namespace(
        repo_root=".",
        path="https://example.invalid/acme/missing.git",
        blueprint=None,
        format="text",
        require_run=False,
        ref=None,
    )
    assert cmd_verify(args) == 2
    err = capsys.readouterr().err
    assert "example.invalid" in err or "clone" in err.lower()


def test_verify_requires_blueprint_without_provenance(tmp_path: Path, repo_root: Path) -> None:
    with pytest.raises(VerifyError, match=r"repave\.yaml is missing"):
        verify_repository(tmp_path, repo_root)


def test_verify_repository_outcome_returns_error_without_raising(
    tmp_path: Path,
    repo_root: Path,
) -> None:
    outcome = verify_repository_outcome(tmp_path, repo_root)
    assert not outcome.ok
    assert outcome.error is not None
    assert outcome.result is None
    assert "repave.yaml is missing" in str(outcome.error)


def test_verify_runs_gates_and_reports_pin_drift(
    terraform_blueprint,
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda _name: False,
    )
    values = validate_inputs(
        terraform_blueprint,
        {
            "module_name": "vpc",
            "description": "VPC",
            "cloud_provider": "aws",
            "provider_services": "ec2",
        },
    )
    module_dir = tmp_path / "module"
    render_blueprint(terraform_blueprint, values, module_dir)

    # Force an older pin than the catalog blueprint carries today.
    repave = module_dir / "repave.yaml"
    text = repave.read_text(encoding="utf-8")
    repave.write_text(
        text.replace(
            f"version: {terraform_blueprint.version}",
            "version: 0.0.1",
            1,
        ),
        encoding="utf-8",
    )

    result = verify_repository(module_dir, repo_root)
    assert result.provenance_present
    assert result.catalog_blueprint_name == terraform_blueprint.name
    assert result.gates_passed
    assert not result.pins_aligned
    assert any(row.field == "Blueprint version" for row in result.pin_changes)
    assert not result.ok


def test_verify_cli_json_ok_when_pins_aligned(
    terraform_blueprint,
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda _name: False,
    )
    values = validate_inputs(
        terraform_blueprint,
        {
            "module_name": "vpc",
            "description": "VPC",
            "cloud_provider": "aws",
            "provider_services": "ec2",
        },
    )
    module_dir = tmp_path / "module"
    render_blueprint(terraform_blueprint, values, module_dir)

    args = argparse.Namespace(
        repo_root=str(repo_root),
        path=str(module_dir),
        blueprint=None,
        format="json",
        require_run=False,
        ref=None,
    )
    assert cmd_verify(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["pins_aligned"] is True
    assert payload["gates_passed"] is True


def test_verify_without_provenance_uses_catalog_gates(
    terraform_blueprint,
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda _name: False,
    )
    values = validate_inputs(
        terraform_blueprint,
        {
            "module_name": "vpc",
            "description": "VPC",
            "cloud_provider": "aws",
            "provider_services": "ec2",
        },
    )
    module_dir = tmp_path / "bare"
    render_blueprint(terraform_blueprint, values, module_dir)
    (module_dir / "repave.yaml").unlink()

    result = verify_repository(
        module_dir,
        repo_root,
        blueprint_name=terraform_blueprint.name,
    )
    assert not result.provenance_present
    assert result.pins_aligned
    assert len(result.gates) == len(terraform_blueprint.gates)
