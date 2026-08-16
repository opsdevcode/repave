from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from repave_engine.cli._style import muted, success
from repave_engine.component_reclaim import (
    ComponentReclaimError,
    reclaim_expired_components,
)
from repave_engine.github_auth import resolve_github_access_token
from repave_engine.settings import ComponentVendingConfig, load_component_vending_config


def _component_vending_config(
    args: argparse.Namespace,
) -> tuple[Path, ComponentVendingConfig]:
    repo_root = Path(args.repo_root).resolve()
    config = load_component_vending_config(repo_root)
    if config is None:
        raise SystemExit(
            "component_vending is not enabled; set component_vending.enabled in "
            "repave.config.yaml or REPAVE_COMPONENT_VENDING=1"
        )
    return repo_root, config


def cmd_components_reclaim(args: argparse.Namespace) -> int:
    repo_root, config = _component_vending_config(args)
    github_token: str | None
    if args.dry_run:
        github_token = None
    else:
        github_token = resolve_github_access_token(getattr(args, "github_token", None))
        if not github_token:
            print(
                "GITHUB_TOKEN is required unless --dry-run is set; "
                "export GITHUB_TOKEN or pass --github-token",
                file=sys.stderr,
            )
            return 1
    try:
        summary = reclaim_expired_components(
            repo_root=repo_root,
            config=config,
            github_token=github_token,
            dry_run=args.dry_run,
            name=(args.name or "").strip() or None,
            kind=(args.kind or "").strip() or None,
        )
    except ComponentReclaimError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(summary.to_public_dict(), indent=2))
        return 0

    if not summary.results:
        print(muted("No expired components eligible for auto-reclaim."))
        return 0

    for item in summary.results:
        if item.mode == "registry_finalize" and item.reclaimed:
            state = success("finalized")
        elif item.reclaimed:
            state = success("reclaimed")
        elif item.skipped:
            state = "skipped"
        elif item.mode == "decommission_review":
            state = "decommission-review"
        else:
            state = "dry-run"
        print(f"{item.kind}/{item.name}: {state} — {item.detail}")
    return 0
