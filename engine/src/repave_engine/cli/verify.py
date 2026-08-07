from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from repave_engine.verify import VerifyError, verify_target


def cmd_verify(args: argparse.Namespace) -> int:
    raw_target = args.path.strip()
    repo_root = Path(args.repo_root).resolve()
    try:
        result = verify_target(
            raw_target,
            repo_root,
            blueprint_name=args.blueprint,
            require_run=args.require_run,
            ref=args.ref,
        )
    except VerifyError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(result.to_json_dict(), indent=2))
    else:
        print(f"Target: {result.target}")
        if result.remote:
            print("Source: shallow git clone (read-only)")
        print(
            f"Catalog blueprint: {result.catalog_blueprint_name}@{result.catalog_blueprint_version}"
        )
        if not result.provenance_present:
            print("Provenance: (none — gates from catalog only)")
        print("Gates:")
        for gate in result.gates:
            status = "SKIP" if gate.skipped else ("PASS" if gate.passed else "FAIL")
            print(f"  [{status}] {gate.name}: {gate.message}")
        if result.pin_changes:
            print("Pin drift (observed vs catalog):")
            for row in result.pin_changes:
                print(f"  {row.field}: {row.before} → {row.after}")
        else:
            print("Pins: aligned with catalog")

    return 0 if result.ok else 1


def cmd_gates(args: argparse.Namespace) -> int:
    from repave_engine.artifact_blueprint import blueprint_from_repave_file
    from repave_engine.gates import all_gates_passed, run_gates

    repo_path = Path(args.path).resolve()
    repave_file = repo_path / "repave.yaml"
    blueprint = blueprint_from_repave_file(repave_file)

    from repave_engine.infracost_policy import effective_gate_names
    from repave_engine.settings import load_gate_overrides

    gate_overrides = load_gate_overrides(repo_path)
    results = run_gates(
        repo_path,
        effective_gate_names(blueprint, gate_overrides),
        blueprint=blueprint,
        gate_overrides=gate_overrides,
    )
    if getattr(args, "json", False):
        # Shape consumed by `repave-tf tf apply --gates` (ADR 004 Phase 3).
        print(
            json.dumps(
                {
                    "gates": [
                        {
                            "name": gate.name,
                            "passed": gate.passed,
                            "skipped": gate.skipped,
                            "message": gate.message,
                        }
                        for gate in results
                    ]
                },
                indent=2,
            )
        )
    else:
        for gate in results:
            status = "SKIP" if gate.skipped else ("PASS" if gate.passed else "FAIL")
            print(f"[{status}] {gate.name}: {gate.message}")

    return 0 if all_gates_passed(results) else 1
