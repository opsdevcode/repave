# Backstage catalog standard (v1.0.0)

Generated repositories may include a **Backstage Software Catalog** descriptor at
`catalog-info.yaml`. The repave engine writes this file after Copier render when
the golden path requires it (`app-service`) or when `include_backstage_catalog`
is `true` (Terraform modules, Helm charts).

## Component shape

- **kind:** `Component`
- **metadata.name:** Primary artifact id (`service_name`, `module_name`, or `chart_name`)
- **metadata.description:** Blueprint `description` input
- **metadata.annotations:** Repave lineage for TechInsights-style checks:
  - `repave.dev/blueprint`, `repave.dev/blueprint-version`
  - `repave.dev/standard-source`, `repave.dev/standard-version`
  - `repave.dev/engine-version`, `repave.dev/artifact-type`
  - `backstage.io/techdocs-ref: dir:.` when the repo has `docs/` or `mkdocs.yml`
  - `backstage.io/kubernetes-id` / `backstage.io/kubernetes-namespace` when
    `catalog_kubernetes_id` / `catalog_kubernetes_namespace` are set
  - `github.com/project-slug` / `backstage.io/source-location` when
    `catalog_github_slug` (or `github_org` + `github_repo`) is set
- **metadata.tags / metadata.links:** Optional from `catalog_tags` / `catalog_links`
- **spec.type:** `service` (app-service, Helm) or `library` (Terraform modules)
- **spec.owner:** Team or group ref (required for app-service; required when catalog is enabled)
- **spec.system:** Optional platform system name
- **spec.lifecycle:** `experimental`, `production`, or `deprecated`
- **spec.dependsOn:** Optional entity refs from `catalog_depends_on` (catalog graph)
- **spec.providesApis:** Optional API refs from `catalog_provides_apis`
- **spec.consumesApis:** Optional API refs from `catalog_consumes_apis`
- **spec.subcomponentOf:** Optional parent component ref from `catalog_subcomponent_of`

## Import

Register the generated git repository as a **Location** in Backstage (file path
`catalog-info.yaml` at repo root) or use the Scaffolder flow in
[`docs/backstage.md`](../../docs/backstage.md).

## Governance

`docs-drift` and `provenance-drift` gates still apply; catalog metadata does not
replace `repave.yaml` provenance.
