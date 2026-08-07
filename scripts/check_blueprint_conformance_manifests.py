#!/usr/bin/env python3
"""Fail when snapshot conformance manifests drift (release blocker).

Uses render-only generation so PR quality jobs do not need the gate toolchain.
CI and Release still run the full gated harness in pytest.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE_SRC = ROOT / "engine" / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from repave_engine.blueprint_conformance import find_snapshot_manifest_drifts  # noqa: E402


def main() -> int:
    staging = ROOT / ".conformance-manifest-check-staging"
    modules = ROOT / ".conformance-manifest-check-modules"
    staging.mkdir(exist_ok=True)
    modules.mkdir(exist_ok=True)

    drifts = find_snapshot_manifest_drifts(
        ROOT,
        modules_root=modules,
        staging_root=staging,
        render_only=True,
    )
    if not drifts:
        print("OK: snapshot conformance manifests match blueprint output")
        return 0

    print("Blueprint conformance manifest drift detected:", file=sys.stderr)
    for drift in drifts:
        print(f"  - {drift}", file=sys.stderr)
    print(
        "\nRun: make blueprint-conformance-update\n"
        "See CONTRIBUTING.md — blueprint template output changes require manifest refresh.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
