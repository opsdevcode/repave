from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from repave_engine.auth_context import current_acting_user
from repave_engine.cli._common import _fleet_registry_path
from repave_engine.fleet import (
    FleetEntry,
    normalize_repo_url,
    pins_from_repave_file,
    read_fleet,
    register_repo,
    unregister_repo,
)
from repave_engine.fleet_manifests import render_manifests
from repave_engine.fleet_operator_status import (
    kubectl_goldenpathrepo_list,
    parse_kubectl_gpr_list,
    write_operator_status_snapshot,
)


def cmd_register(args: argparse.Namespace) -> int:
    registry = _fleet_registry_path(args)

    pins = {
        "blueprint_name": (args.blueprint or "").strip(),
        "blueprint_version": (args.blueprint_version or "").strip(),
        "standard_source": (args.standard_source or "").strip(),
        "standard_version": (args.standard_version or "").strip(),
    }
    if args.path:
        # Provenance in the repo wins: it is what the operator observes.
        pins.update(pins_from_repave_file(Path(args.path).resolve()))
    if not pins["blueprint_name"]:
        raise ValueError("Provide --path to a checkout with repave.yaml, or --blueprint")

    entry = register_repo(
        registry,
        FleetEntry(
            repo_url=args.repo_url,
            blueprint_name=pins["blueprint_name"],
            blueprint_version=pins["blueprint_version"],
            standard_source=pins["standard_source"],
            standard_version=pins["standard_version"],
            owner=(args.owner or "").strip(),
            registered_by=current_acting_user(),
        ),
        repo_root=Path(args.repo_root).resolve(),
    )
    print(json.dumps(entry.to_dict(), indent=2))
    return 0


def cmd_unregister(args: argparse.Namespace) -> int:
    registry = _fleet_registry_path(args)
    root = Path(args.repo_root).resolve()
    if not unregister_repo(registry, args.repo_url, repo_root=root):
        print(f"{args.repo_url} is not registered")
        return 1
    print(f"unregistered {normalize_repo_url(args.repo_url)}")
    return 0


def cmd_fleet(args: argparse.Namespace) -> int:
    registry = _fleet_registry_path(args)
    root = Path(args.repo_root).resolve()
    entries = read_fleet(registry, repo_root=root)

    if args.format == "json":
        print(json.dumps([entry.to_dict() for entry in entries], indent=2))
        return 0

    if not entries:
        print("No repositories registered.")
        return 0
    for entry in entries:
        pin = f"{entry.blueprint_name}@{entry.blueprint_version or '?'}"
        owner = f" owner={entry.owner}" if entry.owner else ""
        print(f"{entry.repo_url}  {pin}{owner}")
    return 0


def cmd_fleet_manifests(args: argparse.Namespace) -> int:
    registry = _fleet_registry_path(args)
    root = Path(args.repo_root).resolve()
    entries = read_fleet(registry, repo_root=root)
    if not entries:
        print("No repositories registered; nothing to render.")
        return 0

    output_dir = Path(args.output).expanduser().resolve()
    rendered = render_manifests(
        entries,
        output_dir,
        namespace=args.namespace,
        enable_remediation=bool(args.enable_remediation),
        prune=bool(args.prune),
        kustomization=bool(args.kustomization),
        gitops_readme=bool(args.gitops_readme),
    )
    for item in rendered:
        print(f"{item.path}  {item.entry.repo_url}")
    print(f"\nRendered {len(rendered)} GoldenPathRepo manifest(s) into {output_dir}")
    if args.kustomization:
        print(f"Kustomization: {output_dir / 'kustomization.yaml'}")
    print(
        f"Apply with: kubectl apply -k {output_dir}"
        if args.kustomization
        else f"Apply with: kubectl apply -f {output_dir}"
    )
    return 0


def cmd_fleet_operator_snapshot(args: argparse.Namespace) -> int:
    try:
        payload = kubectl_goldenpathrepo_list(
            namespace=args.namespace,
            all_namespaces=bool(args.all_namespaces),
        )
    except (RuntimeError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    statuses = parse_kubectl_gpr_list(payload)
    output = Path(args.output).expanduser().resolve()
    write_operator_status_snapshot(output, statuses)
    print(f"Wrote operator status for {len(statuses)} GoldenPathRepo(s) to {output}")
    return 0
