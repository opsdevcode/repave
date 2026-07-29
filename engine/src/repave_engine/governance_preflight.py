"""Form-side governance preflight: gates, policy, repo preview, and gate CLI readiness."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from repave_engine.blueprint import Blueprint, primary_publish_name
from repave_engine.bundle import Bundle
from repave_engine.gate_toolchain import gate_tool_status
from repave_engine.settings import OutputConfig
from repave_engine.target_repo import resolve_module_repository

_GATE_TOOL_HINTS: dict[str, tuple[str, ...]] = {
    "terraform-fmt": ("terraform",),
    "terraform-validate": ("terraform",),
    "terraform-test": ("terraform",),
    "tflint": ("tflint",),
    "checkov": ("checkov",),
    "opa": ("conftest",),
    "azure-policy": ("conftest",),
    "helm-lint": ("helm",),
    "helm-template": ("helm",),
}


@dataclass(frozen=True)
class GovernancePreflight:
    gate_count: int
    gate_names: tuple[str, ...]
    standard_label: str
    policy_profile: str
    example_repo_name: str
    example_repo_url: str
    missing_tools: tuple[str, ...]
    tools_ready: bool

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "gate_count": self.gate_count,
            "gate_names": list(self.gate_names),
            "standard_label": self.standard_label,
            "policy_profile": self.policy_profile,
            "example_repo_name": self.example_repo_name,
            "example_repo_url": self.example_repo_url,
            "missing_tools": list(self.missing_tools),
            "tools_ready": self.tools_ready,
        }


_TEMPLATE_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _example_values(blueprint: Blueprint) -> dict[str, str]:
    values: dict[str, str] = {}
    for field in blueprint.inputs:
        if field.default not in (None, ""):
            values[field.name] = str(field.default)
    values.setdefault("module_name", "example-module")
    values.setdefault("role_name", "example-role")
    values.setdefault("service_name", "example-service")
    for match in _TEMPLATE_PLACEHOLDER.finditer(blueprint.output_repo_name_template):
        key = match.group(1)
        slug = key.replace("_", "-")
        values.setdefault(key, f"example-{slug}")
    return values


def _missing_tools_for_gates(gate_names: tuple[str, ...]) -> tuple[str, ...]:
    status = gate_tool_status()
    needed: set[str] = set()
    for gate in gate_names:
        for tool in _GATE_TOOL_HINTS.get(gate, ()):
            needed.add(tool)
    missing = sorted(tool for tool in needed if not status.get(tool, False))
    return tuple(missing)


def build_blueprint_preflight(
    blueprint: Blueprint,
    *,
    output_config: OutputConfig,
    policy_profile: str = "estate-default",
) -> GovernancePreflight:
    values = _example_values(blueprint)
    module_name = primary_publish_name(blueprint, values)
    repository = resolve_module_repository(
        module_name=module_name,
        config=output_config,
        name_template=blueprint.output_repo_name_template,
        template_values=values,
    )
    gates = tuple(blueprint.gates)
    missing = _missing_tools_for_gates(gates)
    standard = f"{blueprint.standard_source}@{blueprint.standard_version}"
    return GovernancePreflight(
        gate_count=len(gates),
        gate_names=gates,
        standard_label=standard,
        policy_profile=policy_profile,
        example_repo_name=repository.name,
        example_repo_url=repository.web_url,
        missing_tools=missing,
        tools_ready=not missing,
    )


def build_bundle_preflight(
    bundle: Bundle,
    *,
    gate_names: tuple[str, ...],
    total_gate_runs: int,
) -> GovernancePreflight:
    missing = _missing_tools_for_gates(gate_names if gate_names else _STRICT_BUNDLE_GATE_SAMPLE)
    return GovernancePreflight(
        gate_count=total_gate_runs,
        gate_names=gate_names,
        standard_label=f"{len(bundle.members)} member repositories",
        policy_profile="per-member blueprint pins",
        example_repo_name="",
        example_repo_url="",
        missing_tools=missing,
        tools_ready=not missing,
    )


# Representative gates exercised across typical bundle members (terraform + helm + app).
_STRICT_BUNDLE_GATE_SAMPLE: tuple[str, ...] = (
    "terraform-validate",
    "checkov",
    "helm-lint",
)
