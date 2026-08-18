#!/usr/bin/env python3
"""Fail when Backstage yarn audit reports high/critical CVEs outside the allowlist."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKSTAGE = ROOT / "backstage"
ALLOWLIST = ROOT / ".github" / "backstage-audit-allowlist.json"
YARN = ["node", ".yarn/releases/yarn-4.13.0.cjs", "npm", "audit"]
ENFORCE_SEVERITIES = frozenset({"critical", "high"})


def _load_allowlist() -> frozenset[str]:
    if not ALLOWLIST.is_file():
        return frozenset()
    payload = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    entries = payload.get("advisories", [])
    if not isinstance(entries, list):
        raise ValueError(f"invalid allowlist shape in {ALLOWLIST}: expected advisories list")
    return frozenset(str(item) for item in entries)


def _ghsa_id(url: str) -> str | None:
    if "GHSA-" not in url:
        return None
    return url.rsplit("/", 1)[-1]


def main() -> int:
    allowlist = _load_allowlist()
    proc = subprocess.run(
        [*YARN, "-A", "-R", "--no-deprecations", "--json"],
        cwd=BACKSTAGE,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 and not proc.stdout.strip():
        print(proc.stderr, file=sys.stderr)
        return proc.returncode

    violations: list[str] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        child = row.get("children", {})
        if not isinstance(child, dict):
            continue
        severity = str(child.get("Severity", "")).lower()
        if severity not in ENFORCE_SEVERITIES:
            continue
        url = str(child.get("URL", ""))
        ghsa = _ghsa_id(url)
        if ghsa is None:
            continue
        if ghsa in allowlist:
            continue
        package = row.get("value") or child.get("value") or "unknown"
        issue = child.get("Issue", "no description")
        violations.append(f"{severity} {ghsa} {package}: {issue}")

    if violations:
        print("Backstage yarn audit: high/critical CVEs outside allowlist:", file=sys.stderr)
        print("\n".join(violations), file=sys.stderr)
        print(
            f"Allow known transitive advisories in {ALLOWLIST.relative_to(ROOT)} "
            "or upgrade dependencies to clear them.",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: no unallowlisted high/critical CVEs "
        f"({len(allowlist)} advisories on allowlist)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
