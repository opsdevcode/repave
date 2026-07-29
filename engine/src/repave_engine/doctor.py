"""Gate toolchain preflight: CLI presence and pin alignment."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repave_engine import ci_toolchain
from repave_engine.blueprint import Blueprint, load_blueprint
from repave_engine.gate_tool_hints import tools_for_gate_names
from repave_engine.gate_toolchain import checkov_argv, resolve_tool, terraform_cli_ready
from repave_engine.subprocess_run import run_subprocess

_INSTALL_HINT = (
    "Install pinned gate CLIs with deploy/local/install-gate-toolchain.sh "
    "(see deploy/local/README.md) or use deploy/local Docker Compose."
)

_PIN_BY_TOOL: dict[str, str] = {
    "terraform": ci_toolchain.TERRAFORM_VERSION,
    "tflint": ci_toolchain.TFLINT_VERSION,
    "checkov": ci_toolchain.CHECKOV_VERSION,
    "conftest": ci_toolchain.CONFTEST_VERSION,
    "helm": ci_toolchain.HELM_VERSION,
    "hadolint": ci_toolchain.HADOLINT_VERSION,
    "go": ci_toolchain.GO_VERSION,
}

# Matches deploy/local/install-gate-toolchain.sh (CI, Compose, and Release).
CORE_GATE_TOOLS: tuple[str, ...] = (
    "terraform",
    "tflint",
    "checkov",
    "conftest",
    "helm",
)

_DEFAULT_TOOLS: tuple[str, ...] = CORE_GATE_TOOLS


@dataclass(frozen=True)
class ToolCheckResult:
    tool: str
    present: bool
    detected_version: str | None
    pinned_version: str | None
    version_match: bool | None
    install_hint: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "present": self.present,
            "detected_version": self.detected_version,
            "pinned_version": self.pinned_version,
            "version_match": self.version_match,
            "install_hint": self.install_hint if not self.present else "",
        }


def _normalize_version(raw: str) -> str:
    cleaned = raw.strip().lstrip("vV")
    match = re.search(r"(\d+(?:\.\d+)*)", cleaned)
    return match.group(1) if match else cleaned


def _versions_match(detected: str, pinned: str) -> bool:
    return _normalize_version(detected) == _normalize_version(pinned)


def _detect_version(tool: str) -> str | None:
    if tool == "terraform":
        if not terraform_cli_ready():
            return None
        argv = [resolve_tool("terraform") or "terraform", "version"]
    elif tool == "checkov":
        argv_prefix = checkov_argv()
        if argv_prefix is None:
            return None
        argv = [*argv_prefix, "--version"]
    else:
        binary = resolve_tool(tool)
        if not binary:
            return None
        argv = [binary, "--version"]
    try:
        result = run_subprocess(argv, cwd=None, timeout=15, git=False)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    text = (result.stdout or result.stderr or "").strip()
    if not text:
        return None
    first = text.splitlines()[0]
    return _normalize_version(first) or first[:80]


def _tool_present(tool: str) -> bool:
    if tool == "terraform":
        return terraform_cli_ready()
    if tool == "checkov":
        return checkov_argv() is not None
    return resolve_tool(tool) is not None


def check_tools(tools: tuple[str, ...]) -> tuple[ToolCheckResult, ...]:
    results: list[ToolCheckResult] = []
    for tool in tools:
        pinned = _PIN_BY_TOOL.get(tool)
        present = _tool_present(tool)
        detected = _detect_version(tool) if present else None
        version_match: bool | None = None
        if present and pinned and detected:
            version_match = _versions_match(detected, pinned)
        results.append(
            ToolCheckResult(
                tool=tool,
                present=present,
                detected_version=detected,
                pinned_version=pinned,
                version_match=version_match,
                install_hint=_INSTALL_HINT,
            )
        )
    return tuple(results)


def tools_for_blueprint(blueprint: Blueprint) -> tuple[str, ...]:
    scoped = tools_for_gate_names(tuple(blueprint.gates))
    pinned = [tool for tool in scoped if tool in _PIN_BY_TOOL]
    extras = [tool for tool in scoped if tool not in _PIN_BY_TOOL]
    return tuple([*sorted(pinned), *sorted(extras)])


def run_doctor(
    *,
    tools: tuple[str, ...] | None = None,
    all_pins: bool = False,
) -> tuple[ToolCheckResult, ...]:
    if tools is not None:
        selected = tools
    elif all_pins:
        selected = tuple(_PIN_BY_TOOL)
    else:
        selected = _DEFAULT_TOOLS
    return check_tools(selected)


def doctor_exit_code(results: tuple[ToolCheckResult, ...], *, strict: bool) -> int:
    if not strict:
        return 0
    for row in results:
        if not row.present:
            return 1
        if row.pinned_version and row.version_match is False:
            return 1
    return 0


def format_doctor_report(results: tuple[ToolCheckResult, ...]) -> str:
    lines: list[str] = []
    for row in results:
        if not row.present:
            status = "MISSING"
        elif row.version_match is False:
            status = "MISMATCH"
        elif row.version_match is True:
            status = "OK"
        else:
            status = "OK" if row.present else "MISSING"
        pin = f" (pin {row.pinned_version})" if row.pinned_version else ""
        detected = f" detected={row.detected_version}" if row.detected_version else ""
        lines.append(f"[{status}] {row.tool}{pin}{detected}")
        if not row.present:
            lines.append(f"  → {row.install_hint}")
        elif row.version_match is False and row.pinned_version:
            lines.append(
                f"  → expected {row.pinned_version}; reinstall via "
                "deploy/local/install-gate-toolchain.sh"
            )
    return "\n".join(lines)


def load_blueprint_tools(blueprint_path: Path, *, repo_root: Path) -> tuple[str, ...]:
    blueprint = load_blueprint(blueprint_path, repo_root=repo_root)
    return tools_for_blueprint(blueprint)
