from __future__ import annotations

import argparse
import json

import pytest

from repave_engine.cli import _parse_inputs, build_parser, cmd_generate, cmd_list, main
from repave_engine.gates import GateResult
from repave_engine.pipeline import GenerationResult
from repave_engine.render import RenderResult


def _generate_args(repo_root, sample_inputs, output_config, tmp_path, **overrides):
    defaults = {
        "repo_root": str(repo_root),
        "blueprint": "blueprints/terraform-module-generic",
        "input": [f"{key}={value}" for key, value in sample_inputs.items()],
        "staging_root": str(tmp_path / "staging"),
        "dry_run": True,
        "github_token": None,
        "github_org": output_config.github_org,
        "modules_root": str(output_config.modules_root),
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_parse_inputs_valid() -> None:
    values = _parse_inputs(["module_name=example", "description=test module"])
    assert values == {"module_name": "example", "description": "test module"}


def test_parse_inputs_invalid() -> None:
    with pytest.raises(ValueError, match="Invalid --input value"):
        _parse_inputs(["not-valid"])


def test_cmd_list_prints_blueprints(repo_root, capsys) -> None:
    args = argparse.Namespace(repo_root=str(repo_root))
    code = cmd_list(args)
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert any(item["name"] == "terraform-module-generic" for item in output)


def test_cmd_generate_exit_code_success(
    repo_root,
    sample_inputs,
    output_config,
    tmp_path,
    capsys,
) -> None:
    code = cmd_generate(_generate_args(repo_root, sample_inputs, output_config, tmp_path))
    output = capsys.readouterr().out

    assert code == 0
    assert "terraform-module-generic" in output
    assert "tf-aws-example" in output
    assert "Dry-run" in output
    assert "Generated files:" in output
    assert "main.tf" in output


def test_cmd_generate_uses_github_token_from_env_when_not_dry_run(
    repo_root,
    sample_inputs,
    output_config,
    tmp_path,
    monkeypatch,
) -> None:
    from repave_engine.blueprint import load_blueprint

    monkeypatch.setenv("GITHUB_TOKEN", "ghp_from_env")
    captured: dict[str, object] = {}
    blueprint = load_blueprint(
        repo_root / "blueprints" / "terraform-module-generic",
        repo_root,
    )

    def fake_generate_from_path(*_args, **kwargs):
        captured["github_token"] = kwargs.get("github_token")
        return GenerationResult(
            blueprint=blueprint,
            render=RenderResult(output_dir=tmp_path / "staging", values={}),
            gates=[],
            module_repository=None,
            pr_plan=None,
            pr_message="published",
        )

    monkeypatch.setattr("repave_engine.cli.generate_from_path", fake_generate_from_path)

    code = cmd_generate(
        _generate_args(repo_root, sample_inputs, output_config, tmp_path, dry_run=False)
    )

    assert code == 0
    assert captured["github_token"] == "ghp_from_env"


def test_cmd_generate_clears_github_token_on_dry_run(
    repo_root,
    sample_inputs,
    output_config,
    tmp_path,
    monkeypatch,
) -> None:
    from repave_engine.blueprint import load_blueprint

    monkeypatch.setenv("GITHUB_TOKEN", "ghp_from_env")
    captured: dict[str, object] = {}
    blueprint = load_blueprint(
        repo_root / "blueprints" / "terraform-module-generic",
        repo_root,
    )

    def fake_generate_from_path(*_args, **kwargs):
        captured["github_token"] = kwargs.get("github_token")
        return GenerationResult(
            blueprint=blueprint,
            render=RenderResult(output_dir=tmp_path / "staging", values={}),
            gates=[],
            module_repository=None,
            pr_plan=None,
            pr_message="dry-run",
        )

    monkeypatch.setattr("repave_engine.cli.generate_from_path", fake_generate_from_path)

    code = cmd_generate(
        _generate_args(repo_root, sample_inputs, output_config, tmp_path, dry_run=True)
    )

    assert code == 0
    assert captured["github_token"] is None


def test_cmd_generate_prefers_cli_token_over_env(
    repo_root,
    sample_inputs,
    output_config,
    tmp_path,
    monkeypatch,
) -> None:
    from repave_engine.blueprint import load_blueprint

    monkeypatch.setenv("GITHUB_TOKEN", "ghp_from_env")
    captured: dict[str, object] = {}
    blueprint = load_blueprint(
        repo_root / "blueprints" / "terraform-module-generic",
        repo_root,
    )

    def fake_generate_from_path(*_args, **kwargs):
        captured["github_token"] = kwargs.get("github_token")
        return GenerationResult(
            blueprint=blueprint,
            render=RenderResult(output_dir=tmp_path / "staging", values={}),
            gates=[],
            module_repository=None,
            pr_plan=None,
            pr_message="published",
        )

    monkeypatch.setattr("repave_engine.cli.generate_from_path", fake_generate_from_path)

    code = cmd_generate(
        _generate_args(
            repo_root,
            sample_inputs,
            output_config,
            tmp_path,
            dry_run=False,
            github_token="ghp_cli",
        )
    )

    assert code == 0
    assert captured["github_token"] == "ghp_cli"


def test_cmd_generate_exit_code_on_gate_failure(
    repo_root,
    sample_inputs,
    output_config,
    tmp_path,
    capsys,
    monkeypatch,
) -> None:
    from repave_engine.blueprint import load_blueprint

    blueprint = load_blueprint(
        repo_root / "blueprints" / "terraform-module-generic",
        repo_root,
    )

    def fake_generate(*args, **kwargs):
        return GenerationResult(
            blueprint=blueprint,
            render=RenderResult(output_dir=tmp_path / "staging", values={}),
            gates=[GateResult("docs-drift", False, False, "failed")],
            module_repository=None,
            pr_plan=None,
            pr_message="Gates failed; module repository not updated.",
        )

    monkeypatch.setattr("repave_engine.cli.generate_from_path", fake_generate)

    code = cmd_generate(_generate_args(repo_root, sample_inputs, output_config, tmp_path))

    assert code == 1
    assert "FAIL" in capsys.readouterr().out


def test_build_parser_requires_command() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_main_runs_list_command(repo_root, capsys) -> None:
    code = main(["--repo-root", str(repo_root), "list"])
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert isinstance(output, list)


def test_main_accepts_repo_root_after_subcommand(repo_root, capsys) -> None:
    code = main(["list", "--repo-root", str(repo_root)])
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert any(item["name"] == "terraform-module-generic" for item in output)
