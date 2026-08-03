# slo-as-code-generic

Golden path for **SLOs as code**: Prometheus recording rules and multi-window burn-rate
alerts with a repo-local `RUNBOOK.md`.

## Generate

```bash
cd engine
uv run repave generate --blueprint slo-as-code-generic \
  --input service_name=checkout-api \
  --input organization=platform \
  --input team=payments \
  --input description="Checkout availability SLO" \
  --input slo_target_percent=99.9 \
  --input runbook_url=https://wiki.example.com/runbooks/checkout-api \
  --dry-run
```

Pair with [`monitors-as-code-generic`](../monitors-as-code-generic/) for symptom alerts and
[`dashboards-as-code-generic`](../dashboards-as-code-generic/) for golden-signal dashboards.

See `standards/observability/slos-as-code.md`.
