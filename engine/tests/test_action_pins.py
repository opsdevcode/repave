from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_check_action_pins_passes_on_repo_workflows(repo_root: Path) -> None:
    script = repo_root / "scripts" / "check-action-pins.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "OK: verified pinned actions" in result.stdout
