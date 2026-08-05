"""Persist and query the resource graph (ADR 004 Phase 2).

The graph is a derived index over the current state version, rebuilt on every accepted
write. Nothing here is authoritative: dropping every one of these tables and replaying
the blobs reproduces them exactly.
"""

from __future__ import annotations

import json
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Literal

from repave_engine.sql_store import SqlConnection
from repave_engine.statestore.normalize import (
    Edge,
    NormalizedState,
    strip_index,
)

DriftStatus = Literal["added", "removed", "changed", "unchanged"]

#: Guard against pathological graphs; a real state has far fewer hops than this.
MAX_TRAVERSAL_DEPTH: Final = 100


@dataclass(frozen=True)
class ResourceRow:
    address: str
    module: str
    mode: str
    type: str
    name: str
    provider: str
    instance_count: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "module": self.module,
            "mode": self.mode,
            "type": self.type,
            "name": self.name,
            "provider": self.provider,
            "instance_count": self.instance_count,
        }


@dataclass(frozen=True)
class InventoryEntry:
    type: str
    mode: str
    count: int

    def to_payload(self) -> dict[str, Any]:
        return {"type": self.type, "mode": self.mode, "count": self.count}


@dataclass(frozen=True)
class DriftEntry:
    address: str
    status: DriftStatus
    changed_keys: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "status": self.status,
            "changed_keys": list(self.changed_keys),
        }


def _json_placeholder(conn: SqlConnection) -> str:
    """PostgreSQL will not implicitly cast a text parameter into a jsonb column."""
    return "CAST(? AS JSONB)" if conn.dialect == "postgresql" else "?"


def _load_json(value: Any) -> Any:
    """psycopg returns jsonb already decoded; SQLite returns the stored text."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value


def clear_graph(conn: SqlConnection, state_id: str) -> None:
    """Drop every derived row for one state. Caller commits.

    Instances are deleted explicitly rather than through the cascade, because SQLite
    only enforces foreign keys when `PRAGMA foreign_keys` is on and orphans here would
    collide with `UNIQUE (state_id, address)` on the next write.
    """
    conn.execute("DELETE FROM state_edges WHERE state_id = ?", (state_id,))
    conn.execute("DELETE FROM state_resource_instances WHERE state_id = ?", (state_id,))
    conn.execute("DELETE FROM state_resources WHERE state_id = ?", (state_id,))


def replace_graph(
    conn: SqlConnection,
    *,
    state_id: str,
    version_id: str,
    normalized: NormalizedState,
    extra_edges: list[Edge] | None = None,
) -> None:
    """Rebuild the graph for one state. Caller commits."""
    clear_graph(conn, state_id)

    json_slot = _json_placeholder(conn)
    for resource in normalized.resources:
        resource_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO state_resources (resource_id, state_id, version_id, address, "
            "module, mode, type, name, provider, instance_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                resource_id,
                state_id,
                version_id,
                resource.address,
                resource.module,
                resource.mode,
                resource.type,
                resource.name,
                resource.provider,
                len(resource.instances),
            ),
        )
        for instance in resource.instances:
            # json_slot is a dialect literal from _json_placeholder, never caller
            # input; every value below is a bound parameter.
            conn.execute(
                "INSERT INTO state_resource_instances (instance_id, resource_id, state_id, "  # nosec B608
                "address, index_key, schema_version, attributes, redacted_keys) "
                f"VALUES (?, ?, ?, ?, ?, ?, {json_slot}, {json_slot})",
                (
                    uuid.uuid4().hex,
                    resource_id,
                    state_id,
                    instance.address,
                    instance.index_key,
                    instance.schema_version,
                    json.dumps(instance.attributes, sort_keys=True),
                    json.dumps(list(instance.redacted_keys)),
                ),
            )

    known = normalized.addresses
    for edge in [*normalized.edges, *(extra_edges or [])]:
        # Edges to addresses absent from state would make blast radius report
        # resources that do not exist.
        if edge.from_address not in known or edge.to_address not in known:
            continue
        conn.execute(
            "INSERT INTO state_edges (edge_id, state_id, from_address, to_address, kind) "
            "VALUES (?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, state_id, edge.from_address, edge.to_address, edge.kind),
        )


def list_resources(
    conn: SqlConnection,
    state_id: str,
    *,
    resource_type: str | None = None,
    mode: str | None = None,
) -> list[ResourceRow]:
    sql = "SELECT * FROM state_resources WHERE state_id = ?"
    params: list[Any] = [state_id]
    if resource_type:
        sql += " AND type = ?"
        params.append(resource_type)
    if mode:
        sql += " AND mode = ?"
        params.append(mode)
    sql += " ORDER BY address ASC"

    rows = conn.execute(sql, tuple(params)).fetchall()
    return [
        ResourceRow(
            address=str(row["address"]),
            module=str(row["module"]),
            mode=str(row["mode"]),
            type=str(row["type"]),
            name=str(row["name"]),
            provider=str(row["provider"]),
            instance_count=int(row["instance_count"]),
        )
        for row in rows
    ]


def inventory(conn: SqlConnection, state_id: str) -> list[InventoryEntry]:
    rows = conn.execute(
        "SELECT type, mode, COUNT(*) AS total FROM state_resources WHERE state_id = ? "
        "GROUP BY type, mode ORDER BY total DESC, type ASC",
        (state_id,),
    ).fetchall()
    return [
        InventoryEntry(type=str(row["type"]), mode=str(row["mode"]), count=int(row["total"]))
        for row in rows
    ]


def list_edges(conn: SqlConnection, state_id: str) -> list[Edge]:
    rows = conn.execute(
        "SELECT from_address, to_address, kind FROM state_edges WHERE state_id = ? "
        "ORDER BY from_address ASC, to_address ASC",
        (state_id,),
    ).fetchall()
    return [
        Edge(
            from_address=str(row["from_address"]),
            to_address=str(row["to_address"]),
            kind=str(row["kind"]),
        )
        for row in rows
    ]


def blast_radius(conn: SqlConnection, state_id: str, address: str) -> list[str]:
    """Transitive dependents of an address: everything a change here can reach.

    Edges point dependent -> dependency, so this walks them backwards. Cycles are
    tolerated rather than rejected: Terraform forbids them, but a malformed import
    should not hang the query.
    """
    target = strip_index(address.strip())
    if not target:
        return []

    dependents: dict[str, list[str]] = {}
    for edge in list_edges(conn, state_id):
        dependents.setdefault(edge.to_address, []).append(edge.from_address)

    seen: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(target, 0)])
    while queue:
        current, depth = queue.popleft()
        if depth >= MAX_TRAVERSAL_DEPTH:
            continue
        for dependent in dependents.get(current, []):
            if dependent in seen or dependent == target:
                continue
            seen.add(dependent)
            queue.append((dependent, depth + 1))
    return sorted(seen)


def dependencies_of(conn: SqlConnection, state_id: str, address: str) -> list[str]:
    """Direct dependencies of an address (the forward direction)."""
    target = strip_index(address.strip())
    rows = conn.execute(
        "SELECT DISTINCT to_address FROM state_edges WHERE state_id = ? AND from_address = ? "
        "ORDER BY to_address ASC",
        (state_id, target),
    ).fetchall()
    return [str(row["to_address"]) for row in rows]


def stored_instance_attributes(conn: SqlConnection, state_id: str) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        "SELECT address, attributes FROM state_resource_instances WHERE state_id = ?",
        (state_id,),
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        parsed = _load_json(row["attributes"])
        out[str(row["address"])] = parsed if isinstance(parsed, dict) else {}
    return out


def compare_drift(
    stored: dict[str, dict[str, Any]], observed: dict[str, dict[str, Any]]
) -> list[DriftEntry]:
    """Per-resource delta between stored attributes and a refreshed observation.

    Both sides are already redacted, so a redacted attribute compares equal to itself
    and never shows as drift. That is the intended trade: a changed secret is
    invisible here, and detecting it would require storing the secret.
    """
    entries: list[DriftEntry] = []
    for address in sorted(set(stored) | set(observed)):
        before = stored.get(address)
        after = observed.get(address)
        if before is None:
            entries.append(DriftEntry(address=address, status="added"))
            continue
        if after is None:
            entries.append(DriftEntry(address=address, status="removed"))
            continue
        changed = tuple(
            sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
        )
        entries.append(
            DriftEntry(
                address=address,
                status="changed" if changed else "unchanged",
                changed_keys=changed,
            )
        )
    return entries


def cache_provider_schema(
    conn: SqlConnection,
    *,
    provider: str,
    version: str,
    sensitive_by_type: dict[str, set[str]],
) -> None:
    payload = {name: sorted(values) for name, values in sorted(sensitive_by_type.items())}
    json_slot = _json_placeholder(conn)
    conn.execute(
        "DELETE FROM state_provider_schemas WHERE schema_key = ?",
        (f"{provider}@{version}",),
    )
    # json_slot is a dialect literal from _json_placeholder, never caller input;
    # every value below is a bound parameter.
    conn.execute(
        "INSERT INTO state_provider_schemas (schema_key, provider, version, "  # nosec B608
        f"sensitive_paths, fetched_at) VALUES (?, ?, ?, {json_slot}, ?)",
        (
            f"{provider}@{version}",
            provider,
            version,
            json.dumps(payload, sort_keys=True),
            datetime.now(UTC).isoformat(timespec="seconds"),
        ),
    )
    conn.commit()


def load_cached_sensitive_attributes(conn: SqlConnection) -> dict[str, set[str]]:
    """Union of cached provider sensitivity, keyed by resource type."""
    rows = conn.execute("SELECT sensitive_paths FROM state_provider_schemas").fetchall()
    merged: dict[str, set[str]] = {}
    for row in rows:
        payload = _load_json(row["sensitive_paths"])
        if not isinstance(payload, dict):
            continue
        for resource_type, names in payload.items():
            if isinstance(names, list):
                merged.setdefault(str(resource_type), set()).update(str(n) for n in names)
    return merged
