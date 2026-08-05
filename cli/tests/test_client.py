from __future__ import annotations

import json

import httpx
import pytest
from repave_engine.state_contract import CLIENT_HEADER

from repave_cli import __version__
from repave_cli.client import StateClient, StateClientError
from repave_cli.config import ClientConfig


def _client(handler, token: str = "") -> StateClient:
    config = ClientConfig(base_url="https://repave.example.com", token=token, tenant="acme")
    return StateClient(config, transport=httpx.MockTransport(handler))


def test_sends_client_version_header() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json={"states": []})

    with _client(handler) as client:
        client.list_states()
    assert seen[CLIENT_HEADER.lower()] == __version__


def test_sends_bearer_token_when_configured() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json={"states": []})

    with _client(handler, token="abc123") as client:
        client.list_states()
    assert seen["authorization"] == "Bearer abc123"


def test_omits_authorization_without_token() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json={"states": []})

    with _client(handler) as client:
        client.list_states()
    assert "authorization" not in seen


def test_list_states_parses_payload() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "states": [
                    {
                        "tenant": "acme",
                        "state": "prod",
                        "serial": 7,
                        "version_count": 3,
                        "updated_at": "2026-08-04T00:00:00+00:00",
                        "locked": True,
                    }
                ]
            },
        )

    with _client(handler) as client:
        states = client.list_states()
    assert len(states) == 1
    assert states[0].state == "prod"
    assert states[0].serial == 7
    assert states[0].locked is True


def test_list_states_scopes_to_configured_tenant() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json={"states": []})

    with _client(handler) as client:
        client.list_states()
    assert seen["tenant"] == "acme"


def test_export_returns_raw_bytes_untouched() -> None:
    raw = json.dumps({"version": 4, "serial": 1, "lineage": "x"}, indent=4).encode()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=raw)

    with _client(handler) as client:
        assert client.export_state("prod") == raw


def test_import_posts_body_verbatim() -> None:
    captured: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content
        return httpx.Response(200, json={"status": "created", "serial": 1})

    raw = b'{\n  "version": 4\n}'
    with _client(handler) as client:
        result = client.import_state("prod", raw)
    assert captured["body"] == raw
    assert result["status"] == "created"


def test_versions_parsed() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "versions": [
                    {
                        "version_id": "v1",
                        "serial": 2,
                        "terraform_version": "1.9.0",
                        "size": 120,
                        "author": "dev@example.com",
                        "created_at": "2026-08-04T00:00:00+00:00",
                    }
                ]
            },
        )

    with _client(handler) as client:
        versions = client.list_versions("prod")
    assert versions[0].serial == 2
    assert versions[0].author == "dev@example.com"


# -- error mapping ----------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, "REPAVE_STATE_TOKEN"),
        (403, "forbidden"),
        (404, "not found"),
        (500, "state server returned 500"),
    ],
)
def test_error_statuses_name_the_fix(status: int, expected: str) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": "boom"})

    with _client(handler) as client, pytest.raises(StateClientError, match=expected):
        client.list_states()


def test_upgrade_required_explains_client_is_stale() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(426, json={"detail": "repave-tf 1.0.0 is older than 2.24.0"})

    with _client(handler) as client, pytest.raises(StateClientError, match="too old"):
        client.list_states()


def test_conflict_surfaces_server_detail() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "serial went backwards"})

    with _client(handler) as client, pytest.raises(StateClientError, match="serial went backwards"):
        client.import_state("prod", b"{}")


def test_unreachable_server_names_the_address() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with _client(handler) as client, pytest.raises(StateClientError, match=r"repave\.example\.com"):
        client.list_states()


def test_non_json_error_body_falls_back_to_text() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"upstream exploded")

    with _client(handler) as client, pytest.raises(StateClientError, match="upstream exploded"):
        client.list_states()
