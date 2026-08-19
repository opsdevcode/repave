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


def _usable_executable(path: str | Path) -> bool:
    """True when path is a real file whose shebang interpreter still exists."""
    candidate = Path(path)
    try:
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            return False
        with candidate.open("rb") as handle:
            first = handle.readline(256)
        if first.startswith(b"#!"):
            interp = first[2:].split()[0].decode("utf-8", errors="replace")
            if interp.startswith("/") and not Path(interp).exists():
                return False
        return True
    except OSError:
        return False


def resolve_tool(name: str) -> str | None:
    ensure_gate_path()
    found = shutil.which(name)
    # shutil.which treats a dangling symlink as present; exec then FileNotFoundError.
    if found and _usable_executable(found):
        return found
    for directory in _STANDARD_BIN_DIRS:
        candidate = Path(directory) / name
        if _usable_executable(candidate):
            return str(candidate)
    return None


def tool_available(name: str) -> bool:
    return resolve_tool(name) is not None


def checkov_argv() -> list[str] | None:
    """Argv prefix to invoke checkov (current interpreter preferred over cached scripts)."""
    if _checkov_importable():
        return [sys.executable, "-m", "checkov"]
    path = resolve_tool("checkov")
    if path:
        return [path]
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
    """True when an IaC CLI (tofu preferred, terraform fallback) runs `version`."""
    from repave_engine.iac_binary import iac_cli_ready

    return iac_cli_ready()


def node_cli_ready() -> bool:
    """True when node and npm execute (not only a version-manager shim)."""
    node_bin = resolve_tool("node")
    npm_bin = resolve_tool("npm")
    if not node_bin or not npm_bin:
        return False
    run_cwd = subprocess_cwd(Path(tempfile.gettempdir()))
    env = os.environ.copy()
    node_ok = (
        run_subprocess(
            [node_bin, "--version"], cwd=run_cwd, check=False, env=env, timeout=15
        ).returncode
        == 0
    )
    npm_ok = (
        run_subprocess(
            [npm_bin, "--version"], cwd=run_cwd, check=False, env=env, timeout=15
        ).returncode
        == 0
    )
    return node_ok and npm_ok


def maven_cli_ready() -> bool:
    """True when mvn executes (Maven wrapper or system install)."""
    mvn_bin = resolve_tool("mvn")
    if not mvn_bin:
        return False
    run_cwd = subprocess_cwd(Path(tempfile.gettempdir()))
    result = run_subprocess(
        [mvn_bin, "-version"],
        cwd=run_cwd,
        check=False,
        env=os.environ.copy(),
        timeout=30,
    )
    return result.returncode == 0


def dotnet_cli_ready() -> bool:
    """True when dotnet executes."""
    dotnet_bin = resolve_tool("dotnet")
    if not dotnet_bin:
        return False
    run_cwd = subprocess_cwd(Path(tempfile.gettempdir()))
    result = run_subprocess(
        [dotnet_bin, "--version"],
        cwd=run_cwd,
        check=False,
        env=os.environ.copy(),
        timeout=30,
    )
    return result.returncode == 0


def buf_cli_ready() -> bool:
    """True when buf executes."""
    buf_bin = resolve_tool("buf")
    if not buf_bin:
        return False
    run_cwd = subprocess_cwd(Path(tempfile.gettempdir()))
    result = run_subprocess(
        [buf_bin, "--version"],
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
        # Key stays "terraform" for the frozen /readyz contract; the value is true
        # when either OpenTofu or Terraform is usable.
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
