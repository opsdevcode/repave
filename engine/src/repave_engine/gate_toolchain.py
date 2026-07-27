"""Resolve gate CLIs on PATH (Compose, CI, and local dev)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Typical install locations when PATH is trimmed (e.g. uvicorn reload workers).
if sys.platform == "darwin":
    _STANDARD_BIN_DIRS: tuple[str, ...] = (
        "/opt/homebrew/bin",
        "/opt/homebrew/sbin",
        "/usr/local/bin",
        "/usr/local/sbin",
        "/usr/bin",
        "/bin",
    )
else:
    _STANDARD_BIN_DIRS = (
        "/usr/local/bin",
        "/usr/local/sbin",
        "/usr/bin",
        "/bin",
    )

_PATH_PRIMED = False


def ensure_gate_path() -> None:
    """Prepend standard bin dirs so `shutil.which` matches an interactive shell."""
    global _PATH_PRIMED
    if _PATH_PRIMED:
        return
    current = os.environ.get("PATH", "")
    parts = current.split(os.pathsep) if current else []
    prepend = [directory for directory in _STANDARD_BIN_DIRS if directory not in parts]
    if prepend:
        os.environ["PATH"] = os.pathsep.join([*prepend, *parts])
    _PATH_PRIMED = True


def resolve_tool(name: str) -> str | None:
    ensure_gate_path()
    found = shutil.which(name)
    if found:
        return found
    for directory in _STANDARD_BIN_DIRS:
        candidate = Path(directory) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def tool_available(name: str) -> bool:
    return resolve_tool(name) is not None


def checkov_argv() -> list[str] | None:
    """Argv prefix to invoke checkov (script on PATH or python -m fallback)."""
    path = resolve_tool("checkov")
    if path:
        return [path]
    if _checkov_importable():
        return [sys.executable, "-m", "checkov"]
    return None


def _checkov_importable() -> bool:
    import importlib.util

    return importlib.util.find_spec("checkov") is not None


def terraform_cli_ready() -> bool:
    """True when terraform is on PATH and `terraform version` succeeds."""
    terraform_bin = resolve_tool("terraform")
    if not terraform_bin:
        return False
    run_cwd = Path("/tmp")
    run_cwd.mkdir(exist_ok=True)
    result = subprocess.run(
        [terraform_bin, "version"],
        cwd=run_cwd,
        capture_output=True,
        text=True,
        check=False,
        env=os.environ.copy(),
    )
    return result.returncode == 0


def gate_tool_status() -> dict[str, bool]:
    """Tool readiness as seen by the running engine process (for /readyz)."""
    ensure_gate_path()
    return {
        "terraform": terraform_cli_ready(),
        "tflint": tool_available("tflint"),
        "checkov": checkov_argv() is not None,
        "conftest": tool_available("conftest"),
        "helm": tool_available("helm"),
    }


def portal_runtime_info() -> dict[str, str | bool]:
    in_container = Path("/.dockerenv").is_file()
    return {
        "in_container": in_container,
        "platform": sys.platform,
        "serve_kind": "docker" if in_container else "host",
    }
