from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from repave_engine.api import create_app
from repave_engine.cli import build_parser, cmd_fleet, cmd_register, cmd_unregister

PROVENANCE = """
apiVersion: repave.dev/v1beta1
kind: GoldenPathArtifact
spec:
  blueprint:
    name: terraform-module-generic
    version: 0.9.0
  standard:
    source: standards/terraform-standards
    version: 1.1.0
"""

REPO_URL = "https://github.com/acme/tf-vpc.git"


@pytest.fixture
def module_checkout(tmp_path: Path) -> Path:
    checkout = tmp_path / "tf-vpc"
    checkout.mkdir()
    (checkout / "repave.yaml").write_text(PROVENANCE, encoding="utf-8")
    return checkout


@pytest.fixture
def registry_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    registry = tmp_path / "registry.jsonl"
    monkeypatch.setenv("REPAVE_FLEET_FILE", str(registry))
    return registry


def _args(**kwargs: object):
    defaults = {
        "repo_root": ".",
        "path": None,
        "blueprint": None,
        "blueprint_version": None,
        "standard_source": None,
        "standard_version": None,
        "owner": None,
        "format": "json",
    }
    defaults.update(kwargs)
    return type("Args", (), defaults)()


def test_cli_register_reads_pins_from_checkout(
    registry_env: Path, module_checkout: Path, capsys
) -> None:
    assert cmd_register(_args(repo_url=REPO_URL, path=str(module_checkout))) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["blueprint_name"] == "terraform-module-generic"
    assert payload["blueprint_version"] == "0.9.0"
    assert payload["repo_url"] == "https://github.com/acme/tf-vpc"
    assert registry_env.is_file()


def test_cli_register_accepts_explicit_pins(registry_env: Path, capsys) -> None:
    code = cmd_register(
        _args(repo_url=REPO_URL, blueprint="helm-chart-generic", blueprint_version="0.2.0")
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["blueprint_name"] == "helm-chart-generic"


def test_cli_register_requires_pins_or_path(registry_env: Path) -> None:
    with pytest.raises(ValueError, match="--path"):
        cmd_register(_args(repo_url=REPO_URL))


def test_cli_register_without_configured_registry_explains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("REPAVE_FLEET_FILE", raising=False)
    with pytest.raises(ValueError, match="not configured"):
        cmd_register(_args(repo_url=REPO_URL, blueprint="x", repo_root=str(tmp_path)))


def test_cli_fleet_lists_and_unregister_round_trip(
    registry_env: Path, module_checkout: Path, capsys
) -> None:
    cmd_register(_args(repo_url=REPO_URL, path=str(module_checkout)))
    capsys.readouterr()

    assert cmd_fleet(_args(repo_url=REPO_URL, format="json")) == 0
    listed = json.loads(capsys.readouterr().out)
    assert [item["repo_url"] for item in listed] == ["https://github.com/acme/tf-vpc"]

    assert cmd_unregister(_args(repo_url=REPO_URL)) == 0
    capsys.readouterr()

    assert cmd_fleet(_args(repo_url=REPO_URL, format="json")) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_cli_unregister_unknown_repo_exits_nonzero(registry_env: Path, capsys) -> None:
    assert cmd_unregister(_args(repo_url=REPO_URL)) == 1
    assert "not registered" in capsys.readouterr().out


def test_cli_fleet_text_output_is_human_readable(
    registry_env: Path, module_checkout: Path, capsys
) -> None:
    cmd_register(_args(repo_url=REPO_URL, path=str(module_checkout), owner="platform"))
    capsys.readouterr()

    cmd_fleet(_args(repo_url=REPO_URL, format="text"))
    out = capsys.readouterr().out
    assert "terraform-module-generic@0.9.0" in out
    assert "owner=platform" in out


def test_parser_exposes_fleet_commands() -> None:
    parser = build_parser()
    for argv in (
        ["register", REPO_URL, "--path", "/tmp/x"],
        ["unregister", REPO_URL],
        ["fleet", "--format", "json"],
    ):
        assert parser.parse_args(argv).func is not None


def test_api_fleet_register_list_and_unregister(
    repo_root, output_config, registry_env: Path, module_checkout: Path
) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    created = client.post(
        "/api/v1/fleet",
        json={"repo_url": REPO_URL, "path": str(module_checkout), "owner": "platform"},
    )
    assert created.status_code == 201
    assert created.json()["registered"]["blueprint_name"] == "terraform-module-generic"

    listed = client.get("/api/v1/fleet")
    assert listed.status_code == 200
    body = listed.json()
    assert body["count"] == 1
    assert body["repos"][0]["owner"] == "platform"

    removed = client.request("DELETE", "/api/v1/fleet", params={"repo_url": REPO_URL})
    assert removed.status_code == 200
    assert client.get("/api/v1/fleet").json()["count"] == 0


def test_api_fleet_rejects_missing_fields(repo_root, output_config, registry_env: Path) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    assert client.post("/api/v1/fleet", json={}).status_code == 400
    assert client.post("/api/v1/fleet", json={"repo_url": REPO_URL}).status_code == 400
    assert client.request("DELETE", "/api/v1/fleet").status_code == 400
    assert (
        client.request("DELETE", "/api/v1/fleet", params={"repo_url": REPO_URL}).status_code == 404
    )


def test_api_fleet_requires_auth_in_service_mode(
    repo_root, output_config, registry_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REPAVE_SERVICE_MODE", "1")
    monkeypatch.setenv("REPAVE_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("REPAVE_DATABASE_URL", f"sqlite:///{registry_env.parent}/repave.sqlite")
    monkeypatch.setenv("REPAVE_OIDC_ISSUER", "https://idp.example.com")
    monkeypatch.setenv("REPAVE_OIDC_CLIENT_ID", "client")
    monkeypatch.setenv("REPAVE_OIDC_CLIENT_SECRET", "secret")
    monkeypatch.setenv("REPAVE_OIDC_REDIRECT_URI", "https://repave.example.com/auth/callback")

    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    assert client.get("/api/v1/fleet").status_code == 401
    assert client.post("/api/v1/fleet", json={"repo_url": REPO_URL}).status_code == 401


def test_fleet_route_roles_are_least_privilege() -> None:
    from fastapi import HTTPException

    from repave_engine.auth import ROLE_ADMIN, ROLE_GENERATOR, ROLE_VIEWER, AuthUser, require_role

    viewer = AuthUser(subject="v", email="v@example.com", role=ROLE_VIEWER)
    generator = AuthUser(subject="g", email="g@example.com", role=ROLE_GENERATOR)
    admin = AuthUser(subject="a", email="a@example.com", role=ROLE_ADMIN)

    # Reading the fleet is open to any authenticated role.
    for user in (viewer, generator, admin):
        require_role(user, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)

    # Mutating it is admin-only.
    require_role(admin, ROLE_ADMIN)
    for user in (viewer, generator):
        with pytest.raises(HTTPException) as excinfo:
            require_role(user, ROLE_ADMIN)
        assert excinfo.value.status_code == 403


def test_api_fleet_unconfigured_registry_returns_404(
    repo_root, output_config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("REPAVE_FLEET_FILE", raising=False)
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))

    assert client.get("/api/v1/fleet").status_code == 404
