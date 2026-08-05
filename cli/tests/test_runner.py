"""The local IaC runner. A fake binary stands in for tofu so tests need no toolchain."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from repave_cli.runner import IacRunner, RunnerError, plan_change_counts


def _fake_binary(tmp_path: Path, script: str) -> Path:
    path = tmp_path / "fake-tofu"
    path.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _runner(tmp_path: Path, script: str, **kwargs: object) -> IacRunner:
    binary = _fake_binary(tmp_path, script)
    return IacRunner(workdir=tmp_path, binary=str(binary), **kwargs)  # type: ignore[arg-type]


def test_run_returns_stdout_on_success(tmp_path: Path) -> None:
    runner = _runner(tmp_path, 'echo "hello $1"')
    result = runner.run("world")
    assert result.ok
    assert result.stdout.strip() == "hello world"


def test_run_raises_with_the_tools_own_stderr(tmp_path: Path) -> None:
    runner = _runner(tmp_path, 'echo "provider exploded" >&2; exit 3')
    with pytest.raises(RunnerError, match="provider exploded"):
        runner.run("apply")


def test_run_can_return_a_failure_without_raising(tmp_path: Path) -> None:
    runner = _runner(tmp_path, "exit 4")
    result = runner.run("apply", check=False)
    assert not result.ok
    assert result.returncode == 4


def test_a_missing_binary_names_the_fix(tmp_path: Path) -> None:
    runner = IacRunner(workdir=tmp_path, binary=str(tmp_path / "absent"))
    with pytest.raises(RunnerError, match="not on PATH"):
        runner.run("version")


def test_a_timeout_names_the_flag(tmp_path: Path) -> None:
    runner = _runner(tmp_path, "sleep 5", timeout=1)
    with pytest.raises(RunnerError, match="--timeout"):
        runner.run("apply")


def test_show_plan_json_parses_output(tmp_path: Path) -> None:
    payload = {"resource_changes": [{"address": "a.b", "change": {"actions": ["create"]}}]}
    runner = _runner(tmp_path, f"cat <<'EOF'\n{json.dumps(payload)}\nEOF")
    assert runner.show_plan_json(tmp_path / "plan") == payload


def test_show_plan_json_rejects_non_json(tmp_path: Path) -> None:
    runner = _runner(tmp_path, 'echo "not json"')
    with pytest.raises(RunnerError, match="did not return JSON"):
        runner.show_plan_json(tmp_path / "plan")


def test_show_plan_json_returns_empty_for_a_json_array(tmp_path: Path) -> None:
    runner = _runner(tmp_path, "echo '[]'")
    assert runner.show_plan_json(tmp_path / "plan") == {}


def test_providers_schema_rejects_non_json(tmp_path: Path) -> None:
    runner = _runner(tmp_path, 'echo "nope"')
    with pytest.raises(RunnerError, match="did not return JSON"):
        runner.providers_schema()


def test_state_pull_returns_bytes(tmp_path: Path) -> None:
    runner = _runner(tmp_path, "echo '{\"version\": 4}'")
    assert runner.state_pull().strip() == b'{"version": 4}'


def test_plan_writes_to_the_requested_file(tmp_path: Path) -> None:
    runner = _runner(tmp_path, 'echo "$@" > argv.txt')
    plan_file = tmp_path / "out.tfplan"
    runner.plan(plan_file)
    assert str(plan_file) in (tmp_path / "argv.txt").read_text(encoding="utf-8")


def test_apply_passes_auto_approve(tmp_path: Path) -> None:
    runner = _runner(tmp_path, 'echo "$@" > argv.txt')
    runner.apply(tmp_path / "out.tfplan")
    assert "-auto-approve" in (tmp_path / "argv.txt").read_text(encoding="utf-8")


def test_init_runs_non_interactive(tmp_path: Path) -> None:
    runner = _runner(tmp_path, 'echo "$@" > argv.txt')
    runner.init()
    assert "-input=false" in (tmp_path / "argv.txt").read_text(encoding="utf-8")


def test_commands_run_in_the_working_directory(tmp_path: Path) -> None:
    workdir = tmp_path / "stack"
    workdir.mkdir()
    binary = _fake_binary(tmp_path, "pwd")
    runner = IacRunner(workdir=workdir, binary=str(binary))
    assert os.path.realpath(runner.run("version").stdout.strip()) == os.path.realpath(workdir)


def test_name_falls_back_to_the_resolved_binary(tmp_path: Path) -> None:
    assert IacRunner(workdir=tmp_path).name in ("tofu", "terraform")


# -- plan summary -----------------------------------------------------------


def test_plan_change_counts_by_action() -> None:
    payload = {
        "resource_changes": [
            {"address": "a.one", "change": {"actions": ["create"]}},
            {"address": "b.two", "change": {"actions": ["update"]}},
            {"address": "c.three", "change": {"actions": ["delete"]}},
            {"address": "d.four", "change": {"actions": ["no-op"]}},
        ]
    }
    assert plan_change_counts(payload) == (1, 1, 1)


def test_plan_change_counts_treats_replace_as_create_and_delete() -> None:
    payload = {
        "resource_changes": [{"address": "a.b", "change": {"actions": ["delete", "create"]}}]
    }
    assert plan_change_counts(payload) == (1, 0, 1)


def test_plan_change_counts_tolerates_garbage() -> None:
    assert plan_change_counts(None) == (0, 0, 0)
    assert plan_change_counts({"resource_changes": "nope"}) == (0, 0, 0)
    assert plan_change_counts({"resource_changes": [{}, {"change": None}]}) == (0, 0, 0)
