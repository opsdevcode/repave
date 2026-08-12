from __future__ import annotations

import argparse
import json
from unittest.mock import patch

import pytest

from repave_engine.cli import (
    _parse_inputs,
    build_parser,
    cmd_create_repo,
    cmd_generate,
    cmd_list,
    cmd_serve,
    cmd_update,
    main,
)
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


def test_cmd_create_repo_maps_to_generate(repo_root, output_config, tmp_path) -> None:
    args = argparse.Namespace(
        repo_root=str(repo_root),
        name="platform-demo",
        mode="template",
        template="example-org/template-service",
        visibility="private",
        description="demo",
        topics="platform",
        team=["platform-admins", "developers"],
        team_permission="push",
        default_branch="main",
        ruleset_profile="default-pr",
        membership_source_team="platform",
        sync_team_membership=True,
        dry_run=True,
        github_token=None,
        github_org=output_config.github_org,
        modules_root=str(output_config.modules_root),
        staging_root=str(tmp_path / "staging"),
    )
    with patch("repave_engine.cli.create_repo.cmd_generate", return_value=0) as generate:
        code = cmd_create_repo(args)
    assert code == 0
    generate_args = generate.call_args.args[0]
    assert generate_args.blueprint == "blueprints/github-repo-generic"
    assert "repo_name=platform-demo" in generate_args.input
    assert "create_mode=template" in generate_args.input
    assert "template_owner=example-org" in generate_args.input
    assert "template_repo=template-service" in generate_args.input
    assert "team_slugs=platform-admins,developers" in generate_args.input
    assert "ruleset_profile=default-pr" in generate_args.input
    assert "membership_source_team=platform" in generate_args.input
    assert "sync_team_membership=true" in generate_args.input


def test_build_parser_includes_create_repo() -> None:
    parser = build_parser()
    args = parser.parse_args(
        ["create-repo", "--name", "demo", "--team", "platform", "--repo-root", "."]
    )
    assert args.func is cmd_create_repo
    assert args.name == "demo"
    assert args.team == ["platform"]


def test_build_parser_import_batch_search_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "import",
            "placeholder",
            "--batch-file",
            "repos.txt",
            "--org",
            "acme",
            "--language",
            "HCL",
            "--pushed-since",
            "2026-01-01",
            "--include-archived",
            "--include-forks",
        ]
    )
    assert args.batch_file == "repos.txt"
    assert args.org == "acme"
    assert args.language == "HCL"
    assert args.pushed_since == "2026-01-01"
    assert args.include_archived is True
    assert args.include_forks is True


def test_parse_inputs_invalid() -> None:
    with pytest.raises(ValueError, match="Invalid --input value"):
        _parse_inputs(["not-valid"])


def test_cmd_list_prints_blueprints(repo_root, capsys) -> None:
    args = argparse.Namespace(repo_root=str(repo_root))
    code = cmd_list(args)
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert any(item["name"] == "terraform-module-generic" for item in output)


@pytest.mark.slow
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
    assert "ec2_diff.tf" in output
    assert "s3_bucket.tf" in output


@pytest.mark.slow
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
        repo_root=repo_root,
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


@pytest.mark.slow
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
        repo_root=repo_root,
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


@pytest.mark.slow
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
        repo_root=repo_root,
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


@pytest.mark.slow
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
        repo_root=repo_root,
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


def test_cmd_serve_builds_app_and_starts_uvicorn(
    repo_root,
    output_config,
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_create_app(*, repo_root, output_config):
        captured["repo_root"] = repo_root
        captured["output_config"] = output_config
        return "app"

    def fake_uvicorn_run(app, *, host, port):
        captured["app"] = app
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr("repave_engine.api.create_app", fake_create_app)
    monkeypatch.setattr("uvicorn.run", fake_uvicorn_run)

    args = argparse.Namespace(
        repo_root=str(repo_root),
        github_org=output_config.github_org,
        modules_root=str(output_config.modules_root),
        host="0.0.0.0",
        port=9000,
        reload=False,
    )

    code = cmd_serve(args)

    assert code == 0
    assert captured["app"] == "app"
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 9000


def test_build_parser_includes_update_subcommand() -> None:
    parser = build_parser()
    args = parser.parse_args(
        ["update", "--path", "/tmp/module", "--repo-root", ".", "--format", "json"]
    )
    assert args.command == "update"
    assert args.target_repo == "/tmp/module"
    assert args.dry_run is True


def test_cmd_update_dry_run_delegates_to_plan(repo_root, tmp_path, capsys) -> None:
    fixture = repo_root / "operator" / "testdata" / "modules" / "terraform-minimal"
    if not fixture.is_dir():
        pytest.skip("operator fixture not present")

    args = argparse.Namespace(
        repo_root=str(repo_root),
        target_repo=str(fixture),
        blueprint=None,
        staging_root=str(tmp_path / "staging"),
        format="json",
        dry_run=True,
        git_branch=None,
        commit_message="chore(repave): apply blueprint upgrade",
    )
    code = cmd_update(args)
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert output["changed_file_count"] >= 1


def test_cmd_update_apply_requires_git_branch(repo_root) -> None:
    args = argparse.Namespace(
        repo_root=str(repo_root),
        target_repo="/tmp/module",
        blueprint=None,
        staging_root=None,
        format="text",
        dry_run=False,
        git_branch=None,
        commit_message="chore(repave): apply blueprint upgrade",
    )
    with pytest.raises(SystemExit, match="git-branch"):
        cmd_update(args)


def test_cmd_update_open_pr_requires_token(repo_root) -> None:
    args = argparse.Namespace(
        repo_root=str(repo_root),
        target_repo="/tmp/module",
        blueprint=None,
        staging_root=None,
        format="text",
        dry_run=False,
        git_branch="repave/upgrade",
        commit_message="chore(repave): apply blueprint upgrade",
        open_pr=True,
        base_branch="main",
        github_token=None,
    )
    with pytest.raises(SystemExit, match="--open-pr requires"):
        cmd_update(args)
