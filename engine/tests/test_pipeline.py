from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from repave_engine.gates import GateResult
from repave_engine.pipeline import generate_from_blueprint, generate_from_path


def test_generate_terraform_module_generic(
    terraform_blueprint,
    sample_inputs,
    tmp_path: Path,
) -> None:
    result = generate_from_blueprint(
        terraform_blueprint,
        sample_inputs,
        output_root=tmp_path,
        dry_run=True,
    )

    output_dir = result.render.output_dir
    assert output_dir.exists()
    assert (output_dir / "main.tf").exists()
    assert (output_dir / "README.md").exists()
    assert "example" in (output_dir / "README.md").read_text(encoding="utf-8")
    assert result.pr_plan is not None
    assert result.pr_plan.branch == "repave/terraform-module-generic/example"
    assert "Dry-run" in result.pr_message
    assert all(g.passed or g.skipped for g in result.gates)


def test_generate_from_path(
    repo_root: Path,
    sample_inputs,
    tmp_path: Path,
) -> None:
    result = generate_from_path(
        repo_root / "blueprints" / "terraform-module-generic",
        sample_inputs,
        repo_root=repo_root,
        output_root=tmp_path,
        dry_run=True,
    )

    assert result.blueprint.name == "terraform-module-generic"
    assert result.render.output_dir.exists()


@patch("repave_engine.pipeline.run_gates")
def test_gate_failure_blocks_pull_request(
    mock_run_gates,
    terraform_blueprint,
    sample_inputs,
    tmp_path: Path,
) -> None:
    mock_run_gates.return_value = [
        GateResult("docs-drift", False, False, "README missing Usage section"),
    ]

    result = generate_from_blueprint(
        terraform_blueprint,
        sample_inputs,
        output_root=tmp_path,
        dry_run=True,
    )

    assert result.pr_plan is None
    assert "Gates failed" in result.pr_message


@patch("repave_engine.pipeline.create_pull_request")
def test_non_dry_run_passes_github_token(
    mock_create_pr,
    terraform_blueprint,
    sample_inputs,
    tmp_path: Path,
) -> None:
    mock_create_pr.return_value = "created"

    result = generate_from_blueprint(
        terraform_blueprint,
        sample_inputs,
        output_root=tmp_path,
        dry_run=False,
        github_token="ghp_test",
    )

    assert result.pr_message == "created"
    mock_create_pr.assert_called_once()
    assert mock_create_pr.call_args.kwargs["github_token"] == "ghp_test"
