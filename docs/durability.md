# Durability and async generation (Phase 1)

Hosted repave must not block the API event loop on long gate runs. Phase 1 moves
generation to a **thread-pool worker queue** with **SQLite run records** and polling APIs.

## Enable

```yaml
# repave.config.yaml
durability:
  async_generation: true
  max_concurrent_runs: 2
  queue_max_depth: 32
  runs_db: data/runs.sqlite
  require_session_secret: true   # recommended for multi-replica hosted mode
```

Or for a quick trial:

```bash
export REPAVE_ASYNC_GENERATION=1
export REPAVE_RUNS_DB=/var/lib/repave/runs.sqlite
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/runs` | Enqueue a generation (202 + `run_id`) |
| `GET` | `/api/v1/runs/{run_id}` | Poll status; `result` when `succeeded` |
| `POST` | `/api/v1/runs/{run_id}/replay` | Requeue `failed` / `dead_letter` runs (admin) |
| `POST` | `/api/v1/generate` | Pass `"async": true` when durability is enabled |

**Idempotency:** send `client_request_id` in the JSON body or `Idempotency-Key` header; duplicates return the existing run.

**Metrics:** `repave_run_queue_inflight`, `repave_async_runs_total`.

## Roadmap

Phase 2 will move audit and fleet sinks to the same SQL store; Phase 3 adds Kubernetes Job workers. See [roadmap — durability](roadmap.md#durability-and-concurrency-for-hosted-use).
