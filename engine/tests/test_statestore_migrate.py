from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from repave_engine.sql_store import DatabaseConfig, connect
from repave_engine.statestore.migrate import (
    MigrationError,
    applied_versions,
    apply_migrations,
    current_schema_version,
    ensure_migrations_table,
    load_migrations,
    split_sql_statements,
)


def _sqlite_conn(tmp_path: Path):
    return connect(DatabaseConfig(dialect="sqlite", sqlite_path=tmp_path / "state.db"))


def test_split_statements_basic() -> None:
    sql = "CREATE TABLE a (id TEXT);\nCREATE TABLE b (id TEXT);\n"
    assert split_sql_statements(sql) == ("CREATE TABLE a (id TEXT)", "CREATE TABLE b (id TEXT)")


def test_split_statements_strips_line_comments() -> None:
    sql = "-- leading note\nCREATE TABLE a (id TEXT); -- trailing note\n"
    assert split_sql_statements(sql) == ("CREATE TABLE a (id TEXT)",)


def test_split_statements_keeps_semicolon_inside_string_literal() -> None:
    sql = "INSERT INTO t (v) VALUES ('a;b');"
    assert split_sql_statements(sql) == ("INSERT INTO t (v) VALUES ('a;b')",)


def test_split_statements_handles_escaped_quote() -> None:
    sql = "INSERT INTO t (v) VALUES ('it''s; fine');"
    assert split_sql_statements(sql) == ("INSERT INTO t (v) VALUES ('it''s; fine')",)


def test_split_statements_ignores_comment_marker_inside_string() -> None:
    sql = "INSERT INTO t (v) VALUES ('a--b');"
    assert split_sql_statements(sql) == ("INSERT INTO t (v) VALUES ('a--b')",)


def test_split_statements_accepts_missing_trailing_semicolon() -> None:
    assert split_sql_statements("CREATE TABLE a (id TEXT)") == ("CREATE TABLE a (id TEXT)",)


def test_split_statements_empty_input() -> None:
    assert split_sql_statements("\n-- only a comment\n") == ()


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
def test_migrations_load_contiguous_from_version_one(dialect: str) -> None:
    migrations = load_migrations(dialect)  # type: ignore[arg-type]
    assert migrations, f"no migrations found for {dialect}"
    assert [item.version for item in migrations] == list(range(1, len(migrations) + 1))
    assert all(item.statements for item in migrations)


def test_both_dialects_define_the_same_versions() -> None:
    sqlite_versions = [(m.version, m.name) for m in load_migrations("sqlite")]
    postgres_versions = [(m.version, m.name) for m in load_migrations("postgresql")]
    assert sqlite_versions == postgres_versions


def test_apply_migrations_creates_schema(tmp_path: Path) -> None:
    with _sqlite_conn(tmp_path) as conn:
        applied = apply_migrations(conn)
        assert applied == tuple(m.version for m in load_migrations("sqlite"))
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert {"states", "state_versions", "state_locks", "schema_migrations"} <= tables


def test_apply_migrations_is_idempotent(tmp_path: Path) -> None:
    with _sqlite_conn(tmp_path) as conn:
        first = apply_migrations(conn)
        assert first
        assert apply_migrations(conn) == ()
        assert current_schema_version(conn) == max(first)


def test_apply_migrations_resumes_after_partial_history(tmp_path: Path) -> None:
    with _sqlite_conn(tmp_path) as conn:
        all_versions = [m.version for m in load_migrations("sqlite")]
        if len(all_versions) < 2:
            pytest.skip("needs at least two migrations")
        # Simulate a store created before later migrations existed.
        first = load_migrations("sqlite")[0]
        ensure_migrations_table(conn)
        for statement in first.statements:
            conn.execute_ddl(statement)
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
            (first.version, first.name, "2026-01-01T00:00:00+00:00"),
        )
        conn.commit()

        applied = apply_migrations(conn)
        assert applied == tuple(all_versions[1:])
        assert applied_versions(conn) == tuple(all_versions)


def test_apply_migrations_rolls_back_and_reports_file(tmp_path: Path, monkeypatch) -> None:
    from repave_engine.statestore import migrate as migrate_mod

    broken = (migrate_mod.Migration(version=1, name="broken", statements=("CREATE TABLE oops (",)),)
    monkeypatch.setattr(migrate_mod, "load_migrations", lambda _dialect: broken)
    with _sqlite_conn(tmp_path) as conn:
        with pytest.raises(MigrationError, match="0001_broken"):
            apply_migrations(conn)
        assert applied_versions(conn) == ()


def test_current_schema_version_zero_on_fresh_database(tmp_path: Path) -> None:
    with _sqlite_conn(tmp_path) as conn:
        assert current_schema_version(conn) == 0


def test_state_versions_rejects_duplicate_serial(tmp_path: Path) -> None:
    with _sqlite_conn(tmp_path) as conn:
        apply_migrations(conn)
        conn.execute(
            "INSERT INTO state_tenants (tenant_id, display_name, created_at) VALUES (?, ?, ?)",
            ("acme", "Acme", "2026-01-01T00:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO states (state_id, tenant_id, name, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("s1", "acme", "prod", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
        )
        row = (
            "v1",
            "s1",
            1,
            "abc",
            "1.9.0",
            b"{}",
            "sha",
            2,
            "none",
            None,
            "someone",
            "2026-01-01T00:00:00+00:00",
        )
        insert = (
            "INSERT INTO state_versions (version_id, state_id, serial, lineage, "
            "terraform_version, blob, blob_sha256, blob_size, encryption, key_id, "
            "author, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        conn.execute(insert, row)
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(insert, ("v2", *row[1:]))
