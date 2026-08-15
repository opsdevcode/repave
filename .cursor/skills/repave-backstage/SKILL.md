---
name: repave-backstage
description: >-
  Hosted Backstage IDP in opsdevcode/repave: backstage/ create-app layout,
  repave:generate Scaffolder action, catalog provider, lineage card, Helm
  repave.backstage.enabled, and yarn CI. Use when editing backstage/**,
  Backstage plugins, app-config, or the Backstage chart templates.
---

# repave Backstage (hosted IDP)

**Scope:** `backstage/**`, `deploy/k8s/chart/templates/backstage-*.yaml`,
`.github/workflows/backstage.yml`.

This is a **Yarn / TypeScript** Backstage 1.53 app. Portal no-bundler rules
(`repave.js`, no webpack) **do not apply**. Follow Backstage plugin conventions
and [ADR 011](../../../docs/adr/011-hosted-backstage-idp.md).

## Contracts

- HTTP: **`/api/v2` only**. Never scrape HTML forms or call `/api/v1`.
- Generate: `repave:generate` → `POST /api/v2/generate` (`dry_run`, `inputs`).
- Catalog: generated `catalog-info.yaml` + `GET /api/v2/catalog/entities`.
  Do not fork a second entity store.
- Sandbox: `/sandbox` → `GET /api/v2/deployment-sets` + `POST /api/v2/environments/vend`
  via the Backstage proxy (never scrape HTML `/sandbox`).
- Runs: `/runs` → `GET /api/v2/runs` + `GET /api/v2/runs/{id}` via the same proxy.
- Upgrade: `/upgrade` → `POST /api/v2/upgrades/plan` (preview only; apply stays CLI/operator).
- Local-first: `make serve` / `repave generate` must not require yarn.
- Chart: `repave.backstage.enabled` default **off**. Overlay
  `values-backstage.yaml` sets `portal.html: false` (HTML routes 410) and
  documents same-host `/` → Backstage, `/api` → engine.
- HTML portal: `Sunset` / `Link` on HTML routes; sunset 14 Feb 2027.

## Layout

| Path | Role |
|------|------|
| `backstage/packages/app` | Frontend (`repavePlugin` lineage card) |
| `backstage/packages/backend` | Backend + Auth0 + module wiring |
| `backstage/plugins/scaffolder-backend-module-repave` | `repave:generate` |
| `backstage/plugins/catalog-backend-module-repave` | Entity provider |
| `backstage/plugins/plugin-repave` | Lineage card + `/my-services` + `/sandbox` + `/runs` + `/upgrade` |
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
- Portal JS (separate surface): `.cursor/skills/repave-javascript/SKILL.md`
