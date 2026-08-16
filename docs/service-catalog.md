# Service catalog, maturity, and sandboxes

Repave’s developer portal extends the golden-path library with a **service catalog
overlay** ([ADR 006](adr/006-service-catalog-and-maturity.md)): maturity levels,
team views, initiatives, and GitOps sandboxes parameterized by workload profiles.

AI-assisted scaffolding stays on the [v3 roadmap](roadmap.md#beyond-v200--autonomous-estate-and-lifecycle-control-plane).

## Enablement

```yaml
service_catalog:
  enabled: true
  maturity_rubric: config/maturity-rubric.yaml
  workload_profiles: config/workload-profiles.yaml
  deployment_sets: config/deployment-sets.yaml
  initiatives: data/initiatives.jsonl
  default_team: platform

environment_vending:
  enabled: true
  gitops_repo: https://github.com/org/platform-gitops
  file: data/environments/registry.jsonl
  ttl_hours_by_class:
    sandbox: 168
  auto_reclaim_classes: [sandbox]
```

Env override: `REPAVE_SERVICE_CATALOG=1`. That flag (or `service_catalog.enabled: true`
without paths) fills `maturity_rubric`, `workload_profiles`, `deployment_sets`, and
`initiatives` from `examples/platform-dev/` when those files exist, otherwise the
documented `config/` and `data/` paths. `make serve` sets the env flag so Platform
maturity and initiatives collect without a copied config. Compose sets the
same env. The Backstage Helm overlay (`values-backstage.yaml`) sets
`serviceCatalog.enabled` and mounts bundled fixtures — sandbox vend 404s
without that overlay.

Local demo: `make platform-dev-setup && make serve` — see
[`examples/platform-dev/README.md`](../examples/platform-dev/README.md).

## Surfaces

| Route | Audience | Purpose |
| --- | --- | --- |
| `/home` | Builders | My services (owner / default team filter) |
| `/teams/{slug}` | Builders | Team maturity + initiatives |
| `/sandbox` | Builders | Request environment from a deployment set |
| `/library` | Builders | Maturity pills + initiative chips on entities |
| `/services/{id}` | Builders | Tabs: overview, scorecard, dependencies, initiatives |
| `/platform/maturity` | Admins | Fleet maturity distribution + heatmap |
| `/platform/initiatives` | Admins | Progress rollup + create / edit / deactivate |
| Backstage `/maturity` | Admins | Maturity + initiative create / edit / deactivate via `/api/v2` |

## APIs

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/v2/catalog/entities?team=&owner=` | viewer+ |
| `GET` | `/api/v2/catalog/entities/{id}` | viewer+ (includes `maturity`, `initiatives`) |
| `GET` | `/api/v2/deployment-sets` | viewer+ |
| `POST` | `/api/v2/environments/vend` | generator, admin |
| `GET` | `/api/v2/platform/maturity` | admin |
| `GET` | `/api/v2/platform/initiatives` | admin |
| `POST` | `/api/v2/platform/initiatives` | admin |
| `PATCH` | `/api/v2/platform/initiatives/{id}` | admin |
| `DELETE` | `/api/v2/platform/initiatives/{id}` | admin (soft-deactivate) |

## Maturity rubric

Levels are declarative. Each level lists scorecard dimension keys with a minimum
outcome (`pass` / `warn` / …), or custom kinds (`has_oncall`, `has_dependencies`).
The entity receives the **highest** level whose rules all pass.

## Workload profiles and deployment sets

Profiles name a blueprint + default inputs. Deployment sets bind a profile to
`class`, TTL, and stack inputs. `/sandbox` builds an ADR 003 `environment_vend`
payload — GitOps PR only; no apply credentials in repave. JSON clients use
`GET /api/v2/deployment-sets` and `POST /api/v2/environments/vend` (Backstage
`/sandbox` included).

## Initiatives

JSONL store of improvement programs (`title`, `target_level`, `target_rule_keys`,
`due_date`, `owning_team`, `active`). Admins create, edit, and soft-deactivate rows from
`/platform/initiatives` or the v2 API. Inactive programs are hidden from entity chips and
active rollups; the portal lists them under **Inactive** with a reactivate action.
Entity detail shows pass/fail per active initiative.

## Related

- [ADR 006](adr/006-service-catalog-and-maturity.md)
- [ADR 003 — environment lifecycle](adr/003-environment-lifecycle-and-live-state.md)
- [Platform console](platform-console.md)
- [Portal design](portal-design.md)
