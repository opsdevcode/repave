from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from repave_engine.git_clone import (
    FULL_DEPTH,
    CloneError,
    credential_remote,
    is_shallow_update_rejection,
    shallow_clone,
    unshallow,
)
from repave_engine.verify import verify_target


def _git_fixture_remote(tmp_path: Path, *, bare: bool = False) -> str:
    if subprocess.run(["git", "--version"], capture_output=True).returncode != 0:
        pytest.skip("git not installed")
    source = tmp_path / "source"
    source.mkdir()
    if bare:
        (source / "README.md").write_text("fixture\n", encoding="utf-8")
    else:
        (source / "repave.yaml").write_text(
            "apiVersion: repave.dev/v1beta1\nkind: GoldenPathArtifact\n",
            encoding="utf-8",
        )
    for args in (
        ["init", "--initial-branch", "main"],
        ["config", "user.email", "test@repave.dev"],
        ["config", "user.name", "repave test"],
        ["add", "."],
        ["commit", "-m", "fixture"],
    ):
        subprocess.run(["git", *args], cwd=source, check=True, capture_output=True)
    return f"file://{source.resolve()}"


def test_shallow_clone_file_url(tmp_path: Path) -> None:
    remote = _git_fixture_remote(tmp_path)
    dest = tmp_path / "clone"
    shallow_clone(remote, dest)
    assert (dest / "repave.yaml").is_file()


def _clone_args(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("repave_engine.git_clone.run_subprocess", fake_run)
    return calls


def test_shallow_clone_defaults_to_depth_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _clone_args(monkeypatch)
    shallow_clone("https://example.test/acme/mod.git", tmp_path / "dest")

    cmd = calls[0]
    assert "--depth" in cmd
    assert cmd[cmd.index("--depth") + 1] == "1"
    assert "--single-branch" in cmd
    assert "--no-tags" in cmd


def test_full_depth_omits_depth_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _clone_args(monkeypatch)
    shallow_clone(
        "https://example.test/acme/mod.git",
        tmp_path / "dest",
        depth=FULL_DEPTH,
        single_branch=False,
    )

    cmd = calls[0]
    assert "--depth" not in cmd
    assert "--single-branch" not in cmd


def test_full_depth_clone_has_history(tmp_path: Path) -> None:
    remote = _git_fixture_remote(tmp_path)
    dest = tmp_path / "clone"
    shallow_clone(remote, dest, depth=FULL_DEPTH, single_branch=False)

    assert (dest / "repave.yaml").is_file()
    assert not (dest / ".git" / "shallow").exists()


def test_unshallow_converts_shallow_clone(tmp_path: Path) -> None:
    remote = _git_fixture_remote(tmp_path)
    dest = tmp_path / "clone"
    shallow_clone(remote, dest)
    assert (dest / ".git" / "shallow").is_file()

    unshallow(dest)

    assert not (dest / ".git" / "shallow").exists()


def test_unshallow_is_a_noop_on_full_clone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    remote = _git_fixture_remote(tmp_path)
    dest = tmp_path / "clone"
    shallow_clone(remote, dest, depth=FULL_DEPTH, single_branch=False)
    calls = _clone_args(monkeypatch)

    unshallow(dest)

    assert calls == []


def test_is_shallow_update_rejection() -> None:
    assert is_shallow_update_rejection(
        "! [remote rejected] main -> main (shallow update not allowed)"
    )
    assert not is_shallow_update_rejection("! [rejected] main -> main (non-fast-forward)")


def test_credential_remote_preserves_host() -> None:
    url = credential_remote("https://github.example.com/acme/mod.git", "tok")
    assert url.startswith("https://x-access-token:tok@github.example.com/")


def test_clone_redacts_token_in_errors(tmp_path: Path) -> None:
    token = "ghp_testsecrettokenvalue"
    with pytest.raises(CloneError) as excinfo:
        shallow_clone(
            "https://example.invalid/acme/missing.git",
            tmp_path / "dest",
            token=token,
        )
    assert token not in str(excinfo.value)


def test_verify_target_file_remote(
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda _name: False,
    )
    remote = _git_fixture_remote(tmp_path, bare=True)
    result = verify_target(remote, repo_root, blueprint_name="terraform-module-generic")
    assert result.remote
    assert len(result.gates) >= 1
