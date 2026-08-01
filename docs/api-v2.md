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
| `GET` | `/api/v2/runs` | viewer+ | List recent runs (`status`, `limit` query params) |
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

## Read models (v2.0.0 contract freeze)

| Method | Path | Role | Notes |
| --- | --- | --- | --- |
| `POST` | `/api/v2/verify` | viewer+ | Same body/response as `/api/v1/verify` |
| `GET` | `/api/v2/catalog/entities` | viewer+ | Service catalog entities |
| `GET` | `/api/v2/catalog/entities/{entity_id}` | viewer+ | Entity detail + observability/cost/deployment enrichments |
| `GET` | `/api/v2/audit` | viewer+ | Query audit history (same filters as v1) |
| `GET` | `/api/v2/fleet` | viewer+ | Fleet registry rows |
| `POST` | `/api/v2/fleet` | admin | Register a repository |
| `DELETE` | `/api/v2/fleet` | admin | Unregister (`repo_url` query param) |

## `/api/v1` deprecation

`/api/v1` remains available for existing integrations. Responses include:

- `Deprecation: true`
- `Sunset: Sat, 01 Aug 2027 00:00:00 GMT` (planned removal on the v3 line)
- `Link: </docs/api-v2>; rel="successor-version"`

New integrations should use `/api/v2` only. Full migration guide:
[`docs/api-v1-migration.md`](api-v1-migration.md).

## Deployment status (optional)

When `portal.deployment_reader` (or `deployment_status_url`) is set, entity detail includes
`deployment_status` with sync state, health, revision, last-synced time, and a deep link.
Readers: `url` (JSON template), `argocd` (Application API), `flux` (Kustomization/HelmRelease
via the Kubernetes API). Unreachable backends return `sync_status`/`health` of `unknown`
instead of failing the request. See [ADR 003](adr/003-environment-lifecycle-and-live-state.md).

## Configuration

Hosted service mode (`auth.service_mode: true`) requires `durability.database_url`
(or `REPAVE_DATABASE_URL`). JSONL stores are export-only in that mode — see
[`docs/repave-config-v1.md`](repave-config-v1.md).

`repave.config.yaml` accepts `apiVersion: repave.dev/v1`. Unversioned config files
log a deprecation warning at load time. Migration steps:
[`docs/repave-config-v1.md`](repave-config-v1.md).

## Follow-ups

- Service-to-service auth beyond optional `REPAVE_API_TOKEN` Bearer header
- v2 read models for `/api/v1/estate` and `/api/v1/governance/annotations/*`
- Conversational governed AI generation (v2 must-have — see roadmap)
