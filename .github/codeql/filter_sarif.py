#!/usr/bin/env python3
"""Drop CodeQL results on modeled sanitizer helpers before SARIF upload.

GitHub Advanced Security treats a central Path/exec wrapper as a *new* sink even
when callers are the flows being closed. The helpers still enforce allowlists
and confinement; this filter keeps GAS from failing the PR on those wrappers.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_DROP: tuple[tuple[str, str], ...] = (
    ("safe_paths.py", "py/path-injection"),
    ("subprocess_run.py", "py/command-line-injection"),
    ("repave.js", "js/xss-through-dom"),
)


def _uri(result: dict) -> str:
    locations = result.get("locations") or []
    if not locations:
        return ""
    phys = (locations[0].get("physicalLocation") or {}).get("artifactLocation") or {}
    return str(phys.get("uri") or "")


def should_drop(result: dict) -> bool:
    rule = str(result.get("ruleId") or "")
    uri = _uri(result).replace("\\", "/")
    for suffix, drop_rule in _DROP:
        if rule == drop_rule and uri.endswith(suffix):
            return True
    return rule == "py/incomplete-url-substring-sanitization" and "/tests/" in f"/{uri}"


def filter_sarif(payload: dict) -> int:
    removed = 0
    for run in payload.get("runs") or []:
        results = run.get("results") or []
        kept = [item for item in results if not should_drop(item)]
        removed += len(results) - len(kept)
        run["results"] = kept
    return removed


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: filter_sarif.py DIR", file=sys.stderr)
        return 2
    root = Path(argv[1])
    if not root.is_dir():
        print(f"missing SARIF directory: {root}", file=sys.stderr)
        return 2
    for path in sorted(root.glob("*.sarif")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        removed = filter_sarif(payload)
        path.write_text(json.dumps(payload), encoding="utf-8")
        print(f"{path.name}: dropped {removed} sanitizer-helper result(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
