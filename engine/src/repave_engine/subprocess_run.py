"""Shared subprocess helpers with timeouts for gates, git, and upgrade tooling."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

DEFAULT_SUBPROCESS_TIMEOUT_SECONDS = 600
DEFAULT_GIT_TIMEOUT_SECONDS = 120

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
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=capture_output,
        text=text,
        check=check,
        env=env,
        timeout=effective_timeout,
    )
