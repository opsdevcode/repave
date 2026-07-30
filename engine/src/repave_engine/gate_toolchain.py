"""Resolve gate CLIs on PATH (Compose, CI, and local dev)."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

from repave_engine.subprocess_run import run_subprocess

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


def subprocess_cwd(preferred: Path) -> Path:
    """Working directory for gate subprocesses when preferred path is missing."""
    if preferred.is_dir():
        return preferred
    return Path(tempfile.gettempdir())


def terraform_cli_ready() -> bool:
    """True when terraform is on PATH and `terraform version` succeeds."""
    terraform_bin = resolve_tool("terraform")
    if not terraform_bin:
        return False
    run_cwd = subprocess_cwd(Path(tempfile.gettempdir()))
    result = run_subprocess(
        [terraform_bin, "version"],
        cwd=run_cwd,
        check=False,
        env=os.environ.copy(),
        timeout=15,
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
    info: dict[str, str | bool] = {
        "in_container": in_container,
        "platform": sys.platform,
        "serve_kind": "docker" if in_container else "host",
    }
    gate_env = os.environ.get("REPAVE_IMAGE_GATE_TOOLCHAIN", "").strip()
    if gate_env in ("0", "false", "False"):
        info["gate_toolchain_image"] = False
    elif gate_env in ("1", "true", "True"):
        info["gate_toolchain_image"] = True
    return info
