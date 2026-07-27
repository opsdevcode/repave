# monitors-as-code-generic

Golden path for **monitors and alerting** only: Datadog monitors or Prometheus rules +
Alertmanager routing stubs, with pinned standards and validation gates.

## Scope

| Backend | Native | Terraform |
| --- | --- | --- |
| `datadog` | Monitor JSON under `datadog/monitors/` | Datadog provider (`monitors.tf`) |
| `prometheus` | Rules + Alertmanager YAML | `null_resource` payloads in `.tf` files |

Companion paths: **dashboards** (`dashboards-as-code-generic`), **full observability**
(`observability-as-code-generic`).

## Local try

```bash
cd engine
uv run repave generate blueprints/monitors-as-code-generic \
  --set service_name=checkout \
  --set organization=platform \
  --set team=payments \
  --set description="Checkout API alerts" \
  --set backend=prometheus \
  --set runbook_url=https://wiki.example.com/runbooks/checkout \
  --dry-run
```
