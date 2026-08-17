# Hosted Backstage (catalog IDP)

Repave hosts [Backstage](https://backstage.io/) as the **catalog IDP**
([ADR 011](adr/011-hosted-backstage-idp.md)). The night-ops HTML portal is the
hosted and local **workbench**. How they hand off:
[`docs/ui-surfaces.md`](ui-surfaces.md). The engine CLI and `/api/v2` stay the
control plane. Local generate does **not** require yarn or Backstage
(`make serve` / `repave generate`).

Do not clone workbench routes into Backstage plugins. Generate, upgrade, import,
verify, vend, sandbox, runs, and platform stay on HTML.

## What you get

| Piece | Path / contract |
| --- | --- |
| App we own | [`backstage/`](../backstage/) (`packages/app`, `packages/backend`) |
| Generate | Scaffolder action `repave:generate` → `POST /api/v2/generate` (alternate to HTML `/generate`) |
| Template | `terraform-module-generic` with `include_backstage_catalog: true` |
| Catalog | `catalog-info.yaml` file locations **and** `GET /api/v2/catalog/entities` |
| Lineage card | Entity page shows `repave.dev/*` pins plus Generate / upgrade links to the portal |
| My services | `/my-services` — catalog filter for components with `repave.dev/blueprint` |
| Helm | `repave.backstage.enabled` (**default on**); overlay keeps `portal.html: true` |

Do not teach Scaffolder to scrape HTML forms or call `/api/v1`.

## Local (optional)

The full golden-path loop stays CLI-first:

```bash
repave generate --blueprint terraform-module-generic --dry-run ...
make serve   # FastAPI HTML + /api/v2; no yarn
```

To run the hosted UI against a local API:

```bash
# terminal 1 — :8089, sets REPAVE_SERVICE_CATALOG=1
make serve
# terminal 2 — proxy defaults to :8089
cd backstage && yarn install && yarn start
```

Sandbox vend 404s with `Service catalog is not enabled` if the engine
does not have the catalog overlay. `make serve` turns it on. Compose on
`:8088` sets `REPAVE_SERVICE_CATALOG=1` (restart the stack after pull).
To point Backstage at Compose instead:

```bash
export REPAVE_API_BASE_URL=http://127.0.0.1:8088
```

Guest auth is on for local-first (`app-config.yaml` has no Auth0 block).
The hosted image stays guest-only unless `AUTH0_CLIENT_ID` is set (then
`docker-entrypoint.sh` loads `app-config.auth0.yaml`). Empty
`${AUTH0_*:-}` still fails provider init — do not set blank Auth0 env in
chart-smoke. Local Auth0: `yarn start --config app-config.yaml --config app-config.auth0.yaml`.
Hosted Auth0 uses the same tenant as
[`docs/auth-service-mode.md`](auth-service-mode.md) (`AUTH0_DOMAIN`,
`AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`, `AUTH0_AUDIENCE`).

Quality:

```bash
make backstage-lint   # yarn tsc + lint:all
cd backstage && yarn test --watch=false
```

CI: [`.github/workflows/backstage.yml`](../.github/workflows/backstage.yml).

## Helm

```bash
helm upgrade --install repave ./deploy/k8s/chart \
  -f deploy/k8s/chart/values-backstage.yaml \
  --set repave.output.githubOrg=your-org \
  --set secrets.existingSecret=repave-secrets
```

The Backstage container talks to the in-cluster portal Service
(`REPAVE_API_BASE_URL=http://{{ release }}-repave:8088`) unless you set
`repave.backstage.apiBaseUrl`. Pass `AUTH0_CLIENT_ID` (and the other Auth0
keys) plus `REPAVE_API_TOKEN` through `repave.backstage.extraEnv` when you
want Auth0; omit them for guest-only / chart-smoke. The overlay keeps
`portal.html: true` and sets `portal.backstage_url: /idp` so the HTML **Catalog**
nav/button lands on Backstage. It also sets `repave.backstage.publicBaseUrl` to
`https://repave.example.com/idp` (`APP_BASE_URL` → `app.baseUrl`) so Catalog is
same-host. Do **not** iframe `/idp` into Jinja. Override the host when you cut
over Ingress. It also sets `repave.serviceCatalog.enabled` (chart default) and
mounts bundled `examples/platform-dev` catalog YAML. CLI and `/api/v2` stay.
Same-host Ingress (opt-in): `/` → HTML, `/api` → engine, `/idp` → Backstage
(`ingress.enabled` + `repave.backstage.ingress.enabled`).

Image: `ghcr.io/opsdevcode/repave-backstage`, published by
[`.github/workflows/container.yml`](../.github/workflows/container.yml) on `main`
and semver tags (yarn bundle, then Docker context `backstage/`). Local build:
[`deploy/k8s/hack/build-backstage-bundle.sh`](../deploy/k8s/hack/build-backstage-bundle.sh)
then `docker build -f backstage/packages/backend/Dockerfile`.

`make chart-smoke-backstage` builds the engine + Backstage images, installs
`values-kind.yaml` + `values-backstage.yaml` on kind, and probes engine
`/health` + `/api/v2`, HTML **200**, and Backstage liveness/readiness.
CI runs that job when Backstage or overlay paths change. The flag defaults
**on** (owner: [Eric Skaggs](#ownership)). Kind/smoke overlays keep it off.
`make chart-validate` renders the Deployment from default values.

Production config uses SQLite (`connection.directory: /tmp/backstage-db`) so a
chart install does not need Postgres. Swap in a `client: pg` overlay when you
run a real database.

## Scaffolder: `repave:generate`

The in-repo action posts JSON to `/api/v2/generate` (not `run:shell`):

```yaml
steps:
  - id: generate
    name: repave generate
    action: repave:generate
    input:
      blueprint: terraform-module-generic
      dryRun: true
      inputs:
        module_name: ${{ parameters.moduleName }}
        cloud_provider: ${{ parameters.cloudProvider }}
        include_backstage_catalog: "true"
        owner: ${{ parameters.owner }}
```

Template: [`backstage/examples/templates/terraform-module-generic.yaml`](../backstage/examples/templates/terraform-module-generic.yaml).

Scaffolder and the catalog provider call the engine through the Backstage proxy
(`/api/proxy/repave/api/v2/...`) so the browser never holds `REPAVE_API_TOKEN`.
Local `app-config.yaml` targets `http://127.0.0.1:8089`; the production image
uses `REPAVE_API_BASE_URL`. Lineage “Generate in portal” uses
`repave.portalBaseUrl` (`REPAVE_PORTAL_BASE_URL`, default `/` in the image).

When `auth.service_mode` is on, set `repave.apiToken` / `REPAVE_API_TOKEN` so
the backend sends `Authorization: Bearer`. Return body uses `gates_outcome` and
`rendered_files` from [`generate_api.py`](../engine/src/repave_engine/generate_api.py).

| Scaffolder parameter | `/api/v2` input |
| --- | --- |
| `moduleName` | `module_name` |
| `cloudProvider` | `cloud_provider` |
| `owner` | `owner` |
| `dryRun` | `dry_run` (default true) |

## Catalog and lineage

The engine still writes `catalog-info.yaml` after Copier render
([`backstage_catalog.py`](../engine/src/repave_engine/backstage_catalog.py)).

| Golden path | Default | Inputs |
| --- | --- | --- |
| `app-service-generic` | Always | `owner` (required), `system`, `catalog_lifecycle`, `description` |
| `helm-chart-generic` | Off | `include_backstage_catalog=true` and `owner` |
| `terraform-module-generic` | Off | Same optional inputs as Helm |

Each component includes:

| Annotation | Meaning |
| --- | --- |
| `repave.dev/blueprint` | Blueprint name |
| `repave.dev/blueprint-version` | Blueprint semver |
| `repave.dev/standard-source` | Pinned standards path |
| `repave.dev/standard-version` | Pinned standards semver |
| `repave.dev/engine-version` | Engine release that generated |
| `repave.dev/artifact-type` | Golden-path artifact type |
| `backstage.io/techdocs-ref` | `dir:.` when the repo has `docs/` or `mkdocs.yml` |

Standard shape: [`standards/backstage/catalog-standard.md`](../standards/backstage/catalog-standard.md).

**Ingest**

1. File / GitHub Location targeting `catalog-info.yaml` (org discovery or a
   single repo URL).
2. `RepaveEntityProvider` polls `GET /api/v2/catalog/entities` when
   `repave.apiBaseUrl` is set. Idle (no error) when unset so `yarn start`
   without an API still loads example entities.

The entity page **Repave lineage** card shows those annotations. Sample:
`tf-aws-demo` in [`backstage/examples/entities.yaml`](../backstage/examples/entities.yaml)
(also annotated for TechDocs; source is [`examples/docs/`](../backstage/examples/docs/)
next to `mkdocs.yml`). Open **Catalog** → entity → **Docs**.

| Context | TechDocs generate |
| --- | --- |
| Local `yarn start` | `techdocs.generator.runIn: docker` (needs Docker) |
| Hosted image / chart | `runIn: local` — `mkdocs-techdocs-core==1.7.0` in [`packages/backend/Dockerfile`](../backstage/packages/backend/Dockerfile) so the pod does not need Docker-in-Docker |

Do not iframe or clone Docs into the HTML workbench.

Example Location for a published repo:

```yaml
apiVersion: backstage.io/v1alpha1
kind: Location
metadata:
  name: repave-checkout-api
spec:
  type: url
  targets:
    - https://github.com/example/app-checkout-api/blob/main/catalog-info.yaml
```

## Ownership

`repave.backstage.enabled` defaults **on** ([ADR 011](adr/011-hosted-backstage-idp.md)).
Kind and chart-smoke overlays set it false so engine-only installs do not pull
the Backstage image. Use `values-backstage.yaml` for catalog fixtures and the
same-host `/idp` split (HTML workbench stays on).

**Owner:** Eric Skaggs.

The owner is on the hook for:

- Backstage upstream upgrades (`backstage.json` / yarn lock) and `make backstage-lint`
- `ghcr.io/opsdevcode/repave-backstage` publish via `container.yml`
- `chart-smoke-backstage` staying green when plugin or overlay paths change
- Auth0 / guest boot (never ship blank `AUTH0_*`)
- Keeping the default-on flag honest (opt out in kind/smoke overlays only)

## Later phases (same theme)

| Phase | Outcome |
| --- | --- |
| 1 | Hosted app, `repave:generate`, lineage card — **shipped** |
| 2–3 | Parity plugins and HTML 410 cutover — **superseded** (2026-08-17) |
| 4 | HTML template deletion — **cancelled**; workbench stays Jinja |
| — | Chart-smoke boots Backstage; flag defaults **on** (owner: Eric Skaggs) |

## Related

- [ui-surfaces.md](ui-surfaces.md) — split-by-job model
- [ADR 011](adr/011-hosted-backstage-idp.md)
- [ADR 006](adr/006-service-catalog-and-maturity.md) — catalog overlay (not a second store)
- [portal-design.md](portal-design.md)
- [auth-service-mode.md](auth-service-mode.md)
- [concepts.md](concepts.md)
