from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from repave_engine.sql_store import DatabaseConfig, connect
from repave_engine.statestore.graph import DriftEntry, compare_drift
from repave_engine.statestore.normalize import EDGE_REFERENCE, REDACTED, Edge
from repave_engine.statestore.store import StateStore, ensure_state_schema
from statestore_support import make_state, managed_resource

TENANT = "default"
NAME = "prod"


@pytest.fixture
def store(tmp_path: Path):
    conn = connect(DatabaseConfig(dialect="sqlite", sqlite_path=tmp_path / "state.db"))
    ensure_state_schema(conn)
    instance = StateStore(conn)
    instance.ensure_tenant(TENANT)
    try:
        yield instance
    finally:
        conn.close()


def _write(store: StateStore, resources: list[dict[str, Any]], *, serial: int = 1) -> None:
    outcome = store.write_state(
        TENANT,
        NAME,
        make_state(serial=serial, resources=resources),
        author="test",
    )
    assert outcome.status == "created", outcome.detail


def _three_tier() -> list[dict[str, Any]]:
    return [
        managed_resource("aws_vpc", "main"),
        managed_resource("aws_subnet", "web", depends_on=["aws_vpc.main"]),
        managed_resource("aws_instance", "app", depends_on=["aws_subnet.web"]),
        managed_resource("aws_s3_bucket", "assets"),
    ]


def test_write_populates_the_resource_graph(store: StateStore) -> None:
    _write(store, _three_tier())

    addresses = [r.address for r in store.resources(TENANT, NAME)]
    assert addresses == [
        "aws_instance.app",
        "aws_s3_bucket.assets",
        "aws_subnet.web",
        "aws_vpc.main",
    ]


def test_resources_filter_by_type_and_mode(store: StateStore) -> None:
    data_source = managed_resource("aws_ami", "base")
    data_source["mode"] = "data"
    _write(store, [*_three_tier(), data_source])

    assert [r.address for r in store.resources(TENANT, NAME, resource_type="aws_vpc")] == [
        "aws_vpc.main"
    ]
    assert [r.address for r in store.resources(TENANT, NAME, mode="data")] == ["data.aws_ami.base"]


def test_inventory_counts_by_type(store: StateStore) -> None:
    _write(
        store,
        [
            managed_resource("aws_instance", "a"),
            managed_resource("aws_instance", "b"),
            managed_resource("aws_vpc", "main"),
        ],
    )
    counts = {entry.type: entry.count for entry in store.inventory(TENANT, NAME)}
    assert counts == {"aws_instance": 2, "aws_vpc": 1}


def test_blast_radius_is_transitive_over_dependents(store: StateStore) -> None:
    _write(store, _three_tier())

    assert store.blast_radius(TENANT, NAME, "aws_vpc.main") == [
        "aws_instance.app",
        "aws_subnet.web",
    ]
    # A leaf that nothing depends on reaches nobody.
    assert store.blast_radius(TENANT, NAME, "aws_instance.app") == []
    assert store.blast_radius(TENANT, NAME, "aws_s3_bucket.assets") == []


def test_blast_radius_accepts_an_indexed_address(store: StateStore) -> None:
    _write(store, _three_tier())
    assert store.blast_radius(TENANT, NAME, "aws_vpc.main[0]") == [
        "aws_instance.app",
        "aws_subnet.web",
    ]


def test_blast_radius_terminates_on_a_cycle(store: StateStore) -> None:
    _write(
        store,
        [
            managed_resource("aws_a", "one", depends_on=["aws_b.two"]),
            managed_resource("aws_b", "two", depends_on=["aws_a.one"]),
        ],
    )
    assert store.blast_radius(TENANT, NAME, "aws_a.one") == ["aws_b.two"]


def test_dependencies_are_the_forward_direction(store: StateStore) -> None:
    _write(store, _three_tier())
    assert store.dependencies(TENANT, NAME, "aws_subnet.web") == ["aws_vpc.main"]
    assert store.dependencies(TENANT, NAME, "aws_vpc.main") == []


def test_edges_to_unknown_addresses_are_dropped(store: StateStore) -> None:
    _write(store, [managed_resource("aws_subnet", "web", depends_on=["aws_vpc.missing"])])
    assert store.edges(TENANT, NAME) == []


def test_extra_edges_enrich_graph_without_state_depends_on(store: StateStore) -> None:
    """Plan-JSON references fill gaps state dependencies leave empty."""
    outcome = store.write_state(
        TENANT,
        NAME,
        make_state(
            serial=1,
            resources=[
                managed_resource("aws_vpc", "main"),
                managed_resource("aws_subnet", "web"),  # no depends_on in state
            ],
        ),
        author="test",
        extra_edges=[
            Edge(
                from_address="aws_subnet.web",
                to_address="aws_vpc.main",
                kind=EDGE_REFERENCE,
            ),
            Edge(
                from_address="aws_subnet.web",
                to_address="aws_vpc.missing",
                kind=EDGE_REFERENCE,
            ),
        ],
    )
    assert outcome.status == "created", outcome.detail

    edges = store.edges(TENANT, NAME)
    assert [(e.from_address, e.to_address, e.kind) for e in edges] == [
        ("aws_subnet.web", "aws_vpc.main", "reference")
    ]
    assert store.blast_radius(TENANT, NAME, "aws_vpc.main") == ["aws_subnet.web"]


def test_graph_is_replaced_not_appended_on_rewrite(store: StateStore) -> None:
    _write(store, _three_tier())
    _write(store, [managed_resource("aws_vpc", "main")], serial=2)

    assert [r.address for r in store.resources(TENANT, NAME)] == ["aws_vpc.main"]
    assert store.edges(TENANT, NAME) == []


def test_deleting_a_state_clears_its_graph(store: StateStore) -> None:
    _write(store, _three_tier())
    assert store.delete_state(TENANT, NAME) is True
    assert store.resources(TENANT, NAME) == []
    assert store.inventory(TENANT, NAME) == []


def test_queries_on_an_unknown_state_return_empty(store: StateStore) -> None:
    assert store.resources(TENANT, "nope") == []
    assert store.inventory(TENANT, "nope") == []
    assert store.blast_radius(TENANT, "nope", "aws_vpc.main") == []
    assert store.edges(TENANT, "nope") == []


def test_cached_provider_schema_redacts_later_writes(store: StateStore) -> None:
    learned = store.cache_provider_schema(
        {
            "provider_schemas": {
                "registry.terraform.io/hashicorp/aws": {
                    "resource_schemas": {
                        "aws_db_instance": {
                            "block": {"attributes": {"endpoint": {"sensitive": True}}}
                        }
                    }
                }
            }
        },
        provider="hashicorp/aws",
        version="5.0.0",
    )
    assert learned == 1

    _write(
        store,
        [
            managed_resource(
                "aws_db_instance", "db", attributes={"id": "db-1", "endpoint": "host:5432"}
            )
        ],
    )
    drift = store.drift(
        TENANT,
        NAME,
        make_state(
            resources=[
                managed_resource(
                    "aws_db_instance", "db", attributes={"id": "db-1", "endpoint": "moved:5432"}
                )
            ]
        ),
    )
    # Both sides redact to the same marker, so a changed secret is invisible by design.
    assert [(d.address, d.status) for d in drift] == [("aws_db_instance.db", "unchanged")]


def test_drift_reports_added_removed_and_changed(store: StateStore) -> None:
    _write(
        store,
        [
            managed_resource("aws_instance", "app", attributes={"id": "i-1", "size": "small"}),
            managed_resource("aws_s3_bucket", "gone", attributes={"id": "b-1"}),
        ],
    )
    refreshed = make_state(
        resources=[
            managed_resource("aws_instance", "app", attributes={"id": "i-1", "size": "large"}),
            managed_resource("aws_sqs_queue", "new", attributes={"id": "q-1"}),
        ]
    )
    drift = {entry.address: entry for entry in store.drift(TENANT, NAME, refreshed)}

    assert drift["aws_instance.app"].status == "changed"
    assert drift["aws_instance.app"].changed_keys == ("size",)
    assert drift["aws_s3_bucket.gone"].status == "removed"
    assert drift["aws_sqs_queue.new"].status == "added"


def test_drift_on_an_unchanged_state_reports_nothing_changed(store: StateStore) -> None:
    resources = [managed_resource("aws_instance", "app", attributes={"id": "i-1"})]
    _write(store, resources)
    drift = store.drift(TENANT, NAME, make_state(resources=resources))
    assert all(entry.status == "unchanged" for entry in drift)


def test_compare_drift_ignores_equal_redacted_values() -> None:
    stored = {"aws_db.x": {"password": REDACTED, "id": "1"}}
    observed = {"aws_db.x": {"password": REDACTED, "id": "1"}}
    assert compare_drift(stored, observed) == [
        DriftEntry(address="aws_db.x", status="unchanged", changed_keys=())
    ]


def test_timeline_comes_from_state_versions(store: StateStore) -> None:
    _write(store, [managed_resource("aws_vpc", "main")], serial=1)
    _write(store, _three_tier(), serial=2)

    versions = store.list_versions(TENANT, NAME)
    assert [v.serial for v in versions] == [2, 1]
    assert all(v.author == "test" for v in versions)
