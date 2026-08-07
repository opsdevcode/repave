"""Blueprint gate ids must be registered; demo paths must map to installable CLIs."""

from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.blueprint import blueprints_dir, list_blueprints, load_blueprint
from repave_engine.doctor import CORE_GATE_TOOLS, tools_for_blueprint
from repave_engine.gate_registry import registered_gate_names
from repave_engine.gate_tool_hints import GATE_TOOL_HINTS

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Seven-minute demo acts (docs/seven-minute-demo.md).
_DEMO_BLUEPRINTS = (
    "terraform-module-generic",
    "opa-policy-generic",
)

# Gates that run in-process or need no external CLI (doctor / worker image).
_NO_CLI_GATES = frozenset(
    {
        "docs-drift",
        "provenance-drift",
        "secrets",
        "grafana-dashboard",
        "datadog-dashboard",
        "datadog-monitor",
    }
)

# Installed by deploy/local/install-gate-toolchain.sh (default flags).
_INSTALLER_TOOLS = frozenset(
    {
        *CORE_GATE_TOOLS,
        "infracost",
        "ansible-lint",
        "ansible-playbook",
        "yamllint",
        "actionlint",
        "buf",
        "kubectl",
    }
)


def _blueprint_dirs(repo_root: Path) -> list[Path]:
    return [blueprint.path for blueprint in list_blueprints(blueprints_dir(repo_root))]


@pytest.mark.parametrize("blueprint_dir", _blueprint_dirs(_REPO_ROOT), ids=lambda p: p.name)
def test_blueprint_gates_are_registered(blueprint_dir: Path) -> None:
    blueprint = load_blueprint(blueprint_dir, repo_root=_REPO_ROOT)
    registered = registered_gate_names()
    unknown = [gate for gate in blueprint.gates if gate not in registered]
    assert not unknown, f"{blueprint_dir.name}: unknown gates {unknown}"


@pytest.mark.parametrize("blueprint_name", _DEMO_BLUEPRINTS)
def test_demo_blueprint_gate_tools_are_installable(repo_root: Path, blueprint_name: str) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / blueprint_name,
        repo_root=repo_root,
    )
    required_tools = tools_for_blueprint(blueprint)
    missing_hints = [
        gate
        for gate in blueprint.gates
        if gate not in GATE_TOOL_HINTS and gate not in _NO_CLI_GATES
    ]
    assert not missing_hints, (
        f"{blueprint_name}: add GATE_TOOL_HINTS for {missing_hints} "
        "or mark as no-CLI in test_blueprint_gate_toolchain.py"
    )
    not_installed = [tool for tool in required_tools if tool not in _INSTALLER_TOOLS]
    assert not not_installed, (
        f"{blueprint_name}: gate tools {not_installed} are not installed by "
        "deploy/local/install-gate-toolchain.sh"
    )


def test_opa_gate_uses_conftest_not_opa_binary() -> None:
    assert GATE_TOOL_HINTS["opa"] == ("conftest",)
