from __future__ import annotations

from repave_engine.gate_registry import ensure_gates_loaded, get_gate


def test_builtin_gates_registered() -> None:
    ensure_gates_loaded()
    for name in ("terraform-fmt", "checkov", "provenance-drift"):
        assert get_gate(name) is not None
