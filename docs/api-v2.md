# API v2

Stable JSON HTTP surface introduced for [service decomposition Phase 3](adr/002-v2-service-decomposition.md).
`/api/v1` remains available; v2 is the contract freeze target for v2.0.0.

## Metadata

`GET /api/v2` returns the engine version and the supported endpoint list.

## Generation and runs

| Method | Path | Role | Notes |
| --- | --- | --- | --- |
| `POST` | `/api/v2/generate` | generator, admin | Sync by default; pass `"async": true` to enqueue |
| `POST` | `/api/v2/runs` | generator, admin | Async generation or `kind: live_plan` (202 + run record) |
| `GET` | `/api/v2/runs` | viewer+ | List recent runs (`status`, `limit` query params) |
| `GET` | `/api/v2/runs/{run_id}` | viewer+ | Poll run status |
| `GET` | `/api/v2/runs/{run_id}/events` | viewer+ | SSE progress stream |
| `POST` | `/api/v2/runs/{run_id}/replay` | admin | Requeue failed/dead-letter runs |

Async runs require `durability.async_generation` (or `REPAVE_ASYNC_GENERATION=1`).

### Live plan (`kind: live_plan`)

When `live_plan.enabled` (or `REPAVE_LIVE_PLAN=1`) and an environment is configured for the
entity, enqueue a worker-only terraform plan against live state:

```json
{
  "kind": "live_plan",
  "entity_id": "github.com/acme/tf-app",
  "pull_request_url": "https://github.com/acme/tf-app/pull/42"
}
```

Optional overrides: `target`, `secret_name`. To attach the summary to a GitHub pull
request body, include either `pull_request_url` or a `pull_request` object
(`owner`, `repo`, `number`). Requires `GITHUB_TOKEN` with permission to edit the PR.

The run result includes resource add/change/destroy counts and the OPA verdict
(`gates_outcome`); when a PR was requested, `pr_attachment` reports whether the body
was updated. Plan JSON is never retained. Portal:
`POST /services/{entity_id}/live-plan` redirects to the run console. See
[ADR 003](adr/003-environment-lifecycle-and-live-state.md).

### Environment vending (`kind: environment_vend`)

When `environment_vending.enabled` (or `REPAVE_ENVIRONMENT_VENDING=1`), render a governed
`terraform-environment-stack` and open a pull request on a GitOps repository:

```json
{
  "kind": "environment_vend",
  "dry_run": false,
  "inputs": {
    "stack_name": "sandbox-alice",
    "description": "Ephemeral platform sandbox",
    "cloud_provider": "aws",
    "environment": "dev"
  },
  "owner": "team-platform",
  "class": "sandbox"
}
```

Configure defaults under `environment_vending` (`gitops_repo`, `base_branch`, `path_prefix`).
Optional overrides: `blueprint`, `gitops_repo`, `gitops_path`, `base_branch`, `git_branch`,
`owner`, `class`, `dry_run`. Set `"dry_run": true` to evaluate gates without opening a PR.
Requires `GITHUB_TOKEN` with push access to the GitOps repo when `dry_run` is false.

The run result includes `gates_outcome`, `gitops_path`, and when not dry-run
`pull_request_url` / `pull_request_number`. repave does not run `terraform apply`. See
[ADR 003](adr/003-environment-lifecycle-and-live-state.md).

Portal: on a library entity detail page (`/services/{entity_id}`), **Request environment**
submits the same payload via `POST /services/{entity_id}/request-environment` (preview gates
or open GitOps PR). Run progress uses `/runs/{run_id}`; the result page is
`/runs/{run_id}/result`.

When a non–dry-run vend succeeds, repave appends an **environment registry** record
(`environment_vending.file`, default `data/environments/registry.jsonl`). Vended environments
appear in `GET /api/v2/catalog/entities` with `"source": "environment"` and an
`environment` object (GitOps path, TTL, status, vend run id). Optional
`default_ttl_hours` and `ttl_hours_by_class` set `expires_at` on registration.

### Environment TTL reclaim

When environments expire, **sandbox-class** stacks listed in
`environment_vending.auto_reclaim_classes` (default `["sandbox"]`) can be reclaimed by
opening a GitOps decommission pull request that removes the stack path. repave does not run
`terraform apply`.

CLI:

```bash
repave environments reclaim --dry-run
repave environments reclaim --stack sandbox-alice
```

API (`admin` role):

```json
POST /api/v2/environments/reclaim
{ "dry_run": false, "stack_name": "sandbox-alice" }
```

Response: `{ "count", "reclaimed", "decommission_review", "skipped", "results": [...] }`
with per-stack `mode` (`auto_reclaim` or `decommission_review`), `draft`, and
`pull_request_url` when a PR was opened. After sandbox auto-reclaim (or when the GitOps path
is already absent), the environment is removed from the registry. Non-sandbox classes open a
**draft** decommission PR and remain in the catalog with `status: expired` until merge.

Configure `decommission_review_classes` explicitly (for example `prod`, `staging`); when
omitted, every expired class **not** listed in `auto_reclaim_classes` uses the review path.

**Helm:** enable `environmentReclaim.cronJob` with `repave.environmentVending` — see
[`deploy/k8s/chart/values-environment-vending.yaml`](../../deploy/k8s/chart/values-environment-vending.yaml)
and [`deploy/k8s/chart/README.md`](../../deploy/k8s/chart/README.md#environment-vending-and-ttl-reclaim).

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
| `POST` | `/api/v2/environments/reclaim` | admin | Reclaim expired sandbox environments |

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
