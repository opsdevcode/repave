# PostgreSQL durable store — backup and restore

Use this runbook for the **hosted SQL durability store** when `repave.durability.databaseUrl`
(or `REPAVE_DATABASE_URL`) points at PostgreSQL. It covers logical backup/restore, verification,
and periodic drills.

Automated baseline: `make postgres-dr-drill` runs a local backup → wipe → restore roundtrip
via [`deploy/k8s/hack/postgres-dr-drill.sh`](../../deploy/k8s/hack/postgres-dr-drill.sh).

## Scope

| In Postgres (back up) | Out of scope (re-deploy or separate backup) |
| --- | --- |
| Async runs (`runs`, `run_events`) | Blueprints, standards, `repave.config.yaml` (git) |
| Audit log (`audit_events`) | Generated target repositories (GitHub) |
| Fleet registry events (`fleet_events`) | Corpus / portal / worker container images |
| Publish idempotency (`publish_receipts`) | Optional object storage (`artifact_store_uri`) |
| OIDC sessions (`sessions`) | Kubernetes Secrets (session secret, GitHub creds) |

Generated repos are unaffected by Postgres loss. Recovery restores **operational history**
(audit, fleet, run queue state, sessions) so the portal and operator resume with continuity.

Schema is created automatically on startup (`ensure_schema` in `sql_store.py`); restores should
target an empty database or one you intend to overwrite.

## Recovery objectives (v2 Platform GA)

| Objective | Target | Notes |
| --- | --- | --- |
| **RPO** (max acceptable data loss) | **≤ 1 hour** | Hourly logical backup or managed PITR; tighten for stricter compliance |
| **RTO** (time to restore service) | **≤ 4 hours** | Restore DB, redeploy repave with same `databaseUrl`, verify APIs |

These are **hours, not days** — see [roadmap — resilience](../roadmap.md#resilience-and-disaster-recovery).
Multi-region active/passive failover is a follow-on; this runbook covers single-region backup/restore.

**These targets do not apply when the state store is enabled.** Runs, audit records, and
sessions can be regenerated from the repositories repave governs; Terraform state cannot be
regenerated from anything. An hour of lost state is an hour of infrastructure repave can no
longer manage. Enabling the store requires continuous archiving with point-in-time recovery
and a rehearsed, timed restore before any team stores real state — see
[`docs/state-graph.md`](../state-graph.md#operational-obligations) and
[ADR 004](../adr/004-state-custody-and-the-resource-graph.md).

## Prerequisites

- `pg_dump`, `pg_restore`, and `psql` (client tools matching Postgres 14+)
- Network access to the production or staging database (VPN / private link)
- Helm values or Secret containing the current `databaseUrl` (for repoint after restore)
- Non-production cluster or Docker for drills

Chart fixtures: [`deploy/k8s/hack/postgres-kind.yaml`](../../deploy/k8s/hack/postgres-kind.yaml)
(user/db `repave`) used by `make chart-smoke-decomposed`.

## 1. Backup (logical)

Prefer **custom-format** dumps for parallel restore and selective table recovery.

```bash
export REPAVE_DATABASE_URL='postgresql://repave:SECRET@postgres.example.com:5432/repave'
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
pg_dump -Fc "${REPAVE_DATABASE_URL}" -f "repave-${STAMP}.dump"
```

**Schedule:** at least hourly in production (cron, Kubernetes CronJob, or managed backup).
Retain 7–30 days per your retention policy. Store dumps off-cluster (object storage with
encryption and access logging).

**Managed Postgres:** enable automated backups and point-in-time recovery (RDS, Cloud SQL,
Azure Database for PostgreSQL). Treat vendor snapshots as primary; keep a periodic `pg_dump`
for portability and drill validation.

**What not to rely on alone:** PVC volume snapshots without a logical dump — they work for
disaster recovery but are harder to validate and migrate across Postgres versions.

## 2. Restore

Perform restores in a **maintenance window**. Scale repave portal/worker Deployments to zero
(or pause traffic at the ingress) so no writes race the restore.

```bash
export REPAVE_DATABASE_URL='postgresql://repave:SECRET@postgres.example.com:5432/repave'
# Admin connection to the postgres maintenance database
ADMIN_URL="${REPAVE_DATABASE_URL%/*}/postgres"

# Terminate active connections
psql "${ADMIN_URL}" -c "
  SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
  WHERE datname = 'repave' AND pid <> pg_backend_pid();"

psql "${ADMIN_URL}" -c 'DROP DATABASE IF EXISTS repave;'
psql "${ADMIN_URL}" -c 'CREATE DATABASE repave OWNER repave;'

pg_restore -d "${REPAVE_DATABASE_URL}" --no-owner --role=repave repave-YYYYMMDDTHHMMSSZ.dump
```

If `pg_restore` reports benign errors (extension or ACL warnings), confirm row counts below
before bringing repave back.

**New host:** create the database and role first, restore into the new instance, then update
Helm `repave.durability.databaseUrl` (or `REPAVE_DATABASE_URL` Secret) and roll out:

```bash
helm upgrade repave deploy/k8s/chart -f values-decomposed-day2.yaml --wait
kubectl -n repave rollout status deployment/repave-portal
kubectl -n repave rollout status deployment/repave-worker
```

## 3. Post-restore verification

### Row counts

```bash
psql "${REPAVE_DATABASE_URL}" -c "
  SELECT 'runs' AS tbl, COUNT(*) FROM runs
  UNION ALL SELECT 'run_events', COUNT(*) FROM run_events
  UNION ALL SELECT 'audit_events', COUNT(*) FROM audit_events
  UNION ALL SELECT 'fleet_events', COUNT(*) FROM fleet_events
  UNION ALL SELECT 'publish_receipts', COUNT(*) FROM publish_receipts
  UNION ALL SELECT 'sessions', COUNT(*) FROM sessions;"
```

Compare to pre-incident metrics or the latest backup manifest.

### API smoke

With repave running against the restored database:

```bash
curl -sf "https://repave.example.com/health"
curl -sf "https://repave.example.com/readyz" | jq .
curl -sf "https://repave.example.com/api/v1/runs?limit=5" | jq '.runs | length'
curl -sf "https://repave.example.com/api/v2/audit/events?limit=5" | jq '.events | length'
```

Sign in via OIDC (if enabled) and confirm an existing session is invalidated or restored as
expected — sessions in the backup may be stale; users can re-authenticate.

### Portal

- Open **`/runs`** — recent async jobs appear with correct status.
- Open **`/fleet`** — fleet rows and drift state match pre-outage expectations.
- Replay a **dead_letter** run only after confirming workers are healthy.

## 4. Drill (non-production)

Run quarterly (or before major upgrades) in staging or locally.

1. Deploy repave with Postgres (`make chart-smoke-decomposed` or your staging overlay).
2. Create representative data: enqueue a dry-run async run, sign in once, trigger a fleet sync
   if operator is attached.
3. Record row counts and latest `run_id` / audit event id.
4. Take a `pg_dump -Fc` backup.
5. Drop and recreate the `repave` database (step 2 above).
6. `pg_restore` from the dump.
7. Repeat verification (step 3). Row counts and the sample `run_id` must match.
8. Log the drill in [`dr-drill-log.md`](dr-drill-log.md).

**Fast local path:**

```bash
make postgres-dr-drill
```

## 5. Break-glass (no backup)

If no backup exists, repave still starts on an empty database (`ensure_schema`). You lose
audit/fleet/run history but can regenerate from git and GitHub. Document the incident, re-sync
fleet inventory from operator `GoldenPathRepo` objects, and accept loss of in-flight async runs.

## Related

- [`docs/durability.md`](../durability.md) — what lives in the SQL store
- [`docs/operations/README.md`](README.md) — day-2 runbooks and SLOs
- [`docs/operations/dr-drill-log.md`](dr-drill-log.md) — recorded drill history
- [`docs/operations/crd-conversion-recovery.md`](crd-conversion-recovery.md) — operator CRD drill
- [`docs/operations/upgrade-and-rollback.md`](upgrade-and-rollback.md) — Helm rollout after restore
