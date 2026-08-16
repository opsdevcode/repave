# ADR 012: Destructive DDL policy for migration repos

**Status:** Accepted — lands with `db-migration-generic`  
**Date:** 2026-08-16  
**Scope:** generated Alembic / Flyway / Atlas repositories and the
`migration-policy` / `migration-rollback` gates. Does not change Terraform
state custody (ADR 004) or environment vending (ADR 003).
**Related:** [`standards/db/migration-standard.md`](../standards/db/migration-standard.md),
[`docs/operations/mandatory-policy.md`](../operations/mandatory-policy.md)

## Context

Teams keep schema migrations in ad-hoc repos. Destructive DDL (drop table,
drop column, truncate) reaches production without a recorded reason, expiry,
or a paired rollback. The paved-road follow-on asked for Alembic/Flyway/Atlas
layouts plus a policy before scoping the goldpath.

## Decision

**Forward migrations must not contain destructive DDL unless a dated waiver
names the file. Every forward revision must have a rollback.**

### Destructive (forward only)

These patterns fail `migration-policy` when they appear in an upgrade /
`V*` / non-`.down.sql` file:

- `DROP TABLE`, `DROP COLUMN`, `DROP DATABASE`, `DROP SCHEMA`, `DROP VIEW`
- `TRUNCATE`
- `RENAME TABLE`, `RENAME COLUMN`
- Alembic `op.drop_table`, `op.drop_column`

Undo / `downgrade` / Flyway `U*` / `*.down.sql` are **not** scanned. Rollback
scripts are allowed to drop what upgrade created.

Index-only drops are not destructive for this policy.

### Waiver

`waivers/destructive.yaml`:

```yaml
waivers:
  - path: alembic/versions/0002_drop_legacy.py
    reason: "legacy events table archived; drop after 30-day read-only"
    expires_at: "2027-02-01"
```

`path`, `reason`, and `expires_at` (ISO date) are required. An expired or
undated waiver fails closed and names the file. This is the same expiry
spirit as v3 mandatory-policy waivers, scoped to the migration repo.

### Rollback

`migration-rollback` requires a paired down for each forward file:

| Tool | Forward | Rollback |
| --- | --- | --- |
| Alembic | `alembic/versions/*.py` | `def downgrade` in the same file |
| Flyway | `sql/V{n}__*.sql` | `sql/U{n}__*.sql` |
| Atlas | `migrations/*.sql` | `migrations/*.down.sql` |

## Consequences

- Generate emits a safe `CREATE TABLE` revision plus an empty waiver file.
- A later drop without a waiver fails generate and consumer `repave gates`.
- Tooling CLIs (alembic/flyway/atlas) are not required at generate time; the
  gates are in-process SQL/Python scans.
