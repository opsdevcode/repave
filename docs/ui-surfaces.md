# UI surfaces: workbench and catalog IDP

How the night-ops HTML portal and hosted Backstage share one control plane.
Decision: [ADR 011](adr/011-hosted-backstage-idp.md). Visual language:
[portal-design.md](portal-design.md). Operator Backstage notes:
[backstage.md](backstage.md).

They do **not** clone each other. They hand off. Shared **product chrome**
(top nav, mark, night-ops tokens) makes the two jobs read as one product.
Do **not** iframe `/idp` into Jinja.

```mermaid
flowchart LR
  subgraph workbench [Repave UI - night-ops]
    generate[Generate / bundles]
    day2[Upgrade / import / verify]
    ops[Vend / sandbox / runs / platform]
  end

  subgraph idp [Backstage - catalog only]
    catalog[Software Catalog]
    graph[Catalog graph]
    search[Search]
    docs[TechDocs]
    org[Org ownership]
    k8s[Kubernetes]
    lineage[Lineage card]
    scaffolder[Optional Scaffolder]
  end

  subgraph plane [Unchanged]
    api["/api/v2"]
    yaml[catalog-info.yaml]
    cli[CLI]
  end

  workbench --> api
  scaffolder --> api
  api --> yaml
  yaml --> catalog
  catalog --> graph
  catalog --> search
  catalog --> docs
  catalog --> org
  catalog --> k8s
  catalog --> lineage
  cli --> api
```

## Who owns what

| Job | Owner | Why |
| --- | --- | --- |
| Generate, upgrade preview, import, verify, vend, sandbox, runs, fleet, platform | **HTML portal** | Night-ops look; `make serve` stays one process |
| Software catalog, graph, search, API docs, import, org, Kubernetes, TechDocs | **Backstage** | Catalog IDP; do not rebuild it in Jinja |
| Offline / CI | **CLI** | Unchanged |
| Apply / cluster | **CLI + operator** | Unchanged |

New `/api/v2` features land in HTML **or** CLI only. Do not add workbench pages
under `backstage/plugins/plugin-repave`.

## Handoff

- Generate (HTML or CLI) writes `catalog-info.yaml`.
- Backstage ingests that file and `GET /api/v2/catalog/entities`.
- HTML **Golden paths** is `/`. **Catalog** is the Backstage nav/button and
  appears when `portal.backstage_url` (or `REPAVE_BACKSTAGE_URL`) is set —
  library, service detail, generate result.
- The lineage card links **Generate in portal** / **Upgrade in portal** using
  `repave.portalBaseUrl` (`REPAVE_PORTAL_BASE_URL`).
- Scaffolder `repave:generate` stays an alternate submit for teams on `/create`.
- Backstage uses the night-ops theme and a top bar that repeats Golden paths,
  Catalog, Library, Upgrade, Verify. Sidebar stays Catalog / My services / Create.
- Entity **Docs** is TechDocs when `backstage.io/techdocs-ref` is set (example:
  `tf-aws-demo`). Generated `catalog-info.yaml` gets that annotation when the
  repo has `docs/` or `mkdocs.yml`. Hosted builds use `runIn: local` (no
  Docker-in-Docker).
- Catalog **graph**, **search**, **API docs**, **import**, **org**, and
  **Kubernetes** stay on Backstage. Generated `catalog-info.yaml` can set
  `spec.dependsOn` / `spec.providesApis` and `backstage.io/kubernetes-*`
  from `catalog_depends_on` / `catalog_provides_apis` /
  `catalog_kubernetes_id` / `catalog_kubernetes_namespace`. Do not clone
  those pages into Jinja.

## Hosted vs laptop

| Context | UI |
| --- | --- |
| `make serve` | HTML workbench. Optional `yarn start` only when working on catalog ingest. |
| Helm + `values-backstage.yaml` | `/` and `/api` → engine (HTML on). `/idp` → Backstage. |
| CLI | No UI. |

`/idp` is the Backstage path prefix so it does not collide with Backstage’s own
`/catalog` route. Set `app.baseUrl` / `repave.backstage.publicBaseUrl` to
`https://<host>/idp` so Catalog is same-origin. Cookies and Auth0 stay one
site. Do **not** iframe `/idp` into Jinja. `portal.html: false` remains an
operator opt-out (HTML 410).

## Related

- [ADR 011](adr/011-hosted-backstage-idp.md)
- [backstage.md](backstage.md)
- [portal-design.md](portal-design.md)
