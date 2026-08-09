# Platform console (`/platform/*`)

Admin views for fleet governance, operational readiness, standards blast radius,
operator campaigns, adoption/DX metrics, FinOps showback, compliance posture, value
stream signals, and developer feedback.

Roadmap: [Platform as a product](roadmap.md#platform-as-a-product-v2x).

## Quick start (local UI walkthrough)

```bash
make platform-dev-setup   # repave.config.yaml from examples/platform-dev/
make serve                # http://127.0.0.1:8089
```

Platform links appear in the header **More** menu and the footer when you have admin
visibility (everyone when auth is off; signed-in `admin` when auth is on). See
[`examples/platform-dev/README.md`](../examples/platform-dev/README.md) for sample data.

## Do I need Prometheus?

**No** for the portal UI. Repave always exposes `GET /metrics` on the engine process.
Visiting `/platform/finops` or computing adoption metrics updates in-memory gauges
(`repave_finops_*`, `repave_golden_path_*`). Scrape `/metrics` with Prometheus only when
you want Grafana dashboards or chart-managed alerts — see
[`deploy/k8s/chart/README.md`](../deploy/k8s/chart/README.md) and
[`docs/operations/README.md`](operations/README.md).

## Visibility: who sees platform links?

| Condition | Platform nav (More + footer) |
| --- | --- |
| Auth disabled (typical local `make serve`) | Visible to everyone |
| Auth enabled, `coarse_rbac_enabled: false` (default) | Visible after any OIDC login (`admin` role) |
| Auth enabled, coarse RBAC on | Only users in `auth.oidc.roles.admin` groups |

Routes under `/platform/*` and `GET /api/v2/platform/*` require the same **admin** role
when auth service mode is on. See [`auth-service-mode.md`](auth-service-mode.md).

## Enablement matrix

Each page needs the config below to show **data** (not just the shell). Pages without
config show an inline hint naming the missing block.

| Page | Config | Also helps |
| --- | --- | --- |
| **Fleet** | `fleet.enabled: true` + `fleet.file` | Registered repos via `repave register` or sample JSONL |
| **Ops** | *(none required)* | `durability.async_generation`, `audit`, `environment_vending` enrich the view |
| **Standards** | `fleet` + blueprints in repo | Async queue for confirm-drift runs |
| **Campaigns** | `fleet` + `fleet.operator_status_file` | Operator snapshot CronJob in Helm |
| **Adoption** | `platform_metrics.enabled: true` | `fleet`, `audit`, optional `github_orgs` + token for bypass list |
| **Compliance** | `platform_metrics.enabled: true` | Same as adoption (gate friction from audit) |
| **Value stream** | `platform_metrics.enabled: true` | Prior snapshots in `platform_metrics.snapshot_file` for trend sparkline |
| **Feedback** | `platform_metrics.enabled: true` | `platform_metrics.feedback_file`; events from CSAT on result/run console |
| **FinOps** | `portal.cost_reader` **or** `portal.cost_snapshots` | `fleet` entities; `cost_budgets` for budget column |
| **FinOps export** | Same as FinOps | `GET /api/v2/platform/finops/export?format=csv\|json` |
| **FinOps anomalies** | `portal.cost_anomalies.enabled: true` + snapshots | Optional `notifications.events: [finops_anomaly]` |

Cross-links:

- FinOps readers, budgets, FOCUS, export: [`finops.md`](finops.md)
- Adoption metrics, feedback, stakeholder APIs: [`platform-metrics.md`](platform-metrics.md)
- Hosted Auth0 + roles: [`auth-service-mode.md`](auth-service-mode.md)

## Minimal production-shaped config

```yaml
apiVersion: repave.dev/v1

fleet:
  enabled: true
  file: data/fleet/registry.jsonl
  operator_status_file: data/fleet/operator-status.json

audit:
  enabled: true
  file: data/audit/generation.jsonl

platform_metrics:
  enabled: true
  snapshot_file: data/platform-metrics/snapshots.jsonl
  feedback_file: data/platform-metrics/feedback.jsonl
  github_orgs: [your-github-org]

portal:
  cost_reader: focus
  cost_focus:
    file: data/focus/export.json
  cost_snapshots:
    enabled: true
    file: data/fleet/cost-snapshots.jsonl
  cost_budgets:
    default_monthly_usd: 250
```

Helm equivalents: `repave.fleet`, `repave.platformMetrics`, `repave.portal.costSnapshots`
in [`deploy/k8s/chart/values.yaml`](../deploy/k8s/chart/values.yaml) and
[`values-fleet-shared.yaml`](../deploy/k8s/chart/values-fleet-shared.yaml).

## Navigation

Platform links are defined once in `PLATFORM_NAV_LINKS` and rendered in:

- Platform subnav on `/platform/*` pages
- Header **More** menu
- Footer
- Command palette (admin)

No per-page feature flags for nav — only `platform_admin_visible` (auth/role).

## Env overrides (common)

| Variable | Effect |
| --- | --- |
| `REPAVE_FLEET_FILE` | Fleet registry path |
| `REPAVE_FLEET_OPERATOR_STATUS_FILE` | Operator snapshot for campaigns/drift |
| `REPAVE_PLATFORM_METRICS=1` | Enable platform metrics without YAML block |
| `REPAVE_PLATFORM_METRICS_FILE` | DX metrics snapshot JSONL |
| `REPAVE_PLATFORM_FEEDBACK_FILE` | Feedback JSONL |
| `REPAVE_COST_READER` / `REPAVE_COST_FOCUS_FILE` | FinOps actuals source |

See [`repave.config.yaml.example`](../repave.config.yaml.example) for the full list.
