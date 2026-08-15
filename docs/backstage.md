# Hosted Backstage (IDP UI)

Repave hosts [Backstage](https://backstage.io/) as the developer-facing UI
([ADR 011](adr/011-hosted-backstage-idp.md)). The engine CLI and `/api/v2` stay
the control plane. Local generate does **not** require yarn or Backstage
(`make serve` / `repave generate`).

The FastAPI HTML portal (`/home`, `/lab`, `/generate`, `/platform/*`, …) is
**deprecated** for hosted installs. It still ships in this release.

**HTML portal sunset:** Sat, 14 Feb 2027 00:00:00 GMT.

After that date, Phase 4 removes the Jinja templates. CLI and `/api/v2` are not
sunset. Platform-admin HTML becomes Backstage plugins or CLI/API-only — fleet
ops are not dropped silently.

## What you get

| Piece | Path / contract |
| --- | --- |
| App we own | [`backstage/`](../backstage/) (`packages/app`, `packages/backend`) |
| Generate | Scaffolder action `repave:generate` → `POST /api/v2/generate` |
| Template | `terraform-module-generic` with `include_backstage_catalog: true` |
| Catalog | `catalog-info.yaml` file locations **and** `GET /api/v2/catalog/entities` |
| Lineage card | Entity page shows `repave.dev/*` pins |
| My services | `/my-services` — components with `repave.dev/blueprint` |
| Sandbox | `/sandbox` — `GET /api/v2/deployment-sets` + `POST /api/v2/environments/vend` |
| Runs | `/runs` — `GET /api/v2/runs` + `GET /api/v2/runs/{id}` |
| Upgrade | `/upgrade` — `POST /api/v2/upgrades/plan` (preview; apply stays CLI/operator) |
| Helm | `repave.backstage.enabled` (**default off**); overlay sets `portal.html: false` |

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

Guest auth is on for local-first. The hosted image stays guest-only unless
`AUTH0_CLIENT_ID` is set (then it loads `app-config.auth0.yaml`). Empty
`${AUTH0_*:-}` still fails provider init — do not set blank Auth0 env in
chart-smoke. Hosted Auth0 uses the same tenant as
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
want Auth0; omit them for guest-only / chart-smoke. The overlay sets `portal.html: false` so HTML
routes return **410** with `Sunset` / `Link` (14 Feb 2027). It also sets
`repave.serviceCatalog.enabled` and mounts bundled
`examples/platform-dev` catalog YAML so `/sandbox` vend does not 404.
CLI and `/api/v2` stay. Same-host Ingress (opt-in): `/` → Backstage,
`/api` → engine (`ingress.enabled` + `repave.backstage.ingress.enabled`).

Image: `ghcr.io/opsdevcode/repave-backstage` (build from
[`backstage/packages/backend/Dockerfile`](../backstage/packages/backend/Dockerfile)
with context `backstage/` after `yarn tsc && yarn build:backend`).

`make chart-smoke-backstage` builds the engine + Backstage images, installs
`values-kind.yaml` + `values-backstage.yaml` on kind, and probes engine
`/health` + `/api/v2`, HTML **410**, and Backstage liveness/readiness.
CI runs that job when Backstage or overlay paths change. The flag stays
**default off** until a named owner takes the Backstage release treadmill.
`make chart-validate` renders the Deployment when the flag is on.

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

Sandbox (`/sandbox`), Runs (`/runs`), and Upgrade (`/upgrade`) call the engine
through the Backstage proxy (`/api/proxy/repave/api/v2/...`) so the browser
never holds `REPAVE_API_TOKEN`. Local `app-config.yaml` targets
`http://127.0.0.1:8088`; the production image uses `REPAVE_API_BASE_URL`.

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

Standard shape: [`standards/backstage/catalog-standard.md`](../standards/backstage/catalog-standard.md).

**Ingest**

1. File / GitHub Location targeting `catalog-info.yaml` (org discovery or a
   single repo URL).
2. `RepaveEntityProvider` polls `GET /api/v2/catalog/entities` when
   `repave.apiBaseUrl` is set. Idle (no error) when unset so `yarn start`
   without an API still loads example entities.

The entity page **Repave lineage** card shows those annotations. Sample:
`tf-aws-demo` in [`backstage/examples/entities.yaml`](../backstage/examples/entities.yaml).

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

## Later phases (same theme)

| Phase | Outcome |
| --- | --- |
| 2 | My services + sandbox + runs + upgrade preview — **shipped** |
| 3 | Ingress flip; HTML `Sunset`/`Link`; overlay `portal.html: false` — **shipped** |
| 4 | Delete HTML templates; FastAPI is API-only (no calendar gate) |
| — | Chart-smoke boots Backstage (this slice); flag stays default off |

## Related

- [ADR 011](adr/011-hosted-backstage-idp.md)
- [ADR 006](adr/006-service-catalog-and-maturity.md) — catalog overlay (not a second store)
- [portal-design.md](portal-design.md) — Visual v3 sunset note
- [auth-service-mode.md](auth-service-mode.md)
- [concepts.md](concepts.md)
