from __future__ import annotations

from pathlib import Path

from repave_engine.blueprint import artifact_family, load_blueprint
from repave_engine.gates import run_gates
from repave_engine.provenance import build_provenance_document


def _alembic_repo(root: Path, *, destructive: bool = False, downgrade: bool = True) -> None:
    versions = root / "alembic" / "versions"
    versions.mkdir(parents=True)
    body = [
        "revision = '0001'",
        "def upgrade() -> None:",
        "    op.create_table('example_items')",
    ]
    if destructive:
        body.append("    op.drop_table('legacy')")
    if downgrade:
        body.extend(["", "def downgrade() -> None:", "    op.drop_table('example_items')"])
    (versions / "0001_init.py").write_text("\n".join(body) + "\n", encoding="utf-8")
    (root / "waivers").mkdir(exist_ok=True)
    (root / "waivers" / "destructive.yaml").write_text("waivers: []\n", encoding="utf-8")


def test_artifact_family_db_migration() -> None:
    assert artifact_family("db-migration") == "data"


def test_migration_policy_ignores_alembic_downgrade_drop(tmp_path: Path) -> None:
    _alembic_repo(tmp_path)

    results = run_gates(tmp_path, ("migration-policy",))

    assert results[0].passed is True
    assert results[0].skipped is False


def test_migration_policy_fails_unwaived_drop(tmp_path: Path) -> None:
    _alembic_repo(tmp_path, destructive=True)

    results = run_gates(tmp_path, ("migration-policy",))

    assert results[0].passed is False
    assert "destructive.yaml" in results[0].message
    assert "drop_table" in results[0].message.lower() or "DROP" in results[0].message


def test_migration_policy_passes_with_unexpired_waiver(tmp_path: Path) -> None:
    _alembic_repo(tmp_path, destructive=True)
    (tmp_path / "waivers" / "destructive.yaml").write_text(
        "\n".join(
            [
                "waivers:",
                "  - path: alembic/versions/0001_init.py",
                '    reason: "legacy table archived"',
                '    expires_at: "2099-01-01"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    results = run_gates(tmp_path, ("migration-policy",))

    assert results[0].passed is True
    assert results[0].skipped is False


def test_migration_policy_fails_expired_waiver(tmp_path: Path) -> None:
    _alembic_repo(tmp_path, destructive=True)
    (tmp_path / "waivers" / "destructive.yaml").write_text(
        "\n".join(
            [
                "waivers:",
                "  - path: alembic/versions/0001_init.py",
                '    reason: "stale"',
                '    expires_at: "2020-01-01"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    results = run_gates(tmp_path, ("migration-policy",))

    assert results[0].passed is False
    assert "expired" in results[0].message


def test_migration_rollback_fails_without_downgrade(tmp_path: Path) -> None:
    _alembic_repo(tmp_path, downgrade=False)

    results = run_gates(tmp_path, ("migration-rollback",))

    assert results[0].passed is False
    assert "downgrade" in results[0].message


def test_detect_tool_ignores_empty_layout_dirs(tmp_path: Path) -> None:
    sql = tmp_path / "sql"
    sql.mkdir()
    (sql / "V1__init.sql").write_text("CREATE TABLE example_items (id INT);\n", encoding="utf-8")
    (sql / "U1__init.sql").write_text("DROP TABLE example_items;\n", encoding="utf-8")
    (tmp_path / "alembic" / "versions").mkdir(parents=True)
    (tmp_path / "migrations").mkdir()

    results = run_gates(tmp_path, ("migration-policy", "migration-rollback"))

    assert all(result.passed for result in results)


def test_migration_rollback_requires_flyway_undo(tmp_path: Path) -> None:
    sql = tmp_path / "sql"
    sql.mkdir()
    (sql / "V1__init.sql").write_text("CREATE TABLE example_items (id INT);\n", encoding="utf-8")

    results = run_gates(tmp_path, ("migration-rollback",))

    assert results[0].passed is False
    assert "U1__" in results[0].message

    (sql / "U1__init.sql").write_text("DROP TABLE example_items;\n", encoding="utf-8")
    results = run_gates(tmp_path, ("migration-rollback",))
    assert results[0].passed is True


def test_rendered_alembic_layout_passes_migration_gates(
    repo_root: Path, tmp_path: Path, output_config
) -> None:
    from repave_engine.blueprint_conformance import run_blueprint_conformance

    outcome = run_blueprint_conformance(
        repo_root / "blueprints" / "db-migration-generic",
        repo_root=repo_root,
        output_config=output_config,
        staging_root=tmp_path,
        check_snapshot=False,
        render_only=True,
    )
    assert (outcome.output_dir / "alembic" / "versions" / "0001_init.py").is_file()
    assert not (outcome.output_dir / "sql" / "V1__init.sql").is_file()

    results = run_gates(outcome.output_dir, ("migration-policy", "migration-rollback"))

    assert all(result.passed for result in results)


def test_db_migration_blueprint_and_provenance(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "db-migration-generic",
        repo_root=repo_root,
    )
    assert blueprint.artifact_type == "db-migration"
    assert "migration-policy" in blueprint.gates
    document = build_provenance_document(
        blueprint,
        {
            "service_name": "checkout",
            "organization": "platform",
            "tool": "alembic",
        },
    )
    assert document["spec"]["artifactType"] == "db-migration"
    assert document["spec"]["dbMigration"]["tool"] == "alembic"
