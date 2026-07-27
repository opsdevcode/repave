# Observability catalog

`catalog.json` drives observability portal dropdowns and generation:

| Section | Purpose |
| --- | --- |
| `organizations`, `teams`, `services` | Service ownership fields |
| `environments`, `grafana_datasources`, `runbooks`, `slo_targets` | Environment, datasource, runbook, SLO selects |
| `notification_sources` | PagerDuty / Slack / email routing targets |
| `dashboard_packs` | Vendored **community dashboard forks** under `observability/dashboards/` |
| `monitor_packs` | Vendored **community monitor forks** under `observability/monitors/` |

Customize for your estate by overriding `observability/catalog.json` (same pattern as
`policy/catalog.json`).

### Form presets

`form_presets` lists **decision fields** per blueprint (service, backend, dashboard or monitor pack).
When the portal is in **Recommended defaults** mode, all other catalog-backed fields are
filled automatically at submit time.

### Split golden paths

- **Dashboards:** `dashboards-as-code-generic` + `dashboard_packs`
- **Monitors:** `monitors-as-code-generic` + `monitor_packs`
- **Umbrella (legacy):** `observability-as-code-generic` when one repo must mix backends or include OTel

See `observability/dashboards/README.md` and `observability/monitors/README.md` for community packs.
