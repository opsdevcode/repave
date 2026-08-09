#!/usr/bin/env python3
"""Seed hosted-demo cost snapshot history for library FinOps sparklines."""

from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_catalog(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise SystemExit("PyYAML required: cd engine && uv run python ../scripts/seed_hosted_demo_cost_snapshots.py")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid catalog: {path}")
    return data


def _infer_repo_name(blueprint: str, inputs: dict[str, str]) -> str:
    cloud = inputs.get("cloud_provider", "aws")
    if blueprint == "terraform-module-generic":
        return f"tf-{cloud}-{inputs['module_name']}"
    if blueprint == "ansible-role-generic":
        return f"ansible-role-{inputs['role_name']}"
    if blueprint == "opa-policy-generic":
        return f"opa-policy-{inputs['organization']}-{inputs['policy_name']}"
    if blueprint == "checkov-policy-generic":
        return f"checkov-policy-{inputs['organization']}-{inputs['policy_name']}"
    if blueprint == "helm-chart-generic":
        return f"helm-{inputs['chart_name']}"
    if blueprint == "gitops-deployment-generic":
        return f"gitops-{inputs['environment']}-{inputs['service_name']}"
    raise ValueError(f"cannot infer repo name for blueprint {blueprint!r}")


def _base_amount(seed_id: str, blueprint: str) -> float:
    defaults: dict[str, float] = {
        "tf-vpc": 92.0,
        "tf-eks": 468.0,
        "tf-azure-net": 74.0,
        "ansible-web": 11.0,
        "ansible-hardening": 9.5,
        "opa-guardrails": 2.4,
        "checkov-baseline": 1.8,
        "helm-payments": 31.0,
        "gitops-payments": 6.5,
    }
    if seed_id in defaults:
        return defaults[seed_id]
    if blueprint == "terraform-module-generic":
        return 120.0
    if blueprint.startswith("ansible"):
        return 10.0
    return 8.0


def _import_engine(repo_root: Path) -> None:
    engine_src = repo_root / "engine" / "src"
    if str(engine_src) not in sys.path:
        sys.path.insert(0, str(engine_src))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=_repo_root())
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path(__file__).with_name("hosted-demo-library.yaml"),
    )
    parser.add_argument("--github-org", default="opsdevcode")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/fleet/cost-snapshots.jsonl"),
        help="JSONL snapshot file (default: data/fleet/cost-snapshots.jsonl)",
    )
    parser.add_argument("--weeks", type=int, default=8, help="history points per entity")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    catalog = _load_catalog(args.catalog)
    org = str(catalog.get("org", args.github_org))
    raw = catalog.get("repos")
    if not isinstance(raw, list):
        raise ValueError("catalog.repos must be a list")

    repo_root = args.repo_root.resolve()
    _import_engine(repo_root)
    from repave_engine.cost_snapshot_store import CostSnapshotEntry, append_cost_snapshot
    from repave_engine.entity_catalog import entity_id_for_repo_url

    output = args.output
    if not output.is_absolute():
        output = (repo_root / output).resolve()
    if not args.dry_run:
        output.parent.mkdir(parents=True, exist_ok=True)

    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    written = 0
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        seed_id = str(item.get("id", "")).strip()
        blueprint = str(item.get("blueprint", "")).strip()
        inputs_raw = item.get("inputs") or {}
        if not seed_id or not blueprint or not isinstance(inputs_raw, dict):
            continue
        inputs = {str(k): str(v) for k, v in inputs_raw.items()}
        repo_name = _infer_repo_name(blueprint, inputs)
        repo_url = f"https://github.com/{org}/{repo_name}"
        entity_id = entity_id_for_repo_url(repo_url)
        base = _base_amount(seed_id, blueprint)
        for week in range(args.weeks):
            captured_at = (end - timedelta(days=7 * (args.weeks - week - 1))).replace(
                microsecond=0
            )
            wave = math.sin((week + index) * 0.85) * 0.08
            drift = week * 0.012
            amount = base * (1.0 + wave + drift)
            entry = CostSnapshotEntry(
                entity_id=entity_id,
                captured_at=captured_at.isoformat().replace("+00:00", "Z"),
                currency="USD",
                amount_30d=f"{amount:.2f}",
            )
            if args.dry_run:
                print(entry.to_public_dict())
            else:
                append_cost_snapshot(output, entry)
            written += 1

    action = "would write" if args.dry_run else "wrote"
    print(f"{action} {written} cost snapshots to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
