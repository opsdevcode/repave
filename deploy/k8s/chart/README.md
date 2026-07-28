# repave Helm chart

Install the repave **portal and API** on Kubernetes. The container image is built from
[`deploy/local/Dockerfile`](../../local/Dockerfile) (Python engine plus gate toolchain for
dry-run generation).

## Prerequisites

- Kubernetes 1.26+
- Helm 3.10+
- An image built and pushed (or loaded into kind) from the monorepo root:

```bash
docker build -f deploy/local/Dockerfile -t ghcr.io/your-org/repave-engine:1.75.0 .
```

## Quick install (dry-run only)

Dry-run generation does not need `GITHUB_TOKEN`. For kind or minikube, disable module PVCs
so you do not wait on storage:

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

## Observability

Scrape `GET /metrics` on the Service port. Starter Prometheus rules and a Grafana dashboard
live in [`deploy/k8s/`](../README.md) (parent directory).

## Validation

```bash
make chart-validate    # helm lint + template smoke
make chart-smoke       # kind install (optional; requires docker + kind + helm)
```

## Scaling

Default `replicaCount: 1`. Multiple replicas require shared session and run state — see roadmap
**durability and concurrency** before scaling the Deployment.
