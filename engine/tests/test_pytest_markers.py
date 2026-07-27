from __future__ import annotations

import pytest


def test_slow_marker_registered() -> None:
    slow = pytest.mark.slow
    assert slow is not None


def test_fast_suite_excludes_slow_integration_tests() -> None:
    """Guardrail: make test-fast must skip conformance + full generate harnesses."""
    from pathlib import Path

    root = Path(__file__).resolve().parent
    slow_modules = (
        "test_blueprint_conformance.py",
        "test_pipeline.py",
        "test_demo_acts.py",
    )
    for name in slow_modules:
        text = (root / name).read_text(encoding="utf-8")
        assert "pytest.mark.slow" in text, f"{name} should declare slow tests"
