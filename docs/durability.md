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

## Phase 2 — unified SQL store (audit + fleet + runs)

When `database_url` is set, **audit**, **fleet**, and **async runs** share one database.
JSONL paths remain optional **export mirrors** (`export_jsonl: true`, default).

```yaml
durability:
  async_generation: true
  database_url: sqlite:///data/repave.sqlite
  export_jsonl: true
```

Hosted PostgreSQL (requires `uv sync --extra postgres` in the engine image):

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

With **PostgreSQL**, run claims use `FOR UPDATE SKIP LOCKED` so multiple worker replicas
can scale safely.

**Container images (Phase 0–2):** CI publishes digest-pinned images on `main` and semver tags:

- `ghcr.io/opsdevcode/repave-engine` — gate toolchain (`INSTALL_GATE_TOOLCHAIN=1`, no embedded corpus)
- `ghcr.io/opsdevcode/repave-engine-portal` — portal/API without gate CLIs or embedded corpus
- `ghcr.io/opsdevcode/repave-corpus` — generation corpus (`blueprints/`, `standards/`, `policy/`, `schemas/`)

**Phase 2 decomposition:** mount the corpus image read-only via chart `corpus.enabled`; store async
run artifacts in S3-compatible object storage (`durability.artifact_store_uri` or
`REPAVE_ARTIFACT_STORE_URI`) so portal and worker pods need no shared filesystem. Example:
[`values-decomposed.yaml`](../deploy/k8s/chart/values-decomposed.yaml).

See [ADR 002](adr/002-v2-service-decomposition.md) and `.github/workflows/container.yml`.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/runs` | Enqueue a generation (202 + `run_id`) |
| `GET` | `/api/v1/runs/{run_id}` | Poll status; `result` when `succeeded` |
| `POST` | `/api/v1/runs/{run_id}/replay` | Requeue `failed` / `dead_letter` runs (admin) |
| `POST` | `/api/v1/generate` | Pass `"async": true` when durability is enabled |

**Idempotency:** `client_request_id` or `Idempotency-Key` header.

**Metrics:** `repave_run_queue_inflight`, `repave_async_runs_total`.

See [roadmap — durability](roadmap.md#durability-and-concurrency-for-hosted-use).
