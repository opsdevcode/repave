from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from repave_engine.git_clone import CloneError, credential_remote, shallow_clone
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
