from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from repave_engine.iac_binary import (
    IAC_BINARIES,
    IAC_BINARY_ENV,
    IacBinary,
    iac_argv,
    iac_binary_name,
    iac_binary_preference,
    iac_cli_ready,
    resolve_iac_binary,
)


def _fake_resolver(available: set[str]):
    def resolve(name: str) -> str | None:
        return f"/usr/local/bin/{name}" if name in available else None

    return resolve


def test_preference_puts_opentofu_first() -> None:
    assert IAC_BINARIES[0] == "tofu"
    assert iac_binary_preference() == ("tofu", "terraform")


def test_env_pin_narrows_preference(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(IAC_BINARY_ENV, "terraform")
    assert iac_binary_preference() == ("terraform",)


def test_env_pin_rejects_unknown_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(IAC_BINARY_ENV, "pulumi")
    with pytest.raises(ValueError, match="REPAVE_IAC_BINARY"):
        iac_binary_preference()


def test_resolve_prefers_tofu_when_both_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(IAC_BINARY_ENV, raising=False)
    monkeypatch.setattr(
        "repave_engine.iac_binary.resolve_tool", _fake_resolver({"tofu", "terraform"})
    )
    binary = resolve_iac_binary()
    assert binary == IacBinary(name="tofu", path="/usr/local/bin/tofu")
    assert binary is not None and binary.is_opentofu


def test_resolve_falls_back_to_terraform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(IAC_BINARY_ENV, raising=False)
    monkeypatch.setattr("repave_engine.iac_binary.resolve_tool", _fake_resolver({"terraform"}))
    binary = resolve_iac_binary()
    assert binary is not None
    assert binary.name == "terraform"
    assert not binary.is_opentofu


def test_resolve_returns_none_when_neither_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(IAC_BINARY_ENV, raising=False)
    monkeypatch.setattr("repave_engine.iac_binary.resolve_tool", _fake_resolver(set()))
    assert resolve_iac_binary() is None


def test_binary_name_falls_back_to_preferred_when_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(IAC_BINARY_ENV, raising=False)
    monkeypatch.setattr("repave_engine.iac_binary.resolve_tool", _fake_resolver(set()))
    assert iac_binary_name() == "tofu"


def test_iac_argv_leads_with_resolved_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(IAC_BINARY_ENV, raising=False)
    monkeypatch.setattr("repave_engine.iac_binary.resolve_tool", _fake_resolver({"terraform"}))
    assert iac_argv("plan", "-input=false") == ["terraform", "plan", "-input=false"]


def test_cli_ready_false_without_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(IAC_BINARY_ENV, raising=False)
    monkeypatch.setattr("repave_engine.iac_binary.resolve_tool", _fake_resolver(set()))
    assert iac_cli_ready() is False


def test_cli_ready_runs_version(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(IAC_BINARY_ENV, raising=False)
    monkeypatch.setattr("repave_engine.iac_binary.resolve_tool", _fake_resolver({"tofu"}))
    seen: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.append(cmd)
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="OpenTofu v1.9", stderr=""
        )

    monkeypatch.setattr("repave_engine.iac_binary.run_subprocess", fake_run)
    assert iac_cli_ready(tmp_path) is True
    assert seen == [["/usr/local/bin/tofu", "version"]]


def test_cli_ready_false_on_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(IAC_BINARY_ENV, raising=False)
    monkeypatch.setattr("repave_engine.iac_binary.resolve_tool", _fake_resolver({"tofu"}))

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr("repave_engine.iac_binary.run_subprocess", fake_run)
    assert iac_cli_ready() is False
