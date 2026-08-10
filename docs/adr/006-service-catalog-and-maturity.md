# ADR 006: Service catalog overlay, maturity, and GitOps sandboxes

**Status:** Accepted — Phase 1 implementation in progress  
**Date:** 2026-08-10  
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
4. **Optional and off by default** unless `service_catalog.enabled` (or platform-dev profile).

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
- Initiatives JSONL store with admin list/create on `/platform/initiatives` (Phase 2 CRUD).

### AI deferral

Initiative **suggestions**, natural-language env creation, and copilot chat remain v3.
Rule evaluation and rubric scoring stay deterministic forever.

## Consequences

- Library and catalog APIs gain additive fields; existing clients ignore unknown keys.
- Platform-dev enables `service_catalog` + fixture vending for local demos without live GitOps.
- Entity detail gains dependency and initiative panels without a SPA rewrite.

## Non-goals

- Backstage UI replacement
- Runtime apply / direct Kubernetes namespace vending
- AI-assisted scaffolding (v3)
