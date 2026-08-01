# repave-operator

**Kubernetes operator** for governed golden-path reconciliation
([repave](https://github.com/opsdevcode/repave) v1.17+ GA).

```text
ghcr.io/opsdevcode/repave-operator:<tag>
```

Distroless image from [`operator/Dockerfile`](../../../operator/Dockerfile). Runs the
`manager` binary — Kubebuilder controllers for `GoldenPathRepo`, `Blueprint`, fleet campaigns,
and remediation PR workflows.

## What it does

- Watches registered repos (local path or shallow-cloned `spec.repoURL`)
- Reads `repave.yaml` provenance and compares pins to desired blueprint/standard versions
- Opens **governed remediation pull requests** (never direct pushes to module repos)
- Optional HTTP mode: calls portal `/api/v2/upgrades/*` instead of exec'ing the CLI

Does **not** run terraform apply, Argo CD sync, or cloud mutations.

## Deploy

Helm chart: [`deploy/k8s/operator-chart/`](../../k8s/operator-chart/)

```bash
docker pull ghcr.io/opsdevcode/repave-operator:<tag>
helm upgrade --install repave-operator deploy/k8s/operator-chart \
  --set image.repository=ghcr.io/opsdevcode/repave-operator \
  --set image.tag=<tag>
```

Requires `GITHUB_TOKEN` (read for inventory; write for remediation PRs) and optionally
`REPAVE_API_URL` pointing at the portal Service.

## Docs

- [`operator/README.md`](../../../operator/README.md)
- [`docs/operator-ga.md`](../../../docs/operator-ga.md)
- [`docs/operator-local-dev.md`](../../../docs/operator-local-dev.md)

## Source

Monorepo: [opsdevcode/repave](https://github.com/opsdevcode/repave) · Go module:
[`operator/`](../../../operator/)
