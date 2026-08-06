"""Transactions and commit-time conflict detection (ADR 004 Phase 3).

Concurrency here is optimistic. A transaction records the resources it touched and the
serial it read them at; overlap is detected at commit, not prevented during planning.
The alternative — holding a lock across a plan that can run for minutes — is strictly
worse than the whole-state lock Terraform already takes, because it holds longer.

The state machine is deliberately small:

    open -> previewing -> committing -> committed
                                     -> failed
    (open | previewing | committing) -> aborted

Illegal transitions return a `TransactionOutcome` rather than raising, because a client
retrying against a transaction someone else already aborted is expected, not a bug.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final, Literal

from repave_engine.sql_store import SqlConnection
from repave_engine.statestore.normalize import Edge

TransactionStatus = Literal["open", "previewing", "committing", "committed", "failed", "aborted"]
CommitStatus = Literal["committed", "conflict", "blocked", "invalid", "absent"]

INTENT_READ: Final = "read"
INTENT_WRITE: Final = "write"

#: Terminal states. Nothing leaves these.
FINAL_STATUSES: Final[frozenset[str]] = frozenset({"committed", "failed", "aborted"})

_ALLOWED: Final[dict[str, frozenset[str]]] = {
    "open": frozenset({"previewing", "committing", "aborted", "failed"}),
    "previewing": frozenset({"committing", "aborted", "failed"}),
    "committing": frozenset({"committed", "failed", "aborted"}),
    "committed": frozenset(),
    "failed": frozenset(),
    "aborted": frozenset(),
}


class TransactionError(RuntimeError):
    """A broken invariant, not an expected outcome."""


@dataclass(frozen=True)
class GateOutcome:
    """A gate result reported by the client alongside a commit."""

    name: str
    passed: bool
    skipped: bool = False
    message: str = ""

    @property
    def blocking(self) -> bool:
        return not self.passed and not self.skipped

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "skipped": self.skipped,
            "message": self.message,
        }

    @staticmethod
    def from_payload(payload: Any) -> GateOutcome | None:
        if not isinstance(payload, dict):
            return None
        name = str(payload.get("name", "")).strip()
        if not name:
            return None
        return GateOutcome(
            name=name,
            passed=bool(payload.get("passed", False)),
            skipped=bool(payload.get("skipped", False)),
            message=str(payload.get("message", "")),
        )


@dataclass(frozen=True)
class TransactionResource:
    address: str
    intent: str
    action: str = ""

    def to_payload(self) -> dict[str, str]:
        return {"address": self.address, "intent": self.intent, "action": self.action}


@dataclass(frozen=True)
class Transaction:
    tx_id: str
    state_id: str
    status: TransactionStatus
    author: str
    operation: str
    base_version_id: str
    base_serial: int
    detail: str
    created_at: str
    updated_at: str
    committed_serial: int | None = None
    committed_version_id: str = ""
    resources: tuple[TransactionResource, ...] = ()
    gates: tuple[GateOutcome, ...] = ()
    config_edges: tuple[Edge, ...] = ()
    """Plan-JSON configuration edges recorded at preview; applied on commit."""

    @property
    def is_final(self) -> bool:
        return self.status in FINAL_STATUSES

    @property
    def write_set(self) -> tuple[str, ...]:
        return tuple(r.address for r in self.resources if r.intent == INTENT_WRITE)

    def to_payload(self) -> dict[str, Any]:
        return {
            "tx_id": self.tx_id,
            "status": self.status,
            "author": self.author,
            "operation": self.operation,
            "base_serial": self.base_serial,
            "base_version_id": self.base_version_id,
            "committed_serial": self.committed_serial,
            "committed_version_id": self.committed_version_id,
            "detail": self.detail,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "resources": [r.to_payload() for r in self.resources],
            "gates": [g.to_payload() for g in self.gates],
            "config_edges": [
                {
                    "from_address": edge.from_address,
                    "to_address": edge.to_address,
                    "kind": edge.kind,
                }
                for edge in self.config_edges
            ],
        }


@dataclass(frozen=True)
class TransactionOutcome:
    """Result of a state-machine move. Expected failures are data, not exceptions."""

    ok: bool
    detail: str
    transaction: Transaction | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"ok": self.ok, "detail": self.detail}
        if self.transaction is not None:
            payload["transaction"] = self.transaction.to_payload()
        return payload


@dataclass(frozen=True)
class CommitOutcome:
    status: CommitStatus
    detail: str
    transaction: Transaction | None = None
    conflicts: tuple[str, ...] = ()
    conflicting_addresses: tuple[str, ...] = ()
    blocking_gates: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status == "committed"

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "detail": self.detail,
            "conflicts": list(self.conflicts),
            "conflicting_addresses": list(self.conflicting_addresses),
            "blocking_gates": list(self.blocking_gates),
        }
        if self.transaction is not None:
            payload["transaction"] = self.transaction.to_payload()
        return payload


@dataclass
class TransactionStore:
    """Transaction persistence for one state store connection."""

    conn: SqlConnection
    required_gates: frozenset[str] = field(default_factory=frozenset)

    # -- reads ----------------------------------------------------------------

    def get(self, tx_id: str) -> Transaction | None:
        row = self.conn.execute(
            "SELECT * FROM state_transactions WHERE tx_id = ?", (tx_id,)
        ).fetchone()
        if row is None:
            return None
        return self._hydrate(row)

    def list_for_state(
        self, state_id: str, *, status: str | None = None, limit: int = 50
    ) -> list[Transaction]:
        sql = "SELECT * FROM state_transactions WHERE state_id = ?"
        params: list[Any] = [state_id]
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, limit))
        rows = self.conn.execute(sql, tuple(params)).fetchall()
        return [self._hydrate(row) for row in rows]

    def _hydrate(self, row: Any) -> Transaction:
        tx_id = str(row["tx_id"])
        committed = row["committed_serial"]
        return Transaction(
            tx_id=tx_id,
            state_id=str(row["state_id"]),
            status=str(row["status"]),  # type: ignore[arg-type]
            author=str(row["author"]),
            operation=str(row["operation"]),
            base_version_id=str(row["base_version_id"] or ""),
            base_serial=int(row["base_serial"]),
            committed_serial=None if committed is None else int(committed),
            committed_version_id=str(row["committed_version_id"] or ""),
            detail=str(row["detail"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            resources=self._resources(tx_id),
            gates=self._gates(tx_id),
            config_edges=self._config_edges(tx_id),
        )

    def _resources(self, tx_id: str) -> tuple[TransactionResource, ...]:
        rows = self.conn.execute(
            "SELECT address, intent, action FROM state_transaction_resources "
            "WHERE tx_id = ? ORDER BY intent ASC, address ASC",
            (tx_id,),
        ).fetchall()
        return tuple(
            TransactionResource(
                address=str(row["address"]),
                intent=str(row["intent"]),
                action=str(row["action"]),
            )
            for row in rows
        )

    def _gates(self, tx_id: str) -> tuple[GateOutcome, ...]:
        rows = self.conn.execute(
            "SELECT name, passed, skipped, message FROM state_transaction_gates "
            "WHERE tx_id = ? ORDER BY name ASC",
            (tx_id,),
        ).fetchall()
        return tuple(
            GateOutcome(
                name=str(row["name"]),
                passed=bool(row["passed"]),
                skipped=bool(row["skipped"]),
                message=str(row["message"]),
            )
            for row in rows
        )

    def _config_edges(self, tx_id: str) -> tuple[Edge, ...]:
        rows = self.conn.execute(
            "SELECT from_address, to_address, kind FROM state_transaction_edges "
            "WHERE tx_id = ? ORDER BY from_address ASC, to_address ASC, kind ASC",
            (tx_id,),
        ).fetchall()
        return tuple(
            Edge(
                from_address=str(row["from_address"]),
                to_address=str(row["to_address"]),
                kind=str(row["kind"]),
            )
            for row in rows
        )

    # -- lifecycle ------------------------------------------------------------

    def open(
        self,
        state_id: str,
        *,
        author: str,
        operation: str = "apply",
        base_version_id: str = "",
        base_serial: int = 0,
    ) -> Transaction:
        tx_id = uuid.uuid4().hex
        stamp = _now()
        self.conn.execute(
            "INSERT INTO state_transactions (tx_id, state_id, status, author, operation, "
            "base_version_id, base_serial, detail, created_at, updated_at) "
            "VALUES (?, ?, 'open', ?, ?, ?, ?, '', ?, ?)",
            (
                tx_id,
                state_id,
                author,
                operation,
                base_version_id or None,
                base_serial,
                stamp,
                stamp,
            ),
        )
        self.conn.commit()
        found = self.get(tx_id)
        if found is None:  # pragma: no cover - insert then miss is a broken invariant
            raise TransactionError(f"transaction {tx_id} vanished immediately after insert")
        return found

    def record_resources(
        self, tx_id: str, resources: Iterable[TransactionResource]
    ) -> TransactionOutcome:
        """Declare the read and write set. Replaces anything previously recorded."""
        tx = self.get(tx_id)
        if tx is None:
            return TransactionOutcome(ok=False, detail=f"no such transaction: {tx_id}")
        if tx.is_final:
            return TransactionOutcome(
                ok=False,
                detail=f"transaction {tx_id} is {tx.status}; open a new one",
                transaction=tx,
            )

        self.conn.execute("DELETE FROM state_transaction_resources WHERE tx_id = ?", (tx_id,))
        for resource in resources:
            self.conn.execute(
                "INSERT INTO state_transaction_resources (tx_id, address, intent, action) "
                "VALUES (?, ?, ?, ?)",
                (tx_id, resource.address, resource.intent, resource.action),
            )
        self._touch(tx_id)
        self.conn.commit()
        return TransactionOutcome(ok=True, detail="resources recorded", transaction=self.get(tx_id))

    def record_config_edges(self, tx_id: str, edges: Iterable[Edge]) -> TransactionOutcome:
        """Persist plan-JSON configuration edges for the commit-time graph rebuild.

        Replaces anything previously recorded so re-preview stays authoritative.
        """
        tx = self.get(tx_id)
        if tx is None:
            return TransactionOutcome(ok=False, detail=f"no such transaction: {tx_id}")
        if tx.is_final:
            return TransactionOutcome(
                ok=False,
                detail=f"transaction {tx_id} is {tx.status}; open a new one",
                transaction=tx,
            )

        self.conn.execute("DELETE FROM state_transaction_edges WHERE tx_id = ?", (tx_id,))
        seen: set[tuple[str, str, str]] = set()
        for edge in edges:
            key = (edge.from_address, edge.to_address, edge.kind)
            if not edge.from_address or not edge.to_address or key in seen:
                continue
            seen.add(key)
            self.conn.execute(
                "INSERT INTO state_transaction_edges (tx_id, from_address, to_address, kind) "
                "VALUES (?, ?, ?, ?)",
                (tx_id, edge.from_address, edge.to_address, edge.kind),
            )
        self._touch(tx_id)
        self.conn.commit()
        return TransactionOutcome(
            ok=True, detail="config edges recorded", transaction=self.get(tx_id)
        )

    def record_gates(self, tx_id: str, gates: Iterable[GateOutcome]) -> TransactionOutcome:
        tx = self.get(tx_id)
        if tx is None:
            return TransactionOutcome(ok=False, detail=f"no such transaction: {tx_id}")
        if tx.is_final:
            return TransactionOutcome(
                ok=False,
                detail=f"transaction {tx_id} is {tx.status}; open a new one",
                transaction=tx,
            )

        self.conn.execute("DELETE FROM state_transaction_gates WHERE tx_id = ?", (tx_id,))
        for gate in gates:
            self.conn.execute(
                "INSERT INTO state_transaction_gates (tx_id, name, passed, skipped, message) "
                "VALUES (?, ?, ?, ?, ?)",
                (tx_id, gate.name, int(gate.passed), int(gate.skipped), gate.message),
            )
        self._touch(tx_id)
        self.conn.commit()
        return TransactionOutcome(ok=True, detail="gates recorded", transaction=self.get(tx_id))

    def transition(
        self, tx_id: str, target: TransactionStatus, *, detail: str = ""
    ) -> TransactionOutcome:
        tx = self.get(tx_id)
        if tx is None:
            return TransactionOutcome(ok=False, detail=f"no such transaction: {tx_id}")
        if target not in _ALLOWED[tx.status]:
            return TransactionOutcome(
                ok=False,
                detail=f"cannot move transaction {tx_id} from {tx.status} to {target}",
                transaction=tx,
            )
        self._set_status(tx_id, target, detail=detail)
        self.conn.commit()
        return TransactionOutcome(
            ok=True, detail=f"transaction is {target}", transaction=self.get(tx_id)
        )

    def abort(self, tx_id: str, *, detail: str = "aborted by client") -> TransactionOutcome:
        return self.transition(tx_id, "aborted", detail=detail)

    def fail(self, tx_id: str, *, detail: str) -> TransactionOutcome:
        return self.transition(tx_id, "failed", detail=detail)

    # -- conflict detection ---------------------------------------------------

    def conflicts_for(self, tx: Transaction) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Transactions that wrote our write set after we read it.

        Returns (conflicting tx IDs, overlapping addresses). Only write-write overlap
        counts: two transactions that merely read the same resource are not in conflict.
        """
        writes = tx.write_set
        if not writes:
            return (), ()

        placeholders = ", ".join("?" for _ in writes)
        rows = self.conn.execute(
            "SELECT DISTINCT t.tx_id, r.address FROM state_transactions t "
            "JOIN state_transaction_resources r ON r.tx_id = t.tx_id "
            "WHERE t.state_id = ? AND t.status = 'committed' AND t.tx_id != ? "
            "AND t.committed_serial > ? AND r.intent = ? "
            f"AND r.address IN ({placeholders})",  # nosec B608 - placeholders are '?' only
            (tx.state_id, tx.tx_id, tx.base_serial, INTENT_WRITE, *writes),
        ).fetchall()

        ids = sorted({str(row["tx_id"]) for row in rows})
        addresses = sorted({str(row["address"]) for row in rows})
        return tuple(ids), tuple(addresses)

    def blocking_gates(self, tx: Transaction) -> tuple[str, ...]:
        """Required gates that failed or were never reported.

        A missing required gate blocks just as a failing one does. The client runs the
        gates because it holds the working directory, so "absent" cannot be read as
        "passed" without making the requirement advisory.
        """
        reported = {gate.name: gate for gate in tx.gates}
        blocking = [gate.name for gate in tx.gates if gate.blocking]
        blocking.extend(name for name in self.required_gates if name not in reported)
        blocking.extend(
            name for name in self.required_gates if name in reported and reported[name].skipped
        )
        return tuple(sorted(set(blocking)))

    # -- commit ---------------------------------------------------------------

    def prepare_commit(self, tx_id: str) -> CommitOutcome:
        """Check a transaction against conflicts and gates without finalizing it.

        Advisory: nothing stops a conflicting transaction from appearing between this
        call and the commit. `commit` re-checks under the same guard.
        """
        tx = self.get(tx_id)
        if tx is None:
            return CommitOutcome(status="absent", detail=f"no such transaction: {tx_id}")
        return self._evaluate(tx)

    def commit(self, tx_id: str, *, committed_serial: int, version_id: str) -> CommitOutcome:
        """Finalize a transaction after its state version landed.

        Called by the store once the new state is durable, so `committed_serial` is the
        serial actually written rather than one the client asserted.
        """
        tx = self.get(tx_id)
        if tx is None:
            return CommitOutcome(status="absent", detail=f"no such transaction: {tx_id}")
        if tx.status not in ("open", "previewing", "committing"):
            return CommitOutcome(
                status="invalid",
                detail=f"transaction {tx_id} is {tx.status}; open a new one",
                transaction=tx,
            )

        evaluated = self._evaluate(tx)
        if not evaluated.ok:
            self._set_status(tx_id, "failed", detail=evaluated.detail)
            self.conn.commit()
            return CommitOutcome(
                status=evaluated.status,
                detail=evaluated.detail,
                transaction=self.get(tx_id),
                conflicts=evaluated.conflicts,
                conflicting_addresses=evaluated.conflicting_addresses,
                blocking_gates=evaluated.blocking_gates,
            )

        self.conn.execute(
            "UPDATE state_transactions SET status = 'committed', committed_serial = ?, "
            "committed_version_id = ?, detail = ?, updated_at = ? WHERE tx_id = ?",
            (committed_serial, version_id, "committed", _now(), tx_id),
        )
        self.conn.commit()
        return CommitOutcome(
            status="committed",
            detail=f"committed at serial {committed_serial}",
            transaction=self.get(tx_id),
        )

    def _evaluate(self, tx: Transaction) -> CommitOutcome:
        conflicts, addresses = self.conflicts_for(tx)
        if conflicts:
            return CommitOutcome(
                status="conflict",
                detail=(
                    f"{', '.join(addresses)} changed since serial {tx.base_serial}; "
                    f"conflicting transaction(s): {', '.join(conflicts)}. "
                    "Re-plan against current state and retry"
                ),
                transaction=tx,
                conflicts=conflicts,
                conflicting_addresses=addresses,
            )

        blocking = self.blocking_gates(tx)
        if blocking:
            return CommitOutcome(
                status="blocked",
                detail=(
                    f"required gate(s) not passing: {', '.join(blocking)}. "
                    "Fix the findings and re-run before committing"
                ),
                transaction=tx,
                blocking_gates=blocking,
            )
        return CommitOutcome(status="committed", detail="ready to commit", transaction=tx)

    # -- helpers --------------------------------------------------------------

    def _set_status(self, tx_id: str, status: str, *, detail: str) -> None:
        self.conn.execute(
            "UPDATE state_transactions SET status = ?, detail = ?, updated_at = ? WHERE tx_id = ?",
            (status, detail, _now(), tx_id),
        )

    def _touch(self, tx_id: str) -> None:
        self.conn.execute(
            "UPDATE state_transactions SET updated_at = ? WHERE tx_id = ?", (_now(), tx_id)
        )


def resources_from_plan_json(payload: Any) -> list[TransactionResource]:
    """Read and write set from `tofu show -json <plan>`.

    Resources with a `no-op` action are recorded as reads: they were consulted and are
    expected to be unchanged, but another transaction changing them is not a conflict.
    Everything else — create, update, delete, replace — is a write.
    """
    if not isinstance(payload, dict):
        return []
    changes = payload.get("resource_changes")
    if not isinstance(changes, list):
        return []

    found: dict[tuple[str, str], TransactionResource] = {}
    for item in changes:
        if not isinstance(item, dict):
            continue
        address = str(item.get("address", "")).strip()
        if not address:
            continue
        change = item.get("change")
        actions = change.get("actions") if isinstance(change, dict) else None
        action = "-".join(str(a) for a in actions) if isinstance(actions, list) else ""
        intent = INTENT_READ if action in ("", "no-op", "read") else INTENT_WRITE
        found[(address, intent)] = TransactionResource(
            address=address, intent=intent, action=action
        )
    return [found[key] for key in sorted(found)]


def parse_gate_outcomes(payload: Any) -> list[GateOutcome]:
    items = payload if isinstance(payload, list) else []
    parsed = (GateOutcome.from_payload(item) for item in items)
    return [gate for gate in parsed if gate is not None]


def write_addresses(resources: Sequence[TransactionResource]) -> tuple[str, ...]:
    return tuple(sorted({r.address for r in resources if r.intent == INTENT_WRITE}))


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
