# ADR 011: Hosted Backstage as the IDP UI

**Status:** Accepted — Phase 1 (hosted app, generate action, catalog card, default-off
chart) lands with this decision. HTML portal is deprecated, not deleted.
**Date:** 2026-08-14
**Scope:** developer-facing UI, Helm chart, `/api/v2` as the only HTTP contract
Backstage may call. Does not rename CLI, PyPI, CRDs, or `repave.dev/*` annotations.
**Related:** [ADR 006](006-service-catalog-and-maturity.md) (catalog overlay; UI
replacement was a non-goal — superseded here),
[ADR 009](009-v3-product-identity.md) (display name **repave**),
[ADR 002](002-v2-service-decomposition.md) (local-first; API/worker split),
[`docs/backstage.md`](../backstage.md),
[`docs/portal-design.md`](../portal-design.md)

## Context

Repave already emits Backstage `catalog-info.yaml` and documents a Scaffolder
`run:shell` snippet. The developer IDP shell is still a custom FastAPI HTML portal
(~46 templates): catalog, My services, lab, generate forms, upgrade, import, verify,
and the platform console.

That shell duplicates what Backstage already owns (catalog, ownership, Scaffolder,
TechDocs). Growing `/home`, `/lab`, and library HTML is a second IDP, not a
differentiation. Differentiation stays in the engine: gates, golden paths, operator,
`/api/v2`.

Local-first (ADR 002) still holds: the full generate loop must work without a
cluster. CLI remains that path. Backstage is the **hosted** IDP.

## Decision

**Repave hosts Backstage as the developer-facing UI. The FastAPI HTML portal is
deprecated on a published window. CLI and `/api/v2` stay the control plane.**

- Display name stays **repave** (ADR 009). Backstage is the shell, not a rename.
- Backstage may call **`/api/v2` only**. Do not scrape HTML forms or `/api/v1`.
- Catalog source of truth stays generated `catalog-info.yaml` plus existing catalog
  APIs. Do not fork a second entity store (ADR 006 overlay constraint still holds).
- White-label (`portal.logo_url` / `portal.accent_color`) maps to Backstage
  `app-config` branding.
- Fine-grained Auth0 FGA stays parking-lot (ADR 010+). The Sign-In Resolver maps
  groups the same way `auth.oidc.roles` does today.
- Chart flag `repave.backstage.enabled` ships **default off** until
  `make chart-smoke-backstage` boots the image. Ingress may split `/` → Backstage
  and `/api` → engine, or use a second host.
- Named owner required before hosted values default the flag on (Backstage release
  treadmill — same class of cost as ADR 004).

### Phases

| Phase | Outcome |
| --- | --- |
| 1 — this ADR | In-repo `backstage/` app, `repave:generate` action, lineage card, default-off chart |
| 2 | Parity plugins: My services, sandbox vend, upgrade/auto-merge, runs |
| 3 | Ingress flip; HTML routes send `Sunset` + `Link`; hosted overlay sets `portal.html: false` (engine/`make serve` stays true) |
| 4 | Remove HTML templates after the published window; FastAPI is API-only |

HTML portal sunset for hosted installs: **Sat, 14 Feb 2027 00:00:00 GMT**.
Removal of templates is Phase 4 after that date. CLI and `/api/v2` are not sunset.

### Why not the alternatives

**Keep growing the custom portal and treat Backstage as an optional export.**
Rejected. Catalog/home/lab HTML is a second IDP. We already emit the catalog
contract Backstage consumes.

**Plugin-only for customer-owned Backstage, no hosted app.** Useful later as a
distribution of the same plugins. It does not give hosted demos or the default
product UI a Backstage shell.

**Delete HTML templates in the same PR as the scaffold.** Unreviewable; drops
fleet/import/verify/platform ops with no Backstage replacement.

**Require yarn/Backstage for `make serve`.** Violates local-first. CLI stays the
offline path.

## Consequences

- New Node/yarn surface under `backstage/` with its own CI (`yarn tsc`, lint) and
  image. Portal `repave.js` no-bundler rules do not apply there.
- ADR 006 “Backstage UI replacement” non-goal is struck; this ADR owns the UI
  decision.
- Platform-admin HTML (`/platform/*`, `/estate`) becomes Backstage admin plugins
  in Phase 2–3 or CLI/API-only — do not silently drop fleet ops.
- Operator CRDs and `kubectl` stay the cluster control plane.
