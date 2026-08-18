#!/usr/bin/env python3
"""Fail when a PR introduces dependency changes with high/critical CVEs."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

ENFORCE_SEVERITIES = frozenset({"critical", "high"})


def _api_compare(repo: str, base: str, head: str, token: str) -> list[dict[str, object]]:
    url = f"https://api.github.com/repos/{repo}/dependency-graph/compare/{base}...{head}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "repave-dependency-review",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:  # nosec B310
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"dependency-graph compare failed ({exc.code}): enable Dependency graph "
            f"in repo security settings or check token scopes — {body}"
        ) from exc
    if not isinstance(payload, list):
        raise RuntimeError(f"unexpected dependency-graph response: {payload!r}")
    return payload


def _violations(changes: list[dict[str, object]]) -> list[str]:
    violations: list[str] = []
    for change in changes:
        change_type = str(change.get("change_type", ""))
        if change_type not in {"added", "updated"}:
            continue
        vulns = change.get("vulnerabilities", [])
        if not isinstance(vulns, list):
            continue
        name = change.get("name", "unknown")
        version = change.get("version", "unknown")
        ecosystem = change.get("ecosystem", "unknown")
        manifest = change.get("manifest", "unknown")
        for vuln in vulns:
            if not isinstance(vuln, dict):
                continue
            severity = str(vuln.get("severity", "")).lower()
            if severity not in ENFORCE_SEVERITIES:
                continue
            ghsa = vuln.get("advisory_ghsa_id", "unknown")
            summary = vuln.get("advisory_summary", "no summary")
            violations.append(
                f"{severity} {ghsa} {ecosystem}/{name}@{version} "
                f"({change_type} via {manifest}): {summary}"
            )
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Base commit SHA")
    parser.add_argument("--head", required=True, help="Head commit SHA")
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="GitHub repository slug (owner/name)",
    )
    args = parser.parse_args(argv)

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("set GITHUB_TOKEN or GH_TOKEN for dependency-graph compare", file=sys.stderr)
        return 1
    if not args.repo:
        print("set --repo or GITHUB_REPOSITORY", file=sys.stderr)
        return 1

    changes = _api_compare(args.repo, args.base, args.head, token)
    violations = _violations(changes)
    if violations:
        print("Dependency review: high/critical vulnerabilities introduced:", file=sys.stderr)
        print("\n".join(violations), file=sys.stderr)
        return 1

    print(f"OK: no high/critical vulnerabilities in dependency diff ({len(changes)} changes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
