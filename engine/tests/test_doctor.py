from __future__ import annotations

from unittest.mock import patch

from repave_engine.doctor import CORE_GATE_TOOLS, ToolCheckResult, check_tools, doctor_exit_code


def test_core_gate_tools_match_installer() -> None:
    assert CORE_GATE_TOOLS == (
        "terraform",
        "tflint",
        "checkov",
        "conftest",
        "helm",
        "ansible-lint",
        "infracost",
    )


def test_tools_for_helm_blueprint_includes_actionlint(repo_root) -> None:
    from repave_engine.blueprint import load_blueprint
    from repave_engine.doctor import tools_for_blueprint

    blueprint = load_blueprint(
        repo_root / "blueprints" / "helm-chart-generic",
        repo_root=repo_root,
    )
    assert "actionlint" in tools_for_blueprint(blueprint)


def test_doctor_exit_code_strict_missing() -> None:
    results = (
        ToolCheckResult(
            tool="terraform",
            present=False,
            detected_version=None,
            pinned_version="1.9.8",
            version_match=None,
            install_hint="hint",
        ),
    )
    assert doctor_exit_code(results, strict=True) == 1
    assert doctor_exit_code(results, strict=False) == 0


def test_doctor_exit_code_strict_unrunnable_pin() -> None:
    results = (
        ToolCheckResult(
            tool="checkov",
            present=True,
            detected_version=None,
            pinned_version="3.0.0",
            version_match=None,
            install_hint="hint",
        ),
    )
    assert doctor_exit_code(results, strict=True) == 1
    assert doctor_exit_code(results, strict=False) == 0


def test_doctor_exit_code_strict_mismatch() -> None:
    results = (
        ToolCheckResult(
            tool="terraform",
            present=True,
            detected_version="1.0.0",
            pinned_version="1.9.8",
            version_match=False,
            install_hint="hint",
        ),
    )
    assert doctor_exit_code(results, strict=True) == 1


def test_check_tools_uses_gate_toolchain() -> None:
    with (
        patch("repave_engine.doctor._tool_present", return_value=True),
        patch("repave_engine.doctor._detect_version", return_value="1.9.8"),
    ):
        rows = check_tools(("terraform",))
    assert rows[0].present is True
    assert rows[0].version_match is True
