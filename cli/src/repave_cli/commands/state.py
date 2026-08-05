"""`repave-tf state ...` — import, export, list, and inspect stored state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from repave_cli.client import StateClient, StateClientError
from repave_cli.config import load_client_config

EXIT_OK = 0
EXIT_ERROR = 1


def add_state_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("state", help="manage stored Terraform state")
    actions = parser.add_subparsers(dest="state_command", required=True)

    listing = actions.add_parser("list", help="list states")
    listing.add_argument("--json", action="store_true", help="emit JSON")
    listing.set_defaults(handler=cmd_list)

    show = actions.add_parser("show", help="show one state")
    show.add_argument("state")
    show.set_defaults(handler=cmd_show)

    export = actions.add_parser("export", help="write state to a .tfstate file")
    export.add_argument("state")
    export.add_argument("--out", help="output path; defaults to stdout")
    export.set_defaults(handler=cmd_export)

    importer = actions.add_parser("import", help="upload a .tfstate file")
    importer.add_argument("state")
    importer.add_argument("file", help="path to a .tfstate file")
    importer.set_defaults(handler=cmd_import)

    versions = actions.add_parser("versions", help="list stored versions")
    versions.add_argument("state")
    versions.add_argument("--limit", type=int, default=20)
    versions.set_defaults(handler=cmd_versions)


def _client(args: argparse.Namespace) -> StateClient:
    config = load_client_config(base_url=args.server, tenant=args.tenant)
    return StateClient(config)


def cmd_list(args: argparse.Namespace) -> int:
    with _client(args) as client:
        states = client.list_states()
    if args.json:
        print(json.dumps([state.__dict__ for state in states], indent=2))
        return EXIT_OK
    if not states:
        print("no states")
        return EXIT_OK
    width = max(len(state.state) for state in states)
    for state in states:
        lock = " [locked]" if state.locked else ""
        print(
            f"{state.state:<{width}}  serial {state.serial:<6} "
            f"{state.version_count} versions  {state.updated_at}{lock}"
        )
    return EXIT_OK


def cmd_show(args: argparse.Namespace) -> int:
    with _client(args) as client:
        print(json.dumps(client.describe_state(args.state), indent=2))
    return EXIT_OK


def cmd_export(args: argparse.Namespace) -> int:
    """Write byte-exact state. The escape hatch that makes adoption reversible."""
    with _client(args) as client:
        raw = client.export_state(args.state)
    if args.out:
        destination = Path(args.out).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        print(f"wrote {len(raw)} bytes to {destination}")
        return EXIT_OK
    sys.stdout.buffer.write(raw)
    return EXIT_OK


def cmd_import(args: argparse.Namespace) -> int:
    source = Path(args.file).resolve()
    if not source.is_file():
        raise StateClientError(f"no such state file: {source}")
    raw = source.read_bytes()
    with _client(args) as client:
        result = client.import_state(args.state, raw)
    print(f"{result.get('status', 'ok')}: serial {result.get('serial')} ({result.get('detail')})")
    return EXIT_OK


def cmd_versions(args: argparse.Namespace) -> int:
    with _client(args) as client:
        versions = client.list_versions(args.state, limit=args.limit)
    if not versions:
        print("no versions")
        return EXIT_OK
    for version in versions:
        print(
            f"serial {version.serial:<6} {version.created_at}  {version.author:<24} "
            f"{version.size} bytes  {version.version_id}"
        )
    return EXIT_OK
