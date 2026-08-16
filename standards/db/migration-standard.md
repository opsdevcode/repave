# Database migration standard v1.0.0

Version: 1.0.0

Governed Alembic, Flyway, or Atlas repositories from the `db-migration-generic`
golden path. Policy: [ADR 012](../../docs/adr/012-destructive-ddl-policy.md).

## Naming

- Repository name: `db-migration-{organization}-{service_name}`.
- One tool per repo (`alembic`, `flyway`, or `atlas`).

## Required files

| Tool | Forward | Rollback | Waiver |
| --- | --- | --- | --- |
| Alembic | `alembic/versions/*.py` | `def downgrade` in the same file | `waivers/destructive.yaml` |
| Flyway | `sql/V{n}__*.sql` | `sql/U{n}__*.sql` | `waivers/destructive.yaml` |
| Atlas | `migrations/*.sql` | `migrations/*.down.sql` | `waivers/destructive.yaml` |

## Validation

- **migration-policy** — forward files must not contain destructive DDL
  (`DROP TABLE` / `DROP COLUMN` / `TRUNCATE` / `op.drop_table` / …) unless a
  waiver names the file with `reason` and `expires_at`.
- **migration-rollback** — every forward revision has a paired down.
- **secrets**, **docs-drift**, **provenance-drift**

Undo scripts are not scanned for destructive DDL.

## Provenance

Lineage is recorded in `repave.yaml` (`artifactType: db-migration`).
