# helm-chart-generic

Golden path for **Helm charts**: lint-clean `Chart.yaml`, `values.yaml`, templates,
and optional Ingress.

## Example

```bash
cd engine
uv run repave generate ../blueprints/helm-chart-generic \
  --set chart_name=checkout-api \
  --set app_name=checkout-api \
  --set description="Checkout API workload" \
  --set image_repository=ghcr.io/example/checkout-api \
  --set image_tag=1.2.3 \
  --dry-run
```

Requires `helm` on PATH for `helm-lint` and `helm-template` gates.

Optional Backstage catalog: `--input include_backstage_catalog=true --input owner=group:platform`
(see [`docs/backstage.md`](../../docs/backstage.md)).
