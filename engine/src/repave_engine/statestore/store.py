"""State store operations: versions, locks, and the write guards (ADR 004 Phase 1).

Expected failures are returned as data (`WriteOutcome`, `LockOutcome`) so callers can
map them onto HTTP status codes without exception plumbing. Exceptions are reserved
for broken invariants such as blob corruption.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Literal

from repave_engine.sql_store import SqlConnection
from repave_engine.statestore.crypto import StateCrypto, open_blob, seal_blob
from repave_engine.statestore.graph import (
    DriftEntry,
    InventoryEntry,
    ResourceRow,
    blast_radius,
    cache_provider_schema,
    clear_graph,
    compare_drift,
    dependencies_of,
    inventory,
    list_edges,
    list_resources,
    load_cached_sensitive_attributes,
    replace_graph,
    stored_instance_attributes,
)
from repave_engine.statestore.migrate import apply_migrations
from repave_engine.statestore.normalize import (
    Edge,
    normalize_state,
    sensitive_attributes_from_provider_schema,
)
from repave_engine.statestore.state_document import (
    StateDocument,
    StateDocumentError,
    parse_state_document,
)
from repave_engine.statestore.transactions import (
    CommitOutcome,
    Transaction,
    TransactionStore,
)

logger = logging.getLogger(__name__)

WriteStatus = Literal["created", "unchanged", "conflict", "locked", "invalid"]
LockStatus = Literal["acquired", "held", "released", "mismatch", "absent"]

DEFAULT_TENANT: Final = "default"


class StateCorruptionError(RuntimeError):
    """A stored blob did not match the digest recorded when it was written."""


@dataclass(frozen=True)
class LockInfo:
    """Terraform's `statemgr.LockInfo`, as sent on LOCK and echoed on conflict."""

    id: str
    who: str = ""
    operation: str = ""
    info: str = ""
    version: str = ""
    created_at: str = ""

    def to_payload(self) -> dict[str, str]:
        return {
            "ID": self.id,
            "Who": self.who,
            "Operation": self.operation,
            "Info": self.info,
            "Version": self.version,
            "Created": self.created_at,
        }

    @staticmethod
    def from_payload(payload: Any) -> LockInfo | None:
        if not isinstance(payload, dict):
            return None
        lock_id = str(payload.get("ID", "")).strip()
        if not lock_id:
            return None
        return LockInfo(
            id=lock_id,
            who=str(payload.get("Who", "")),
            operation=str(payload.get("Operation", "")),
            info=str(payload.get("Info", "")),
            version=str(payload.get("Version", "")),
            created_at=str(payload.get("Created", "")),
        )


@dataclass(frozen=True)
class StateSummary:
    tenant_id: str
    name: str
    state_id: str
    serial: int
    lineage: str
    version_count: int
    updated_at: str
    locked: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "tenant": self.tenant_id,
            "state": self.name,
            "state_id": self.state_id,
            "serial": self.serial,
            "lineage": self.lineage,
            "version_count": self.version_count,
            "updated_at": self.updated_at,
            "locked": self.locked,
        }


@dataclass(frozen=True)
class StateVersionInfo:
    version_id: str
    serial: int
    lineage: str
    terraform_version: str
    size: int
    sha256: str
    author: str
    created_at: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "version_id": self.version_id,
            "serial": self.serial,
            "lineage": self.lineage,
            "terraform_version": self.terraform_version,
            "size": self.size,
            "sha256": self.sha256,
            "author": self.author,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class WriteOutcome:
    status: WriteStatus
    detail: str
    version_id: str | None = None
    serial: int = 0

    @property
    def accepted(self) -> bool:
        return self.status in ("created", "unchanged")


@dataclass(frozen=True)
class LockOutcome:
    status: LockStatus
    detail: str
    holder: LockInfo | None = None

    @property
    def ok(self) -> bool:
        return self.status in ("acquired", "released")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _locked_write(held: LockInfo) -> WriteOutcome:
    return WriteOutcome(
        status="locked",
        detail=f"state is locked by {held.who or held.id}; supply the matching lock ID",
    )


def _new_id() -> str:
    return uuid.uuid4().hex


def ensure_state_schema(conn: SqlConnection) -> None:
    apply_migrations(conn)


class StateStore:
    """Authoritative store for state bytes, keyed by (tenant, state name)."""

    def __init__(
        self,
        conn: SqlConnection,
        *,
        crypto: StateCrypto | None = None,
        required_gates: frozenset[str] = frozenset(),
    ) -> None:
        self._conn = conn
        self._crypto = crypto
        self._transactions = TransactionStore(conn, required_gates=required_gates)

    @property
    def connection(self) -> SqlConnection:
        return self._conn

    @property
    def transactions(self) -> TransactionStore:
        return self._transactions

    # -- tenants and states -------------------------------------------------

    def ensure_tenant(self, tenant_id: str) -> None:
        row = self._conn.execute(
            "SELECT tenant_id FROM state_tenants WHERE tenant_id = ?", (tenant_id,)
        ).fetchone()
        if row is not None:
            return
        self._conn.execute(
            "INSERT INTO state_tenants (tenant_id, display_name, created_at) VALUES (?, ?, ?)",
            (tenant_id, tenant_id, _now()),
        )
        self._conn.commit()

    def _state_row(self, tenant_id: str, name: str, *, for_update: bool = False) -> Any:
        sql = "SELECT * FROM states WHERE tenant_id = ? AND name = ?"
        if for_update and self._conn.dialect == "postgresql":
            sql += " FOR UPDATE"
        return self._conn.execute(sql, (tenant_id, name)).fetchone()

    def ensure_state(self, tenant_id: str, name: str) -> str:
        self.ensure_tenant(tenant_id)
        row = self._state_row(tenant_id, name)
        if row is not None:
            return str(row["state_id"])
        state_id = _new_id()
        stamp = _now()
        self._conn.execute(
            "INSERT INTO states (state_id, tenant_id, name, serial, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (state_id, tenant_id, name, 0, stamp, stamp),
        )
        self._conn.commit()
        return state_id

    def state_exists(self, tenant_id: str, name: str) -> bool:
        return self._state_row(tenant_id, name) is not None

    def list_states(self, tenant_id: str | None = None) -> list[StateSummary]:
        sql = (
            "SELECT s.*, "
            "(SELECT COUNT(*) FROM state_versions v WHERE v.state_id = s.state_id) AS versions, "
            "(SELECT COUNT(*) FROM state_locks l WHERE l.state_id = s.state_id) AS locks "
            "FROM states s"
        )
        params: tuple[Any, ...] = ()
        if tenant_id is not None:
            sql += " WHERE s.tenant_id = ?"
            params = (tenant_id,)
        sql += " ORDER BY s.tenant_id ASC, s.name ASC"
        rows = self._conn.execute(sql, params).fetchall()
        return [
            StateSummary(
                tenant_id=str(row["tenant_id"]),
                name=str(row["name"]),
                state_id=str(row["state_id"]),
                serial=int(row["serial"]),
                lineage=str(row["lineage"] or ""),
                version_count=int(row["versions"]),
                updated_at=str(row["updated_at"]),
                locked=int(row["locks"]) > 0,
            )
            for row in rows
        ]

    def summary(self, tenant_id: str, name: str) -> StateSummary | None:
        for item in self.list_states(tenant_id):
            if item.name == name:
                return item
        return None

    # -- reads --------------------------------------------------------------

    def read_current_bytes(self, tenant_id: str, name: str) -> bytes | None:
        """Plaintext bytes of the newest version, byte-identical to what was written."""
        row = self._conn.execute(
            "SELECT v.blob, v.encryption, v.blob_sha256 FROM states s "
            "JOIN state_versions v ON v.version_id = s.current_version_id "
            "WHERE s.tenant_id = ? AND s.name = ?",
            (tenant_id, name),
        ).fetchone()
        if row is None:
            return None
        return self._open_and_verify(row)

    def read_version_bytes(self, version_id: str) -> bytes | None:
        row = self._conn.execute(
            "SELECT blob, encryption, blob_sha256 FROM state_versions WHERE version_id = ?",
            (version_id,),
        ).fetchone()
        if row is None:
            return None
        return self._open_and_verify(row)

    def _open_and_verify(self, row: Any) -> bytes:
        stored = row["blob"]
        raw = bytes(stored) if not isinstance(stored, bytes) else stored
        plaintext = open_blob(raw, str(row["encryption"]), self._crypto)
        digest = hashlib.sha256(plaintext).hexdigest()
        expected = str(row["blob_sha256"])
        if digest != expected:
            raise StateCorruptionError(
                f"state blob digest mismatch: stored {expected}, computed {digest}. "
                "Restore from backup; do not write to this state"
            )
        return plaintext

    def list_versions(
        self, tenant_id: str, name: str, *, limit: int = 100
    ) -> list[StateVersionInfo]:
        rows = self._conn.execute(
            "SELECT v.* FROM state_versions v JOIN states s ON s.state_id = v.state_id "
            "WHERE s.tenant_id = ? AND s.name = ? "
            "ORDER BY v.serial DESC LIMIT ?",
            (tenant_id, name, max(1, limit)),
        ).fetchall()
        return [
            StateVersionInfo(
                version_id=str(row["version_id"]),
                serial=int(row["serial"]),
                lineage=str(row["lineage"]),
                terraform_version=str(row["terraform_version"]),
                size=int(row["blob_size"]),
                sha256=str(row["blob_sha256"]),
                author=str(row["author"]),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    # -- graph queries --------------------------------------------------------

    def _require_state_id(self, tenant_id: str, name: str) -> str | None:
        row = self._state_row(tenant_id, name)
        return None if row is None else str(row["state_id"])

    def resources(
        self,
        tenant_id: str,
        name: str,
        *,
        resource_type: str | None = None,
        mode: str | None = None,
    ) -> list[ResourceRow]:
        state_id = self._require_state_id(tenant_id, name)
        if state_id is None:
            return []
        return list_resources(self._conn, state_id, resource_type=resource_type, mode=mode)

    def inventory(self, tenant_id: str, name: str) -> list[InventoryEntry]:
        """Resource counts by type — what the estate is made of."""
        state_id = self._require_state_id(tenant_id, name)
        if state_id is None:
            return []
        return inventory(self._conn, state_id)

    def blast_radius(self, tenant_id: str, name: str, address: str) -> list[str]:
        """Everything a change to `address` can transitively reach."""
        state_id = self._require_state_id(tenant_id, name)
        if state_id is None:
            return []
        return blast_radius(self._conn, state_id, address)

    def dependencies(self, tenant_id: str, name: str, address: str) -> list[str]:
        state_id = self._require_state_id(tenant_id, name)
        if state_id is None:
            return []
        return dependencies_of(self._conn, state_id, address)

    def edges(self, tenant_id: str, name: str) -> list[Edge]:
        state_id = self._require_state_id(tenant_id, name)
        if state_id is None:
            return []
        return list_edges(self._conn, state_id)

    def drift(self, tenant_id: str, name: str, refreshed: bytes) -> list[DriftEntry]:
        """Compare stored attributes against a refreshed state produced elsewhere.

        Repave does not run `refresh` itself (ADR 004 decision 4): the client holds the
        cloud credentials, so it refreshes and posts the result here for comparison.
        """
        state_id = self._require_state_id(tenant_id, name)
        if state_id is None:
            return []
        document = parse_state_document(refreshed)
        observed = normalize_state(
            document, schema_sensitive=load_cached_sensitive_attributes(self._conn)
        )
        observed_attributes = {
            instance.address: instance.attributes
            for resource in observed.resources
            for instance in resource.instances
        }
        return compare_drift(stored_instance_attributes(self._conn, state_id), observed_attributes)

    def cache_provider_schema(self, payload: Any, *, provider: str, version: str = "") -> int:
        """Record provider sensitivity so later writes redact more than the denylist can.

        Returns the number of resource types learned.
        """
        sensitive = sensitive_attributes_from_provider_schema(payload)
        cache_provider_schema(
            self._conn, provider=provider, version=version, sensitive_by_type=sensitive
        )
        return len(sensitive)

    # -- transactions ---------------------------------------------------------

    def open_transaction(
        self, tenant_id: str, name: str, *, author: str, operation: str = "apply"
    ) -> Transaction:
        """Start a transaction pinned to the state's current serial.

        The pin is what makes conflict detection possible: at commit we ask whether
        anything in the write set moved since this point.
        """
        state_id = self.ensure_state(tenant_id, name)
        row = self._state_row(tenant_id, name)
        base_serial = int(row["serial"]) if row is not None else 0
        base_version_id = str(row["current_version_id"] or "") if row is not None else ""
        return self._transactions.open(
            state_id,
            author=author,
            operation=operation,
            base_version_id=base_version_id,
            base_serial=base_serial,
        )

    def list_transactions(
        self, tenant_id: str, name: str, *, status: str | None = None, limit: int = 50
    ) -> list[Transaction]:
        state_id = self._require_state_id(tenant_id, name)
        if state_id is None:
            return []
        return self._transactions.list_for_state(state_id, status=status, limit=limit)

    def commit_transaction(
        self, tx_id: str, raw: bytes, *, author: str, lock_id: str | None = None
    ) -> CommitOutcome:
        """Write state and finalize a transaction, or refuse and fail the transaction.

        Conflicts and gates are checked before the write, so a rejected transaction
        never leaves a half-applied version behind.
        """
        tx = self._transactions.get(tx_id)
        if tx is None:
            return CommitOutcome(status="absent", detail=f"no such transaction: {tx_id}")

        located = self._locate_state(tx.state_id)
        if located is None:  # pragma: no cover - cascade should prevent this
            return CommitOutcome(
                status="invalid", detail="the state this transaction targets was deleted"
            )
        tenant_id, name = located

        prepared = self._transactions.prepare_commit(tx_id)
        if not prepared.ok:
            self._transactions.fail(tx_id, detail=prepared.detail)
            return CommitOutcome(
                status=prepared.status,
                detail=prepared.detail,
                transaction=self._transactions.get(tx_id),
                conflicts=prepared.conflicts,
                conflicting_addresses=prepared.conflicting_addresses,
                blocking_gates=prepared.blocking_gates,
            )

        written = self.write_state(tenant_id, name, raw, author=author, lock_id=lock_id)
        if written.status in ("invalid", "conflict", "locked"):
            self._transactions.fail(tx_id, detail=written.detail)
            return CommitOutcome(
                status="invalid" if written.status == "invalid" else "conflict",
                detail=written.detail,
                transaction=self._transactions.get(tx_id),
            )

        return self._transactions.commit(
            tx_id, committed_serial=written.serial, version_id=written.version_id or ""
        )

    def _locate_state(self, state_id: str) -> tuple[str, str] | None:
        row = self._conn.execute(
            "SELECT tenant_id, name FROM states WHERE state_id = ?", (state_id,)
        ).fetchone()
        if row is None:
            return None
        return str(row["tenant_id"]), str(row["name"])

    # -- writes -------------------------------------------------------------

    def write_state(
        self,
        tenant_id: str,
        name: str,
        raw: bytes,
        *,
        author: str,
        lock_id: str | None = None,
    ) -> WriteOutcome:
        """Persist a new state version, enforcing lock, lineage, and serial guards."""
        try:
            document = parse_state_document(raw)
        except StateDocumentError as exc:
            return WriteOutcome(status="invalid", detail=str(exc))

        state_id = self.ensure_state(tenant_id, name)
        row = self._state_row(tenant_id, name, for_update=True)
        if row is None:  # pragma: no cover - ensure_state just created it
            return WriteOutcome(status="invalid", detail="state disappeared during write")

        held = self._lock_row(state_id)
        if held is not None and lock_id != held.id:
            return _locked_write(held)

        guard = self._guard_write(row, document)
        if guard is not None:
            return guard

        current_sha = self._current_sha256(row)
        if int(row["serial"]) == document.serial and current_sha == document.sha256:
            return WriteOutcome(
                status="unchanged",
                detail="state already at this serial with identical content",
                version_id=str(row["current_version_id"] or ""),
                serial=document.serial,
            )

        return self._insert_version(state_id, document, author=author)

    def _guard_write(self, row: Any, document: StateDocument) -> WriteOutcome | None:
        stored_lineage = str(row["lineage"] or "")
        if stored_lineage and stored_lineage != document.lineage:
            return WriteOutcome(
                status="conflict",
                detail=(
                    f"lineage mismatch: state holds {stored_lineage}, write carries "
                    f"{document.lineage}. Refusing to overwrite an unrelated state"
                ),
                serial=int(row["serial"]),
            )

        stored_serial = int(row["serial"])
        if document.serial < stored_serial:
            return WriteOutcome(
                status="conflict",
                detail=(
                    f"serial went backwards: state is at {stored_serial}, write carries "
                    f"{document.serial}. Re-run plan against current state"
                ),
                serial=stored_serial,
            )

        same_serial_different_content = (
            document.serial == stored_serial
            and stored_serial > 0
            and self._current_sha256(row) != document.sha256
        )
        if same_serial_different_content:
            return WriteOutcome(
                status="conflict",
                detail=(
                    f"serial {document.serial} already exists with different content; "
                    "another write landed first. Re-run plan against current state"
                ),
                serial=stored_serial,
            )
        return None

    def _current_sha256(self, row: Any) -> str:
        version_id = row["current_version_id"]
        if not version_id:
            return ""
        found = self._conn.execute(
            "SELECT blob_sha256 FROM state_versions WHERE version_id = ?",
            (str(version_id),),
        ).fetchone()
        return str(found["blob_sha256"]) if found is not None else ""

    def _insert_version(
        self, state_id: str, document: StateDocument, *, author: str
    ) -> WriteOutcome:
        blob, encryption, key_id = seal_blob(document.raw, self._crypto)
        version_id = _new_id()
        stamp = _now()
        normalized = normalize_state(
            document, schema_sensitive=load_cached_sensitive_attributes(self._conn)
        )
        try:
            self._conn.execute(
                "INSERT INTO state_versions (version_id, state_id, serial, lineage, "
                "terraform_version, blob, blob_sha256, blob_size, encryption, key_id, "
                "author, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    version_id,
                    state_id,
                    document.serial,
                    document.lineage,
                    document.terraform_version,
                    blob,
                    document.sha256,
                    document.size,
                    encryption,
                    key_id,
                    author,
                    stamp,
                ),
            )
            self._conn.execute(
                "UPDATE states SET serial = ?, lineage = ?, current_version_id = ?, "
                "updated_at = ? WHERE state_id = ?",
                (document.serial, document.lineage, version_id, stamp, state_id),
            )
            # The graph is a derived index of the current version, rebuilt in the same
            # transaction that moves the pointer. An index that can lag the blob it
            # describes is worse than no index.
            replace_graph(
                self._conn,
                state_id=state_id,
                version_id=version_id,
                normalized=normalized,
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return WriteOutcome(
            status="created",
            detail=f"stored serial {document.serial}",
            version_id=version_id,
            serial=document.serial,
        )

    def delete_state(self, tenant_id: str, name: str) -> bool:
        row = self._state_row(tenant_id, name)
        if row is None:
            return False
        state_id = str(row["state_id"])
        clear_graph(self._conn, state_id)
        self._conn.execute("DELETE FROM states WHERE state_id = ?", (state_id,))
        self._conn.commit()
        return True

    # -- locks --------------------------------------------------------------

    def _lock_row(self, state_id: str) -> LockInfo | None:
        row = self._conn.execute(
            "SELECT * FROM state_locks WHERE state_id = ?", (state_id,)
        ).fetchone()
        if row is None:
            return None
        return LockInfo(
            id=str(row["lock_id"]),
            who=str(row["who"]),
            operation=str(row["operation"]),
            info=str(row["info"]),
            version=str(row["version"]),
            created_at=str(row["created_at"]),
        )

    def current_lock(self, tenant_id: str, name: str) -> LockInfo | None:
        row = self._state_row(tenant_id, name)
        if row is None:
            return None
        return self._lock_row(str(row["state_id"]))

    def acquire_lock(self, tenant_id: str, name: str, lock: LockInfo) -> LockOutcome:
        state_id = self.ensure_state(tenant_id, name)
        held = self._lock_row(state_id)
        if held is not None:
            if held.id == lock.id:
                return LockOutcome(
                    status="acquired", detail="lock already held by this ID", holder=held
                )
            return LockOutcome(
                status="held",
                detail=f"state is locked by {held.who or 'another client'}",
                holder=held,
            )
        try:
            self._conn.execute(
                "INSERT INTO state_locks (state_id, lock_id, who, operation, info, version, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    state_id,
                    lock.id,
                    lock.who,
                    lock.operation,
                    lock.info,
                    lock.version,
                    lock.created_at or _now(),
                ),
            )
            self._conn.commit()
        except Exception:
            # Lost a race on the primary key: report the winner rather than failing.
            self._conn.rollback()
            winner = self._lock_row(state_id)
            if winner is not None and winner.id != lock.id:
                return LockOutcome(
                    status="held",
                    detail=f"state is locked by {winner.who or 'another client'}",
                    holder=winner,
                )
            raise
        return LockOutcome(status="acquired", detail="lock acquired", holder=lock)

    def release_lock(self, tenant_id: str, name: str, lock_id: str | None) -> LockOutcome:
        row = self._state_row(tenant_id, name)
        if row is None:
            return LockOutcome(status="absent", detail="state does not exist")
        state_id = str(row["state_id"])
        held = self._lock_row(state_id)
        if held is None:
            return LockOutcome(status="absent", detail="state is not locked")
        # Terraform sends an empty body for force-unlock; treat that as authorized.
        if lock_id and held.id != lock_id:
            return LockOutcome(
                status="mismatch",
                detail=f"lock is held by {held.id}, not {lock_id}",
                holder=held,
            )
        self._conn.execute("DELETE FROM state_locks WHERE state_id = ?", (state_id,))
        self._conn.commit()
        return LockOutcome(status="released", detail="lock released", holder=held)


def parse_lock_body(body: bytes) -> LockInfo | None:
    if not body.strip():
        return None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return LockInfo.from_payload(payload)
