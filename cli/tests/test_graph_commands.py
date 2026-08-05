"""Phase 2 acceptance: graph queries over the wire and through the command layer."""

from __future__ import annotations

import json
import socket
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


def _resource(resource_type: str, name: str, *, depends_on: list[str] | None = None, **attrs: str):
    instance: dict[str, object] = {
        "schema_version": 0,
        "attributes": {"id": f"{name}-id", **attrs},
    }
    if depends_on:
        instance["dependencies"] = depends_on
    return {
        "mode": "managed",
        "type": resource_type,
        "name": name,
        "provider": 'provider["registry.terraform.io/hashicorp/aws"]',
        "instances": [instance],
    }


def _tfstate(serial: int = 1, *, resources: list[dict[str, object]] | None = None) -> bytes:
    payload = {
        "version": 4,
        "terraform_version": "1.9.8",
        "serial": serial,
        "lineage": LINEAGE,
        "outputs": {},
        "resources": resources
        if resources is not None
        else [
            _resource("aws_vpc", "main"),
            _resource("aws_subnet", "web", depends_on=["aws_vpc.main"]),
            _resource("aws_instance", "app", depends_on=["aws_subnet.web"], size="small"),
        ],
    }
    return json.dumps(payload, indent=2).encode("utf-8")


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    root = tmp_path_factory.mktemp("graphstore")
    config = StateStoreConfig(
        database=DatabaseConfig(dialect="sqlite", sqlite_path=root / "state.db"),
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


@pytest.fixture
def client(server: str) -> Iterator[StateClient]:
    with StateClient(ClientConfig(base_url=server, tenant="acme")) as instance:
        instance.import_state("graph", _tfstate())
        yield instance


@pytest.fixture
def cli_env(server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPAVE_STATE_URL", server)
    monkeypatch.setenv("REPAVE_STATE_TENANT", "acme")


# -- client -----------------------------------------------------------------


def test_importing_state_populates_the_graph(client: StateClient) -> None:
    rows = client.list_resources("graph")
    assert [row.address for row in rows] == [
        "aws_instance.app",
        "aws_subnet.web",
        "aws_vpc.main",
    ]


def test_resources_can_be_filtered_by_type(client: StateClient) -> None:
    rows = client.list_resources("graph", resource_type="aws_vpc")
    assert [row.address for row in rows] == ["aws_vpc.main"]


def test_inventory_totals_over_the_wire(client: StateClient) -> None:
    payload = client.inventory("graph")
    assert payload["total"] == 3


def test_blast_radius_is_transitive_over_the_wire(client: StateClient) -> None:
    payload = client.blast_radius("graph", "aws_vpc.main")
    assert payload["affected"] == ["aws_instance.app", "aws_subnet.web"]


def test_graph_returns_nodes_and_edges(client: StateClient) -> None:
    payload = client.graph("graph")
    assert len(payload["nodes"]) == 3
    assert {(edge["from"], edge["to"]) for edge in payload["edges"]} == {
        ("aws_subnet.web", "aws_vpc.main"),
        ("aws_instance.app", "aws_subnet.web"),
    }


def test_drift_detects_a_changed_attribute(client: StateClient) -> None:
    refreshed = _tfstate(
        resources=[
            _resource("aws_vpc", "main"),
            _resource("aws_subnet", "web", depends_on=["aws_vpc.main"]),
            _resource("aws_instance", "app", depends_on=["aws_subnet.web"], size="large"),
        ]
    )
    payload = client.drift("graph", refreshed)
    assert payload["changed_count"] == 1
    assert payload["drift"][0]["address"] == "aws_instance.app"
    assert payload["drift"][0]["changed_keys"] == ["size"]


def test_blast_radius_cost_prices_the_scope(client: StateClient) -> None:
    breakdown = json.dumps(
        {
            "currency": "USD",
            "projects": [
                {
                    "breakdown": {
                        "resources": [
                            {"name": "aws_subnet.web", "monthlyCost": "5.00"},
                            {"name": "aws_instance.app", "monthlyCost": "30.00"},
                        ]
                    }
                }
            ],
        }
    ).encode("utf-8")
    payload = client.blast_radius_cost("graph", "aws_subnet.web", breakdown)
    assert payload["monthly_cost"] == "35.00"


# -- command layer ----------------------------------------------------------


def test_cli_resources_lists_addresses(
    cli_env: None, client: StateClient, capsys: pytest.CaptureFixture
) -> None:
    assert main(["graph", "resources", "graph"]) == 0
    assert "aws_vpc.main" in capsys.readouterr().out


def test_cli_inventory_prints_a_total(
    cli_env: None, client: StateClient, capsys: pytest.CaptureFixture
) -> None:
    assert main(["graph", "inventory", "graph"]) == 0
    assert "total: 3" in capsys.readouterr().out


def test_cli_blast_radius_lists_dependents(
    cli_env: None, client: StateClient, capsys: pytest.CaptureFixture
) -> None:
    assert main(["graph", "blast-radius", "graph", "aws_vpc.main"]) == 0
    out = capsys.readouterr().out
    assert "affects 2 resource(s)" in out
    assert "-> aws_subnet.web" in out


def test_cli_blast_radius_json_is_machine_readable(
    cli_env: None, client: StateClient, capsys: pytest.CaptureFixture
) -> None:
    assert main(["graph", "blast-radius", "graph", "aws_vpc.main", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["affected_count"] == 2


def test_cli_drift_reports_changes(
    cli_env: None, client: StateClient, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    refreshed = tmp_path / "refreshed.tfstate"
    refreshed.write_bytes(
        _tfstate(
            resources=[
                _resource("aws_vpc", "main"),
                _resource("aws_subnet", "web", depends_on=["aws_vpc.main"]),
            ]
        )
    )
    assert main(["graph", "drift", "graph", str(refreshed)]) == 0
    assert "removed" in capsys.readouterr().out


def test_cli_drift_missing_file_is_an_error(
    cli_env: None, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    assert main(["graph", "drift", "graph", str(tmp_path / "nope.tfstate")]) == 1
    assert "no such state file" in capsys.readouterr().err


def test_cli_cache_provider_schema_reports_learned_types(
    cli_env: None, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    schema = tmp_path / "schema.json"
    schema.write_text(
        json.dumps(
            {
                "provider_schemas": {
                    "registry.terraform.io/hashicorp/aws": {
                        "resource_schemas": {
                            "aws_db_instance": {
                                "block": {"attributes": {"password": {"sensitive": True}}}
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    assert main(["graph", "cache-provider-schema", str(schema), "--provider", "hashicorp/aws"]) == 0
    assert "cached 1 resource type(s)" in capsys.readouterr().out


def test_cli_resources_json_is_machine_readable(
    cli_env: None, client: StateClient, capsys: pytest.CaptureFixture
) -> None:
    assert main(["graph", "resources", "graph", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert {row["address"] for row in rows} == {
        "aws_vpc.main",
        "aws_subnet.web",
        "aws_instance.app",
    }


def test_cli_resources_filters_by_mode(
    cli_env: None, client: StateClient, capsys: pytest.CaptureFixture
) -> None:
    assert main(["graph", "resources", "graph", "--mode", "data"]) == 0
    assert "no resources" in capsys.readouterr().out


def test_cli_inventory_json_includes_totals(
    cli_env: None, client: StateClient, capsys: pytest.CaptureFixture
) -> None:
    assert main(["graph", "inventory", "graph", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["total"] == 3


def test_cli_show_dumps_nodes_and_edges(
    cli_env: None, client: StateClient, capsys: pytest.CaptureFixture
) -> None:
    assert main(["graph", "show", "graph"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["nodes"]) == 3
    assert len(payload["edges"]) == 2


def test_cli_blast_radius_with_cost_prints_a_total(
    cli_env: None, client: StateClient, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    breakdown = tmp_path / "infracost.json"
    breakdown.write_text(
        json.dumps(
            {
                "currency": "USD",
                "projects": [
                    {
                        "breakdown": {
                            "resources": [
                                {"name": "aws_subnet.web", "monthlyCost": "5.00"},
                                {"name": "aws_instance.app", "monthlyCost": "30.00"},
                            ]
                        }
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert main(["graph", "blast-radius", "graph", "aws_subnet.web", "--cost", str(breakdown)]) == 0
    out = capsys.readouterr().out
    assert "monthly cost: USD 35.00" in out


def test_cli_blast_radius_cost_names_unpriced_resources(
    cli_env: None, client: StateClient, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    breakdown = tmp_path / "infracost.json"
    breakdown.write_text(json.dumps({"projects": []}), encoding="utf-8")
    assert main(["graph", "blast-radius", "graph", "aws_vpc.main", "--cost", str(breakdown)]) == 0
    out = capsys.readouterr().out
    assert "monthly cost: USD 0.00" in out
    assert "unpriced: aws_instance.app, aws_subnet.web, aws_vpc.main" in out


def test_cli_blast_radius_cost_missing_file_is_an_error(
    cli_env: None, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    assert (
        main(
            ["graph", "blast-radius", "graph", "aws_vpc.main", "--cost", str(tmp_path / "no.json")]
        )
        == 1
    )
    assert "no such infracost breakdown" in capsys.readouterr().err


def test_cli_drift_reports_no_drift_when_identical(
    cli_env: None, client: StateClient, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    refreshed = tmp_path / "same.tfstate"
    refreshed.write_bytes(_tfstate())
    assert main(["graph", "drift", "graph", str(refreshed)]) == 0
    assert "no drift across 3 resource(s)" in capsys.readouterr().out


def test_cli_drift_json_reports_counts(
    cli_env: None, client: StateClient, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    refreshed = tmp_path / "changed.tfstate"
    refreshed.write_bytes(
        _tfstate(
            resources=[
                _resource("aws_vpc", "main"),
                _resource("aws_subnet", "web", depends_on=["aws_vpc.main"]),
                _resource("aws_instance", "app", depends_on=["aws_subnet.web"], size="large"),
            ]
        )
    )
    assert main(["graph", "drift", "graph", str(refreshed), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["changed_count"] == 1


def test_cli_cache_provider_schema_missing_file_is_an_error(
    cli_env: None, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    assert (
        main(
            [
                "graph",
                "cache-provider-schema",
                str(tmp_path / "nope.json"),
                "--provider",
                "hashicorp/aws",
            ]
        )
        == 1
    )
    assert "no such provider schema" in capsys.readouterr().err
