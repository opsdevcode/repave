from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import pytest

from repave_engine.sql_store import DatabaseConfig, connect
from repave_engine.statestore.crypto import (
    STATE_KEK_ENV,
    STATE_KEK_ID_ENV,
    StateCrypto,
    StateCryptoError,
    load_state_crypto,
    open_blob,
    seal_blob,
)
from repave_engine.statestore.state_document import StateDocumentError, parse_state_document
from repave_engine.statestore.store import (
    LockInfo,
    StateCorruptionError,
    StateStore,
    ensure_state_schema,
    parse_lock_body,
)
from statestore_support import make_state


@pytest.fixture
def store(tmp_path: Path) -> StateStore:
    conn = connect(DatabaseConfig(dialect="sqlite", sqlite_path=tmp_path / "state.db"))
    ensure_state_schema(conn)
    return StateStore(conn)


# -- state document parsing -------------------------------------------------


def test_parse_rejects_empty() -> None:
    with pytest.raises(StateDocumentError, match="empty"):
        parse_state_document(b"   ")


def test_parse_rejects_non_json() -> None:
    with pytest.raises(StateDocumentError, match="valid JSON"):
        parse_state_document(b"not json")


def test_parse_rejects_non_object() -> None:
    with pytest.raises(StateDocumentError, match="JSON object"):
        parse_state_document(b"[1, 2, 3]")


def test_parse_rejects_unsupported_version() -> None:
    raw = json.dumps({"version": 3, "serial": 1, "lineage": "x"}).encode()
    with pytest.raises(StateDocumentError, match="unsupported state format version 3"):
        parse_state_document(raw)


def test_parse_rejects_missing_lineage() -> None:
    raw = json.dumps({"version": 4, "serial": 1}).encode()
    with pytest.raises(StateDocumentError, match="lineage"):
        parse_state_document(raw)


def test_parse_rejects_negative_serial() -> None:
    raw = json.dumps({"version": 4, "serial": -1, "lineage": "x"}).encode()
    with pytest.raises(StateDocumentError, match="serial"):
        parse_state_document(raw)


def test_parse_keeps_raw_bytes_for_byte_exactness() -> None:
    raw = make_state()
    doc = parse_state_document(raw)
    assert doc.raw == raw
    assert doc.serial == 1
    assert doc.terraform_version == "1.9.0"


# -- crypto -----------------------------------------------------------------


def test_seal_open_round_trip() -> None:
    crypto = StateCrypto(key=os.urandom(32), key_id="k1")
    plaintext = make_state()
    sealed, label, key_id = seal_blob(plaintext, crypto)
    assert label == "aes-256-gcm"
    assert key_id == "k1"
    assert plaintext not in sealed
    assert open_blob(sealed, label, crypto) == plaintext


def test_seal_without_crypto_is_passthrough() -> None:
    plaintext = make_state()
    sealed, label, key_id = seal_blob(plaintext, None)
    assert (sealed, label, key_id) == (plaintext, "none", None)


def test_open_with_wrong_key_fails() -> None:
    sealed, label, _ = seal_blob(make_state(), StateCrypto(key=os.urandom(32), key_id="k1"))
    other = StateCrypto(key=os.urandom(32), key_id="k1")
    with pytest.raises(StateCryptoError, match="failed authentication"):
        open_blob(sealed, label, other)


def test_open_with_wrong_key_id_names_the_mismatch() -> None:
    crypto = StateCrypto(key=os.urandom(32), key_id="k1")
    sealed, label, _ = seal_blob(make_state(), crypto)
    rotated = StateCrypto(key=crypto.key, key_id="k2")
    with pytest.raises(StateCryptoError, match="sealed with key id"):
        open_blob(sealed, label, rotated)


def test_open_encrypted_without_key_explains() -> None:
    sealed, label, _ = seal_blob(make_state(), StateCrypto(key=os.urandom(32), key_id="k1"))
    with pytest.raises(StateCryptoError, match="REPAVE_STATE_KEK is not set"):
        open_blob(sealed, label, None)


def test_open_rejects_truncated_envelope() -> None:
    crypto = StateCrypto(key=os.urandom(32), key_id="k1")
    sealed, label, _ = seal_blob(make_state(), crypto)
    with pytest.raises(StateCryptoError):
        open_blob(sealed[:20], label, crypto)


def test_load_crypto_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(STATE_KEK_ENV, raising=False)
    assert load_state_crypto() is None


def test_load_crypto_rejects_short_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(STATE_KEK_ENV, base64.b64encode(b"tooshort").decode())
    with pytest.raises(StateCryptoError, match="32 bytes"):
        load_state_crypto()


def test_load_crypto_rejects_non_base64(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(STATE_KEK_ENV, "not base64 !!!")
    with pytest.raises(StateCryptoError, match="base64"):
        load_state_crypto()


def test_load_crypto_reads_key_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(STATE_KEK_ENV, base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setenv(STATE_KEK_ID_ENV, "kek-2026")
    crypto = load_state_crypto()
    assert crypto is not None and crypto.key_id == "kek-2026"


# -- write guards -----------------------------------------------------------


def test_first_write_creates_version(store: StateStore) -> None:
    outcome = store.write_state("acme", "prod", make_state(), author="dev@example.com")
    assert outcome.status == "created"
    assert outcome.serial == 1
    assert outcome.accepted


def test_round_trip_is_byte_exact(store: StateStore) -> None:
    raw = make_state(resources=[{"mode": "managed", "type": "aws_s3_bucket", "name": "b"}])
    store.write_state("acme", "prod", raw, author="dev")
    assert store.read_current_bytes("acme", "prod") == raw


def test_round_trip_is_byte_exact_when_encrypted(tmp_path: Path) -> None:
    conn = connect(DatabaseConfig(dialect="sqlite", sqlite_path=tmp_path / "state.db"))
    ensure_state_schema(conn)
    encrypted = StateStore(conn, crypto=StateCrypto(key=os.urandom(32), key_id="k1"))
    raw = make_state()
    encrypted.write_state("acme", "prod", raw, author="dev")
    assert encrypted.read_current_bytes("acme", "prod") == raw

    stored = conn.execute("SELECT blob, encryption FROM state_versions").fetchone()
    assert stored["encryption"] == "aes-256-gcm"
    assert b"lineage" not in bytes(stored["blob"])


def test_serial_must_advance(store: StateStore) -> None:
    store.write_state("acme", "prod", make_state(serial=5), author="dev")
    outcome = store.write_state("acme", "prod", make_state(serial=4), author="dev")
    assert outcome.status == "conflict"
    assert "serial went backwards" in outcome.detail


def test_lineage_mismatch_is_rejected(store: StateStore) -> None:
    store.write_state("acme", "prod", make_state(serial=1, lineage="lineage-a"), author="dev")
    outcome = store.write_state(
        "acme", "prod", make_state(serial=2, lineage="lineage-b"), author="dev"
    )
    assert outcome.status == "conflict"
    assert "lineage mismatch" in outcome.detail


def test_same_serial_identical_content_is_idempotent(store: StateStore) -> None:
    raw = make_state(serial=3)
    store.write_state("acme", "prod", raw, author="dev")
    outcome = store.write_state("acme", "prod", raw, author="dev")
    assert outcome.status == "unchanged"
    assert len(store.list_versions("acme", "prod")) == 1


def test_same_serial_different_content_conflicts(store: StateStore) -> None:
    store.write_state("acme", "prod", make_state(serial=3), author="dev")
    changed = make_state(
        serial=3, resources=[{"mode": "managed", "type": "aws_vpc", "name": "main"}]
    )
    outcome = store.write_state("acme", "prod", changed, author="dev")
    assert outcome.status == "conflict"
    assert "already exists with different content" in outcome.detail


def test_invalid_document_is_rejected_without_creating_a_version(store: StateStore) -> None:
    outcome = store.write_state("acme", "prod", b"{}", author="dev")
    assert outcome.status == "invalid"
    assert store.list_versions("acme", "prod") == []


def test_versions_accumulate_newest_first(store: StateStore) -> None:
    for serial in (1, 2, 3):
        store.write_state("acme", "prod", make_state(serial=serial), author="dev")
    versions = store.list_versions("acme", "prod")
    assert [item.serial for item in versions] == [3, 2, 1]
    assert store.read_current_bytes("acme", "prod") == make_state(serial=3)


def test_older_version_bytes_remain_readable(store: StateStore) -> None:
    store.write_state("acme", "prod", make_state(serial=1), author="dev")
    store.write_state("acme", "prod", make_state(serial=2), author="dev")
    oldest = store.list_versions("acme", "prod")[-1]
    assert store.read_version_bytes(oldest.version_id) == make_state(serial=1)


def test_corrupted_blob_is_detected_on_read(store: StateStore) -> None:
    store.write_state("acme", "prod", make_state(), author="dev")
    store.connection.execute("UPDATE state_versions SET blob = ?", (b'{"version": 4}',))
    store.connection.commit()
    with pytest.raises(StateCorruptionError, match="digest mismatch"):
        store.read_current_bytes("acme", "prod")


def test_read_missing_state_returns_none(store: StateStore) -> None:
    assert store.read_current_bytes("acme", "nope") is None


def test_delete_removes_state_and_versions(store: StateStore) -> None:
    store.write_state("acme", "prod", make_state(), author="dev")
    assert store.delete_state("acme", "prod") is True
    assert store.state_exists("acme", "prod") is False
    assert store.delete_state("acme", "prod") is False


# -- locks ------------------------------------------------------------------


def test_lock_acquire_and_release(store: StateStore) -> None:
    lock = LockInfo(id="lock-1", who="dev@host", operation="OperationTypeApply")
    assert store.acquire_lock("acme", "prod", lock).status == "acquired"
    assert store.current_lock("acme", "prod") is not None
    assert store.release_lock("acme", "prod", "lock-1").status == "released"
    assert store.current_lock("acme", "prod") is None


def test_second_lock_reports_holder(store: StateStore) -> None:
    store.acquire_lock("acme", "prod", LockInfo(id="lock-1", who="alice"))
    outcome = store.acquire_lock("acme", "prod", LockInfo(id="lock-2", who="bob"))
    assert outcome.status == "held"
    assert outcome.holder is not None and outcome.holder.who == "alice"


def test_relocking_with_same_id_is_idempotent(store: StateStore) -> None:
    store.acquire_lock("acme", "prod", LockInfo(id="lock-1", who="alice"))
    assert store.acquire_lock("acme", "prod", LockInfo(id="lock-1", who="alice")).status == (
        "acquired"
    )


def test_unlock_with_wrong_id_is_rejected(store: StateStore) -> None:
    store.acquire_lock("acme", "prod", LockInfo(id="lock-1", who="alice"))
    outcome = store.release_lock("acme", "prod", "lock-9")
    assert outcome.status == "mismatch"
    assert store.current_lock("acme", "prod") is not None


def test_force_unlock_without_id_is_allowed(store: StateStore) -> None:
    store.acquire_lock("acme", "prod", LockInfo(id="lock-1", who="alice"))
    assert store.release_lock("acme", "prod", None).status == "released"


def test_write_without_lock_id_is_rejected_while_locked(store: StateStore) -> None:
    store.acquire_lock("acme", "prod", LockInfo(id="lock-1", who="alice"))
    outcome = store.write_state("acme", "prod", make_state(), author="bob")
    assert outcome.status == "locked"


def test_write_with_matching_lock_id_succeeds(store: StateStore) -> None:
    store.acquire_lock("acme", "prod", LockInfo(id="lock-1", who="alice"))
    outcome = store.write_state("acme", "prod", make_state(), author="alice", lock_id="lock-1")
    assert outcome.status == "created"


def test_write_with_wrong_lock_id_is_rejected(store: StateStore) -> None:
    store.acquire_lock("acme", "prod", LockInfo(id="lock-1", who="alice"))
    outcome = store.write_state("acme", "prod", make_state(), author="bob", lock_id="lock-2")
    assert outcome.status == "locked"


def test_parse_lock_body_variants() -> None:
    assert parse_lock_body(b"") is None
    assert parse_lock_body(b"not json") is None
    assert parse_lock_body(b'{"Who": "x"}') is None
    lock = parse_lock_body(b'{"ID": "abc", "Who": "dev", "Operation": "OperationTypeApply"}')
    assert lock is not None and lock.id == "abc" and lock.who == "dev"


# -- listings ---------------------------------------------------------------


def test_list_states_reports_counts_and_lock(store: StateStore) -> None:
    store.write_state("acme", "prod", make_state(serial=1), author="dev")
    store.write_state("acme", "prod", make_state(serial=2), author="dev")
    store.write_state("acme", "stage", make_state(serial=1), author="dev")
    store.acquire_lock("acme", "prod", LockInfo(id="lock-1", who="alice"))

    states = {item.name: item for item in store.list_states("acme")}
    assert states["prod"].version_count == 2
    assert states["prod"].serial == 2
    assert states["prod"].locked is True
    assert states["stage"].locked is False


def test_list_states_scopes_by_tenant(store: StateStore) -> None:
    store.write_state("acme", "prod", make_state(), author="dev")
    store.write_state("other", "prod", make_state(), author="dev")
    assert [item.tenant_id for item in store.list_states("acme")] == ["acme"]
    assert len(store.list_states()) == 2
