"""`repave-tf tf plan|apply` — drive OpenTofu locally against a governed transaction.

The split is the whole design: `tofu` runs here, with the caller's cloud credentials,
in the caller's working directory. The store gets a plan summary, gate results, and the
resulting state document. It never gets a credential and never runs a provider.

`apply` is a sequence with a bail-out at every step:

    open tx -> tofu plan -> preview (write set + gates) -> tofu apply -> commit

A preview that reports a conflict or a blocking gate stops before `apply`, so a
governance failure costs a plan rather than a half-applied change.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from repave_cli.client import CommitResult, StateClient, StateClientError
from repave_cli.config import load_client_config
from repave_cli.runner import IacRunner, RunnerError, plan_change_counts

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_BLOCKED = 2

PLAN_FILE = "repave.tfplan"


def add_tf_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("tf", help="run tofu/terraform against a governed transaction")
    actions = parser.add_subparsers(dest="tf_command", required=True)

    plan = actions.add_parser("plan", help="plan and preview without applying")
    _add_common(plan)
    plan.set_defaults(handler=cmd_plan)

    apply = actions.add_parser("apply", help="plan, preview, apply, and commit")
    _add_common(apply)
    apply.add_argument(
        "--allow-no-changes",
        action="store_true",
        help="commit even when the plan is empty (default: skip the apply)",
    )
    apply.set_defaults(handler=cmd_apply)

    abort = actions.add_parser("abort", help="abort an open transaction")
    abort.add_argument("tx_id")
    abort.set_defaults(handler=cmd_abort)

    status = actions.add_parser("status", help="show transactions for a state")
    status.add_argument("state")
    status.add_argument("--status", dest="filter_status", help="filter by transaction status")
    status.add_argument("--json", action="store_true", help="emit JSON")
    status.set_defaults(handler=cmd_status)


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("state", help="state name in the store")
    parser.add_argument("--chdir", default=".", help="directory holding the configuration")
    parser.add_argument("--skip-init", action="store_true", help="assume the directory is ready")
    parser.add_argument(
        "--gates",
        metavar="GATES_JSON",
        help="gate results to report; a required gate that is absent blocks the commit",
    )
    parser.add_argument("--timeout", type=int, default=3600, help="per-command timeout in seconds")
    parser.add_argument("--json", action="store_true", help="emit JSON")


def _client(args: argparse.Namespace) -> StateClient:
    return StateClient(load_client_config(base_url=args.server, tenant=args.tenant))


def _runner(args: argparse.Namespace) -> IacRunner:
    workdir = Path(args.chdir).resolve()
    if not workdir.is_dir():
        raise RunnerError(f"no such directory: {workdir}")
    return IacRunner(workdir=workdir, timeout=args.timeout)


def _load_gates(raw_path: str | None) -> list[dict[str, Any]]:
    if not raw_path:
        return []
    path = Path(raw_path).resolve()
    if not path.is_file():
        raise StateClientError(f"no such gates file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StateClientError(f"gates file is not JSON: {exc}") from exc
    if isinstance(payload, dict):
        payload = payload.get("gates", [])
    if not isinstance(payload, list):
        raise StateClientError("gates file must be a JSON list, or an object with a 'gates' list")
    return [item for item in payload if isinstance(item, dict)]


def cmd_plan(args: argparse.Namespace) -> int:
    """Plan and preview. Opens a transaction, then aborts it — nothing is applied."""
    runner = _runner(args)
    gates = _load_gates(args.gates)

    with _client(args) as client, tempfile.TemporaryDirectory() as scratch:
        plan_json = _plan(runner, Path(scratch) / PLAN_FILE, skip_init=args.skip_init)
        transaction = client.open_transaction(args.state, operation="plan")
        tx_id = str(transaction["tx_id"])
        try:
            preview = client.preview_transaction(tx_id, plan=plan_json, gates=gates)
        finally:
            client.abort_transaction(tx_id)

    if args.json:
        print(json.dumps({"plan": _counts(plan_json), "preview": preview}, indent=2))
        return EXIT_OK if preview.get("status") == "committed" else EXIT_BLOCKED

    _print_plan(plan_json)
    return _print_preview(preview)


def cmd_apply(args: argparse.Namespace) -> int:
    runner = _runner(args)
    gates = _load_gates(args.gates)

    with _client(args) as client, tempfile.TemporaryDirectory() as scratch:
        plan_file = Path(scratch) / PLAN_FILE
        plan_json = _plan(runner, plan_file, skip_init=args.skip_init)
        create, update, delete = plan_change_counts(plan_json)

        if not any((create, update, delete)) and not args.allow_no_changes:
            if args.json:
                print(json.dumps({"status": "no-changes", "plan": _counts(plan_json)}, indent=2))
            else:
                print("no changes; nothing to apply")
            return EXIT_OK

        transaction = client.open_transaction(args.state, operation="apply")
        tx_id = str(transaction["tx_id"])

        preview = client.preview_transaction(tx_id, plan=plan_json, gates=gates)
        if preview.get("status") != "committed":
            client.abort_transaction(tx_id)
            if args.json:
                print(json.dumps(preview, indent=2))
                return EXIT_BLOCKED
            print("refusing to apply:")
            return _print_preview(preview)

        try:
            runner.apply(plan_file)
        except RunnerError:
            client.abort_transaction(tx_id)
            raise

        result = client.commit_transaction(tx_id, runner.state_pull())

    if args.json:
        print(json.dumps(_commit_payload(result, plan_json), indent=2))
        return EXIT_OK if result.ok else EXIT_BLOCKED
    return _print_commit(result, create, update, delete)


def cmd_abort(args: argparse.Namespace) -> int:
    with _client(args) as client:
        client.abort_transaction(args.tx_id)
    print(f"aborted {args.tx_id}")
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    with _client(args) as client:
        items = client.list_transactions(args.state, status=args.filter_status)
    if args.json:
        print(json.dumps(items, indent=2))
        return EXIT_OK
    if not items:
        print("no transactions")
        return EXIT_OK
    for item in items:
        writes = [r for r in item.get("resources", []) if r.get("intent") == "write"]
        print(
            f"{item.get('status', '')!s:<11} {item.get('tx_id', '')}  "
            f"{item.get('operation', ''):<6} {len(writes)} write(s)  "
            f"{item.get('author', '')}  {item.get('created_at', '')}"
        )
    return EXIT_OK


# -- helpers ----------------------------------------------------------------


def _plan(runner: IacRunner, plan_file: Path, *, skip_init: bool) -> dict[str, Any]:
    if not skip_init:
        runner.init()
    runner.plan(plan_file)
    return runner.show_plan_json(plan_file)


def _counts(plan_json: dict[str, Any]) -> dict[str, int]:
    create, update, delete = plan_change_counts(plan_json)
    return {"create": create, "update": update, "delete": delete}


def _print_plan(plan_json: dict[str, Any]) -> None:
    create, update, delete = plan_change_counts(plan_json)
    print(f"plan: {create} to create, {update} to change, {delete} to destroy")


def _print_preview(preview: dict[str, Any]) -> int:
    status = str(preview.get("status", ""))
    if status == "committed":
        print("no conflicts; gates clear")
        return EXIT_OK

    print(f"{status}: {preview.get('detail', '')}")
    for address in preview.get("conflicting_addresses", []):
        print(f"  conflicting resource: {address}")
    for name in preview.get("blocking_gates", []):
        print(f"  blocking gate: {name}")
    return EXIT_BLOCKED


def _print_commit(result: CommitResult, create: int, update: int, delete: int) -> int:
    if result.ok:
        serial = result.transaction.get("committed_serial")
        print(f"applied {create} created, {update} changed, {delete} destroyed")
        print(f"committed at serial {serial}")
        return EXIT_OK

    print(f"{result.status}: {result.detail}")
    for address in result.conflicting_addresses:
        print(f"  conflicting resource: {address}")
    for tx_id in result.conflicts:
        print(f"  conflicting transaction: {tx_id}")
    for name in result.blocking_gates:
        print(f"  blocking gate: {name}")
    return EXIT_BLOCKED


def _commit_payload(result: CommitResult, plan_json: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": result.status,
        "detail": result.detail,
        "plan": _counts(plan_json),
        "conflicts": list(result.conflicts),
        "conflicting_addresses": list(result.conflicting_addresses),
        "blocking_gates": list(result.blocking_gates),
        "transaction": result.transaction,
    }
