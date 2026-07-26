#!/usr/bin/env python3
"""Check external policy/community references and refresh the committed snapshot."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_SRC = REPO_ROOT / "engine" / "src"
sys.path.insert(0, str(ENGINE_SRC))

from repave_engine.policy_standards_watch import check_standards_watch  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update",
        action="store_true",
        help="Write policy/standards-watch.snapshot.json and report markdown.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 when snapshot would change (implies --update).",
    )
    args = parser.parse_args()
    update = args.update or args.check
    changed, report = check_standards_watch(REPO_ROOT, update=update)
    print(report, end="")
    if args.check and changed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
