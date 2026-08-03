#!/usr/bin/env python3
"""Sync Helm Chart.yaml version and appVersion to the engine release semver."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

CHART_PATHS: tuple[str, ...] = (
    "deploy/k8s/chart/Chart.yaml",
    "deploy/k8s/operator-chart/Chart.yaml",
)

VERSION_LINE = re.compile(r"^version:\s*[\d.]+$", re.MULTILINE)
APP_VERSION_LINE = re.compile(r'^appVersion:\s*["\'][\d.]+["\']$', re.MULTILINE)


def read_engine_version() -> str:
    init_path = REPO_ROOT / "engine" / "src" / "repave_engine" / "__init__.py"
    text = init_path.read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.M)
    if not match:
        raise SystemExit(f"Could not read __version__ from {init_path}")
    return match.group(1)


def apply_sync(version: str, *, check: bool = False) -> list[Path]:
    changed: list[Path] = []

    for rel_path in CHART_PATHS:
        path = REPO_ROOT / rel_path
        if not path.is_file():
            raise SystemExit(f"Missing chart file: {path}")

        original = path.read_text(encoding="utf-8")
        updated_text = original
        updated_text = VERSION_LINE.sub(f"version: {version}", updated_text, count=1)
        updated_text = APP_VERSION_LINE.sub(f'appVersion: "{version}"', updated_text, count=1)

        if updated_text != original:
            changed.append(path)
            if not check:
                path.write_text(updated_text, encoding="utf-8")

    if check and changed:
        names = ", ".join(str(p.relative_to(REPO_ROOT)) for p in changed)
        raise SystemExit(f"Chart version pointers out of date (run sync): {names}")

    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "version",
        nargs="?",
        help="Semver without v prefix (default: engine __version__)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if files would change (CI)",
    )
    args = parser.parse_args(argv)

    version = args.version or read_engine_version()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit(f"Invalid semver: {version!r}")

    changed = apply_sync(version, check=args.check)
    if args.check:
        return 0
    if changed:
        for path in changed:
            print(f"updated {path.relative_to(REPO_ROOT)}")
    else:
        print(f"chart version pointers already at {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
