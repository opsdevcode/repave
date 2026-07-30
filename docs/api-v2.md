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
| `POST` | `/api/v2/upgrades/plan` | `{ "target_repo" \| "repo_url", "blueprint"?, "staging_root"? }` |
| `POST` | `/api/v2/upgrades/apply` | `{ "target_repo" \| "repo_url", "git_branch", "commit_message", "blueprint"?, "preserve_local"?, "push"?, "staging_root"? }` |

When `repo_url` is set (or `target_repo` is an `http(s)` URL), the API shallow-clones the
repository server-side. For apply, `"push": true` pushes the branch with `GITHUB_TOKEN`
after commit (used by the operator in HTTP mode).

Response shapes match the CLI JSON documents (`UpgradePlanResult`, `ApplyUpgradeResult`).
Apply responses may include `"pushed": true` when the branch was pushed remotely.

## Operator (Phase 3b–3c)

Set `REPAVE_API_URL` on the operator Deployment (for example `http://repave-portal:8088`).
When set, plan/apply call `/api/v2/upgrades/*` instead of exec'ing the CLI. Remote
`spec.repoURL` repos use `repo_url` so the API clones server-side; optional
`REPAVE_API_TOKEN` is sent as a Bearer token when service auth is enabled.

`make operator-e2e` deploys the slim distroless operator plus an in-cluster portal
(`operator/config/e2e/portal.yaml`) with the same `/modules` hostPath as the operator
so plan-upgrade can read `spec.localPath` targets.

CLI mode remains the default when `REPAVE_API_URL` is unset (`REPAVE_REPO_ROOT` +
`REPAVE_CLI`).

## Authentication

When `auth.service_enabled` is true, v2 routes use the same session roles as v1.
Unauthenticated `/api/v2/*` requests receive `401` JSON.

## Follow-ups

- Mirror remaining v1 read models (fleet, audit, catalog) under v2
- Published `/api/v1` deprecation timeline
- Service-to-service auth beyond optional `REPAVE_API_TOKEN` Bearer header
