# dashboards-as-code-generic

Golden path for **dashboards-as-code** under the observability family: Grafana and
Datadog JSON aligned with RED / golden signals and community tagging practice.

## Standard

Pinned at `standards/observability/dashboards-as-code.md` v1.1.0 (Grafana + Datadog
best practices, OpenTelemetry-style tags, references to SRE / Grafana / Datadog docs).

## Local try

Grafana:

```bash
cd engine
uv run repave generate ../blueprints/dashboards-as-code-generic \
  --set service_name=checkout \
  --set organization=platform \
  --set team=payments \
  --set description="Checkout service dashboards" \
  --set backend=grafana \
  --dry-run
```

Datadog:

```bash
uv run repave generate ../blueprints/dashboards-as-code-generic \
  --set service_name=checkout \
  --set organization=platform \
  --set team=payments \
  --set description="Checkout service dashboards" \
  --set backend=datadog \
  --set environment=prod \
  --dry-run
```
