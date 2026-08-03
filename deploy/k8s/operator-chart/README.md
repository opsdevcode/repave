# repave operator Helm chart

Install the repave **Kubernetes operator** (GoldenPathRepo and Blueprint reconciliation)
alongside the [portal chart](../chart/). Image builds from [`operator/Dockerfile`](../../../operator/Dockerfile).

## Prerequisites

- Kubernetes 1.26+
- Helm 3.10+
- Portal/API reachable at `repave.apiUrl` (typically the portal Service in another namespace)
- Webhook TLS Secret (`webhook.secretName`, default `webhook-server-cert`) before pods become ready
- Base64-encoded webhook CA in `webhook.caBundle` when `crds.install=true`

Install from the published OCI chart (semver tags only):

```bash
helm upgrade --install repave-operator oci://ghcr.io/opsdevcode/charts/repave-operator \
  --version 2.15.0 \
  --namespace repave-system --create-namespace \
  -f deploy/k8s/operator-chart/values-day2.yaml \
  --set repave.apiUrl=http://repave.repave.svc.cluster.local:8088
```

Chart `version` and `appVersion` match the engine release tag, so unpinned installs pull
`ghcr.io/opsdevcode/repave-operator:<release>`.

## Quick install (with portal)

Typical layout:

| Component | Namespace | Chart |
| --- | --- | --- |
| Portal / API | `repave` | [`../chart/`](../chart/) |
| Operator | `repave-system` | this chart |

```bash
# 1. Portal (see ../chart/README.md)
helm upgrade --install repave ./deploy/k8s/chart \
  --namespace repave --create-namespace \
  -f deploy/k8s/chart/values-day2.yaml \
  --set repave.output.githubOrg=your-org \
  --set secrets.existingSecret=repave-secrets

# 2. Webhook TLS (self-signed example; use cert-manager in production)
operator/hack/setup-webhook-certs.sh
CA_BUNDLE="$(base64 < operator/hack/webhook-certs/ca.crt | tr -d '\n')"

# 3. Operator
helm upgrade --install repave-operator ./deploy/k8s/operator-chart \
  --namespace repave-system --create-namespace \
  -f deploy/k8s/operator-chart/values-day2.yaml \
  --set repave.apiUrl=http://repave.repave.svc.cluster.local:8088 \
  --set secrets.existingSecret=repave-operator-secrets \
  --set webhook.caBundle="${CA_BUNDLE}"
```

Create `repave-operator-secrets` with GitHub PAT or App keys (same keys as the portal chart).
See [`docs/github-app-auth.md`](../../../docs/github-app-auth.md).

## kind co-install

The repo [`kind-co-install.sh`](../hack/kind-co-install.sh) (`make kind-co-install`) installs
both charts, seeds a fleet registry for operator fleetSync, and runs the drift fixture. Operator
values come from [`values-kind.yaml`](values-kind.yaml) and [`values-fleet-shared.yaml`](values-fleet-shared.yaml).

## Configuration

| Values path | Purpose |
| --- | --- |
| `repave.apiUrl` | Portal `/api/v2` base URL (**required**) |
| `image.*` | Operator manager image (`ghcr.io/opsdevcode/repave-operator`) |
| `manager.leaderElect` | Controller-runtime leader election (default **true**) |
| `manager.metrics.*` | Prometheus metrics on `:8080` when enabled |
| `webhook.caBundle` | Base64 CA for CRD conversion webhook (required when `crds.install=true`) |
| `webhook.secretName` / `webhook.existingSecret` | Webhook serving cert Secret |
| `crds.install` | Render and apply `repave.dev` CRDs from chart (default **true**) |
| `modules.hostPath` | Mount test/module fixtures (kind only) |
| `fleetSync.*` | Continuous GPR sync from shared fleet registry JSONL (see [`values-fleet-shared.yaml`](values-fleet-shared.yaml)) |
| `fleetRegistry.*` | PVC or emptyDir backing `fleetSync.registryPath` |
| `secrets.existingSecret` | GitHub PAT or App credentials |
| `podDisruptionBudget` | Voluntary disruption budget |
| `monitoring.serviceMonitor` | Prometheus Operator scrape of `/metrics` |

## Day-2 operability

[`values-day2.yaml`](values-day2.yaml) enables two replicas with leader election, metrics
Service, ServiceMonitor, and production resource defaults. Pair with cert-manager or your
PKI for webhook TLS instead of `setup-webhook-certs.sh` on production clusters.

## CRD sync

Packaged CRDs under `files/crd/` are derived from [`operator/config/crd/bases`](../../../operator/config/crd/bases).
After controller-gen updates, refresh with:

```bash
./deploy/k8s/hack/sync-operator-chart-crds.sh
```

## Validation

```bash
make chart-validate    # includes operator-chart lint + template checks
make kind-co-install   # portal + operator Helm on kind (full stack smoke)
```

Raw YAML under `operator/config/e2e/` remains for operator unit/e2e tests; prefer this chart
for cluster installs.
