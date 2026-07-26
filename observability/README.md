# Observability catalog

`catalog.json` drives observability portal dropdowns and generation:

| Section | Purpose |
| --- | --- |
| `organizations`, `teams`, `services` | Service ownership fields |
| `environments`, `grafana_datasources`, `runbooks`, `slo_targets` | Environment, datasource, runbook, SLO selects |
| `notification_sources` | PagerDuty / Slack / email routing targets |
| `dashboard_packs` | Vendored **community dashboard forks** under `observability/dashboards/` |

Customize for your estate by overriding `observability/catalog.json` (same pattern as
`policy/catalog.json`).

### Form presets

`form_presets` lists **decision fields** per blueprint (service, backend, dashboard pack).
When the portal is in **Recommended defaults** mode, all other catalog-backed fields are
filled automatically at submit time.

See `observability/dashboards/README.md` for adding Grafana.com or Datadog community packs.
