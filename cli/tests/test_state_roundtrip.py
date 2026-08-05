"""Phase 1 acceptance gate: a `.tfstate` file survives import and export byte-for-byte.

Runs against a real HTTP server rather than an in-process ASGI shim, because the
things most likely to break byte-exactness — content negotiation, encoding, and
buffering — only exist on the wire.
"""

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

from repave_cli.client import StateClient, StateClientError
from repave_cli.config import ClientConfig
from repave_cli.main import main

pytestmark = pytest.mark.slow

# Awkward on purpose: 4-space indent, trailing newline, non-alphabetical keys.
# Anything that re-serializes this document instead of storing its bytes will differ.
TFSTATE = (
    b"{\n"
    b'    "version": 4,\n'
    b'    "terraform_version": "1.9.8",\n'
    b'    "serial": 12,\n'
    b'    "lineage": "4f9a8b7c-1111-2222-3333-444455556666",\n'
    b'    "outputs": {\n'
    b'        "bucket_arn": {\n'
    b'            "value": "arn:aws:s3:::example",\n'
    b'            "type": "string"\n'
    b"        }\n"
    b"    },\n"
    b'    "resources": [\n'
    b"        {\n"
    b'            "mode": "managed",\n'
    b'            "type": "aws_s3_bucket",\n'
    b'            "name": "example",\n'
    b'            "provider": "provider[\\"registry.terraform.io/hashicorp/aws\\"]",\n'
    b'            "instances": [\n'
    b"                {\n"
    b'                    "schema_version": 0,\n'
    b'                    "attributes": {\n'
    b'                        "id": "example",\n'
    b'                        "tags": {"env": "prod"}\n'
    b"                    }\n"
    b"                }\n"
    b"            ]\n"
    b"        }\n"
    b"    ]\n"
    b"}\n"
)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    root = tmp_path_factory.mktemp("statestore")
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
        yield instance


def test_import_export_is_byte_identical(client: StateClient) -> None:
    """The acceptance gate for Phase 1."""
    result = client.import_state("roundtrip", TFSTATE)
    assert result["status"] == "created"

    assert client.export_state("roundtrip") == TFSTATE


def test_export_parses_as_the_same_document(client: StateClient) -> None:
    client.import_state("parsed", TFSTATE)
    exported = client.export_state("parsed")
    assert json.loads(exported) == json.loads(TFSTATE)


def test_discovery_reports_the_contract(client: StateClient) -> None:
    payload = client.describe()
    assert payload["api_version"] == "v1"
    assert payload["min_supported_client"]


def test_state_appears_in_listing(client: StateClient) -> None:
    client.import_state("listed", TFSTATE)
    names = {item.state for item in client.list_states()}
    assert "listed" in names


def test_versions_record_serial_and_author(client: StateClient) -> None:
    client.import_state("versioned", TFSTATE)
    versions = client.list_versions("versioned")
    assert versions[0].serial == 12
    assert versions[0].terraform_version == "1.9.8"
    assert versions[0].size == len(TFSTATE)


def test_reimporting_identical_bytes_is_idempotent(client: StateClient) -> None:
    client.import_state("idem", TFSTATE)
    again = client.import_state("idem", TFSTATE)
    assert again["status"] == "unchanged"
    assert len(client.list_versions("idem")) == 1


def test_stale_serial_is_refused_over_the_wire(client: StateClient) -> None:
    client.import_state("guarded", TFSTATE)
    stale = TFSTATE.replace(b'"serial": 12', b'"serial": 3')
    with pytest.raises(StateClientError, match="serial went backwards"):
        client.import_state("guarded", stale)


def test_missing_state_export_is_a_clear_error(client: StateClient) -> None:
    with pytest.raises(StateClientError, match="not found"):
        client.export_state("never-created")


# -- command layer ----------------------------------------------------------


def test_cli_export_writes_byte_identical_file(
    server: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REPAVE_STATE_URL", server)
    monkeypatch.setenv("REPAVE_STATE_TENANT", "acme")

    source = tmp_path / "terraform.tfstate"
    source.write_bytes(TFSTATE)
    assert main(["state", "import", "cli-round", str(source)]) == 0

    destination = tmp_path / "exported.tfstate"
    assert main(["state", "export", "cli-round", "--out", str(destination)]) == 0
    assert destination.read_bytes() == TFSTATE


def test_cli_list_and_versions(
    server: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setenv("REPAVE_STATE_URL", server)
    monkeypatch.setenv("REPAVE_STATE_TENANT", "acme")
    source = tmp_path / "terraform.tfstate"
    source.write_bytes(TFSTATE)
    main(["state", "import", "cli-listed", str(source)])

    assert main(["state", "list"]) == 0
    assert "cli-listed" in capsys.readouterr().out

    assert main(["state", "versions", "cli-listed"]) == 0
    assert "serial 12" in capsys.readouterr().out


def test_cli_import_missing_file_is_an_error(
    server: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setenv("REPAVE_STATE_URL", server)
    assert main(["state", "import", "x", str(tmp_path / "nope.tfstate")]) == 1
    assert "no such state file" in capsys.readouterr().err


def test_cli_reports_unreachable_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setenv("REPAVE_STATE_URL", f"http://127.0.0.1:{_free_port()}")
    assert main(["state", "list"]) == 1
    assert "cannot reach" in capsys.readouterr().err
