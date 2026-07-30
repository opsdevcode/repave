"""Shared subprocess helpers with timeouts for gates, git, and upgrade tooling."""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_SUBPROCESS_TIMEOUT_SECONDS = 600
DEFAULT_GIT_TIMEOUT_SECONDS = 120
SUBPROCESS_TIMEOUT_RETURN_CODE = 124

_ENV_TIMEOUT = "REPAVE_SUBPROCESS_TIMEOUT_SECONDS"
_ENV_GIT_TIMEOUT = "REPAVE_GIT_TIMEOUT_SECONDS"


def subprocess_timeout_seconds(*, git: bool = False) -> int:
    key = _ENV_GIT_TIMEOUT if git else _ENV_TIMEOUT
    default = DEFAULT_GIT_TIMEOUT_SECONDS if git else DEFAULT_SUBPROCESS_TIMEOUT_SECONDS
    raw = os.environ.get(key, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(1, value)


def command_timed_out(result: subprocess.CompletedProcess[str]) -> bool:
    return result.returncode == SUBPROCESS_TIMEOUT_RETURN_CODE


def _kill_process_tree(process: subprocess.Popen[Any]) -> None:
    if process.pid is None:
        return
    try:
        if hasattr(os, "killpg"):
            child_pgid = os.getpgid(process.pid)
            # Never kill our own process group (pytest-xdist workers share pgid with
            # children when start_new_session is unavailable or misbehaves).
            if child_pgid != os.getpgid(0):
                os.killpg(child_pgid, signal.SIGKILL)
                return
        process.kill()
    except ProcessLookupError:
        pass


def run_subprocess(
    cmd: list[str],
    *,
    cwd: Path | str | None = None,
    capture_output: bool = True,
    text: bool = True,
    check: bool = False,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
    git: bool = False,
) -> subprocess.CompletedProcess[str]:
    effective_timeout = timeout if timeout is not None else subprocess_timeout_seconds(git=git)
    start_new_session = os.name == "posix"
    try:
        return subprocess.run(  # nosec B603
            cmd,
            cwd=cwd,
            capture_output=capture_output,
            text=text,
            check=check,
            env=env,
            timeout=effective_timeout,
            start_new_session=start_new_session,
        )
    except subprocess.TimeoutExpired as exc:
        process = getattr(exc, "process", None)
        if isinstance(process, subprocess.Popen):
            _kill_process_tree(process)
        raise


def git_subprocess_error(args: list[str], exc: subprocess.TimeoutExpired) -> RuntimeError:
    joined = " ".join(args)
    return RuntimeError(f"git {joined} timed out after {exc.timeout}s")
