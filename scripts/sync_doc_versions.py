#!/usr/bin/env python3
"""Sync engine semver pointers in top-level docs after a release."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASE_URL = "https://github.com/opsdevcode/repave/releases/tag/v{version}"

# (path relative to repo root, list of (compiled pattern, replacement template))
# Replacement templates use {version} and {release_url}.
# roadmap.md: only Current release / path "today" — keep a blank line after
# Current release so feature edits to In progress / Shipped merge cleanly.
DOC_TARGETS: tuple[tuple[str, tuple[tuple[re.Pattern[str], str], ...]], ...] = (
    (
        "docs/roadmap.md",
        (
            (
                re.compile(r"(\*\*Current release:\*\* )v[\d.]+"),
                r"\g<1>v{version}",
            ),
            (
                re.compile(r"^v[\d.]+(\s+today\s+)", re.MULTILINE),
                r"v{version}\g<1>",
            ),
        ),
    ),
    (
        "README.md",
        (
            (
                re.compile(
                    r"\[v[\d.]+\]\("
                    r"https://github\.com/opsdevcode/repave/releases"
                    r"(?:/tag/v[\d.]+)?\)"
                ),
                r"[v{version}]({release_url})",
            ),
        ),
    ),
    (
        "docs/portal-design.md",
        (
            (
                re.compile(r"(engine tags through \*\*)v[\d.]+(\*\*)"),
                r"\g<1>v{version}\g<2>",
            ),
        ),
    ),
    (
        "docs/demo-verification.md",
        (
            (
                re.compile(r"\(engine v[\d.]+\,"),
                r"(engine v{version},",
            ),
        ),
    ),
    (
        "docs/operator-ga.md",
        (
            (
                re.compile(r"\(engine \*\*v[\d.]+\*\*\)"),
                r"(engine **v{version}**)",
            ),
        ),
    ),
)


DOC_TARGET_PATHS: tuple[str, ...] = tuple(rel for rel, _ in DOC_TARGETS)


def read_engine_version() -> str:
    init_path = REPO_ROOT / "engine" / "src" / "repave_engine" / "__init__.py"
    text = init_path.read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.M)
    if not match:
        raise SystemExit(f"Could not read __version__ from {init_path}")
    return match.group(1)


def apply_sync(version: str, *, check: bool = False) -> list[Path]:
    release_url = RELEASE_URL.format(version=version)
    changed: list[Path] = []

    for rel_path, patterns in DOC_TARGETS:
        path = REPO_ROOT / rel_path
        if not path.is_file():
            raise SystemExit(f"Missing doc file: {path}")

        original = path.read_text(encoding="utf-8")
        updated = original
        for pattern, repl in patterns:
            updated = pattern.sub(
                repl.format(version=version, release_url=release_url),
                updated,
            )

        if updated != original:
            changed.append(path)
            if not check:
                path.write_text(updated, encoding="utf-8")

    if check and changed:
        names = ", ".join(str(p.relative_to(REPO_ROOT)) for p in changed)
        raise SystemExit(f"Doc version pointers out of date (run sync): {names}")

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
        if args.check and re.fullmatch(r"\d+\.\d+\.\d+-.+", version):
            print(f"Skipping doc version check for prerelease {version!r}")
            return 0
        raise SystemExit(f"Invalid semver: {version!r}")

    changed = apply_sync(version, check=args.check)
    if args.check:
        return 0
    if changed:
        for path in changed:
            print(f"updated {path.relative_to(REPO_ROOT)}")
    else:
        print(f"doc version pointers already at v{version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
