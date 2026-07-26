# Backstage integration

Repave can emit a [Backstage Software Catalog](https://backstage.io/docs/features/software-catalog/)
`catalog-info.yaml` in generated repositories so platform teams register golden-path
artifacts alongside hand-written services.

## When catalog-info is generated

| Golden path | Default | Inputs |
| --- | --- | --- |
| `app-service-generic` | Always | `owner` (required), `system`, `catalog_lifecycle`, `description` |
| `helm-chart-generic` | Off | Set `include_backstage_catalog` to `true` and provide `owner` |
| `terraform-module-generic` | Off | Same optional inputs as Helm |

The engine writes the file **after** Copier render (see `backstage_catalog.py`) so
Repave lineage annotations stay aligned with the blueprint pin, standard version, and
engine release used at generate time.

## Annotations (TechInsights / custom processors)

Each component includes:

| Annotation | Meaning |
| --- | --- |
| `repave.dev/blueprint` | Blueprint name (e.g. `terraform-module-generic`) |
| `repave.dev/blueprint-version` | Blueprint semver from `blueprint.yaml` |
| `repave.dev/standard-source` | Pinned standards path |
| `repave.dev/standard-version` | Pinned standards semver |
| `repave.dev/engine-version` | `repave-engine` version that performed generate |
| `repave.dev/artifact-type` | Golden-path artifact type |

Standard shape and lifecycle values are documented in
[`standards/backstage/catalog-standard.md`](../standards/backstage/catalog-standard.md).

## Import into Backstage

1. Generate or publish the golden-path repository (portal dry-run or `repave generate`).
2. In Backstage, register a **Location** pointing at the repo URL with target
   `catalog-info.yaml`, or add the file path to an existing org-wide catalog location.
3. Confirm the **Component** appears with the expected owner, system, and Repave
   annotations.

Example location snippet:

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

## Scaffolder custom action (repave golden paths)

Backstage [custom actions](https://backstage.io/docs/features/software-templates/writing-custom-actions/)
can call repave without the web portal. The stable contract today is the **repave CLI**
(shipped in the engine package and `deploy/local` images):

```yaml
# Template excerpt — run repave generate from a Scaffolder workspace step
steps:
  - id: generate
    name: Generate golden path
    action: run:shell
    input:
      command: |
        repave generate \
          --blueprint blueprints/terraform-module-generic \
          --input module_name=${{ parameters.moduleName }} \
          --input description="${{ parameters.description }}" \
          --input cloud_provider=${{ parameters.cloudProvider }} \
          --input provider_services=${{ parameters.providerServices }} \
          --input include_backstage_catalog=true \
          --input owner=${{ parameters.owner }} \
          --dry-run \
          --staging-root ./generated
```

For production Scaffolder flows:

1. **Dry-run in CI or Scaffolder** — validate gates locally (`repave generate --dry-run`).
2. **Publish** — re-run with `--no-dry-run` and `GITHUB_TOKEN` (same as portal publish),
   or push the workspace output to a target repo your action creates.
3. **Catalog** — commit includes `catalog-info.yaml` when enabled; register the new repo
   in Backstage via Location API or an org catalog repo.

A dedicated HTTP JSON API for headless generate is not required for v1.32; the portal
`POST /generate` form endpoint remains the browser UX. Scaffolder integrations should
prefer the CLI in a container action (reuse `deploy/local/Dockerfile` tooling) until a
stable REST contract is published as a follow-up.

### Suggested action inputs

Mirror blueprint inputs (module name, cloud provider, owner, `include_backstage_catalog`,
etc.) as Scaffolder `parameters`, then pass each as `repave generate --input key=value`.

## Related docs

- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — merge queue and CI on `main`
- [`concepts.md`](concepts.md) — golden paths and provenance
- [`blueprints/_partials/catalog-inputs.yaml`](../blueprints/_partials/catalog-inputs.yaml) — input reference for authors
