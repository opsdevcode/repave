# `repave.config.yaml` — `repave.dev/v1`

Published as part of the [v2.0.0 contract freeze](roadmap.md#v200--platform-ga). The
config file gains an explicit **`apiVersion`** so repave can evolve schema lines without
silent breaking changes.

## Required shape (v2 onward)

Add this as the **first key** in every `repave.config.yaml`:

```yaml
apiVersion: repave.dev/v1
```

The canonical example is [`repave.config.yaml.example`](../repave.config.yaml.example).

## Loader behavior

| `apiVersion` | Result |
| --- | --- |
| `repave.dev/v1` | Accepted |
| *(missing)* | **Warning** at load time; file still works for one minor (deprecated) |
| Any other value | **Error** — unsupported apiVersion |

Supported versions are defined in `SUPPORTED_CONFIG_API_VERSIONS` in
[`engine/src/repave_engine/settings.py`](../engine/src/repave_engine/settings.py).

## Migration from unversioned config

1. Copy your existing `repave.config.yaml`.
2. Insert `apiVersion: repave.dev/v1` at the top (before `output:`).
3. Restart the portal/worker or re-run the CLI — confirm the deprecation warning disappears
   from logs.
4. Commit the versioned file to git (ConfigMap source for Helm).

No other keys change for this migration.

## Hosted service mode (`auth.service_mode: true`)

When OIDC service mode is enabled, repave **requires** a unified SQL durability store.
JSONL files (`audit.file`, `fleet.file`, `runs_db`) are **export mirrors only** — not the
system of record.

```yaml
auth:
  service_mode: true

durability:
  database_url: postgresql://repave:secret@postgres:5432/repave
  export_jsonl: false   # recommended in production; SQL is authoritative
  async_generation: true
```

Or set `REPAVE_DATABASE_URL`. Startup fails fast if service mode is on without SQL:

```text
auth.service_mode requires durability.database_url or REPAVE_DATABASE_URL
(JSONL stores are export-only in hosted mode)
```

See [`docs/durability.md`](durability.md) and [`docs/auth-service-mode.md`](auth-service-mode.md).

## JSONL export mirrors

When `database_url` is set:

| Store | SQL table | Optional JSONL mirror |
| --- | --- | --- |
| Async runs | `runs`, `run_events` | — (SQL only) |
| Audit | `audit_events` | `audit.file` when `export_jsonl: true` |
| Fleet | `fleet_events` | `fleet.file` when `export_jsonl: true` |
| DX metrics snapshots | `dx_metrics_snapshots` | `platform_metrics.snapshot_file` when `export_jsonl: true` |
| Platform feedback | `feedback_events` | `platform_metrics.feedback_file` when `export_jsonl: true` |
| OIDC sessions | `sessions` | — |

Platform adoption config (`platform_metrics`) is documented in
[`platform-metrics.md`](platform-metrics.md).

Set `durability.export_jsonl: false` in production when you rely on Postgres backup/restore
([`docs/operations/postgres-backup-restore.md`](operations/postgres-backup-restore.md))
instead of file tailing.

**Local development** (`auth.service_mode: false`) may keep SQLite or JSONL-only paths
without Postgres — see [`docs/durability.md`](durability.md#configuration).

## Helm

Mount the versioned config in the chart ConfigMap. Production overlays:

- [`values-decomposed-day2.yaml`](../deploy/k8s/chart/values-decomposed-day2.yaml) —
  Postgres + worker split
- [`values-day2.yaml`](../deploy/k8s/chart/values-day2.yaml) — monolithic day-2

Set `repave.durability.databaseUrl` and `secrets.sessionSecret` before scaling replicas.

## Related

- [`docs/api-v2.md`](api-v2.md) — HTTP contract freeze
- [`docs/api-v1-migration.md`](api-v1-migration.md) — `/api/v1` sunset
- [`docs/operations/postgres-backup-restore.md`](operations/postgres-backup-restore.md) — DR
