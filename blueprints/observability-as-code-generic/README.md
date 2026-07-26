# observability-as-code-generic

Golden path for **observability-as-code** (roadmap v1.40): governed alerts and dashboards
with pinned standards and validation gates.

## MVP scope

- Artifact type `observability`
- **Prometheus native** recording/alert rules under `prometheus/rules/`
- Optional Grafana dashboard JSON when `backend=grafana`
- Placeholder README stubs for `datadog` and `otel` backends

Terraform provider mode is planned as a separate expansion.

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
