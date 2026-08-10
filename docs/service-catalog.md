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

Env override: `REPAVE_SERVICE_CATALOG=1`.

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
| `/platform/initiatives` | Admins | Progress rollup + create initiative |

## APIs

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/v2/catalog/entities?team=&owner=` | viewer+ |
| `GET` | `/api/v2/catalog/entities/{id}` | viewer+ (includes `maturity`, `initiatives`) |
| `GET` | `/api/v2/platform/maturity` | admin |
| `GET` | `/api/v2/platform/initiatives` | admin |

## Maturity rubric

Levels are declarative. Each level lists scorecard dimension keys with a minimum
outcome (`pass` / `warn` / …), or custom kinds (`has_oncall`, `has_dependencies`).
The entity receives the **highest** level whose rules all pass.

## Workload profiles and deployment sets

Profiles name a blueprint + default inputs. Deployment sets bind a profile to
`class`, TTL, and stack inputs. `/sandbox` builds an ADR 003 `environment_vend`
payload — GitOps PR only; no apply credentials in repave.

## Initiatives

JSONL store of improvement programs (`title`, `target_level`, `target_rule_keys`,
`due_date`, `owning_team`). Admins create rows from `/platform/initiatives`;
entity detail shows pass/fail per active initiative.

## Related

- [ADR 006](adr/006-service-catalog-and-maturity.md)
- [ADR 003 — environment lifecycle](adr/003-environment-lifecycle-and-live-state.md)
- [Platform console](platform-console.md)
- [Portal design](portal-design.md)
