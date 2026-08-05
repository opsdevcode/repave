"""`repave-tf graph ...` — query the resource graph derived from stored state.

Reads only. Anything that would change infrastructure lives under `repave-tf tf`
(Phase 3), because those commands need cloud credentials and these do not.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from repave_cli.client import StateClient, StateClientError
from repave_cli.config import load_client_config

EXIT_OK = 0


def add_graph_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("graph", help="query the resource graph")
    actions = parser.add_subparsers(dest="graph_command", required=True)

    resources = actions.add_parser("resources", help="list resources in a state")
    resources.add_argument("state")
    resources.add_argument("--type", help="filter by resource type")
    resources.add_argument("--mode", choices=("managed", "data"), help="filter by mode")
    resources.add_argument("--json", action="store_true", help="emit JSON")
    resources.set_defaults(handler=cmd_resources)

    inventory = actions.add_parser("inventory", help="count resources by type")
    inventory.add_argument("state")
    inventory.add_argument("--json", action="store_true", help="emit JSON")
    inventory.set_defaults(handler=cmd_inventory)

    show = actions.add_parser("show", help="dump nodes and edges as JSON")
    show.add_argument("state")
    show.set_defaults(handler=cmd_show)

    blast = actions.add_parser("blast-radius", help="what a change to an address can reach")
    blast.add_argument("state")
    blast.add_argument("address", help="resource address, for example aws_vpc.main")
    blast.add_argument(
        "--cost",
        metavar="INFRACOST_JSON",
        help="price the radius against an infracost breakdown file",
    )
    blast.add_argument("--json", action="store_true", help="emit JSON")
    blast.set_defaults(handler=cmd_blast_radius)

    drift = actions.add_parser("drift", help="compare stored state against a refreshed state")
    drift.add_argument("state")
    drift.add_argument("file", help="path to a refreshed .tfstate file")
    drift.add_argument("--json", action="store_true", help="emit JSON")
    drift.set_defaults(handler=cmd_drift)

    schema = actions.add_parser(
        "cache-provider-schema", help="upload `providers schema -json` to improve redaction"
    )
    schema.add_argument("file", help="path to provider schema JSON")
    schema.add_argument("--provider", required=True, help="for example hashicorp/aws")
    schema.add_argument("--provider-version", default="", help="provider version")
    schema.set_defaults(handler=cmd_cache_provider_schema)


def _client(args: argparse.Namespace) -> StateClient:
    return StateClient(load_client_config(base_url=args.server, tenant=args.tenant))


def _read_json_file(raw_path: str, *, what: str) -> bytes:
    path = Path(raw_path).resolve()
    if not path.is_file():
        raise StateClientError(f"no such {what}: {path}")
    return path.read_bytes()


def cmd_resources(args: argparse.Namespace) -> int:
    with _client(args) as client:
        rows = client.list_resources(args.state, resource_type=args.type, mode=args.mode)
    if args.json:
        print(json.dumps([row.__dict__ for row in rows], indent=2))
        return EXIT_OK
    if not rows:
        print("no resources")
        return EXIT_OK
    width = max(len(row.address) for row in rows)
    for row in rows:
        count = f"  x{row.instance_count}" if row.instance_count != 1 else ""
        print(f"{row.address:<{width}}  {row.mode}{count}")
    return EXIT_OK


def cmd_inventory(args: argparse.Namespace) -> int:
    with _client(args) as client:
        payload = client.inventory(args.state)
    if args.json:
        print(json.dumps(payload, indent=2))
        return EXIT_OK
    entries = payload.get("inventory", [])
    if not entries:
        print("no resources")
        return EXIT_OK
    width = max(len(str(entry.get("type", ""))) for entry in entries)
    for entry in entries:
        print(f"{entry.get('type', '')!s:<{width}}  {entry.get('count', 0)}")
    print(f"\ntotal: {payload.get('total', 0)}")
    return EXIT_OK


def cmd_show(args: argparse.Namespace) -> int:
    with _client(args) as client:
        print(json.dumps(client.graph(args.state), indent=2))
    return EXIT_OK


def cmd_blast_radius(args: argparse.Namespace) -> int:
    with _client(args) as client:
        if args.cost:
            breakdown = _read_json_file(args.cost, what="infracost breakdown")
            payload = client.blast_radius_cost(args.state, args.address, breakdown)
        else:
            payload = client.blast_radius(args.state, args.address)

    if args.json:
        print(json.dumps(payload, indent=2))
        return EXIT_OK

    if args.cost:
        scope = payload.get("scope", [])
        print(f"{payload.get('address')} affects {max(0, len(scope) - 1)} resource(s)")
        print(f"monthly cost: {payload.get('currency', 'USD')} {payload.get('monthly_cost')}")
        unpriced = payload.get("unpriced", [])
        if unpriced:
            print(f"unpriced: {', '.join(unpriced)}")
        return EXIT_OK

    affected = payload.get("affected", [])
    depends_on = payload.get("depends_on", [])
    print(f"{payload.get('address')} affects {len(affected)} resource(s)")
    for item in affected:
        print(f"  -> {item}")
    if depends_on:
        print("depends on:")
        for item in depends_on:
            print(f"  <- {item}")
    return EXIT_OK


def cmd_drift(args: argparse.Namespace) -> int:
    refreshed = _read_json_file(args.file, what="state file")
    with _client(args) as client:
        payload = client.drift(args.state, refreshed)
    if args.json:
        print(json.dumps(payload, indent=2))
        return EXIT_OK

    entries = payload.get("drift", [])
    if not entries:
        print(f"no drift across {payload.get('compared_count', 0)} resource(s)")
        return EXIT_OK
    for entry in entries:
        keys = entry.get("changed_keys") or []
        suffix = f" ({', '.join(keys)})" if keys else ""
        print(f"{entry.get('status', ''):<10} {entry.get('address', '')}{suffix}")
    print(f"\n{payload.get('changed_count', 0)} changed of {payload.get('compared_count', 0)}")
    return EXIT_OK


def cmd_cache_provider_schema(args: argparse.Namespace) -> int:
    schema = _read_json_file(args.file, what="provider schema")
    with _client(args) as client:
        payload = client.cache_provider_schema(
            schema, provider=args.provider, version=args.provider_version
        )
    print(
        f"cached {payload.get('types', 0)} resource type(s) for "
        f"{payload.get('provider')} {payload.get('version')}".rstrip()
    )
    return EXIT_OK
