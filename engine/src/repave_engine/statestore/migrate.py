"""Forward-only versioned SQL migrations for the state store (ADR 004 Phase 0).

The runs/audit/session store in `sql_store.py` uses inline `CREATE TABLE IF NOT
EXISTS`, which does not survive a schema that evolves across phases. State store
schema is versioned files instead: `migrations/<dialect>/NNNN_<name>.sql`.

Dialects get separate files rather than one templated file, matching the existing
split between `_ensure_schema_sqlite` and `_ensure_schema_postgres`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from importlib import resources
from typing import Final

from repave_engine.sql_store import Dialect, SqlConnection

logger = logging.getLogger(__name__)

MIGRATIONS_PACKAGE: Final = "repave_engine.statestore.migrations"

_FILENAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]


class MigrationError(RuntimeError):
    """Schema could not be brought to the expected version."""


def split_sql_statements(text: str) -> tuple[str, ...]:
    """Split a migration file into statements on top-level semicolons.

    Handles `--` line comments and single-quoted literals. Migration SQL is plain
    DDL by convention: no dollar-quoted bodies, triggers, or stored procedures.
    """
    statements: list[str] = []
    buffer: list[str] = []
    in_string = False
    in_comment = False
    index = 0
    while index < len(text):
        char = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""

        if in_comment:
            if char == "\n":
                in_comment = False
                buffer.append(char)
            index += 1
            continue

        if in_string:
            buffer.append(char)
            if char == "'":
                # '' is an escaped quote inside a literal.
                if nxt == "'":
                    buffer.append(nxt)
                    index += 2
                    continue
                in_string = False
            index += 1
            continue

        if char == "-" and nxt == "-":
            in_comment = True
            index += 2
            continue
        if char == "'":
            in_string = True
            buffer.append(char)
            index += 1
            continue
        if char == ";":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
            index += 1
            continue

        buffer.append(char)
        index += 1

    trailing = "".join(buffer).strip()
    if trailing:
        statements.append(trailing)
    return tuple(statements)


@lru_cache(maxsize=4)
def load_migrations(dialect: Dialect) -> tuple[Migration, ...]:
    """Migrations for a dialect, ordered by version."""
    root = resources.files(MIGRATIONS_PACKAGE) / dialect
    if not root.is_dir():
        raise MigrationError(
            f"no migrations for dialect {dialect!r}: expected {MIGRATIONS_PACKAGE}.{dialect}"
        )

    found: list[Migration] = []
    seen: dict[int, str] = {}
    for entry in root.iterdir():
        match = _FILENAME.match(entry.name)
        if match is None:
            continue
        version = int(match.group(1))
        name = match.group(2)
        if version in seen:
            raise MigrationError(
                f"duplicate migration version {version:04d} for {dialect}: "
                f"{seen[version]} and {name}"
            )
        seen[version] = name
        found.append(
            Migration(
                version=version,
                name=name,
                statements=split_sql_statements(entry.read_text(encoding="utf-8")),
            )
        )

    found.sort(key=lambda item: item.version)
    _require_contiguous(found, dialect)
    return tuple(found)


def _require_contiguous(migrations: list[Migration], dialect: Dialect) -> None:
    for offset, migration in enumerate(migrations, start=1):
        if migration.version != offset:
            raise MigrationError(
                f"migration versions for {dialect} must start at 1 and be contiguous; "
                f"expected {offset:04d}, found {migration.version:04d}_{migration.name}"
            )


def ensure_migrations_table(conn: SqlConnection) -> None:
    conn.execute_ddl(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def applied_versions(conn: SqlConnection) -> tuple[int, ...]:
    ensure_migrations_table(conn)
    cur = conn.execute("SELECT version FROM schema_migrations ORDER BY version ASC")
    rows = cur.fetchall() if hasattr(cur, "fetchall") else list(cur)
    out: list[int] = []
    for row in rows:
        value = row["version"] if isinstance(row, dict) else row[0]
        out.append(int(value))
    return tuple(out)


def current_schema_version(conn: SqlConnection) -> int:
    versions = applied_versions(conn)
    return versions[-1] if versions else 0


def apply_migrations(conn: SqlConnection) -> tuple[int, ...]:
    """Apply pending migrations in order. Returns versions applied this call.

    Forward-only and idempotent: already-applied versions are skipped, so calling
    this on every startup is safe.
    """
    migrations = load_migrations(conn.dialect)
    already = set(applied_versions(conn))
    pending = [item for item in migrations if item.version not in already]
    if not pending:
        return ()

    applied: list[int] = []
    for migration in pending:
        logger.info(
            "applying state store migration %04d_%s (%s)",
            migration.version,
            migration.name,
            conn.dialect,
        )
        try:
            for statement in migration.statements:
                conn.execute_ddl(statement)
            conn.execute(
                "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                (
                    migration.version,
                    migration.name,
                    datetime.now(UTC).isoformat(timespec="seconds"),
                ),
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            raise MigrationError(
                f"migration {migration.version:04d}_{migration.name} failed on "
                f"{conn.dialect}: {exc}"
            ) from exc
        applied.append(migration.version)
    return tuple(applied)
