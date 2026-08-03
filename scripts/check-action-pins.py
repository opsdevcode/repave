#!/usr/bin/env python3
"""Verify workflow actions are pinned to SHAs listed in .github/action-pins.json."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINS = json.loads((ROOT / ".github" / "action-pins.json").read_text(encoding="utf-8"))
SHA_BY_REPO = {key.split("@")[0]: sha for key, sha in PINS.items()}
USE_RE = re.compile(r"uses:\s*([^\s#]+)")


def _pinned_files() -> list[Path]:
    """Workflows plus local composite actions, which also run third-party actions."""
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    composites = sorted((ROOT / ".github" / "actions").glob("*/action.yml"))
    return workflows + composites


def main() -> int:
    errors: list[str] = []
    paths = _pinned_files()
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for match in USE_RE.finditer(text):
            spec = match.group(1).strip()
            if spec.startswith("./"):
                continue
            if "@" not in spec:
                errors.append(f"{path.relative_to(ROOT)}: missing action ref on {spec!r}")
                continue
            repo, ref = spec.rsplit("@", 1)
            expected = SHA_BY_REPO.get(repo)
            if expected is None:
                errors.append(f"{path.relative_to(ROOT)}: action {repo!r} missing from action-pins.json")
                continue
            if ref != expected:
                errors.append(
                    f"{path.relative_to(ROOT)}: {repo}@{ref} != expected @{expected}"
                )
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"OK: verified pinned actions in {len(paths)} workflow and composite action files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
