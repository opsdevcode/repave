from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from repave_engine import __version__
from repave_engine.api_state import build_state_router
from repave_engine.auth import AuthConfig
from repave_engine.sql_store import DatabaseConfig
from repave_engine.state_contract import (
    CLIENT_HEADER,
    MIN_SUPPORTED_CLIENT,
    STATE_API_ENDPOINTS,
    ClientCompatibility,
    evaluate_client_version,
    parse_version,
)
from repave_engine.statestore.settings import StateStoreConfig
from statestore_support import make_state, managed_resource

BACKEND = "/api/state/v1/backend/acme/prod"


def _auth_config(api_token: str = "svc-token") -> AuthConfig:
    return AuthConfig(
        service_enabled=True,
        session_secret="secret",
        api_token=api_token,
        oidc_issuer="",
        oidc_client_id="",
        oidc_client_secret="",
        oidc_redirect_uri="",
        oidc_scopes=("openid",),
        groups_claim="groups",
        admin_groups=frozenset(),
        generator_groups=frozenset(),
    )


def _client(tmp_path: Path, auth_config: AuthConfig | None = None) -> TestClient:
    config = StateStoreConfig(
        database=DatabaseConfig(dialect="sqlite", sqlite_path=tmp_path / "state.db"),
    )
    app = FastAPI()
    app.include_router(
        build_state_router(repo_root=tmp_path, config=config, auth_config=auth_config)
    )
    return TestClient(app)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with _client(tmp_path) as instance:
        yield instance


# -- contract ---------------------------------------------------------------


def test_discovery_reports_contract(client: TestClient) -> None:
    payload = client.get("/api/state/v1").json()
    assert payload["api_version"] == "v1"
    assert payload["server_version"] == __version__
    assert payload["min_supported_client"] == MIN_SUPPORTED_CLIENT
    assert "GET /api/state/v1/states" in payload["endpoints"]


def test_contract_lists_every_mounted_client_route(client: TestClient) -> None:
    """Endpoints are advertised to pinned clients; drift here is a contract break."""
    declared = {entry.split(" ", 1)[1] for entry in STATE_API_ENDPOINTS}
    mounted = {
        route.path  # type: ignore[attr-defined]
        for route in client.app.routes  # type: ignore[attr-defined]
        if getattr(route, "path", "").startswith("/api/state/v1")
    }
    assert mounted <= declared, f"undeclared routes: {sorted(mounted - declared)}"


def test_parse_version_handles_suffixes() -> None:
    assert parse_version("2.24.0") == (2, 24, 0)
    assert parse_version("2.24.0-rc1") == (2, 24, 0)
    assert parse_version("nonsense") is None


def test_absent_client_header_is_allowed() -> None:
    """Stock terraform sends no header; refusing it would be a self-inflicted outage."""
    assert evaluate_client_version(None) == ClientCompatibility(supported=True)
    assert evaluate_client_version("") == ClientCompatibility(supported=True)


def test_old_client_is_rejected(client: TestClient) -> None:
    response = client.get("/api/state/v1/states", headers={CLIENT_HEADER: "1.0.0"})
    assert response.status_code == 426
    assert MIN_SUPPORTED_CLIENT in response.json()["detail"]


def test_current_client_gets_no_warning(client: TestClient) -> None:
    response = client.get("/api/state/v1/states", headers={CLIENT_HEADER: __version__})
    assert response.status_code == 200
    assert "Warning" not in response.headers


def test_unparseable_client_version_is_served_with_warning() -> None:
    outcome = evaluate_client_version("banana")
    assert outcome.supported
    assert "unrecognized" in outcome.warning


# -- terraform http backend protocol ---------------------------------------


def test_get_missing_state_returns_404(client: TestClient) -> None:
    assert client.get(BACKEND).status_code == 404


def test_post_then_get_round_trips_bytes(client: TestClient) -> None:
    raw = make_state()
    assert client.post(BACKEND, content=raw).status_code == 200
    response = client.get(BACKEND)
    assert response.status_code == 200
    assert response.content == raw


def test_post_invalid_document_returns_400(client: TestClient) -> None:
    response = client.post(BACKEND, content=b'{"version": 99}')
    assert response.status_code == 400


def test_post_stale_serial_returns_409(client: TestClient) -> None:
    client.post(BACKEND, content=make_state(serial=5))
    response = client.post(BACKEND, content=make_state(serial=2))
    assert response.status_code == 409
    assert "serial went backwards" in response.json()["detail"]


def test_lock_then_conflicting_lock_returns_423(client: TestClient) -> None:
    first = client.request("LOCK", BACKEND, content=json.dumps({"ID": "a", "Who": "alice"}))
    assert first.status_code == 200

    second = client.request("LOCK", BACKEND, content=json.dumps({"ID": "b", "Who": "bob"}))
    assert second.status_code == 423
    assert second.json()["Who"] == "alice"
    assert second.json()["ID"] == "a"


def test_lock_requires_body(client: TestClient) -> None:
    assert client.request("LOCK", BACKEND, content=b"").status_code == 400


def test_write_while_locked_requires_lock_id(client: TestClient) -> None:
    client.request("LOCK", BACKEND, content=json.dumps({"ID": "a", "Who": "alice"}))

    denied = client.post(BACKEND, content=make_state())
    assert denied.status_code == 423

    allowed = client.post(f"{BACKEND}?ID=a", content=make_state())
    assert allowed.status_code == 200


def test_unlock_releases(client: TestClient) -> None:
    client.request("LOCK", BACKEND, content=json.dumps({"ID": "a", "Who": "alice"}))
    released = client.request("UNLOCK", BACKEND, content=json.dumps({"ID": "a"}))
    assert released.status_code == 200
    assert released.json()["released"] is True
    assert client.post(BACKEND, content=make_state()).status_code == 200


def test_unlock_with_wrong_id_returns_423(client: TestClient) -> None:
    client.request("LOCK", BACKEND, content=json.dumps({"ID": "a", "Who": "alice"}))
    response = client.request("UNLOCK", BACKEND, content=json.dumps({"ID": "zzz"}))
    assert response.status_code == 423


def test_delete_removes_state(client: TestClient) -> None:
    client.post(BACKEND, content=make_state())
    assert client.delete(BACKEND).status_code == 200
    assert client.get(BACKEND).status_code == 404
    assert client.delete(BACKEND).status_code == 404


# -- repave-tf client surface ----------------------------------------------


def test_list_states_and_describe(client: TestClient) -> None:
    client.post(BACKEND, content=make_state(serial=1))
    client.post(BACKEND, content=make_state(serial=2))

    listed = client.get("/api/state/v1/states").json()["states"]
    assert [item["state"] for item in listed] == ["prod"]
    assert listed[0]["serial"] == 2
    assert listed[0]["version_count"] == 2

    detail = client.get("/api/state/v1/states/acme/prod").json()
    assert detail["lock"] is None
    assert detail["tenant"] == "acme"


def test_describe_missing_state_returns_404(client: TestClient) -> None:
    assert client.get("/api/state/v1/states/acme/nope").status_code == 404


def test_export_is_byte_identical_to_import(client: TestClient) -> None:
    raw = make_state(resources=[{"mode": "managed", "type": "aws_vpc", "name": "main"}])
    imported = client.post("/api/state/v1/states/acme/prod/import", content=raw)
    assert imported.status_code == 200
    assert imported.json()["status"] == "created"

    exported = client.get("/api/state/v1/states/acme/prod/export")
    assert exported.content == raw


def test_import_rejects_invalid_document(client: TestClient) -> None:
    response = client.post("/api/state/v1/states/acme/prod/import", content=b"{}")
    assert response.status_code == 400


def test_import_conflict_returns_409(client: TestClient) -> None:
    client.post("/api/state/v1/states/acme/prod/import", content=make_state(serial=4))
    response = client.post("/api/state/v1/states/acme/prod/import", content=make_state(serial=1))
    assert response.status_code == 409


def test_versions_listing(client: TestClient) -> None:
    for serial in (1, 2, 3):
        client.post(BACKEND, content=make_state(serial=serial))
    versions = client.get("/api/state/v1/states/acme/prod/versions").json()["versions"]
    assert [item["serial"] for item in versions] == [3, 2, 1]
    assert all(item["author"] for item in versions)


def test_versions_missing_state_returns_404(client: TestClient) -> None:
    assert client.get("/api/state/v1/states/acme/nope/versions").status_code == 404


# -- auth -------------------------------------------------------------------


def test_backend_requires_credentials_in_service_mode(tmp_path: Path) -> None:
    with _client(tmp_path, _auth_config()) as client:
        assert client.get(BACKEND).status_code == 401


def test_backend_accepts_basic_auth(tmp_path: Path) -> None:
    """Terraform's http backend can only send Basic credentials or mTLS."""
    with _client(tmp_path, _auth_config("svc-token")) as client:
        encoded = base64.b64encode(b"terraform:svc-token").decode()
        headers = {"Authorization": f"Basic {encoded}"}
        assert client.post(BACKEND, content=make_state(), headers=headers).status_code == 200
        assert client.get(BACKEND, headers=headers).status_code == 200


def test_backend_rejects_wrong_basic_password(tmp_path: Path) -> None:
    with _client(tmp_path, _auth_config("svc-token")) as client:
        encoded = base64.b64encode(b"terraform:wrong").decode()
        response = client.get(BACKEND, headers={"Authorization": f"Basic {encoded}"})
        assert response.status_code == 401


def test_backend_rejects_malformed_basic_header(tmp_path: Path) -> None:
    with _client(tmp_path, _auth_config()) as client:
        response = client.get(BACKEND, headers={"Authorization": "Basic !!!not-base64"})
        assert response.status_code == 401


def test_backend_accepts_bearer_token(tmp_path: Path) -> None:
    with _client(tmp_path, _auth_config("svc-token")) as client:
        headers = {"Authorization": "Bearer svc-token"}
        assert client.post(BACKEND, content=make_state(), headers=headers).status_code == 200


# -- resource graph ---------------------------------------------------------


def _seed_graph(client: TestClient) -> None:
    resources = [
        managed_resource("aws_vpc", "main"),
        managed_resource("aws_subnet", "web", depends_on=["aws_vpc.main"]),
        managed_resource("aws_instance", "app", depends_on=["aws_subnet.web"]),
    ]
    assert client.post(BACKEND, content=make_state(resources=resources)).status_code == 200


def test_resources_endpoint_lists_the_graph(client: TestClient) -> None:
    _seed_graph(client)
    payload = client.get("/api/state/v1/states/acme/prod/resources").json()
    assert [row["address"] for row in payload["resources"]] == [
        "aws_instance.app",
        "aws_subnet.web",
        "aws_vpc.main",
    ]


def test_resources_endpoint_filters_by_type(client: TestClient) -> None:
    _seed_graph(client)
    payload = client.get(
        "/api/state/v1/states/acme/prod/resources", params={"type": "aws_vpc"}
    ).json()
    assert [row["address"] for row in payload["resources"]] == ["aws_vpc.main"]


def test_inventory_endpoint_totals_resources(client: TestClient) -> None:
    _seed_graph(client)
    payload = client.get("/api/state/v1/states/acme/prod/inventory").json()
    assert payload["total"] == 3
    assert {entry["type"] for entry in payload["inventory"]} == {
        "aws_vpc",
        "aws_subnet",
        "aws_instance",
    }


def test_graph_endpoint_returns_nodes_and_edges(client: TestClient) -> None:
    _seed_graph(client)
    payload = client.get("/api/state/v1/states/acme/prod/graph").json()
    assert len(payload["nodes"]) == 3
    assert {(edge["from"], edge["to"]) for edge in payload["edges"]} == {
        ("aws_subnet.web", "aws_vpc.main"),
        ("aws_instance.app", "aws_subnet.web"),
    }


def test_blast_radius_endpoint_reports_dependents_and_dependencies(client: TestClient) -> None:
    _seed_graph(client)
    payload = client.get(
        "/api/state/v1/states/acme/prod/blast-radius", params={"address": "aws_subnet.web"}
    ).json()
    assert payload["affected"] == ["aws_instance.app"]
    assert payload["affected_count"] == 1
    assert payload["depends_on"] == ["aws_vpc.main"]


def test_drift_endpoint_reports_only_changes(client: TestClient) -> None:
    _seed_graph(client)
    refreshed = make_state(
        resources=[
            managed_resource("aws_vpc", "main"),
            managed_resource("aws_subnet", "web", depends_on=["aws_vpc.main"]),
        ]
    )
    payload = client.post("/api/state/v1/states/acme/prod/drift", content=refreshed).json()
    assert payload["compared_count"] == 3
    assert payload["changed_count"] == 1
    assert payload["drift"][0] == {
        "address": "aws_instance.app",
        "status": "removed",
        "changed_keys": [],
    }


def test_drift_endpoint_rejects_a_non_state_body(client: TestClient) -> None:
    _seed_graph(client)
    response = client.post("/api/state/v1/states/acme/prod/drift", content=b"{}")
    assert response.status_code == 400


def test_graph_endpoints_404_on_unknown_state(client: TestClient) -> None:
    for path in ("resources", "inventory", "graph"):
        assert client.get(f"/api/state/v1/states/acme/missing/{path}").status_code == 404
    assert (
        client.get(
            "/api/state/v1/states/acme/missing/blast-radius", params={"address": "aws_vpc.main"}
        ).status_code
        == 404
    )


def test_provider_schema_cache_redacts_subsequent_writes(client: TestClient) -> None:
    schema = {
        "provider_schemas": {
            "registry.terraform.io/hashicorp/aws": {
                "resource_schemas": {
                    "aws_db_instance": {"block": {"attributes": {"endpoint": {"sensitive": True}}}}
                }
            }
        }
    }
    cached = client.post(
        "/api/state/v1/provider-schemas",
        params={"provider": "hashicorp/aws", "version": "5.0.0"},
        json=schema,
    )
    assert cached.status_code == 200
    assert cached.json()["types"] == 1

    resource = managed_resource(
        "aws_db_instance", "db", attributes={"id": "db-1", "endpoint": "host:5432"}
    )
    assert client.post(BACKEND, content=make_state(resources=[resource])).status_code == 200

    # The blob keeps the real value; only the queryable index is redacted.
    exported = client.get("/api/state/v1/states/acme/prod/export").json()
    assert exported["resources"][0]["instances"][0]["attributes"]["endpoint"] == "host:5432"


def test_provider_schema_rejects_invalid_json(client: TestClient) -> None:
    response = client.post(
        "/api/state/v1/provider-schemas",
        params={"provider": "hashicorp/aws"},
        content=b"not json",
    )
    assert response.status_code == 400


def test_blast_radius_cost_joins_infracost_by_address(client: TestClient) -> None:
    _seed_graph(client)
    breakdown = {
        "currency": "USD",
        "projects": [
            {
                "breakdown": {
                    "resources": [
                        {"name": "aws_subnet.web", "monthlyCost": "5.00"},
                        {
                            "name": "aws_instance.app",
                            "monthlyCost": "30.00",
                            "subresources": [{"name": "root_block_device", "monthlyCost": "2.50"}],
                        },
                    ]
                }
            }
        ],
    }
    payload = client.post(
        "/api/state/v1/states/acme/prod/blast-radius/cost",
        params={"address": "aws_subnet.web"},
        json=breakdown,
    ).json()

    assert payload["scope"] == ["aws_subnet.web", "aws_instance.app"]
    # 5.00 for the subnet + 30.00 + 2.50 rolled up from the instance's subresource.
    assert payload["monthly_cost"] == "37.50"
    assert payload["unpriced"] == []


def test_blast_radius_cost_reports_unpriced_resources(client: TestClient) -> None:
    _seed_graph(client)
    breakdown = {"projects": [{"breakdown": {"resources": [{"name": "aws_vpc.main"}]}}]}
    payload = client.post(
        "/api/state/v1/states/acme/prod/blast-radius/cost",
        params={"address": "aws_vpc.main"},
        json=breakdown,
    ).json()

    assert payload["monthly_cost"] == "0.00"
    assert payload["unpriced"] == ["aws_instance.app", "aws_subnet.web"]


def test_blast_radius_cost_rejects_invalid_json(client: TestClient) -> None:
    _seed_graph(client)
    response = client.post(
        "/api/state/v1/states/acme/prod/blast-radius/cost",
        params={"address": "aws_vpc.main"},
        content=b"not json",
    )
    assert response.status_code == 400
