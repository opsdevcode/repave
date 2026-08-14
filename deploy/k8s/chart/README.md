# repave Helm chart

Install the repave **portal and API** on Kubernetes. Images build from
[`deploy/local/Dockerfile`](../../local/Dockerfile):

| Variant | Build | Helm |
| --- | --- | --- |
| **Gate toolchain** (default) | `docker build -f deploy/local/Dockerfile -t repave-engine:TAG .` | `image.gateToolchain: true` (default) |
| **Portal-only** | `docker build -f deploy/local/Dockerfile --build-arg INSTALL_GATE_TOOLCHAIN=0 --build-arg INCLUDE_CORPUS=0 -t repave-engine-portal:TAG .` | `-f values-portal.yaml` or `image.gateToolchain: false` |
| **Corpus** | `docker build -f deploy/local/Dockerfile.corpus -t repave-corpus:TAG .` | `corpus.enabled: true` (see `values-decomposed.yaml`) |
| **Backstage** (ADR 011) | `docker build -f backstage/packages/backend/Dockerfile -t ghcr.io/opsdevcode/repave-backstage:TAG backstage/` | `repave.backstage.enabled` (**default off**); overlay [`values-backstage.yaml`](values-backstage.yaml) |

The gate-toolchain image includes pinned CLIs for Plan/dry-run. The portal-only image
is smaller and suits catalog/auth-only deployments; dry-run gates report missing tools.
Hosted Backstage is a second Deployment (`:7007`). Chart-smoke does not boot that
image yet — leave the flag off until it does. See [`docs/backstage.md`](../../../docs/backstage.md).

## Prerequisites

- Kubernetes 1.26+
- Helm 3.10+
- An image built and pushed (or loaded into kind) from the monorepo root, **or** install from
  the published OCI chart (semver tags only):

```bash
helm upgrade --install repave oci://ghcr.io/opsdevcode/charts/repave \
  --version 2.15.0 \
  --namespace repave --create-namespace \
  -f deploy/k8s/chart/values-day2.yaml \
  --set repave.output.githubOrg=your-org
```

Chart `version` and `appVersion` both match the engine release tag (for example `2.15.0`), so
unpinned installs pull matching GHCR images. Override with `image.tag` or pin by digest — see
[`values-digest-pinned.yaml`](values-digest-pinned.yaml).

Local build example:

```bash
docker build -f deploy/local/Dockerfile -t ghcr.io/your-org/repave-engine:2.15.0 .
```

## Quick install (dry-run only)

Dry-run generation does not need `GITHUB_TOKEN` or GitHub App credentials. For publish on
hosted clusters, use a PAT (`secrets.githubToken`) or GitHub App keys — see
[`docs/github-app-auth.md`](../../../docs/github-app-auth.md). For **kind** (especially with the
operator), prefer [`values-kind.yaml`](values-kind.yaml): fleet registry on `emptyDir` and
no module PVC:

```bash
helm upgrade --install repave ./deploy/k8s/chart \
  --namespace repave --create-namespace \
  -f deploy/k8s/chart/values-kind.yaml \
  --set repave.output.githubOrg=your-org \
  --set image.repository=repave-engine \
  --set image.tag=local \
  --set image.pullPolicy=Never
```

Without fleet registry, disable module PVCs only:

```bash
helm upgrade --install repave ./deploy/k8s/chart \
  --namespace repave --create-namespace \
  --set repave.output.githubOrg=your-org \
  --set persistence.modules.enabled=false \
  --set image.repository=repave-engine \
  --set image.tag=local \
  --set image.pullPolicy=IfNotPresent
```

Port-forward and open the catalog:

```bash
kubectl port-forward svc/repave 8088:8088 -n repave
open http://127.0.0.1:8088
```

Probes use `GET /health` (liveness), `GET /readyz` (readiness), and an optional
**startup** probe for slow gate-toolchain images.

## Day-2 operability

| Values path | Purpose |
| --- | --- |
| `resources` | CPU/memory requests and limits (defaults sized for gate-toolchain) |
| `autoscaling.enabled` | HorizontalPodAutoscaler on CPU (omits static `replicaCount`) |
| `podDisruptionBudget` | Voluntary disruption budget (`minAvailable: 1` by default) |
| `deploymentStrategy` | Rolling update (`maxUnavailable: 0` default) |
| `terminationGracePeriodSeconds` | Time for uvicorn to drain in-flight requests on SIGTERM |
| `lifecycle.preStop` | Optional sleep before SIGTERM so endpoints drop the pod first |
| `probes.*` | Liveness, readiness, and startup probe timings |

**Scaling replicas:** default `replicaCount: 1`. Multiple replicas need shared session and
run state — set `repave.durability.databaseUrl` (PostgreSQL) and `secrets.sessionSecret`
before enabling `autoscaling`. See [`values-day2.yaml`](values-day2.yaml) for a production
overlay (HPA 2–5, monitoring hooks, `requireSessionSecret`, `readyRequireGithub`).

```bash
helm upgrade --install repave ./deploy/k8s/chart \
  -f deploy/k8s/chart/values.yaml \
  -f deploy/k8s/chart/values-day2.yaml \
  --set repave.durability.databaseUrl=postgresql://... \
  --set secrets.existingSecret=repave-secrets \
  ...
```

Pair with [`values-decomposed.yaml`](values-decomposed.yaml) when workers run in a separate
Deployment (`repave.durability.workerMode: external`). For production hosted clusters, prefer
[`values-decomposed-day2.yaml`](values-decomposed-day2.yaml) — it merges decomposed images,
Postgres queue, worker HPA, monitoring hooks, and GitHub readiness checks.

```bash
helm upgrade --install repave ./deploy/k8s/chart \
  -f deploy/k8s/chart/values.yaml \
  -f deploy/k8s/chart/values-decomposed-day2.yaml \
  --set repave.durability.databaseUrl=postgresql://... \
  --set secrets.existingSecret=repave-secrets \
  ...
```

| `shutdown.drainSeconds` | Async run drain before exit (`REPAVE_SHUTDOWN_DRAIN_SECONDS`) |
| `shutdown.readyRequireGithub` | Fail `/readyz` when GitHub API unreachable (publish clusters) |
| `monitoring.serviceMonitor` | Prometheus Operator scrape of `/metrics` |
| `monitoring.prometheusRules` | Alert rules with runbook URLs (generation, async, queue, JSONL) |
| `repave.durability.*` | Async run queue + SQLite at `runsDb` (default **on** for chart) |
| `repave.durability.maxRunAttempts` / `runStaleSeconds` / `runRetryBaseSeconds` | Retry backoff and stale-run reclaim (see `docs/durability.md`) |
| `workerImage.*` | Gate-toolchain image for external worker Deployment or per-run Jobs (defaults to `repave-engine`) |
| `repave.durability.workerMode` | `inline` (default), `external` (worker Deployment), or `job` (one Job per run — see `values-decomposed-job.yaml`) |
| `workerAutoscaling.enabled` | HPA on the external worker Deployment (omit static `workerReplicas` when enabled) |
| `corpus.*` | Mount digest-pinned corpus OCI artifact (Phase 2 decomposition) |
| `image.digest` / `workerImage.digest` / `corpus.digest` | Render `repository@digest` instead of `:tag` — see [`values-digest-pinned.yaml`](values-digest-pinned.yaml) and [`docs/supply-chain.md`](../../../docs/supply-chain.md) |
| `repave.durability.artifactStoreUri` | Optional S3-compatible store for full staging-tree retention (previews default in run record) |
| `persistence.runs` | PVC for `/data/runs` (use `emptyDir` when `enabled: false`) |

**Graceful shutdown:** SIGTERM sets `/readyz` to 503, stops new async submits, drains the queue
for `shutdown.drainSeconds`, then exits. Pair with `terminationGracePeriodSeconds` and
`lifecycle.preStop`.

See [upgrade and rollback](../../../docs/operations/upgrade-and-rollback.md) for release steps.

Example HPA (after durability or for portal-only read paths):

```bash
helm upgrade --install repave ./deploy/k8s/chart \
  --set autoscaling.enabled=true \
  --set autoscaling.minReplicas=2 \
  --set autoscaling.maxReplicas=4 \
  ...
```

See also [`docs/operations/README.md`](../../../docs/operations/README.md) for SLOs and alerts.

## Configuration

| Values path | Purpose |
| --- | --- |
| `repave.output.*` | Rendered into `repave.config.yaml` `output` block |
| `repave.audit.enabled` | JSONL generation audit at `repave.audit.file` |
| `repave.fleet.enabled` | Fleet registry JSONL at `repave.fleet.file` |
| `repave.fleet.operatorStatusFile` | Operator GPR/campaign snapshot for `/platform/campaigns` |
| `repave.platformMetrics.enabled` | Platform metrics ConfigMap block (default **on**); set `githubOrgs` in values |
| `platformMetricsSnapshot.cronJob.enabled` | Hourly `repave metrics adoption --persist` (default **on** with metrics) |
| `repave.gates.infracost.*` | Org floor for Infracost gate (`required`, `maxMonthlyUsd`) |
| `secrets` / `infracost-api-key` | Injected as `INFRACOST_API_KEY` on portal/worker |
| `repave.auth.serviceMode` | OIDC login; requires `secrets.sessionSecret` and OIDC issuer/client |
| `repave.auth.sessionHttpsOnly` | Session cookie `Secure` flag (`REPAVE_SESSION_HTTPS_ONLY`); default `true` |
| `repave.auth.oidc.scopes` | OIDC scopes rendered into ConfigMap (default `openid`/`profile`/`email`) |
| `repave.auth.oidc.logoutReturnTo` | Post-logout URL (Auth0 Allowed Logout URLs) |
| `secrets.existingSecret` | Pre-created Secret (`github-token`, session/OIDC, optional `infracost-api-key`) |
| `persistence.modules` | PVC for module staging (`modules_root`); use `emptyDir` when `enabled: false` |
| `ingress.enabled` | Expose the Service via Ingress |

Environment variables `REPAVE_GITHUB_ORG` and `REPAVE_MODULES_ROOT` mirror config for
operators who prefer env-only overrides.

## Secrets (publish and auth)

```bash
kubectl create secret generic repave-secrets -n repave \
  --from-literal=github-token="$GITHUB_TOKEN" \
  --from-literal=session-secret="$REPAVE_SESSION_SECRET" \
  --from-literal=oidc-client-secret="$REPAVE_OIDC_CLIENT_SECRET" \
  --from-literal=infracost-api-key="$INFRACOST_API_KEY"

helm upgrade --install repave ./deploy/k8s/chart \
  --set secrets.existingSecret=repave-secrets \
  --set repave.auth.serviceMode=true \
  ...
```

Do not commit real tokens in `values.yaml`. Use `secrets.create: true` only on kind.

### Infracost gate (FinOps estimates)

Workers read `INFRACOST_API_KEY` from Secret key `infracost-api-key` (optional). Set
`repave.gates.infracost.required: true` (enabled in `values-decomposed-day2.yaml`) so
missing CLI/key fails instead of skipping. See [`docs/finops.md`](../../../docs/finops.md).

```bash
# Add or rotate the key on an existing Secret (does not print the value):
kubectl -n repave get secret repave-secrets -o json \
  | jq --arg k "$(printf %s "$INFRACOST_API_KEY" | base64)" \
    '.data["infracost-api-key"]=$k' \
  | kubectl apply -f -
kubectl -n repave rollout restart deploy -l app.kubernetes.io/name=repave
```

### Auth0 portal access

Use [`values-auth0.yaml`](values-auth0.yaml) with
[`values-decomposed-day2.yaml`](values-decomposed-day2.yaml) so the hosted portal
and mutating APIs require Auth0 login (TLS-terminated Ingress).

- Operator checklist: [`docs/operations/auth0-portal.md`](../../../docs/operations/auth0-portal.md)
- Post-Login Action: [`../auth0/post-login-groups.js`](../auth0/post-login-groups.js)
- Secrets: [`../hack/bootstrap-auth0-secrets.sh`](../hack/bootstrap-auth0-secrets.sh)
- Config reference: [`docs/auth-service-mode.md`](../../../docs/auth-service-mode.md#auth0-for-portal-access-day-1)

### State store (ADR 004)

Use [`values-state-store.yaml`](values-state-store.yaml) only after the enablement
checklist. Defaults stay **off** (`repave.stateStore.enabled: false`).

- Operator checklist: [`docs/operations/state-store-enablement.md`](../../../docs/operations/state-store-enablement.md)
- Secrets (KEK): [`../hack/bootstrap-state-store-secrets.sh`](../hack/bootstrap-state-store-secrets.sh)
- Operator guide: [`docs/state-graph.md`](../../../docs/state-graph.md)
- Design: [`docs/adr/004-state-custody-and-the-resource-graph.md`](../../../docs/adr/004-state-custody-and-the-resource-graph.md)

Server env: `REPAVE_STATE_STORE_URL` (enables), `REPAVE_STATE_KEK` (required in shared
deploy). Client/CI env: `REPAVE_STATE_URL` (portal base URL) — different name on purpose.

## Co-install with the operator

Typical layout:

- **Namespace:** `repave-system` (or split `repave-portal` / `repave-operator`)
- **Portal:** this chart — serves catalog and generation
- **Operator:** [`deploy/k8s/operator-chart/`](../operator-chart/) — reconciles `GoldenPathRepo`
  and `Blueprint` CRs (conversion webhook, leader election, day-2 overlays)

Share notification webhook URLs between `repave.config.yaml` and operator env vars (see
[`repave.config.yaml.example`](../../../repave.config.yaml.example)).

Fleet registry manifests from `repave fleet-manifests` can target the same namespace as
operator-managed `GoldenPathRepo` objects, or enable **continuous sync** with a shared PVC
([`values-fleet-shared.yaml`](values-fleet-shared.yaml) + operator
[`values-fleet-shared.yaml`](../operator-chart/values-fleet-shared.yaml) in the same namespace).

### Full kind stack (portal + operator + fleet)

After `make install` (engine venv), run:

```bash
CO_INSTALL_KEEP_CLUSTER=1 make kind-co-install
kubectl port-forward svc/repave 8088:8088 -n repave
```

This creates a kind cluster with operator module fixtures mounted at `/modules`, installs
the portal (with the same `/modules` hostPath via `values-kind.yaml`) and the operator Helm
chart (`REPAVE_API_URL` → portal Service), seeds
[`deploy/k8s/testdata/fleet-registry.jsonl`](../testdata/fleet-registry.jsonl) on the shared
fleet PVC, and waits for operator **fleetSync** to create GPRs before applying the local
`e2e-drift` fixture. Remote `repoURL` entries show fetch errors until you point at reachable
git; `e2e-drift` exercises plan-only drift on `/modules/terraform-minimal`.

Reuse an existing cluster or images: `CO_INSTALL_SKIP_CLUSTER=1`, `CO_INSTALL_SKIP_BUILD=1`.
See [`deploy/k8s/hack/kind-co-install.sh`](../hack/kind-co-install.sh).

## Observability

Scrape `GET /metrics` on the Service port.

| Mode | When to use |
| --- | --- |
| **Chart-managed** | `monitoring.serviceMonitor.enabled` and `monitoring.prometheusRules.enabled` (see `values-day2.yaml`) |
| **Standalone** | Apply [`deploy/k8s/prometheus-rules.yaml`](../prometheus-rules.yaml) and import [`grafana-dashboard-repave.json`](../grafana-dashboard-repave.json) when not using the chart templates |

Set `monitoring.prometheusRules.includeKubeStateAlerts: true` when kube-state-metrics is
available (HPA-at-max alert).

## Environment vending and TTL reclaim

Governed environment stacks ([ADR 003](../../../docs/adr/003-environment-lifecycle-and-live-state.md)
Phase 3) use `repave.environmentVending` in the ConfigMap and a shared
`persistence.environments` volume for the JSONL registry.

| Values path | Purpose |
| --- | --- |
| `repave.environmentVending.*` | GitOps repo, TTL classes, auto-reclaim vs review classes |
| `persistence.environments` | PVC for `registry.jsonl` (portal + reclaim CronJob) |
| `environmentReclaim.cronJob` | Scheduled TTL reclaim (`invoke: cli` or `http`) |

Example overlay: [`values-environment-vending.yaml`](values-environment-vending.yaml).

v3 developer lab (`/lab` alias, My services copy) is a second opt-in on top of catalog
YAML you already mount. Default-off (ADR 008):

```bash
helm upgrade --install repave ./deploy/k8s/chart \
  --set repave.v3.enabled=true \
  --set repave.v3.developerLab.enabled=true \
  --set repave.serviceCatalog.enabled=true \
  --set repave.output.githubOrg=your-org
```

`developerLab.enabled`, `autoMerge.enabled`, and `mandatoryPolicy.enabled` require
`v3.enabled`. Lab does not invent a GitOps repo or turn on environment vending.
Catalog files still have to exist at the `serviceCatalog.*` paths (or, in a git
checkout, `v3.developer_lab.enabled` can wire `examples/platform-dev`). Auto-merge
is a plan verdict; `apply-upgrade --open-pr` squash-merges Allowed mechanical pin
bumps. Fleet demote:
`--set repave.v3.autoMerge.killSwitch=true`. Mandatory policy refuses
`enable_policy: false` on `regulatedFamilies` unless a `mandatory-policy` waiver
is on file. See [`docs/v3-development.md`](../../../docs/v3-development.md),
[`docs/operations/auto-merge-revert.md`](../../../docs/operations/auto-merge-revert.md),
and [`docs/operations/mandatory-policy.md`](../../../docs/operations/mandatory-policy.md).

```bash
helm upgrade --install repave ./deploy/k8s/chart \
  -f deploy/k8s/chart/values-environment-vending.yaml \
  --set repave.output.githubOrg=your-org \
  --set repave.environmentVending.gitopsRepo=https://github.com/your-org/platform-gitops \
  --set secrets.existingSecret=repave-secrets
```

**CronJob invoke modes**

| `invoke` | Behavior |
| --- | --- |
| `cli` (default) | Runs `repave environments reclaim` in-cluster; mounts the shared environments PVC and needs `GITHUB_TOKEN` (or GitHub App keys) on the Secret for GitOps PRs. |
| `http` | `curl` POST to `/api/v2/environments/reclaim` on the portal Service; portal owns the registry PVC. When `auth.service_mode` is on, set `secrets.apiToken` (maps to `REPAVE_API_TOKEN`) on the portal and CronJob. |

Use `environmentReclaim.cronJob.dryRun: true` to preview without opening PRs.

Manual reclaim from a pod: `kubectl exec deploy/repave -n repave -- repave environments reclaim --dry-run`.

## Fleet operator snapshot (platform console)

When the repave operator is installed, the portal can show live `GoldenPathRepo` phase and
`UpgradeCampaign` rows on `/platform/campaigns` and `/fleet` from a JSON snapshot on the
shared fleet PVC — not by calling the Kubernetes API from the portal process.

| Values path | Purpose |
| --- | --- |
| `repave.fleet.operatorStatusFile` | Path for operator status JSON (default `/data/fleet/operator-status.json`) |
| `persistence.fleet` | Shared PVC for registry JSONL + operator snapshot (portal + CronJob) |
| `fleetOperatorSnapshot.cronJob` | Scheduled `repave fleet-operator-snapshot` (requires gate-toolchain image with `kubectl`) |
| `fleetOperatorSnapshot.cronJob.operatorNamespace` | Namespace where GPRs and UpgradeCampaigns live (defaults to release namespace) |

Example overlay: [`values-fleet-shared.yaml`](values-fleet-shared.yaml) (enables fleet PVC,
operator status path, and a `*/15` CronJob for co-install with the operator).

```bash
helm upgrade --install repave ./deploy/k8s/chart \
  -f deploy/k8s/chart/values-fleet-shared.yaml \
  --set repave.output.githubOrg=your-org \
  --set secrets.existingSecret=repave-secrets
```

When the portal and operator run in different namespaces, set
`fleetOperatorSnapshot.cronJob.operatorNamespace` to the operator install namespace. The chart
creates a **Role** (or **ClusterRole** when `allNamespaces: true`) so the portal
ServiceAccount can list `repave.dev/goldenpathrepos` and `get`/`list`/`patch`
`upgradecampaigns` (snapshot refresh plus in-portal campaign pause/resume on
`/platform/campaigns`).

Manual refresh from a pod:

```bash
kubectl exec deploy/repave -n repave -- repave fleet-operator-snapshot \
  --output /data/fleet/operator-status.json \
  --namespace repave-system
```

See [`docs/fleet-registry.md`](../../../docs/fleet-registry.md) for registry sync and snapshot
semantics.

## Validation

```bash
make chart-validate           # helm lint + template smoke (CI: chart-validate)
make chart-smoke              # kind install (CI: chart-smoke on chart/image paths)
make chart-smoke-decomposed   # decomposed portal + worker + Postgres async run (CI: chart-smoke-decomposed)
make chart-smoke-multi-replica   # two portal replicas + shared Postgres sessions/queue (CI: chart-smoke-multi-replica)
make chart-smoke-environment-vending   # environment vending PVC + reclaim CronJob (CI: chart-smoke-environment-vending)
make chart-smoke-fleet-snapshot   # fleet PVC + fleetSync prune + snapshot CronJob + campaign pause (CI: chart-smoke-fleet-snapshot)
```

## Scaling

Default `replicaCount: 1`. The chart ships **HPA**, **PDB**, resource defaults, rolling
update strategy, startup probe, graceful termination, and optional **ServiceMonitor** /
**PrometheusRule** — see **Day-2 operability** above. Enable autoscaling only after shared
SQL durability (`databaseUrl`) and session secret are configured.
