# Service registry and inventory (observability)

Version: 1.0.0

Service-centric observability golden paths (`observability-as-code-generic`,
`dashboards-as-code-generic`) treat **service_name** as the primary governance key.
Labels, runbooks, notification routing, and repo naming all derive from that id.

## Two sources of truth

| Source | Role |
| --- | --- |
| `observability/catalog.json` | Curated estate defaults — org, team, runbook URLs, notification presets |
| `modules_root` inventory | Live list of services already provisioned as golden-path repos |

The portal **Service** dropdown merges both: catalog entries win on id conflicts;
repos under `modules_root` with `spec.artifactType: observability` and names
`observability-*` or `dashboards-*` contribute discovered services read from
`spec.observability.service_name`.

Configure `output.modules_root` in `repave.config.yaml` (same root used for
Terraform module inventory).

## Governance linkage

Every generated observability repo records:

- Domain standard pin (`standards/observability/observability-as-code.md` or
  `dashboards-as-code.md`)
- Baseline gates from `standards/policy/governance-baseline.md` (`secrets`,
  `docs-drift`, `provenance-drift`, plus artifact-specific gates)

Inventory does not replace catalog governance — it **extends** the dropdown so
teams reuse existing service ids instead of inventing duplicates.

## Operator and API

- `GET /blueprints/{name}/observability-catalog` — merged services with
  `source_kind` (`catalog` | `discovered`)
- `GET /blueprints/{name}/service-inventory` — inventory payload for automation

Future: remote inventory via `GoldenPathRepo.spec.repoURL` (see ADR 001).
