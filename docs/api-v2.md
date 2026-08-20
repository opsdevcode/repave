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
| `GET` | `/api/v2/runs/{run_id}` | viewer+ | Poll run status (Backstage `/run-console`) |
| `GET` | `/api/v2/runs/{run_id}/events` | viewer+ | SSE progress stream |
| `POST` | `/api/v2/runs/{run_id}/replay` | admin | Requeue failed/dead-letter runs (Backstage `/runs` and `/run-console`) |

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
`POST /services/{entity_id}/live-plan` redirects to the run console. Backstage
`/services` posts the same `{ kind: "live_plan", entity_id }` body to
`POST /api/v2/runs`. See
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

Named deployment sets (Backstage `/sandbox`) use the same payload
builder:

| Method | Path | Role | Notes |
| --- | --- | --- | --- |
| `GET` | `/api/v2/deployment-sets` | viewer+ | Lists sets + workload profiles; `vend_available` is true when async runs and `environment_vending` are on |
| `POST` | `/api/v2/environments/vend` | generator, admin | `{ "deployment_set", "stack_name", "owner"?, "dry_run"? }` → 202 run (`kind: environment_vend`) |

`stack_name` must be 3–63 lowercase letters, numbers, and hyphens. `dry_run` defaults
to `true` (plan only, no GitOps PR).

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

Response: `{ "count", "reclaimed", "decommission_review", "finalized", "skipped", "results": [...] }`
with per-stack `mode` (`auto_reclaim`, `decommission_review`, or `registry_finalize`), `draft`,
and `pull_request_url` when a PR was opened. After sandbox auto-reclaim (or when the GitOps path
is already absent), the environment is removed from the registry. Non-sandbox classes open a
**draft** decommission PR and remain in the catalog with `status: expired` until merge; each
reclaim pass also checks merged decommission PRs and removes finalized environments from the
registry (`mode: registry_finalize`, `finalized` count in the summary).

Configure `decommission_review_classes` explicitly (for example `prod`, `staging`); when
omitted, every expired class **not** listed in `auto_reclaim_classes` uses the review path.

**Helm:** enable `environmentReclaim.cronJob` with `repave.environmentVending` — see
[`deploy/k8s/chart/values-environment-vending.yaml`](../../deploy/k8s/chart/values-environment-vending.yaml)
and [`deploy/k8s/chart/README.md`](../../deploy/k8s/chart/README.md#environment-vending-and-ttl-reclaim).

### Component vending (`kind: component_vend`)

When `component_vending.enabled` (or `REPAVE_COMPONENT_VENDING=1`), request a managed
`database`, `bucket`, or `queue` through the same GitOps PR flow as environment
vending. repave does not run `terraform apply`. See
[ADR 013](adr/013-component-self-service-vending.md).

`gitops_repo` falls back to `environment_vending.gitops_repo` when omitted.
Default path: `{path_prefix}/{kind}/{name}` (`path_prefix` defaults to `components`).
Built-in kinds render `terraform-component-database`, `terraform-component-bucket`,
and `terraform-component-queue` (same GitOps composition as
`terraform-environment-stack`, with an RDS/S3/SQS-shaped stub module).

| Method | Path | Role | Notes |
| --- | --- | --- | --- |
| `GET` | `/api/v2/component-kinds` | viewer+ | Built-in kinds plus optional `component_vending.kinds` YAML; `vend_available` when async runs and vending are on (Backstage `/vend`) |
| `POST` | `/api/v2/components/vend` | generator, admin | `{ "kind": "database"\|"bucket"\|"queue", "name", "owner"?, "dry_run"? }` → 202 run (`kind: component_vend`; Backstage `/vend`) |
| `POST` | `/api/v2/components/reclaim` | admin | `{ "name"?, "kind"?, "dry_run"? }` — expire managed components via GitOps decommission PRs (Backstage `/reclaim`) |

`name` on vend must be 3–63 lowercase letters, numbers, and hyphens. Vend
`dry_run` defaults to `true`. A successful non–dry-run vend appends
`data/components/registry.jsonl` and the catalog entity uses
`"source": "component"`. Reclaim `dry_run` defaults to `false` when omitted
(same as environment reclaim); pass `"dry_run": true` to preview.

Set `component_vending.default_ttl_hours` or `ttl_hours_by_kind` so vended
rows get `expires_at`. `auto_reclaim_kinds` defaults to `database` / `bucket` /
`queue`. Other observed kinds open a **draft** decommission PR and stay in the
catalog as `status: expired` until merge (`mode: registry_finalize`).

CLI:

```bash
repave components reclaim --dry-run
repave components reclaim --name checkout-db --kind database
```

This is not `POST /api/v2/components/plan` (`repave add` onto an existing repo)
and not `POST /api/v2/environments/reclaim`.

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

## Component add (multi-blueprint repos)

Layer a second golden path onto a governed repository ([`docs/add.md`](add.md)):

| Method | Path | Role | Body |
| --- | --- | --- | --- |
| `POST` | `/api/v2/components/plan` | generator, admin | `{ "target_repo", "blueprint", "component_id"?, "inputs"?, "force"? }` (Backstage `/add`) |
| `POST` | `/api/v2/components/apply` | generator, admin | same; optional `"git_branch"` (Backstage `/add`) |

Plan returns file lists and conflicts; apply commits on a local checkout and records a
`component_add` audit event. HTTP `409` when the repo is not governed or conflicts remain.

## Operator (Phase 3b–3c)

Set `REPAVE_API_URL` on the operator Deployment (for example `http://repave-portal:8088`).
When set, plan/apply call `/api/v2/upgrades/*` instead of exec'ing the CLI. Remote
`spec.repoURL` repos use `repo_url` so the API clones server-side. Set `REPAVE_API_TOKEN`
(or chart `secrets.apiToken`) to the same value as the portal's configured `auth.api_token`
when `auth.service_mode` is enabled.

`make operator-e2e` deploys the slim distroless operator plus an in-cluster portal
(`operator/config/e2e/portal.yaml`) with the same `/modules` hostPath as the operator
so plan-upgrade can read `spec.localPath` targets.

CLI mode remains the default when `REPAVE_API_URL` is unset (`REPAVE_REPO_ROOT` +
`REPAVE_CLI`).

## Authentication

When `auth.service_enabled` is true, v2 routes use the same session roles as v1.
Unauthenticated `/api/v2/*` requests receive `401` JSON.

Service callers (operator HTTP mode, environment reclaim CronJob with `invoke: http`) may
authenticate with `Authorization: Bearer <token>` when `REPAVE_API_TOKEN` or
`auth.api_token` is configured. Valid tokens receive the **admin** role for API authorization.

## Read models (v2.0.0 contract freeze)

| Method | Path | Role | Notes |
| --- | --- | --- | --- |
| `POST` | `/api/v2/verify` | viewer+ | Same body/response as `/api/v1/verify` (Backstage `/verify`; 422 = failed verify) |
| `GET` | `/api/v2/catalog/entities` | viewer+ | Service catalog entities (`?team=`, `?owner=`; maturity when `service_catalog` on; Backstage `/teams`) |
| `GET` | `/api/v2/catalog/entities/{entity_id}` | viewer+ | Entity detail + cost/deployment/maturity/initiatives enrichments (Backstage `/services`) |
| `GET` | `/api/v2/catalog/blueprints` | viewer+ | Family-grouped blueprint catalog plus input schemas (Backstage `/generate`) |
| `POST` | `/api/v2/assistant/resolve` | generator+ | Intent → matches, citations, optional draft/synthesis/gated files; read-only fleet/drift/audit when the role can already see those APIs |
| `GET` | `/api/v2/bundles` | viewer+ | Golden-path bundle list (Backstage `/bundles`) |
| `GET` | `/api/v2/bundles/{name}` | viewer+ | Bundle members + topology (Backstage `/bundles`) |
| `GET` | `/api/v2/library` | viewer+ | Grouped artifact library (`?family=`, `?owner=`; Backstage `/library`) |
| `GET` | `/api/v2/audit` | viewer+ | Query audit history (Backstage `/activity`) |
| `GET` | `/api/v2/fleet` | viewer+ | Fleet registry rows (Backstage `/fleet`) |
| `GET` | `/api/v2/estate` | viewer+ | Estate map tiles (Backstage `/estate`; fleet freshness + audit sparklines) |
| `GET` | `/api/v2/governance/annotations/{blueprint_name}` | viewer+ | Governance preflight annotation previews |
| `GET` | `/api/v2/github/teams` | viewer+ | Org teams for `github-repo-generic` (requires GitHub credentials) |
| `POST` | `/api/v2/github/org-scan` | generator, admin | Classify org repos (Backstage `/import/batch`; engine GitHub token) |
| `POST` | `/api/v2/fleet` | admin | Register a repository |
| `DELETE` | `/api/v2/fleet` | admin | Unregister (`repo_url` query param) |
| `POST` | `/api/v2/imports/plan` | generator, admin | Single-repo import preview (Backstage `/import`) |
| `POST` | `/api/v2/imports/apply` | generator, admin | Open import PR (engine GitHub token) |
| `POST` | `/api/v2/imports/batch/plan` | generator, admin | Batch preview (Backstage `/import/batch`) |
| `POST` | `/api/v2/imports/batch/apply` | generator, admin | Open batch import PRs (engine GitHub token) |
| `GET` | `/api/v2/deployment-sets` | viewer+ | Named sandbox / lab deployment sets |
| `POST` | `/api/v2/environments/vend` | generator, admin | Request a sandbox from a deployment set |
| `GET` | `/api/v2/component-kinds` | viewer+ | Built-in kinds (Backstage `/vend`) |
| `POST` | `/api/v2/components/vend` | generator, admin | Request a managed component (Backstage `/vend`) |
| `POST` | `/api/v2/components/reclaim` | admin | Reclaim expired managed components (Backstage `/reclaim`) |
| `POST` | `/api/v2/environments/reclaim` | admin | Reclaim expired sandboxes (Backstage `/reclaim`) |
| `GET` | `/api/v2/platform/metrics` | admin | Golden-path adoption (Backstage `/adoption`; `?persist=1`, `?history=N`) — see [`platform-metrics.md`](platform-metrics.md) |
| `GET` | `/api/v2/platform/maturity` | admin | Fleet maturity (Backstage `/maturity`) — see [`service-catalog.md`](service-catalog.md) |
| `GET` | `/api/v2/platform/initiatives` | admin | Initiative progress (Backstage `/maturity`; + inactive list) |
| `POST` | `/api/v2/platform/initiatives` | admin | Create initiative (`title` required; Backstage `/maturity`) |
| `PATCH` | `/api/v2/platform/initiatives/{id}` | admin | Partial update (title, targets, `active`, …; Backstage `/maturity`) |
| `DELETE` | `/api/v2/platform/initiatives/{id}` | admin | Soft-deactivate (`active: false`; Backstage `/maturity`) |
| `GET` | `/api/v2/platform/compliance` | admin | Gate pass rate + bypasses (Backstage `/compliance`) |
| `GET` | `/api/v2/platform/value-stream` | admin | Adoption history (Backstage `/value-stream`) |
| `GET` | `/api/v2/platform/roadmap-evidence` | admin | Theme adoption + sunset candidates (Backstage `/roadmap`) |
| `GET` | `/api/v2/platform/feedback` | admin | CSAT rollup (Backstage `/feedback`) |
| `POST` | `/api/v2/platform/feedback` | generator, admin | CSAT event (`surface=backstage` from Backstage `/feedback`) |
| `GET` | `/api/v2/platform/finops/export` | admin | Chargeback JSON/CSV (Backstage `/finops`) |
| `GET` | `/api/v2/platform/ops` | admin | Readiness, doctor, queue, dead-letter (Backstage `/ops`) |
| `GET` | `/api/v2/platform/standards` | admin | Fleet pin drift (Backstage `/standards`) |
| `GET` | `/api/v2/platform/campaigns` | admin | Operator campaigns (Backstage `/campaigns`) |
| `POST` | `/api/v2/platform/campaigns/{ns}/{name}/paused` | admin | Pause or resume a campaign |

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

- Conversational governed AI generation (**v3.0.0** — catalog intent resolve shipped
  behind `v3.assistant.enabled`; LLM draft remains open — see
  [roadmap](roadmap.md#conversational-and-governed-ai-generation))
