# repave Helm chart

Install the repave **portal and API** on Kubernetes. Images build from
[`deploy/local/Dockerfile`](../../local/Dockerfile):

| Variant | Build | Helm |
| --- | --- | --- |
| **Gate toolchain** (default) | `docker build -f deploy/local/Dockerfile -t repave-engine:TAG .` | `image.gateToolchain: true` (default) |
| **Portal-only** | `docker build -f deploy/local/Dockerfile --build-arg INSTALL_GATE_TOOLCHAIN=0 -t repave-engine-portal:TAG .` | `-f values-portal.yaml` or `image.gateToolchain: false` |

The gate-toolchain image includes pinned CLIs for Plan/dry-run. The portal-only image
is smaller and suits catalog/auth-only deployments; dry-run gates report missing tools.

## Prerequisites

- Kubernetes 1.26+
- Helm 3.10+
- An image built and pushed (or loaded into kind) from the monorepo root:

```bash
docker build -f deploy/local/Dockerfile -t ghcr.io/your-org/repave-engine:1.75.0 .
```

## Quick install (dry-run only)

Dry-run generation does not need `GITHUB_TOKEN`. For **kind** (especially with the
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

Probes use `GET /health` (liveness) and `GET /readyz` (readiness).

## Configuration

| Values path | Purpose |
| --- | --- |
| `repave.output.*` | Rendered into `repave.config.yaml` `output` block |
| `repave.audit.enabled` | JSONL generation audit at `repave.audit.file` |
| `repave.fleet.enabled` | Fleet registry JSONL at `repave.fleet.file` |
| `repave.auth.serviceMode` | OIDC login; requires `secrets.sessionSecret` and OIDC issuer/client |
| `secrets.existingSecret` | Pre-created Secret with keys `github-token`, `session-secret`, `oidc-client-secret` |
| `persistence.modules` | PVC for module staging (`modules_root`); use `emptyDir` when `enabled: false` |
| `ingress.enabled` | Expose the Service via Ingress |

Environment variables `REPAVE_GITHUB_ORG` and `REPAVE_MODULES_ROOT` mirror config for
operators who prefer env-only overrides.

## Secrets (publish and auth)

```bash
kubectl create secret generic repave-secrets -n repave \
  --from-literal=github-token="$GITHUB_TOKEN" \
  --from-literal=session-secret="$REPAVE_SESSION_SECRET" \
  --from-literal=oidc-client-secret="$REPAVE_OIDC_CLIENT_SECRET"

helm upgrade --install repave ./deploy/k8s/chart \
  --set secrets.existingSecret=repave-secrets \
  --set repave.auth.serviceMode=true \
  ...
```

Do not commit real tokens in `values.yaml`. Use `secrets.create: true` only on kind.

## Co-install with the operator

Typical layout:

- **Namespace:** `repave-system` (or split `repave-portal` / `repave-operator`)
- **Portal:** this chart — serves catalog and generation
- **Operator:** `operator/config/e2e` or your overlay — reconciles `GoldenPathRepo`

Share notification webhook URLs between `repave.config.yaml` and operator env vars (see
[`repave.config.yaml.example`](../../../repave.config.yaml.example)).

Fleet registry manifests from `repave fleet-manifests` can target the same namespace as
operator-managed `GoldenPathRepo` objects.

### Full kind stack (portal + operator + fleet)

After `make install` (engine venv), run:

```bash
CO_INSTALL_KEEP_CLUSTER=1 make kind-co-install
kubectl port-forward svc/repave 8088:8088 -n repave
```

This creates a kind cluster with operator module fixtures mounted at `/modules`, installs
the portal with [`values-kind.yaml`](values-kind.yaml), seeds
[`deploy/k8s/testdata/fleet-registry.jsonl`](../testdata/fleet-registry.jsonl), renders
GPRs with `repave fleet-manifests`, applies them plus the local `e2e-drift` fixture. Remote
`repoURL` entries show fetch errors until you point at reachable git; `e2e-drift` exercises
plan-only drift on `/modules/terraform-minimal`.

Reuse an existing cluster or images: `CO_INSTALL_SKIP_CLUSTER=1`, `CO_INSTALL_SKIP_BUILD=1`.
See [`deploy/k8s/hack/kind-co-install.sh`](../hack/kind-co-install.sh).

## Observability

Scrape `GET /metrics` on the Service port. Starter Prometheus rules and a Grafana dashboard
live in [`deploy/k8s/`](../README.md) (parent directory).

## Validation

```bash
make chart-validate    # helm lint + template smoke (CI: chart-validate)
make chart-smoke       # kind install (CI: chart-smoke on chart/image paths)
```

## Scaling

Default `replicaCount: 1`. Multiple replicas require shared session and run state — see roadmap
**durability and concurrency** before scaling the Deployment.
