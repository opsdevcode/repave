from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from repave_engine.audit_history import audit_filters_from_mapping, query_audit_entries
from repave_engine.cli._common import _audit_file


def cmd_audit_query(args: argparse.Namespace) -> int:
    root = Path(args.repo_root).resolve()
    try:
        audit_path = _audit_file(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    raw = {
        "blueprint": (args.blueprint or "").strip(),
        "module_name": (args.module_name or "").strip(),
        "repository_url": (args.repository_url or "").strip(),
        "acting_user": (args.acting_user or "").strip(),
        "gates_outcome": (args.gates_outcome or "").strip(),
        "since": (args.since or "").strip(),
        "until": (args.until or "").strip(),
        "limit": str(args.limit),
        "offset": str(args.offset),
    }
    filters = audit_filters_from_mapping(raw)
    result = query_audit_entries(audit_path, filters, repo_root=root)
    if args.format == "json":
        payload = {
            "total": result.total,
            "limit": result.limit,
            "offset": result.offset,
            "entries": [entry.to_public_dict() for entry in result.entries],
        }
        print(json.dumps(payload, indent=2))
        return 0
    if not result.entries:
        print("No matching audit entries.")
        return 0
    for entry in result.entries:
        mode = "dry-run" if entry.dry_run else "publish"
        print(
            f"{entry.timestamp}  {entry.blueprint_name}@{entry.blueprint_version}  "
            f"{entry.gates_outcome}  {mode}  user={entry.acting_user}  "
            f"module={entry.module_name}"
        )
    print(f"\n{result.total} matching (showing {len(result.entries)})")
    return 0
