# ADR 006: Service catalog overlay, maturity, and GitOps sandboxes

**Status:** Accepted — Phase 1 + Phase 2 (initiatives CRUD) shipped on `main`  
**Date:** 2026-08-10
**Amendment (2026-08-16):** Hosted Helm chart defaults `repave.serviceCatalog.enabled`
and `bundleExamples` **on** so Backstage `/sandbox` / `/maturity` do not 404.
Engine `load_service_catalog_config` stays off unless config or
`REPAVE_SERVICE_CATALOG`. Kind/smoke keep Backstage off; catalog fixtures are
small ConfigMaps.  
**Scope:** portal catalog read models, `repave.config.yaml` `service_catalog` block,
environment vending parameterization, platform console maturity surfaces — v2.x line

## Context

repave already ships a golden-path catalog, library entities with fixed scorecard dimensions,
fleet/admin platform console pages, and GitOps environment vending
([ADR 003](003-environment-lifecycle-and-live-state.md)). Product direction asks for three
adjacent IDP shapes without cloning vendor UIs or pulling AI forward from v3:

1. **OpsLevel-style maturity** — configurable rubrics over existing scorecard signals, fleet
   maturity reporting, ownership/on-call metadata.
2. **Humanitec-style sandbox (no AI)** — named workload profiles and deployment sets that
   parameterize environment vending; self-service `/sandbox` UX.
3. **Cortex-style developer density** — "My services" home, team pages, initiatives over
   scorecards — keeping the night-ops theme from [`portal-design.md`](../portal-design.md).

Constraints:

1. **Do not fork the catalog.** Extend `CatalogEntity` via enrichment (`dataclasses.replace`),
   not a second entity store.
2. **GitOps-only sandboxes.** No `terraform apply` in repave; profiles only fill ADR 003
   vend requests.
3. **Deterministic rules.** Maturity and initiatives evaluate config + scorecard data.
   Conversational / AI suggestions stay [v3](../roadmap.md#beyond-v200--autonomous-estate-and-lifecycle-control-plane).
4. **Engine off by default** unless `service_catalog.enabled` or
   `REPAVE_SERVICE_CATALOG` (or platform-dev / developer-lab paths). The hosted
   Helm chart defaults the overlay **on** with bundled fixtures.

## Decision

### Catalog overlay

Add `service_catalog` config:

```yaml
service_catalog:
  enabled: true
  maturity_rubric: config/maturity-rubric.yaml
  workload_profiles: config/workload-profiles.yaml
  deployment_sets: config/deployment-sets.yaml
  initiatives: data/initiatives.jsonl
  default_team: platform
```

`service_catalog_overlay.py` enriches entities with team slug, on-call, dependencies
(from `catalog-info.yaml` `spec.dependsOn` / `repave.dev/oncall`), maturity results, initiative
badges, and optional workload profile id.

### Maturity rubric

`maturity_rubric.yaml` maps levels (1–5) to required scorecard dimension outcomes
(`pins`/`pass`, `has-runbook`/`pass`, …) and optional custom checks. Pure evaluator
`evaluate_maturity(entity, rubric) -> MaturityResult`. Platform page
`/platform/maturity` + `GET /api/v2/platform/maturity`.

### Workload profiles and deployment sets

YAML catalogs name blueprint + default inputs (`workload_profiles`) and stack class/TTL
(`deployment_sets`). `/sandbox` pre-fills ADR 003 vend payloads. No new apply path.

### Developer hub and initiatives

- `GET /home` — services matching the session user (email / owner substring) or
  `default_team` when auth is off.
- `GET /teams/{slug}` — filtered library + maturity summary.
- Initiatives JSONL store with admin list/create/update/deactivate on
  `/platform/initiatives` and `/api/v2/platform/initiatives` (POST/PATCH/DELETE soft-deactivate).

### AI deferral

Initiative **suggestions**, natural-language env creation, and copilot chat remain v3.
Rule evaluation and rubric scoring stay deterministic forever.

## Consequences

- Library and catalog APIs gain additive fields; existing clients ignore unknown keys.
- Platform-dev enables `service_catalog` + fixture vending for local demos without live GitOps.
- Entity detail gains dependency and initiative panels without a SPA rewrite.
- Initiative deactivation is soft (`active: false`); inactive rows stay in the JSONL for audit
  and can be reactivated from the portal.

## Non-goals

- Runtime apply / direct Kubernetes namespace vending
- AI-assisted scaffolding (v3)

**Superseded:** “Backstage UI replacement” was a non-goal. Hosted Backstage is
the developer UI — [ADR 011](011-hosted-backstage-idp.md). The catalog overlay
and APIs in this ADR stay; HTML catalog/home/lab pages are deprecated.
