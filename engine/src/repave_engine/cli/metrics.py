"""CLI for platform adoption / DX metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from repave_engine.cli._style import brand, heading, muted
from repave_engine.dx_metrics_store import capture_dx_metrics, read_dx_metrics_snapshots
from repave_engine.github_auth import resolve_github_access_token
from repave_engine.settings import load_platform_metrics_config


def cmd_metrics_adoption(args: argparse.Namespace) -> int:
    root = Path(args.repo_root).resolve()
    metrics_cfg = load_platform_metrics_config(root)
    if metrics_cfg is None:
        print(
            "platform_metrics is not enabled. Set platform_metrics.enabled in "
            "repave.config.yaml or REPAVE_PLATFORM_METRICS=1."
        )
        return 1

    token = resolve_github_access_token()
    snapshot = capture_dx_metrics(
        root,
        github_token=token,
        persist=bool(args.persist),
    )

    if args.format == "json":
        payload = snapshot.to_public_dict()
        if args.history:
            history = read_dx_metrics_snapshots(
                metrics_cfg.snapshot_file,
                repo_root=root,
                limit=int(args.history),
            )
            payload["history"] = [item.to_public_dict() for item in history]
        print(json.dumps(payload, indent=2))
        return 0

    ratio = (
        f"{snapshot.adoption_ratio * 100:.0f}%" if snapshot.adoption_ratio is not None else "n/a"
    )
    plan_apply = (
        f"{snapshot.plan_apply_ratio * 100:.0f}%"
        if snapshot.plan_apply_ratio is not None
        else "n/a"
    )
    print(
        f"{heading('Adoption ratio:')} {ratio} "
        f"({snapshot.governed_count}/{snapshot.eligible_count})"
    )
    print(
        f"{heading('Plan → apply:')}   {plan_apply} ({snapshot.apply_count}/{snapshot.plan_count})"
    )
    if snapshot.time_to_first_artifact_seconds_p50 is not None:
        print(
            f"{heading('Time to first artifact p50/p90:')} "
            f"{snapshot.time_to_first_artifact_seconds_p50}s / "
            f"{snapshot.time_to_first_artifact_seconds_p90}s"
        )
    if snapshot.message:
        print(muted(f"Note: {snapshot.message}"))
    if snapshot.funnels:
        print(heading("Funnels:"))
        for row in snapshot.funnels[:15]:
            print(
                f"  {brand(row.blueprint_name)}: plans={row.plans} applies={row.applies} "
                f"conversion={row.conversion_ratio * 100:.0f}%"
            )
    if snapshot.bypass_repos:
        print(heading(f"Bypass repos ({len(snapshot.bypass_repos)}):"))
        for url in snapshot.bypass_repos[:20]:
            print(f"  {url}")
    return 0
