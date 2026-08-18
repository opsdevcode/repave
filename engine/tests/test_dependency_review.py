from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_check_dependency_review_passes_on_pr_diff(repo_root: Path) -> None:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        return

    script = repo_root / "scripts" / "check_dependency_review.py"
    base = subprocess.check_output(
        ["git", "merge-base", "origin/main", "HEAD"],
        cwd=repo_root,
        text=True,
    ).strip()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()
    env = os.environ.copy()
    env.setdefault("GITHUB_REPOSITORY", "opsdevcode/repave")
    result = subprocess.run(
        [sys.executable, str(script), "--base", base, "--head", head],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "OK: no high/critical vulnerabilities" in result.stdout
