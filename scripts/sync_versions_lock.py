#!/usr/bin/env python3
"""Sync versions.lock engine pins to the engine release semver."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCK_REL_PATH = "versions.lock"
IMAGE_KEYS = (
    "operator_image",
    "corpus_image",
    "portal_image",
    "worker_image",
)
# PEP 440 / PSR: 2.61.0 and 2.61.0-rc.1
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


def read_engine_version() -> str:
    init_path = REPO_ROOT / "engine" / "src" / "repave_engine" / "__init__.py"
    text = init_path.read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.M)
    if not match:
        raise SystemExit(f"Could not read __version__ from {init_path}")
    return match.group(1)


def _rewrite_lock(text: str, version: str) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines(keepends=True):
        newline = "\n" if raw_line.endswith("\n") else ""
        line = raw_line.rstrip("\r\n")
        if line.startswith("engine_version:"):
            lines.append(f"engine_version: '{version}'{newline}")
            continue
        if line.startswith("chart_version:"):
            lines.append(f"chart_version: '{version}'{newline}")
            continue
        key = next((item for item in IMAGE_KEYS if line.startswith(f"{item}:")), None)
        if key is not None:
            _, _, value = line.partition(":")
            image_ref = value.strip().strip("'\"")
            image, sep, _tag = image_ref.rpartition(":")
            if not sep or not image:
                raise SystemExit(f"Invalid image pin in {LOCK_REL_PATH}: {line}")
            lines.append(f"{key}: '{image}:{version}'{newline}")
            continue
        lines.append(raw_line)
    return "".join(lines)


def apply_sync(version: str, *, check: bool = False) -> list[Path]:
    path = REPO_ROOT / LOCK_REL_PATH
    if not path.is_file():
        raise SystemExit(f"Missing versions lock: {path}")

    original = path.read_text(encoding="utf-8")
    updated = _rewrite_lock(original, version)
    if updated == original:
        return []

    if check:
        raise SystemExit(f"versions.lock out of date (run sync): {LOCK_REL_PATH}")

    path.write_text(updated, encoding="utf-8")
    return [path]


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
    if not VERSION_RE.fullmatch(version):
        raise SystemExit(f"Invalid semver: {version!r}")

    changed = apply_sync(version, check=args.check)
    if args.check:
        return 0
    if changed:
        for path in changed:
            print(f"updated {path.relative_to(REPO_ROOT)}")
    else:
        print(f"versions.lock already at {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
