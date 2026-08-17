---
name: repave-backstage
description: >-
  Hosted Backstage catalog IDP in opsdevcode/repave: backstage/ create-app layout,
  repave:generate Scaffolder action, catalog provider, lineage card, Helm
  repave.backstage.enabled, and yarn CI. Use when editing backstage/**,
  Backstage plugins, app-config, or the Backstage chart templates.
---

# repave Backstage (catalog IDP)

**Scope:** `backstage/**`, `deploy/k8s/chart/templates/backstage-*.yaml`,
`.github/workflows/backstage.yml`.

This is a **Yarn / TypeScript** Backstage 1.53 app. Portal no-bundler rules
(`repave.js`, no webpack) **do not apply**. Follow Backstage plugin conventions
and [ADR 011](../../../docs/adr/011-hosted-backstage-idp.md).
Surfaces: [`docs/ui-surfaces.md`](../../../docs/ui-surfaces.md).

## Contracts

- HTTP: **`/api/v2` only**. Never scrape HTML forms or call `/api/v1`.
- Catalog: generated `catalog-info.yaml` + `GET /api/v2/catalog/entities`.
  Do not fork a second entity store.
- Lineage card: `repave.dev/*` pins plus Generate / upgrade links to the HTML
  portal (`repave.portalBaseUrl`).
- TechDocs: frontend `@backstage/plugin-techdocs/alpha` on the entity Docs tab.
  Example `tf-aws-demo` uses `backstage.io/techdocs-ref: dir:.`. Engine emit
  adds that annotation when `docs/` or `mkdocs.yml` exists. Do not clone
  TechDocs into Jinja.
- My services: `/my-services` filters catalog components with
  `repave.dev/blueprint`.
- Scaffolder `repave:generate` remains an **alternate** submit path
  (`POST /api/v2/generate`). Workbench generate/upgrade/import/verify/vend/runs
  stay on HTML.
- Do **not** add workbench pages under `backstage/plugins/plugin-repave`.
- Local-first: `make serve` / `repave generate` must not require yarn.
- Chart: `repave.backstage.enabled` default **on** (owner: Eric Skaggs).
  Kind/smoke overlays set it off. Overlay `values-backstage.yaml` keeps
  `portal.html: true` and sets `portal.backstage_url: /idp` plus
  `repave.backstage.publicBaseUrl` (`APP_BASE_URL` → `app.baseUrl`) so
  Catalog is `https://<host>/idp`. Same-host `/` + `/api` → engine,
  `/idp` → Backstage. Do not iframe `/idp`.
- Smoke: `make chart-smoke-backstage` (CI job `chart-smoke-backstage`, path-gated).
  Guest-only: do not set blank `AUTH0_*`. Catalog provider must not fail
  connect() if the engine is still starting.
- Publish: `container.yml` matrix key `backstage` → `ghcr.io/opsdevcode/repave-backstage`
  after `deploy/k8s/hack/build-backstage-bundle.sh`. Flag defaults on.

## Layout

| Path | Role |
|------|------|
| `backstage/packages/app` | Frontend (`repavePlugin` lineage card + My services) |
| `backstage/packages/backend` | Backend + Auth0 + module wiring |
| `backstage/plugins/scaffolder-backend-module-repave` | `repave:generate` |
| `backstage/plugins/catalog-backend-module-repave` | Entity provider |
| `backstage/plugins/plugin-repave` | Lineage card + My services |
| `backstage/examples/templates/terraform-module-generic.yaml` | Software Template |

## Quality

```bash
make backstage-lint
cd backstage && yarn test --watch=false
```

Pin versions to the create-app lock (`backstage/backstage.json`). Run
`yarn install` in `backstage/` and commit `yarn.lock`.

## Related

- Operator docs: [`docs/backstage.md`](../../../docs/backstage.md)
- Split-by-job model: [`docs/ui-surfaces.md`](../../../docs/ui-surfaces.md)
- Portal JS (separate surface): `.cursor/skills/repave-javascript/SKILL.md`
