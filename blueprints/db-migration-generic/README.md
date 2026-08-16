# db-migration-generic

Golden path for **database migrations**: Alembic, Flyway, or Atlas layout,
destructive-DDL policy ([ADR 012](../../docs/adr/012-destructive-ddl-policy.md)),
and a required rollback for every forward revision.

## Example

```bash
cd engine
uv run repave generate \
  --repo-root .. \
  --blueprint db-migration-generic \
  --input service_name=checkout \
  --input organization=platform \
  --input description="Checkout schema migrations" \
  --input tool=alembic \
  --dry-run
```

Generate-time gates are in-process (no alembic/flyway/atlas CLI required).
A later `DROP TABLE` in a forward file fails unless
`waivers/destructive.yaml` names that path with a reason and `expires_at`.
