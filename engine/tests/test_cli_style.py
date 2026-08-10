from __future__ import annotations

import io

import pytest

from repave_engine.cli._style import brand, color_enabled, gate_status, heading


def test_color_disabled_when_no_color(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    stream = io.StringIO()
    assert color_enabled(stream=stream) is False
    assert brand("repave", stream=stream) == "repave"
    assert heading("Blueprint:", stream=stream) == "Blueprint:"
    assert gate_status("PASS", stream=stream) == "PASS"


def test_color_enabled_with_force_color(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")
    stream = io.StringIO()
    assert color_enabled(stream=stream) is True
    assert "\033[" in brand("path", stream=stream)
    assert "\033[" in heading("Blueprint:", stream=stream)
    assert "\033[" in gate_status("PASS", stream=stream)
    assert "PASS" in gate_status("PASS", stream=stream)
    assert "FAIL" in gate_status("FAIL", stream=stream)
