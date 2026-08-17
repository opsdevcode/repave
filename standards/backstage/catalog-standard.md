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
- **spec.type:** `service` (app-service, Helm) or `library` (Terraform modules)
- **spec.owner:** Team or group ref (required for app-service; required when catalog is enabled)
- **spec.system:** Optional platform system name
- **spec.lifecycle:** `experimental`, `production`, or `deprecated`

## Import

Register the generated git repository as a **Location** in Backstage (file path
`catalog-info.yaml` at repo root) or use the Scaffolder flow in
[`docs/backstage.md`](../../docs/backstage.md).

## Governance

`docs-drift` and `provenance-drift` gates still apply; catalog metadata does not
replace `repave.yaml` provenance.
