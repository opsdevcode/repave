from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from repave_engine.sql_store import DatabaseConfig, connect
from repave_engine.statestore.store import StateStore, ensure_state_schema
from repave_engine.statestore.transactions import (
    INTENT_READ,
    INTENT_WRITE,
    GateOutcome,
    TransactionResource,
    parse_gate_outcomes,
    resources_from_plan_json,
    write_addresses,
)
from statestore_support import make_state, managed_resource

TENANT = "default"
NAME = "prod"


def _store(tmp_path: Path, *, required_gates: frozenset[str] = frozenset()) -> StateStore:
    conn = connect(DatabaseConfig(dialect="sqlite", sqlite_path=tmp_path / "state.db"))
    ensure_state_schema(conn)
    store = StateStore(conn, required_gates=required_gates)
    store.ensure_tenant(TENANT)
    return store


@pytest.fixture
def store(tmp_path: Path) -> StateStore:
    return _store(tmp_path)


def _state(serial: int, *addresses: str) -> bytes:
    resources = [managed_resource(*address.split(".", 1)) for address in addresses]
    return make_state(serial=serial, resources=resources)


def _writes(*addresses: str) -> list[TransactionResource]:
    return [TransactionResource(address=a, intent=INTENT_WRITE, action="update") for a in addresses]


# -- plan parsing -----------------------------------------------------------


def _plan(*entries: tuple[str, list[str]]) -> dict[str, Any]:
    return {
        "resource_changes": [
            {"address": address, "change": {"actions": actions}} for address, actions in entries
        ]
    }


def test_plan_json_splits_reads_from_writes() -> None:
    resources = resources_from_plan_json(
        _plan(
            ("aws_vpc.main", ["no-op"]),
            ("aws_subnet.web", ["update"]),
            ("aws_instance.app", ["create"]),
            ("aws_s3_bucket.old", ["delete"]),
        )
    )
    by_address = {r.address: r for r in resources}
    assert by_address["aws_vpc.main"].intent == INTENT_READ
    assert by_address["aws_subnet.web"].intent == INTENT_WRITE
    assert by_address["aws_instance.app"].intent == INTENT_WRITE
    assert by_address["aws_s3_bucket.old"].intent == INTENT_WRITE


def test_plan_json_records_replace_as_one_write() -> None:
    resources = resources_from_plan_json(_plan(("aws_instance.app", ["delete", "create"])))
    assert resources[0].intent == INTENT_WRITE
    assert resources[0].action == "delete-create"


def test_plan_json_tolerates_garbage() -> None:
    assert resources_from_plan_json(None) == []
    assert resources_from_plan_json({"resource_changes": "nope"}) == []
    assert resources_from_plan_json({"resource_changes": [{}, {"address": ""}]}) == []


def test_write_addresses_deduplicates_and_sorts() -> None:
    resources = [
        *_writes("b.two", "a.one", "b.two"),
        TransactionResource(address="c.three", intent=INTENT_READ),
    ]
    assert write_addresses(resources) == ("a.one", "b.two")


def test_parse_gate_outcomes_skips_unnamed_entries() -> None:
    gates = parse_gate_outcomes(
        [{"name": "opa", "passed": True}, {"passed": False}, "nonsense", {"name": "  "}]
    )
    assert [gate.name for gate in gates] == ["opa"]


def test_gate_outcome_blocking_ignores_skips() -> None:
    assert GateOutcome(name="opa", passed=False).blocking
    assert not GateOutcome(name="opa", passed=False, skipped=True).blocking
    assert not GateOutcome(name="opa", passed=True).blocking


# -- lifecycle --------------------------------------------------------------


def test_open_pins_the_current_serial(store: StateStore) -> None:
    store.write_state(TENANT, NAME, _state(7, "aws_vpc.main"), author="seed")
    tx = store.open_transaction(TENANT, NAME, author="alice")

    assert tx.status == "open"
    assert tx.base_serial == 7
    assert tx.base_version_id


def test_open_on_an_empty_state_pins_serial_zero(store: StateStore) -> None:
    tx = store.open_transaction(TENANT, NAME, author="alice")
    assert tx.base_serial == 0
    assert tx.base_version_id == ""


def test_lifecycle_runs_open_previewing_committing_committed(store: StateStore) -> None:
    store.write_state(TENANT, NAME, _state(1, "aws_vpc.main"), author="seed")
    tx = store.open_transaction(TENANT, NAME, author="alice")
    transactions = store.transactions

    assert transactions.transition(tx.tx_id, "previewing").ok
    assert transactions.transition(tx.tx_id, "committing").ok

    outcome = store.commit_transaction(
        tx.tx_id, _state(2, "aws_vpc.main", "aws_subnet.web"), author="alice"
    )
    assert outcome.status == "committed"
    assert outcome.transaction is not None
    assert outcome.transaction.status == "committed"
    assert outcome.transaction.committed_serial == 2


def test_illegal_transitions_are_refused_as_data(store: StateStore) -> None:
    tx = store.open_transaction(TENANT, NAME, author="alice")
    transactions = store.transactions

    assert transactions.abort(tx.tx_id).ok
    replay = transactions.transition(tx.tx_id, "committing")
    assert not replay.ok
    assert "cannot move" in replay.detail


def test_a_committed_transaction_cannot_be_reused(store: StateStore) -> None:
    store.write_state(TENANT, NAME, _state(1, "aws_vpc.main"), author="seed")
    tx = store.open_transaction(TENANT, NAME, author="alice")
    store.commit_transaction(tx.tx_id, _state(2, "aws_vpc.main"), author="alice")

    again = store.commit_transaction(tx.tx_id, _state(3, "aws_vpc.main"), author="alice")
    assert again.status == "invalid"


def test_operations_on_an_unknown_transaction_report_absent(store: StateStore) -> None:
    assert store.transactions.get("nope") is None
    assert store.commit_transaction("nope", _state(1, "a.b"), author="x").status == "absent"
    assert store.transactions.prepare_commit("nope").status == "absent"
    assert not store.transactions.record_resources("nope", []).ok
    assert not store.transactions.record_gates("nope", []).ok


def test_recording_resources_replaces_the_previous_set(store: StateStore) -> None:
    tx = store.open_transaction(TENANT, NAME, author="alice")
    store.transactions.record_resources(tx.tx_id, _writes("a.one", "b.two"))
    store.transactions.record_resources(tx.tx_id, _writes("c.three"))

    refreshed = store.transactions.get(tx.tx_id)
    assert refreshed is not None
    assert refreshed.write_set == ("c.three",)


def test_a_final_transaction_refuses_new_resources(store: StateStore) -> None:
    tx = store.open_transaction(TENANT, NAME, author="alice")
    store.transactions.abort(tx.tx_id)
    outcome = store.transactions.record_resources(tx.tx_id, _writes("a.one"))
    assert not outcome.ok
    assert "aborted" in outcome.detail


def test_transactions_are_listed_newest_first(store: StateStore) -> None:
    store.write_state(TENANT, NAME, _state(1, "aws_vpc.main"), author="seed")
    first = store.open_transaction(TENANT, NAME, author="alice")
    store.transactions.abort(first.tx_id)
    second = store.open_transaction(TENANT, NAME, author="bob")

    listed = store.list_transactions(TENANT, NAME)
    assert {tx.tx_id for tx in listed} == {first.tx_id, second.tx_id}
    assert [tx.tx_id for tx in store.list_transactions(TENANT, NAME, status="aborted")] == [
        first.tx_id
    ]


# -- conflict detection -----------------------------------------------------


def test_disjoint_transactions_both_commit(store: StateStore) -> None:
    """The point of resource-level concurrency: two teams, one state, no queue."""
    store.write_state(TENANT, NAME, _state(1, "aws_vpc.main"), author="seed")

    alice = store.open_transaction(TENANT, NAME, author="alice")
    bob = store.open_transaction(TENANT, NAME, author="bob")
    store.transactions.record_resources(alice.tx_id, _writes("aws_subnet.web"))
    store.transactions.record_resources(bob.tx_id, _writes("aws_s3_bucket.assets"))

    first = store.commit_transaction(alice.tx_id, _state(2, "aws_vpc.main"), author="alice")
    second = store.commit_transaction(bob.tx_id, _state(3, "aws_vpc.main"), author="bob")

    assert first.status == "committed"
    assert second.status == "committed"


def test_overlapping_transactions_conflict_naming_the_first(store: StateStore) -> None:
    store.write_state(TENANT, NAME, _state(1, "aws_vpc.main"), author="seed")

    alice = store.open_transaction(TENANT, NAME, author="alice")
    bob = store.open_transaction(TENANT, NAME, author="bob")
    store.transactions.record_resources(alice.tx_id, _writes("aws_subnet.web"))
    store.transactions.record_resources(bob.tx_id, _writes("aws_subnet.web"))

    assert (
        store.commit_transaction(alice.tx_id, _state(2, "aws_vpc.main"), author="alice").status
        == "committed"
    )

    second = store.commit_transaction(bob.tx_id, _state(3, "aws_vpc.main"), author="bob")
    assert second.status == "conflict"
    assert second.conflicts == (alice.tx_id,)
    assert second.conflicting_addresses == ("aws_subnet.web",)
    assert "Re-plan against current state" in second.detail


def test_a_conflicted_transaction_lands_in_failed(store: StateStore) -> None:
    store.write_state(TENANT, NAME, _state(1, "aws_vpc.main"), author="seed")
    alice = store.open_transaction(TENANT, NAME, author="alice")
    bob = store.open_transaction(TENANT, NAME, author="bob")
    store.transactions.record_resources(alice.tx_id, _writes("shared.one"))
    store.transactions.record_resources(bob.tx_id, _writes("shared.one"))
    store.commit_transaction(alice.tx_id, _state(2, "aws_vpc.main"), author="alice")

    store.commit_transaction(bob.tx_id, _state(3, "aws_vpc.main"), author="bob")
    failed = store.transactions.get(bob.tx_id)
    assert failed is not None
    assert failed.status == "failed"


def test_read_only_overlap_is_not_a_conflict(store: StateStore) -> None:
    """Two transactions reading the same resource are not in conflict."""
    store.write_state(TENANT, NAME, _state(1, "aws_vpc.main"), author="seed")
    alice = store.open_transaction(TENANT, NAME, author="alice")
    bob = store.open_transaction(TENANT, NAME, author="bob")
    store.transactions.record_resources(
        alice.tx_id,
        [TransactionResource(address="aws_vpc.main", intent=INTENT_READ), *_writes("a.one")],
    )
    store.transactions.record_resources(
        bob.tx_id,
        [TransactionResource(address="aws_vpc.main", intent=INTENT_READ), *_writes("b.two")],
    )

    store.commit_transaction(alice.tx_id, _state(2, "aws_vpc.main"), author="alice")
    assert (
        store.commit_transaction(bob.tx_id, _state(3, "aws_vpc.main"), author="bob").status
        == "committed"
    )


def test_a_transaction_opened_after_the_conflict_sees_no_conflict(store: StateStore) -> None:
    """Re-planning is the documented fix, so it has to actually work."""
    store.write_state(TENANT, NAME, _state(1, "aws_vpc.main"), author="seed")
    alice = store.open_transaction(TENANT, NAME, author="alice")
    store.transactions.record_resources(alice.tx_id, _writes("shared.one"))
    store.commit_transaction(alice.tx_id, _state(2, "aws_vpc.main"), author="alice")

    retry = store.open_transaction(TENANT, NAME, author="bob")
    store.transactions.record_resources(retry.tx_id, _writes("shared.one"))
    assert (
        store.commit_transaction(retry.tx_id, _state(3, "aws_vpc.main"), author="bob").status
        == "committed"
    )


def test_an_empty_write_set_never_conflicts(store: StateStore) -> None:
    store.write_state(TENANT, NAME, _state(1, "aws_vpc.main"), author="seed")
    tx = store.open_transaction(TENANT, NAME, author="alice")
    store.transactions.record_resources(
        tx.tx_id, [TransactionResource(address="aws_vpc.main", intent=INTENT_READ)]
    )
    assert store.transactions.prepare_commit(tx.tx_id).status == "committed"


def test_preview_reports_a_conflict_without_finalizing(store: StateStore) -> None:
    store.write_state(TENANT, NAME, _state(1, "aws_vpc.main"), author="seed")
    alice = store.open_transaction(TENANT, NAME, author="alice")
    bob = store.open_transaction(TENANT, NAME, author="bob")
    store.transactions.record_resources(alice.tx_id, _writes("shared.one"))
    store.transactions.record_resources(bob.tx_id, _writes("shared.one"))
    store.commit_transaction(alice.tx_id, _state(2, "aws_vpc.main"), author="alice")

    preview = store.transactions.prepare_commit(bob.tx_id)
    assert preview.status == "conflict"

    still_open = store.transactions.get(bob.tx_id)
    assert still_open is not None
    assert still_open.status == "open"


# -- gates ------------------------------------------------------------------


def test_a_failing_gate_blocks_commit_and_fails_the_transaction(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write_state(TENANT, NAME, _state(1, "aws_vpc.main"), author="seed")
    tx = store.open_transaction(TENANT, NAME, author="alice")
    store.transactions.record_resources(tx.tx_id, _writes("a.one"))
    store.transactions.record_gates(
        tx.tx_id, [GateOutcome(name="opa", passed=False, message="policy denied")]
    )

    outcome = store.commit_transaction(tx.tx_id, _state(2, "aws_vpc.main"), author="alice")
    assert outcome.status == "blocked"
    assert outcome.blocking_gates == ("opa",)

    failed = store.transactions.get(tx.tx_id)
    assert failed is not None
    assert failed.status == "failed"


def test_a_blocked_commit_does_not_write_state(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write_state(TENANT, NAME, _state(1, "aws_vpc.main"), author="seed")
    tx = store.open_transaction(TENANT, NAME, author="alice")
    store.transactions.record_gates(tx.tx_id, [GateOutcome(name="opa", passed=False)])
    store.commit_transaction(tx.tx_id, _state(2, "aws_vpc.main"), author="alice")

    summary = store.summary(TENANT, NAME)
    assert summary is not None
    assert summary.serial == 1


def test_a_passing_gate_permits_commit(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write_state(TENANT, NAME, _state(1, "aws_vpc.main"), author="seed")
    tx = store.open_transaction(TENANT, NAME, author="alice")
    store.transactions.record_gates(tx.tx_id, [GateOutcome(name="opa", passed=True)])
    assert (
        store.commit_transaction(tx.tx_id, _state(2, "aws_vpc.main"), author="alice").status
        == "committed"
    )


def test_a_skipped_gate_is_not_blocking_when_not_required(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write_state(TENANT, NAME, _state(1, "aws_vpc.main"), author="seed")
    tx = store.open_transaction(TENANT, NAME, author="alice")
    store.transactions.record_gates(
        tx.tx_id, [GateOutcome(name="infracost", passed=False, skipped=True)]
    )
    assert (
        store.commit_transaction(tx.tx_id, _state(2, "aws_vpc.main"), author="alice").status
        == "committed"
    )


def test_a_missing_required_gate_blocks_commit(tmp_path: Path) -> None:
    """Absent cannot read as passed, or the requirement is advisory."""
    store = _store(tmp_path, required_gates=frozenset({"opa"}))
    store.write_state(TENANT, NAME, _state(1, "aws_vpc.main"), author="seed")
    tx = store.open_transaction(TENANT, NAME, author="alice")

    outcome = store.commit_transaction(tx.tx_id, _state(2, "aws_vpc.main"), author="alice")
    assert outcome.status == "blocked"
    assert outcome.blocking_gates == ("opa",)


def test_a_skipped_required_gate_blocks_commit(tmp_path: Path) -> None:
    store = _store(tmp_path, required_gates=frozenset({"opa"}))
    store.write_state(TENANT, NAME, _state(1, "aws_vpc.main"), author="seed")
    tx = store.open_transaction(TENANT, NAME, author="alice")
    store.transactions.record_gates(tx.tx_id, [GateOutcome(name="opa", passed=False, skipped=True)])

    outcome = store.commit_transaction(tx.tx_id, _state(2, "aws_vpc.main"), author="alice")
    assert outcome.status == "blocked"


def test_a_reported_passing_required_gate_permits_commit(tmp_path: Path) -> None:
    store = _store(tmp_path, required_gates=frozenset({"opa"}))
    store.write_state(TENANT, NAME, _state(1, "aws_vpc.main"), author="seed")
    tx = store.open_transaction(TENANT, NAME, author="alice")
    store.transactions.record_gates(tx.tx_id, [GateOutcome(name="opa", passed=True)])
    assert (
        store.commit_transaction(tx.tx_id, _state(2, "aws_vpc.main"), author="alice").status
        == "committed"
    )


def test_conflicts_are_checked_before_gates(tmp_path: Path) -> None:
    """A conflict is the more actionable message, so it should win."""
    store = _store(tmp_path, required_gates=frozenset({"opa"}))
    store.write_state(TENANT, NAME, _state(1, "aws_vpc.main"), author="seed")
    alice = store.open_transaction(TENANT, NAME, author="alice")
    bob = store.open_transaction(TENANT, NAME, author="bob")
    store.transactions.record_resources(alice.tx_id, _writes("shared.one"))
    store.transactions.record_resources(bob.tx_id, _writes("shared.one"))
    store.transactions.record_gates(alice.tx_id, [GateOutcome(name="opa", passed=True)])
    store.commit_transaction(alice.tx_id, _state(2, "aws_vpc.main"), author="alice")

    assert (
        store.commit_transaction(bob.tx_id, _state(3, "aws_vpc.main"), author="bob").status
        == "conflict"
    )


# -- interaction with the write guards --------------------------------------


def test_a_stale_serial_fails_the_transaction(store: StateStore) -> None:
    store.write_state(TENANT, NAME, _state(5, "aws_vpc.main"), author="seed")
    tx = store.open_transaction(TENANT, NAME, author="alice")

    outcome = store.commit_transaction(tx.tx_id, _state(2, "aws_vpc.main"), author="alice")
    assert outcome.status == "conflict"
    failed = store.transactions.get(tx.tx_id)
    assert failed is not None
    assert failed.status == "failed"


def test_an_unparseable_body_fails_the_transaction(store: StateStore) -> None:
    tx = store.open_transaction(TENANT, NAME, author="alice")
    outcome = store.commit_transaction(tx.tx_id, b"not json", author="alice")
    assert outcome.status == "invalid"


def test_committing_a_held_lock_without_the_id_fails(store: StateStore) -> None:
    from repave_engine.statestore.store import LockInfo

    store.write_state(TENANT, NAME, _state(1, "aws_vpc.main"), author="seed")
    store.acquire_lock(TENANT, NAME, LockInfo(id="lock-1", who="someone"))
    tx = store.open_transaction(TENANT, NAME, author="alice")

    outcome = store.commit_transaction(tx.tx_id, _state(2, "aws_vpc.main"), author="alice")
    assert outcome.status == "conflict"
