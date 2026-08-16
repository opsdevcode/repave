# Durability and async generation

Hosted repave must not block the API event loop on long gate runs.

## Phase 1 — in-process queue

Generation runs on a **thread-pool worker queue** with **SQLite run records** and polling APIs.

```yaml
durability:
  async_generation: true
  max_concurrent_runs: 2
  queue_max_depth: 32
  runs_db: data/runs.sqlite
  require_session_secret: true   # recommended for multi-replica hosted mode
```

Or:

```bash
export REPAVE_ASYNC_GENERATION=1
export REPAVE_RUNS_DB=/var/lib/repave/runs.sqlite
```

## Phase 2 — unified SQL store (audit + fleet + runs + sessions)

When `database_url` is set, **audit**, **fleet**, **async runs**, and **OIDC sessions**
share one database. JSONL paths remain optional **export mirrors** (`export_jsonl: true`,
default).

**Hosted service mode** (`auth.service_mode: true`) requires `database_url`; JSONL is
export-only and must not be the sole store. See [`repave-config-v1.md`](repave-config-v1.md).

With `database_url` configured, the portal stores auth session payloads in the `sessions`
table and keeps only a signed session id in the browser cookie — so multiple portal
replicas share login state without sticky sessions. `REPAVE_SESSION_SECRET` (or
`require_session_secret`) remains required to sign session ids.

```yaml
durability:
  async_generation: true
  database_url: sqlite:///data/repave.sqlite
  export_jsonl: true
```

Hosted PostgreSQL (requires `uv sync --extra postgres` locally; included in published
portal/worker images):

```yaml
durability:
  async_generation: true
  database_url: postgresql://repave:secret@postgres:5432/repave
  export_jsonl: false
```

Environment override: `REPAVE_DATABASE_URL`.

## Phase 3 — external workers (Kubernetes Jobs)

API pods enqueue runs only; workers execute them. Enable with:

```yaml
durability:
  worker_mode: external   # inline (default) | external | kubernetes | job
```

Or `REPAVE_EXTERNAL_WORKERS=1`.

Run a worker locally:

```bash
repave run-worker --repo-root /app --once
```

Kubernetes Job entrypoint (single run):

```bash
repave run-worker --repo-root /app --run-id "$RUN_ID" --once
```

Poll loop for a worker Deployment:

```bash
repave run-worker --repo-root /app --poll-interval 5
```

The Helm chart can set `repave.durability.workerMode: external` and install a worker
Deployment alongside the portal (see [`deploy/k8s/chart/README.md`](../deploy/k8s/chart/README.md)).

## Phase 4 — per-run Kubernetes Jobs

Instead of a long-lived worker Deployment, each enqueued run spawns a **batch Job** that
executes:

```bash
repave run-worker --repo-root /app --run-id "$RUN_ID" --once
```

Enable with:

```yaml
durability:
  worker_mode: job
  execution_mode: worker
  database_url: postgresql://repave:secret@postgres:5432/repave
```

Helm example: [`values-decomposed-job.yaml`](../deploy/k8s/chart/values-decomposed-job.yaml).
The portal ServiceAccount receives RBAC to create Jobs in its namespace (`REPAVE_RUN_JOBS=1`).

Job pods use the gate-toolchain worker image, mount `repave.config.yaml`, and optionally the
corpus initContainer — same as the external worker Deployment. Publish idempotency and run
record snapshots apply unchanged.

**Local dev:** `worker_mode: job` without in-cluster credentials leaves runs queued; use
`repave run-worker --run-id … --once` manually or switch to `inline` / `external`.

## Service decomposition (Phase 0–1)

**Execution mode** splits the API from gate execution:

| Mode | API / portal | Workers |
| --- | --- | --- |
| `inprocess` (default) | Thread pool runs gates (SQLite local dev) | Same process |
| `worker` | Enqueue only — no gate subprocesses | `repave run-worker` or chart worker Deployment |

```yaml
durability:
  async_generation: true
  database_url: postgresql://repave:secret@postgres:5432/repave
  execution_mode: worker      # API pods
  worker_mode: external       # chart worker Deployment
```

Environment: `REPAVE_EXECUTION_MODE=worker`, `REPAVE_EXTERNAL_WORKERS=1`.

When `execution_mode=worker`, the API and portal **do not run gates in-process**. Sync
`POST /api/v1/generate` and `POST /api/v2/generate` return **409** unless `"async": true`;
use `POST /api/v1/runs` or Backstage `/run-console` (async is automatic in worker
mode). Bundle generation uses the same async queue as blueprint runs.

See [ADR 002](adr/002-v2-service-decomposition.md).

**Container images (Phase 0–2):** CI publishes digest-pinned images on `main` and semver tags:

- `ghcr.io/opsdevcode/repave-engine` — gate toolchain (`INSTALL_GATE_TOOLCHAIN=1`, no embedded corpus)
- `ghcr.io/opsdevcode/repave-engine-portal` — portal/API without gate CLIs or embedded corpus
- `ghcr.io/opsdevcode/repave-corpus` — generation corpus (`blueprints/`, `standards/`, `policy/`, `schemas/`)
- `ghcr.io/opsdevcode/repave-backstage` — hosted Backstage IDP (yarn bundle, then Docker)

**Phase 2 decomposition:** mount the corpus image read-only via chart `corpus.enabled`. Async run
previews rehydrate from **bounded `rendered_files` snapshots in `result_json`** (Postgres/SQLite)
so portal and worker pods need no shared filesystem — see
[ADR 002 addendum](adr/002-addendum-run-artifact-rehydrate.md). Optional S3-compatible storage
(`durability.artifact_store_uri`) retains the full staging tree when configured. Examples:
[`values-decomposed.yaml`](../deploy/k8s/chart/values-decomposed.yaml) and the recommended
production overlay [`values-decomposed-day2.yaml`](../deploy/k8s/chart/values-decomposed-day2.yaml).

See [ADR 002](adr/002-v2-service-decomposition.md) and `.github/workflows/container.yml`.

## Multi-replica Helm (day-2)

Before `autoscaling.enabled` or `replicaCount` > 1, set `repave.durability.databaseUrl`
(PostgreSQL recommended) and `secrets.sessionSecret`. The chart
[`values-day2.yaml`](../deploy/k8s/chart/values-day2.yaml) overlay enables HPA, optional
Prometheus Operator monitoring, and stricter readiness checks. Runbooks:
[`docs/operations/README.md`](operations/README.md).

## Backup and disaster recovery (PostgreSQL)

When using PostgreSQL for hosted mode, back up the unified SQL store on a schedule and
practice restore in non-production. Targets: **RPO ≤ 1 hour**, **RTO ≤ 4 hours** (see
[postgres-backup-restore.md](operations/postgres-backup-restore.md)).

- Logical backup: `pg_dump -Fc` against `REPAVE_DATABASE_URL`
- Automated drill: `make postgres-dr-drill`
- Record drills in [`docs/operations/dr-drill-log.md`](operations/dr-drill-log.md)

JSONL export mirrors are optional; they do not replace database backup for recovery.

**When the state store is enabled**, these targets are no longer sufficient. Runs and audit
records can be regenerated; Terraform state cannot. Tighten to continuous archiving with
point-in-time recovery, and rehearse the restore — see
[`docs/state-graph.md`](state-graph.md#operational-obligations). Byte-exact
`repave-tf state export` is the last-resort escape hatch, not the backup strategy.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/runs` | Enqueue a generation (202 + `run_id`) |
| `GET` | `/api/v1/runs/{run_id}` | Poll status; `result` when `succeeded` |
| `GET` | `/api/v1/runs?status=queued&limit=50` | List recent runs (optional status filter) |
| `POST` | `/api/v1/runs/{run_id}/replay` | Requeue `failed` / `dead_letter` runs (admin) |
| `POST` | `/api/v1/generate` | Pass `"async": true` when durability is enabled |

Portal: **`/runs`** lists recent async jobs with status filter and admin replay for
dead-letter rows; **`/runs/{id}`** is the live run console. Backstage `/runs` calls
the same `POST /api/v2/runs/{id}/replay` for failed and dead-letter rows.

**Idempotency:** `client_request_id` or `Idempotency-Key` header dedupes run enqueue.
Publish idempotency extends through GitHub publish: when a worker retries the same gated
output for the same target repository, the engine reuses the stored `pr_message` from
`publish_receipts` (keyed by `github:{owner}/{repo}:{content_hash}`) instead of pushing
again.

**Metrics:** `repave_run_queue_inflight`, `repave_async_runs_total`.

**Retry and reclaim:** infrastructure failures retry with exponential backoff before
`dead_letter`. Stale `running` rows (worker loss) are reclaimed automatically.
Tune with `max_run_attempts`, `run_stale_seconds`, and `run_retry_base_seconds` in
`repave.config.yaml`, or `REPAVE_RUN_MAX_ATTEMPTS`, `REPAVE_RUN_STALE_SECONDS`, and
`REPAVE_RUN_RETRY_BASE_SECONDS`.

See [roadmap — durability](roadmap-archive.md#durability-and-concurrency-for-hosted-use).
