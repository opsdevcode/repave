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
- Generate: `/generate` lists `GET /api/v2/catalog/blueprints` (includes
  `inputs`); form posts `POST /api/v2/generate` (`dry_run`, `inputs`).
  Scaffolder `repave:generate` remains an alternate submit path.
- Bundles: `/bundles` → `GET /api/v2/bundles` + `GET /api/v2/bundles/{name}`.
- Library: `/library` → `GET /api/v2/library` (`?family=`, `?owner=`).
- Teams: `/teams` → `GET /api/v2/catalog/entities?team=`.
- Services: `/services` → `GET /api/v2/catalog/entities/{id}`; live plan via
  `POST /api/v2/runs` `{ kind: "live_plan", entity_id }`.
- Catalog: generated `catalog-info.yaml` + `GET /api/v2/catalog/entities`.
  Do not fork a second entity store.
- Sandbox: `/sandbox` → `GET /api/v2/deployment-sets` + `POST /api/v2/environments/vend`
  via the Backstage proxy (never scrape HTML `/sandbox`).
- Vend: `/vend` → `GET /api/v2/component-kinds` + `POST /api/v2/components/vend`
  (GitOps component request; not `POST /api/v2/components/plan`).
- Reclaim: `/reclaim` → `POST /api/v2/environments/reclaim` and
  `POST /api/v2/components/reclaim` (admin; dry-run default).
- Runs: `/runs` → `GET /api/v2/runs` + `GET /api/v2/runs/{id}` +
  `POST /api/v2/runs/{id}/replay` (admin; failed/dead-letter only).
  Console: `/run-console?run=` polls the same get/replay contract.
- Upgrade: `/upgrade` → `POST /api/v2/upgrades/plan` (preview only; apply stays CLI/operator).
- Add: `/add` → `POST /api/v2/components/plan` + `/apply` (local checkout; no remote PR).
- Fleet: `/fleet` → `GET` / `POST` / `DELETE /api/v2/fleet` via the same proxy
  (register/unregister need admin; 404 if `fleet.file` / `REPAVE_FLEET_FILE` unset).
- Ops: `/ops` → `GET /api/v2/platform/ops` (admin; reclaim/replay use existing v2).
- Standards: `/standards` → `GET /api/v2/platform/standards` +
  `POST /api/v2/runs` `fleet_drift_confirm`.
- Campaigns: `/campaigns` → `GET /api/v2/platform/campaigns` +
  `POST /api/v2/platform/campaigns/{namespace}/{name}/paused`.
- Import: `/import` → `POST /api/v2/imports/plan` + `/apply` via the same proxy.
- Batch import: `/import/batch` → `POST /api/v2/imports/batch/plan` + `/apply`
  and `POST /api/v2/github/org-scan` (sync classify; async org-scan job stays CLI).
- Verify: `/verify` → `POST /api/v2/verify` (422 is a failed verify, not transport).
- Estate: `/estate` → `GET /api/v2/estate` (404 if `fleet.file` / `REPAVE_FLEET_FILE` unset).
- Adoption: `/adoption` → `GET /api/v2/platform/metrics` (admin; 404 if unset).
- Roadmap: `/roadmap` → `GET /api/v2/platform/roadmap-evidence` (admin; 404 if unset).
- Activity: `/activity` → `GET /api/v2/audit` (404 if audit is unset).
- Maturity: `/maturity` → `GET /api/v2/platform/maturity` + `/initiatives`
  (create/edit/deactivate via POST/PATCH/DELETE).
- Compliance: `/compliance` → `GET /api/v2/platform/compliance`.
- Value stream: `/value-stream` → `GET /api/v2/platform/value-stream`.
- Feedback: `/feedback` → `GET` + `POST /api/v2/platform/feedback` (`surface=backstage`).
- FinOps: `/finops` → `GET /api/v2/platform/finops/export`.
- Local-first: `make serve` / `repave generate` must not require yarn.
- Chart: `repave.backstage.enabled` default **on** (owner: Eric Skaggs).
  Kind/smoke overlays set it off. Overlay `values-backstage.yaml` sets
  `portal.html: false` (HTML routes 410). Chart defaults enable
  `serviceCatalog` with bundled platform-dev fixtures (sandbox vend 404s
  without it). Overlay documents same-host `/` → Backstage, `/api` → engine.
- HTML portal: `Sunset` / `Link` on HTML routes; sunset 14 Feb 2027.
- Smoke: `make chart-smoke-backstage` (CI job `chart-smoke-backstage`, path-gated).
  Guest-only: do not set blank `AUTH0_*`. Catalog provider must not fail
  connect() if the engine is still starting.
- Publish: `container.yml` matrix key `backstage` → `ghcr.io/opsdevcode/repave-backstage`
  after `deploy/k8s/hack/build-backstage-bundle.sh`. Flag defaults on.

## Layout

| Path | Role |
|------|------|
| `backstage/packages/app` | Frontend (`repavePlugin` lineage card) |
| `backstage/packages/backend` | Backend + Auth0 + module wiring |
| `backstage/plugins/scaffolder-backend-module-repave` | `repave:generate` |
| `backstage/plugins/catalog-backend-module-repave` | Entity provider |
| `backstage/plugins/plugin-repave` | Lineage card + pages (`/generate` … `/finops`, `/import/batch`, `/add`, `/vend`) |
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
