from __future__ import annotations

from pathlib import Path

from repave_engine.artifact_blueprint import blueprint_from_repave_file
from repave_engine.blueprint import validate_inputs
from repave_engine.gates import run_gates
from repave_engine.render import render_blueprint


def test_repave_gates_runs_from_provenance_ci_block(
    terraform_blueprint,
    tmp_path: Path,
) -> None:
    values = validate_inputs(
        terraform_blueprint,
        {
            "module_name": "vpc",
            "description": "VPC",
            "cloud_provider": "aws",
            "provider_services": "ec2",
        },
    )
    output_dir = tmp_path / "module"
    render_blueprint(terraform_blueprint, values, output_dir)

    repave = output_dir / "repave.yaml"
    assert repave.is_file()
    blueprint = blueprint_from_repave_file(repave)
    assert "terraform-test" in blueprint.gates

    results = run_gates(output_dir, blueprint.gates, blueprint=blueprint)
    assert all(g.passed or g.skipped for g in results)


def test_cli_gates_exits_zero_on_passing_repo(
    terraform_blueprint,
    tmp_path: Path,
    monkeypatch,
) -> None:
    from repave_engine.cli import cmd_gates

    values = validate_inputs(
        terraform_blueprint,
        {
            "module_name": "vpc",
            "description": "VPC",
            "cloud_provider": "aws",
            "provider_services": "ec2",
        },
    )
    output_dir = tmp_path / "module"
    render_blueprint(terraform_blueprint, values, output_dir)

    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda name: False,
    )
    args = type("Args", (), {"path": str(output_dir)})()
    assert cmd_gates(args) == 0


def test_blueprint_from_repave_requires_ci_gates(tmp_path: Path) -> None:
    path = tmp_path / "repave.yaml"
    path.write_text(
        "---\n"
        "apiVersion: repave.dev/v1beta1\n"
        "kind: GoldenPathArtifact\n"
        "metadata:\n"
        "  name: demo\n"
        "spec:\n"
        "  artifactType: terraform-module\n"
        "  blueprint:\n"
        "    name: terraform-module-generic\n"
        "    version: 0.11.0\n"
        "  standard:\n"
        "    source: standards/terraform-standards\n"
        "    version: 1.1.0\n"
        "  generation:\n"
        "    engine_version: 1.42.0\n"
        "    generated_at: '2026-01-01T00:00:00+00:00'\n"
        "  governance:\n"
        "    baseline_source: standards/policy/governance-baseline.md\n"
        "    baseline_version: 1.0.0\n",
        encoding="utf-8",
    )

    import pytest

    with pytest.raises(ValueError, match=r"ci\.gates is required"):
        blueprint_from_repave_file(path)
