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
