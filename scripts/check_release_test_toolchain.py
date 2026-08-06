#!/usr/bin/env python3
"""Guard: CI and Release must share gate-toolchain (incl. JDK/.NET) for engine tests.

Tags from Release drive downstream EKS deploys. If Release drifts from CI's
test toolchain, engine tests fail and versioning stalls. Fail the PR early.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / ".github" / "actions" / "gate-toolchain" / "action.yml"
CI = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE = ROOT / ".github" / "workflows" / "release.yml"
SHARED = "./.github/actions/gate-toolchain"


def main() -> int:
    errors: list[str] = []
    gate = GATE.read_text(encoding="utf-8")
    for needle, label in (
        ("actions/setup-java@", "Temurin/setup-java"),
        ("actions/setup-dotnet@", "setup-dotnet"),
        ("Install Maven", "Maven install step"),
        ('java-version: "21"', "Java 21"),
        ("dotnet-version:", ".NET SDK"),
    ):
        if needle not in gate:
            errors.append(f"gate-toolchain/action.yml must include {label} ({needle!r})")

    for path, label in ((CI, "ci.yml"), (RELEASE, "release.yml")):
        text = path.read_text(encoding="utf-8")
        if SHARED not in text:
            errors.append(f"{label} must use {SHARED} before engine tests")

    # Release must not re-introduce ad-hoc runtime setup that can drift from CI.
    release = RELEASE.read_text(encoding="utf-8")
    for forbidden in ("actions/setup-java@", "actions/setup-dotnet@"):
        if forbidden in release:
            errors.append(
                f"release.yml must not call {forbidden} directly; "
                "use gate-toolchain so CI and Release stay identical"
            )

    if errors:
        print("Release/CI test toolchain drift detected:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        print(
            "\nAdd new engine-test runtimes to .github/actions/gate-toolchain/action.yml "
            "(not only ci.yml). Tags from Release drive EKS deploys.",
            file=sys.stderr,
        )
        return 1

    print("OK: CI and Release share gate-toolchain with Java 21, .NET, and Maven")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
