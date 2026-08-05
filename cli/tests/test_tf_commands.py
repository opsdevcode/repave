"""Phase 3 acceptance: the plan/preview/apply/commit cycle end to end.

A fake `tofu` shell script stands in for the real binary. It is scripted per test to
return a chosen plan and state, which is what makes conflict and gate behavior testable
without a cloud account.
"""

from __future__ import annotations

import json
import os
import socket
import stat
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="needs repave-engine[server]")

import uvicorn
from fastapi import FastAPI
from repave_engine.api_state import build_state_router
from repave_engine.sql_store import DatabaseConfig
from repave_engine.statestore.settings import StateStoreConfig

from repave_cli.client import StateClient
from repave_cli.config import ClientConfig
from repave_cli.main import main

pytestmark = pytest.mark.slow

LINEAGE = "4f9a8b7c-1111-2222-3333-444455556666"


def _tfstate(serial: int, *addresses: str) -> str:
    resources = [
        {
            "mode": "managed",
            "type": address.split(".", 1)[0],
            "name": address.split(".", 1)[1],
            "provider": 'provider["registry.terraform.io/hashicorp/aws"]',
            "instances": [{"schema_version": 0, "attributes": {"id": address}}],
        }
        for address in addresses
    ]
    return json.dumps(
        {
            "version": 4,
            "terraform_version": "1.9.8",
            "serial": serial,
            "lineage": LINEAGE,
            "outputs": {},
            "resources": resources,
        },
        indent=2,
    )


def _plan_json(*entries: tuple[str, list[str]]) -> str:
    return json.dumps(
        {
            "resource_changes": [
                {"address": address, "change": {"actions": actions}} for address, actions in entries
            ]
        }
    )


def _fake_tofu(workdir: Path, *, plan: str, state: str) -> Path:
    """A stand-in that answers `show -json` and `state pull` from fixed files."""
    (workdir / "plan.json").write_text(plan, encoding="utf-8")
    (workdir / "state.json").write_text(state, encoding="utf-8")

    script = workdir / "fake-tofu"
    script.write_text(
        "#!/bin/sh\n"
        f'cd "{workdir}" || exit 1\n'
        'case "$1 $2" in\n'
        f'  "show -json") cat "{workdir}/plan.json" ;;\n'
        f'  "state pull") cat "{workdir}/state.json" ;;\n'
        # Only apply is recorded: tests assert on whether the change was made, and
        # logging init or plan here would make that assertion meaningless.
        '  *) [ "$1" = "apply" ] && echo "$@" >> applied.log ;;\n'
        "esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return script


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A configuration directory with the fake binary first on PATH as `tofu`."""
    stack = tmp_path / "stack"
    stack.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # Prepend, never replace: the fake script still needs `cat` and friends.
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.delenv("REPAVE_IAC_BINARY", raising=False)
    return stack


def _install_tofu(workdir: Path, *, plan: str, state: str) -> None:
    script = _fake_tofu(workdir, plan=plan, state=state)
    link = workdir.parent / "bin" / "tofu"
    link.write_text(
        f'#!/bin/sh\nexec "{script}" "$@"\n',
        encoding="utf-8",
    )
    link.chmod(link.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _serve(root: Path, *, required_gates: frozenset[str] = frozenset()) -> Iterator[str]:
    config = StateStoreConfig(
        database=DatabaseConfig(dialect="sqlite", sqlite_path=root / "state.db"),
        required_gates=required_gates,
    )
    app = FastAPI()
    app.include_router(build_state_router(repo_root=root, config=config, auth_config=None))

    port = _free_port()
    instance = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=instance.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 20
    while not instance.started:
        if time.monotonic() > deadline:
            instance.should_exit = True
            raise RuntimeError("state server did not start within 20s")
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        instance.should_exit = True
        thread.join(timeout=10)


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    yield from _serve(tmp_path_factory.mktemp("txstore"))


@pytest.fixture(scope="module")
def gated_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    yield from _serve(tmp_path_factory.mktemp("gated"), required_gates=frozenset({"opa"}))


@pytest.fixture
def cli_env(server: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("REPAVE_STATE_URL", server)
    monkeypatch.setenv("REPAVE_STATE_TENANT", "acme")
    return server


def _client(base_url: str) -> StateClient:
    return StateClient(ClientConfig(base_url=base_url, tenant="acme"))


# -- plan -------------------------------------------------------------------


def test_plan_reports_counts_and_applies_nothing(
    cli_env: str, workdir: Path, capsys: pytest.CaptureFixture
) -> None:
    _install_tofu(
        workdir,
        plan=_plan_json(("aws_subnet.web", ["create"]), ("aws_vpc.main", ["no-op"])),
        state=_tfstate(1, "aws_vpc.main"),
    )
    assert main(["tf", "plan", "prod", "--chdir", str(workdir)]) == 0

    out = capsys.readouterr().out
    assert "1 to create, 0 to change, 0 to destroy" in out
    assert "no conflicts; gates clear" in out
    assert not (workdir / "state.db").exists()


def test_plan_leaves_no_open_transaction(cli_env: str, workdir: Path) -> None:
    """A plan is a question, not a claim on the state."""
    _install_tofu(
        workdir, plan=_plan_json(("a.one", ["create"])), state=_tfstate(1, "aws_vpc.main")
    )
    main(["tf", "plan", "prod", "--chdir", str(workdir)])

    with _client(cli_env) as client:
        statuses = {tx["status"] for tx in client.list_transactions("prod")}
    assert statuses == {"aborted"}


def test_plan_json_output_is_machine_readable(
    cli_env: str, workdir: Path, capsys: pytest.CaptureFixture
) -> None:
    _install_tofu(workdir, plan=_plan_json(("a.one", ["create"])), state=_tfstate(1, "a.one"))
    assert main(["tf", "plan", "prod", "--chdir", str(workdir), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["plan"]["create"] == 1
    assert payload["preview"]["status"] == "committed"


def test_plan_in_a_missing_directory_names_the_path(
    cli_env: str, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    assert main(["tf", "plan", "prod", "--chdir", str(tmp_path / "absent")]) == 1
    assert "no such directory" in capsys.readouterr().err


# -- apply ------------------------------------------------------------------


def test_apply_commits_the_resulting_state(
    cli_env: str, workdir: Path, capsys: pytest.CaptureFixture
) -> None:
    _install_tofu(
        workdir,
        plan=_plan_json(("aws_subnet.web", ["create"])),
        state=_tfstate(2, "aws_vpc.main", "aws_subnet.web"),
    )
    assert main(["tf", "apply", "prod", "--chdir", str(workdir)]) == 0

    out = capsys.readouterr().out
    assert "applied 1 created, 0 changed, 0 destroyed" in out
    assert "committed at serial 2" in out

    with _client(cli_env) as client:
        assert client.describe_state("prod")["serial"] == 2
        assert [r.address for r in client.list_resources("prod")] == [
            "aws_subnet.web",
            "aws_vpc.main",
        ]


def test_apply_skips_when_the_plan_is_empty(
    cli_env: str, workdir: Path, capsys: pytest.CaptureFixture
) -> None:
    _install_tofu(workdir, plan=_plan_json(("a.one", ["no-op"])), state=_tfstate(1, "a.one"))
    assert main(["tf", "apply", "prod", "--chdir", str(workdir)]) == 0
    assert "no changes; nothing to apply" in capsys.readouterr().out
    assert not (workdir / "applied.log").exists()


def test_apply_runs_the_binary_only_after_the_preview_clears(cli_env: str, workdir: Path) -> None:
    _install_tofu(workdir, plan=_plan_json(("a.one", ["create"])), state=_tfstate(2, "a.one"))
    main(["tf", "apply", "prod", "--chdir", str(workdir)])
    applied = (workdir / "applied.log").read_text(encoding="utf-8")
    assert "apply" in applied


def test_apply_records_a_committed_transaction(cli_env: str, workdir: Path) -> None:
    _install_tofu(workdir, plan=_plan_json(("a.one", ["create"])), state=_tfstate(2, "a.one"))
    main(["tf", "apply", "prod", "--chdir", str(workdir)])

    with _client(cli_env) as client:
        committed = client.list_transactions("prod", status="committed")
    assert len(committed) == 1
    assert committed[0]["committed_serial"] == 2


# -- conflicts --------------------------------------------------------------


def test_a_second_apply_on_a_stale_plan_is_refused(
    cli_env: str, workdir: Path, capsys: pytest.CaptureFixture
) -> None:
    """The acceptance case: overlapping writes, second one gets told who won."""
    _install_tofu(
        workdir, plan=_plan_json(("shared.one", ["update"])), state=_tfstate(2, "shared.one")
    )

    with _client(cli_env) as client:
        # A transaction opened at serial 1 that has not committed yet.
        stale = client.open_transaction("stale")
        client.preview_transaction(
            str(stale["tx_id"]),
            plan={
                "resource_changes": [{"address": "shared.one", "change": {"actions": ["update"]}}]
            },
        )

        assert main(["tf", "apply", "stale", "--chdir", str(workdir)]) == 0
        capsys.readouterr()

        result = client.commit_transaction(str(stale["tx_id"]), _tfstate(3, "shared.one").encode())

    assert result.status == "conflict"
    assert result.conflicting_addresses == ("shared.one",)


def test_a_conflicting_preview_stops_before_apply(
    cli_env: str, workdir: Path, capsys: pytest.CaptureFixture
) -> None:
    _install_tofu(
        workdir, plan=_plan_json(("shared.one", ["update"])), state=_tfstate(2, "shared.one")
    )
    # Land a committed transaction on the same address first.
    main(["tf", "apply", "conflicted", "--chdir", str(workdir)])
    capsys.readouterr()
    (workdir / "applied.log").unlink()

    with _client(cli_env) as client:
        stale = client.open_transaction("conflicted")
        client.preview_transaction(
            str(stale["tx_id"]),
            plan={
                "resource_changes": [{"address": "shared.one", "change": {"actions": ["update"]}}]
            },
        )
        # A newer transaction commits the same address.
        _install_tofu(
            workdir, plan=_plan_json(("shared.one", ["update"])), state=_tfstate(3, "shared.one")
        )
        main(["tf", "apply", "conflicted", "--chdir", str(workdir)])
        capsys.readouterr()

        result = client.commit_transaction(str(stale["tx_id"]), _tfstate(4, "shared.one").encode())
    assert result.status == "conflict"


# -- gates ------------------------------------------------------------------


def test_a_failing_gate_blocks_apply_before_the_binary_runs(
    server: str,
    workdir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.setenv("REPAVE_STATE_URL", server)
    monkeypatch.setenv("REPAVE_STATE_TENANT", "acme")
    _install_tofu(workdir, plan=_plan_json(("a.one", ["create"])), state=_tfstate(2, "a.one"))
    gates = tmp_path / "gates.json"
    gates.write_text(
        json.dumps([{"name": "opa", "passed": False, "message": "policy denied"}]),
        encoding="utf-8",
    )

    assert main(["tf", "apply", "blocked", "--chdir", str(workdir), "--gates", str(gates)]) == 2

    out = capsys.readouterr().out
    assert "refusing to apply" in out
    assert "blocking gate: opa" in out
    assert not (workdir / "applied.log").exists()


def test_a_missing_required_gate_blocks_apply(
    gated_server: str,
    workdir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.setenv("REPAVE_STATE_URL", gated_server)
    monkeypatch.setenv("REPAVE_STATE_TENANT", "acme")
    _install_tofu(workdir, plan=_plan_json(("a.one", ["create"])), state=_tfstate(2, "a.one"))
    assert main(["tf", "apply", "gated", "--chdir", str(workdir)]) == 2
    assert "blocking gate: opa" in capsys.readouterr().out


def test_a_passing_required_gate_permits_apply(
    gated_server: str, workdir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REPAVE_STATE_URL", gated_server)
    monkeypatch.setenv("REPAVE_STATE_TENANT", "acme")
    _install_tofu(workdir, plan=_plan_json(("a.one", ["create"])), state=_tfstate(2, "a.one"))
    gates = tmp_path / "gates.json"
    gates.write_text(json.dumps({"gates": [{"name": "opa", "passed": True}]}), encoding="utf-8")

    assert main(["tf", "apply", "ok", "--chdir", str(workdir), "--gates", str(gates)]) == 0


def test_a_missing_gates_file_is_an_error(
    cli_env: str, workdir: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    _install_tofu(workdir, plan=_plan_json(), state=_tfstate(1, "a.one"))
    assert (
        main(["tf", "plan", "prod", "--chdir", str(workdir), "--gates", str(tmp_path / "no.json")])
        == 1
    )
    assert "no such gates file" in capsys.readouterr().err


def test_a_malformed_gates_file_is_an_error(
    cli_env: str, workdir: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    _install_tofu(workdir, plan=_plan_json(), state=_tfstate(1, "a.one"))
    gates = tmp_path / "gates.json"
    gates.write_text("42", encoding="utf-8")
    assert main(["tf", "plan", "prod", "--chdir", str(workdir), "--gates", str(gates)]) == 1
    assert "must be a JSON list" in capsys.readouterr().err


# -- status and abort -------------------------------------------------------


def test_status_lists_transactions(
    cli_env: str, workdir: Path, capsys: pytest.CaptureFixture
) -> None:
    _install_tofu(workdir, plan=_plan_json(("a.one", ["create"])), state=_tfstate(2, "a.one"))
    main(["tf", "apply", "listed", "--chdir", str(workdir)])
    capsys.readouterr()

    assert main(["tf", "status", "listed"]) == 0
    out = capsys.readouterr().out
    assert "committed" in out
    assert "1 write(s)" in out


def test_status_reports_an_empty_state(
    cli_env: str, workdir: Path, capsys: pytest.CaptureFixture
) -> None:
    _install_tofu(workdir, plan=_plan_json(), state=_tfstate(1, "a.one"))
    main(["tf", "apply", "empty", "--chdir", str(workdir), "--allow-no-changes"])
    capsys.readouterr()
    assert main(["tf", "status", "empty", "--status", "aborted"]) == 0
    assert "no transactions" in capsys.readouterr().out


def test_abort_closes_an_open_transaction(
    cli_env: str, workdir: Path, capsys: pytest.CaptureFixture
) -> None:
    with _client(cli_env) as client:
        tx = client.open_transaction("abortable")
        tx_id = str(tx["tx_id"])

    assert main(["tf", "abort", tx_id]) == 0
    assert f"aborted {tx_id}" in capsys.readouterr().out

    with _client(cli_env) as client:
        assert client.describe_transaction(tx_id)["status"] == "aborted"
