# gitops-deployment-generic

Golden path for **GitOps delivery**: an Argo CD `Application` or Flux `HelmRelease` pinned to an
exact chart version, with the sync policy recorded as an explicit decision.

One repository describes one service in one environment, so a promotion is a reviewable commit
in exactly one place.

## Example

```bash
cd engine
uv run repave generate --blueprint blueprints/gitops-deployment-generic \
  --input service_name=checkout-api \
  --input environment=dev \
  --input gitops_engine=argocd \
  --input chart_repo_url=https://charts.example.com \
  --input chart_name=checkout-api \
  --input chart_version=1.2.3 \
  --input target_namespace=checkout \
  --dry-run
```

Flux variant:

```bash
uv run repave generate --blueprint blueprints/gitops-deployment-generic \
  --input service_name=checkout-api \
  --input gitops_engine=flux \
  --input flux_source_name=example-charts \
  --input chart_repo_url=https://charts.example.com \
  --input chart_name=checkout-api \
  --input chart_version=1.2.3 \
  --dry-run
```

Requires `conftest` on PATH for the `opa` gate and `yamllint` for the `yamllint` gate; both skip
cleanly when absent.

Pairs with [`helm-chart-generic`](../helm-chart-generic/README.md) — generate the chart, publish
it to a repository, then point this manifest at that chart version. See
[`standards/gitops/deployment-standard.md`](../../standards/gitops/deployment-standard.md).
