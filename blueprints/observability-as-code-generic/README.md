# observability-as-code-generic

Golden path for **observability-as-code**: governed alerts, monitors, and routing
artifacts with pinned standards and validation gates.

## Scope (v0.2)

| Backend | Native | Terraform |
| --- | --- | --- |
| `prometheus` | Rules + Alertmanager stub | — |
| `grafana` | Dashboard JSON | — |
| `datadog` | Monitor JSON | Datadog provider at repo root |
| `otel` | Collector config YAML | — |

Companion **dashboards-only** repos: `dashboards-as-code-generic`.

## Local try

```bash
cd engine
uv run repave generate blueprints/observability-as-code-generic \
  --set service_name=checkout \
  --set organization=platform \
  --set team=payments \
  --set description="Checkout API SLOs and alerts" \
  --set runbook_url=https://wiki.example.com/runbooks/checkout \
  --dry-run
```

Datadog Terraform:

```bash
uv run repave generate blueprints/observability-as-code-generic \
  --set backend=datadog \
  --set output_mode=terraform \
  ... \
  --dry-run
```
