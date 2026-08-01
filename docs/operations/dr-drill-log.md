# Disaster recovery drill log

Record Postgres backup/restore drills here. Procedure:
[`postgres-backup-restore.md`](postgres-backup-restore.md).

| Date (UTC) | Environment | Backup method | RTO measured | RPO assumed | Result | Operator |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-08-01 | Local Docker `postgres:16-alpine` via `make postgres-dr-drill` | `pg_dump -Fc` → drop DB → `pg_restore` | &lt; 5 min (automated script) | N/A (synthetic seed) | **Pass** | repave CI / operator |

## Template (copy for each drill)

```markdown
### YYYY-MM-DD — {staging|production-like}

- **Cluster / host:**
- **Postgres version:**
- **Repave chart / image tag:**
- **Steps:** 1–7 from postgres-backup-restore.md §4
- **Pre-drill row counts:** runs=… audit_events=… fleet_events=…
- **Post-restore row counts:** (must match)
- **API checks:** /health, /readyz, /api/v1/runs, /api/v2/audit/events
- **RTO:** wall-clock from "scale down" to "verified"
- **Issues / follow-ups:**
- **Result:** Pass | Fail
```

## Related

- [`postgres-backup-restore.md`](postgres-backup-restore.md)
- [`crd-conversion-recovery.md`](crd-conversion-recovery.md) — operator conversion drill log lives in release checklists
