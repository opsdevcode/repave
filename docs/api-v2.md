# API v2

Stable JSON HTTP surface introduced for [service decomposition Phase 3](adr/002-v2-service-decomposition.md).
`/api/v1` remains available; v2 is the contract freeze target for v2.0.0.

## Metadata

`GET /api/v2` returns the engine version and the supported endpoint list.

## Generation and runs

| Method | Path | Role | Notes |
| --- | --- | --- | --- |
| `POST` | `/api/v2/generate` | generator, admin | Sync by default; pass `"async": true` to enqueue |
| `POST` | `/api/v2/runs` | generator, admin | Async generation (202 + run record) |
| `GET` | `/api/v2/runs/{run_id}` | viewer+ | Poll run status |
| `GET` | `/api/v2/runs/{run_id}/events` | viewer+ | SSE progress stream |
| `POST` | `/api/v2/runs/{run_id}/replay` | admin | Requeue failed/dead-letter runs |

Async runs require `durability.async_generation` (or `REPAVE_ASYNC_GENERATION=1`).

## Operator upgrades

These endpoints mirror `repave plan-upgrade` / `apply-upgrade --format json` so the
operator can call HTTP instead of exec'ing the CLI.

| Method | Path | Body |
| --- | --- | --- |
| `POST` | `/api/v2/upgrades/plan` | `{ "target_repo", "blueprint"?, "staging_root"? }` |
| `POST` | `/api/v2/upgrades/apply` | `{ "target_repo", "git_branch", "commit_message", "blueprint"?, "preserve_local"?, "staging_root"? }` |

Response shapes match the CLI JSON documents (`UpgradePlanResult`, `ApplyUpgradeResult`).

## Authentication

When `auth.service_enabled` is true, v2 routes use the same session roles as v1.
Unauthenticated `/api/v2/*` requests receive `401` JSON.

## Follow-ups

- Operator `HTTPPlanUpgrader` / `HTTPApplyUpgrader` (Phase 3b)
- Mirror remaining v1 read models (fleet, audit, catalog) under v2
- Published `/api/v1` deprecation timeline
