"""Tests for gate CLI resolution."""

from __future__ import annotations

import os

from repave_engine.gate_toolchain import ensure_gate_path, resolve_tool, tool_available


def test_resolve_tool_finds_bin_under_standard_dir(tmp_path, monkeypatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "terraform"
    fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(
        "repave_engine.gate_toolchain._STANDARD_BIN_DIRS",
        (str(bin_dir),),
    )
    # Reset path priming so test PATH is honored
    import repave_engine.gate_toolchain as gt

    gt._PATH_PRIMED = False
    assert resolve_tool("terraform") == str(fake)
    assert tool_available("terraform") is True


def test_ensure_gate_path_prepends_standard_dirs(monkeypatch) -> None:
    import repave_engine.gate_toolchain as gt

    gt._PATH_PRIMED = False
    monkeypatch.setenv("PATH", "/custom/bin")
    ensure_gate_path()
    path = os.environ["PATH"]
    assert "/custom/bin" in path
    assert any(prefix in path for prefix in gt._STANDARD_BIN_DIRS)


def test_portal_runtime_info_reads_gate_toolchain_env(monkeypatch) -> None:
    from repave_engine.gate_toolchain import portal_runtime_info

    monkeypatch.delenv("REPAVE_IMAGE_GATE_TOOLCHAIN", raising=False)
    assert "gate_toolchain_image" not in portal_runtime_info()

    monkeypatch.setenv("REPAVE_IMAGE_GATE_TOOLCHAIN", "0")
    assert portal_runtime_info()["gate_toolchain_image"] is False

    monkeypatch.setenv("REPAVE_IMAGE_GATE_TOOLCHAIN", "1")
    assert portal_runtime_info()["gate_toolchain_image"] is True
