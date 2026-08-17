# ADR 011: Hosted Backstage as the catalog IDP

**Status:** Accepted — amended 2026-08-17. Backstage is the **catalog IDP**
(ingest, lineage, optional Scaffolder). The night-ops HTML portal is the
**hosted workbench**. Phase 2–3 parity plugins and Phase 4 HTML removal are
**superseded**.
**Amendment (2026-08-17):** Split by job. Do not clone workbench routes into
Backstage. HTML is the growing UI. Backstage keeps catalog provider, lineage
card, My services (catalog filter), and `repave:generate`. Hosted overlay keeps
`portal.html: true`. Same-host ingress is `/` + `/api` → engine, `/idp` →
Backstage. Shared product chrome: HTML `/` is **Golden paths**; **Catalog** is
Backstage (`app.baseUrl` = `https://<host>/idp`). Night-ops theme + top bar on
Backstage. Do not iframe `/idp`. See [`docs/ui-surfaces.md`](../ui-surfaces.md).
**Amendment (2026-08-16):** Owner **Eric Skaggs**. `repave.backstage.enabled`
defaults **on**. Kind/smoke overlays keep it off.
**Date:** 2026-08-14
**Scope:** developer-facing UI, Helm chart, `/api/v2` as the only HTTP contract
Backstage may call. Does not rename CLI, PyPI, CRDs, or `repave.dev/*` annotations.
**Related:** [ADR 006](006-service-catalog-and-maturity.md) (catalog overlay; no
second entity store),
[ADR 009](009-v3-product-identity.md) (display name **repave**),
[ADR 002](002-v2-service-decomposition.md) (local-first; API/worker split),
[`docs/ui-surfaces.md`](../ui-surfaces.md),
[`docs/backstage.md`](../backstage.md),
[`docs/portal-design.md`](../portal-design.md)

## Context

Repave already emits Backstage `catalog-info.yaml` and documents a Scaffolder
`run:shell` snippet. The developer workbench is a custom FastAPI HTML portal
(night-ops): catalog, generate, upgrade, import, verify, sandbox, and the
platform console.

Backstage already owns software catalog, ownership, Scaffolder, and TechDocs.
Cloning every `/api/v2` workbench page into `plugin-repave` created a second
full portal (generic MUI forms) without the night-ops look. That dual UI is
the cost to stop.

Local-first (ADR 002) still holds: the full generate loop must work without a
cluster. CLI remains the offline path. `make serve` keeps the HTML workbench
(no yarn).

## Decision

**Repave hosts Backstage as the catalog IDP next to `/api/v2`. The FastAPI HTML
portal is the hosted and local workbench. CLI and `/api/v2` stay the control
plane.**

- Display name stays **repave** (ADR 009). Backstage is not a rename.
- Backstage may call **`/api/v2` only**. Do not scrape HTML forms or `/api/v1`.
- Catalog source of truth stays generated `catalog-info.yaml` plus existing catalog
  APIs. Do not fork a second entity store (ADR 006 overlay constraint still holds).
- Backstage scope is **catalog ingest**, **lineage card**, **My services** (filter
  on `repave.dev/blueprint`), and Scaffolder **`repave:generate`**. Do not add
  workbench pages under `backstage/plugins/plugin-repave`.
- New `/api/v2` features land in HTML **or** CLI only — not both UIs.
- White-label (`portal.logo_url` / `portal.accent_color`) is shared: HTML and
  the Backstage night-ops chrome both read those values. Optional
  `portal.backstage_url` enables the **Catalog** nav/button (not an iframe).
- Fine-grained Auth0 FGA stays parking-lot (ADR 010+). The Sign-In Resolver maps
  groups the same way `auth.oidc.roles` does today.
- Chart flag `repave.backstage.enabled` defaults **on** (owner: Eric Skaggs).
  Kind/smoke overlays keep it off. Hosted overlay keeps `portal.html: true`.
- Same-host Ingress (opt-in): `/` → HTML, `/api` → engine, `/idp` → Backstage.
  `/idp` avoids colliding with Backstage’s own `/catalog` route.

### Phases

| Phase | Outcome |
| --- | --- |
| 1 — this ADR | In-repo `backstage/` app, `repave:generate` action, lineage card, chart |
| 2–3 | **Superseded (2026-08-17).** Parity plugins and HTML 410 cutover were the wrong scope. |
| 4 | **Cancelled** for the workbench. Do not delete Jinja. Delete plugin clones instead. |

HTML portal sunset (14 Feb 2027) is **withdrawn**. CLI and `/api/v2` were never
sunset. `portal.html: false` remains an operator opt-out (HTML routes 410).

They work together by **handoff**, not by mirroring:

- Generate (HTML or CLI) writes `catalog-info.yaml`
- Backstage ingests it and shows the entity + lineage card
- HTML **Catalog** links to the Backstage entity page when
  `portal.backstage_url` is set. `/` is **Golden paths**. Do not iframe `/idp`.
- Lineage card “Generate / upgrade” links back to the portal
- Scaffolder `repave:generate` stays an **alternate** submit for `/create`

### Why not the alternatives

**Keep growing two full portals (HTML + plugin clones).**
Rejected. Dual work with a worse copy of the night-ops look.

**Theme Backstage to look like night-ops, then delete HTML.**
Rejected. Rebuilds the portal on Material / the Backstage frontend system and
keeps the upgrade treadmill on every workbench form.

**Delete Backstage hosting; emit `catalog-info.yaml` only.**
Rejected for the hosted catalog demo. Keep the hosted app; do not use it as a
second portal.

**Plugin-only for customer-owned Backstage, no hosted app.**
Useful later as a distribution of the same thin plugins. It does not give
hosted demos a catalog shell.

**Require yarn/Backstage for `make serve`.**
Violates local-first. CLI stays the offline path. HTML stays the laptop UI.

## Consequences

- New Node/yarn surface under `backstage/` with its own CI (`yarn tsc`, lint) and
  image. Portal `repave.js` no-bundler rules do not apply there.
- ADR 006 “Backstage UI replacement” non-goal is struck only for **catalog /
  lineage / Scaffolder**. The workbench UI decision is HTML.
- Platform-admin and builder HTML stay on the night-ops portal. Do not silently
  drop fleet ops.
- Operator CRDs and `kubectl` stay the cluster control plane.
- Earlier 2026-08-16 amendments that pointed hosted HTML at Backstage pages, set
  `portal.html: false`, or scheduled Phase 4 Jinja deletion are superseded by
  the 2026-08-17 amendment.
