from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from repave_engine.gate_runners import run_command
from repave_engine.subprocess_run import (
    SUBPROCESS_TIMEOUT_RETURN_CODE,
    command_timed_out,
    run_subprocess,
)


def test_run_command_reports_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPAVE_SUBPROCESS_TIMEOUT_SECONDS", "1")
    interpreter = sys.executable
    result = run_command([interpreter, "-c", "import time; time.sleep(5)"], tmp_path)
    assert result.returncode == SUBPROCESS_TIMEOUT_RETURN_CODE
    assert command_timed_out(result)
    assert "timed out" in (result.stderr or "").lower()


def test_run_subprocess_git_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPAVE_GIT_TIMEOUT_SECONDS", "1")
    with pytest.raises(subprocess.TimeoutExpired):
        run_subprocess(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            git=True,
            timeout=1,
        )
