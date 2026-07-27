# observability-as-code-generic

Golden path for **full-stack observability-as-code** (umbrella): alerts, monitors,
dashboards, OTel, and routing in one repository.

## Prefer split paths for new repos

| Goal | Use instead |
| --- | --- |
| Dashboards only (Grafana / Datadog + community packs) | [`dashboards-as-code-generic`](../dashboards-as-code-generic/) |
| Monitors / alerts only (Datadog / Prometheus + monitor packs) | [`monitors-as-code-generic`](../monitors-as-code-generic/) |

Keep this blueprint when you intentionally combine multiple backends in one repo or need
the OTel collector scaffold alongside alerts.

## Scope (v0.2)

| Backend | Native | Terraform |
| --- | --- | --- |
| `prometheus` | Rules + Alertmanager stub | `null_resource` payloads |
| `grafana` | Dashboard JSON | Grafana provider |
| `datadog` | Monitor JSON | Datadog provider at repo root |
| `otel` | Collector config YAML | Helm chart stub |

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
