from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_check_yarn_audit_passes_with_allowlist(repo_root: Path) -> None:
    script = repo_root / "scripts" / "check_yarn_audit.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "OK: no unallowlisted high/critical CVEs" in result.stdout
