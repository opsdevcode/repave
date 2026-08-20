from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from itsdangerous import URLSafeSerializer

from license_helpers import install_repave_license
from repave_engine.api import create_app
from repave_engine.session_store import load_session_store
from repave_engine.settings import OutputConfig
from repave_engine.sql_store import connect, ensure_schema, load_session, save_session


def _write_sql_durability_config(repo_root: Path, db_rel: str) -> None:
    (repo_root / "repave.config.yaml").write_text(
        f"""
durability:
  async_generation: true
  database_url: sqlite:///{db_rel}
  export_jsonl: false
  require_session_secret: true
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_session_store_roundtrip(tmp_path: Path) -> None:
    _write_sql_durability_config(tmp_path, "data/repave.sqlite")
    store = load_session_store(tmp_path)
    assert store is not None

    session_id = store.create_id()
    payload = {"repave_user": {"sub": "user-1", "email": "u@example.com", "role": "admin"}}
    store.save(session_id, payload)
    assert store.load(session_id) == payload

    store.delete(session_id)
    assert store.load(session_id) is None


def test_session_store_expired_session_removed(tmp_path: Path) -> None:
    _write_sql_durability_config(tmp_path, "data/repave.sqlite")
    store = load_session_store(tmp_path)
    assert store is not None

    session_id = store.create_id()
    with connect(store.database) as conn:
        ensure_schema(conn)
        save_session(
            conn,
            session_id,
            {"repave_user": {"sub": "old"}},
            expires_at="2000-01-01T00:00:00+00:00",
            updated_at="2000-01-01T00:00:00+00:00",
        )
        conn.commit()

    assert store.load(session_id) is None
    with connect(store.database) as conn:
        ensure_schema(conn)
        assert load_session(conn, session_id, now="2026-01-01T00:00:00+00:00") is None


def test_sql_sessions_shared_across_app_instances(
    tmp_path: Path,
    output_config: OutputConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_sql_durability_config(tmp_path, "data/repave.sqlite")
    monkeypatch.setenv("REPAVE_SESSION_SECRET", "shared-secret")
    monkeypatch.setenv("REPAVE_SERVICE_MODE", "1")
    monkeypatch.setenv("REPAVE_OIDC_ISSUER", "https://idp.example.com")
    monkeypatch.setenv("REPAVE_OIDC_CLIENT_ID", "client")
    monkeypatch.setenv("REPAVE_OIDC_CLIENT_SECRET", "secret")
    monkeypatch.setenv("REPAVE_OIDC_REDIRECT_URI", "https://repave.example.com/auth/callback")
    install_repave_license(monkeypatch, tmp_path)

    store = load_session_store(tmp_path)
    assert store is not None
    session_id = store.create_id()
    store.save(
        session_id,
        {"repave_user": {"sub": "user-42", "email": "user@example.com", "role": "generator"}},
    )

    signer = URLSafeSerializer("shared-secret", salt="repave-sql-session")
    cookie_value = signer.dumps(session_id)

    app_b = create_app(repo_root=tmp_path, output_config=output_config)
    client_b = TestClient(app_b)
    client_b.cookies.set("session", cookie_value)

    response = client_b.get("/")
    assert response.status_code == 200


def test_sql_session_logout_deletes_server_row(
    tmp_path: Path,
    output_config: OutputConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_sql_durability_config(tmp_path, "data/repave.sqlite")
    monkeypatch.setenv("REPAVE_SESSION_SECRET", "shared-secret")

    store = load_session_store(tmp_path)
    assert store is not None
    session_id = store.create_id()
    store.save(
        session_id,
        {"repave_user": {"sub": "user-1", "email": "u@example.com", "role": "viewer"}},
    )

    signer = URLSafeSerializer("shared-secret", salt="repave-sql-session")
    client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))
    client.cookies.set("session", signer.dumps(session_id))

    response = client.post("/auth/logout", follow_redirects=False)
    assert response.status_code == 302
    assert store.load(session_id) is None


def test_readiness_includes_session_store_when_sql_enabled(
    tmp_path: Path,
    output_config: OutputConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_sql_durability_config(tmp_path, "data/repave.sqlite")
    monkeypatch.setenv("REPAVE_SESSION_SECRET", "shared-secret")

    client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))
    payload = client.get("/readyz").json()

    assert payload["checks"]["session_store"] is True


def test_service_mode_uses_sql_sessions(
    tmp_path: Path,
    output_config: OutputConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_sql_durability_config(tmp_path, "data/repave.sqlite")
    monkeypatch.setenv("REPAVE_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("REPAVE_SERVICE_MODE", "1")
    monkeypatch.setenv("REPAVE_OIDC_ISSUER", "https://idp.example.com")
    monkeypatch.setenv("REPAVE_OIDC_CLIENT_ID", "client")
    monkeypatch.setenv("REPAVE_OIDC_CLIENT_SECRET", "secret")
    monkeypatch.setenv("REPAVE_OIDC_REDIRECT_URI", "https://repave.example.com/auth/callback")
    install_repave_license(monkeypatch, tmp_path)

    client = TestClient(
        create_app(repo_root=tmp_path, output_config=output_config),
        raise_server_exceptions=False,
    )
    assert client.post("/api/v1/generate", json={}).status_code == 401

    store = load_session_store(tmp_path)
    assert store is not None
    session_id = store.create_id()
    store.save(
        session_id,
        {"repave_user": {"sub": "gen", "email": "gen@example.com", "role": "generator"}},
    )
    signer = URLSafeSerializer("test-secret", salt="repave-sql-session")
    client.cookies.set("session", signer.dumps(session_id))

    assert client.get("/").status_code == 200
