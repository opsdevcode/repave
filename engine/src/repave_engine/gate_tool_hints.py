"""Map gate ids to gate-toolchain CLI names (portal preflight and repave doctor)."""

from __future__ import annotations

GATE_TOOL_HINTS: dict[str, tuple[str, ...]] = {
    "terraform-fmt": ("terraform",),
    "terraform-validate": ("terraform",),
    "terraform-test": ("terraform",),
    "tflint": ("tflint",),
    "infracost": ("infracost",),
    "checkov": ("checkov",),
    "opa": ("conftest",),
    "azure-policy": ("conftest",),
    "helm-lint": ("helm",),
    "helm-template": ("helm",),
    "yamllint": ("yamllint",),
    "dockerfile-lint": ("hadolint",),
    "actionlint": ("actionlint",),
    "ansible-lint": ("ansible-lint",),
    "ansible-syntax-check": ("ansible-playbook",),
    "molecule": ("molecule",),
    "python-lint": ("ruff",),
    "python-test": ("pytest",),
    "go-lint": ("go",),
    "go-test": ("go",),
    "node-lint": ("node", "npm"),
    "node-test": ("node", "npm"),
    "java-build": ("mvn", "java"),
    "dotnet-test": ("dotnet",),
    "promtool": ("promtool",),
    "amtool": ("amtool",),
}


def tools_for_gate_names(gate_names: tuple[str, ...]) -> tuple[str, ...]:
    needed: set[str] = set()
    for gate in gate_names:
        for tool in GATE_TOOL_HINTS.get(gate, ()):
            needed.add(tool)
    return tuple(sorted(needed))
