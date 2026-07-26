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

A dedicated HTTP JSON API is available for headless generate:

```http
POST /api/v1/generate
Content-Type: application/json

{
  "blueprint": "terraform-module-generic",
  "dry_run": true,
  "inputs": {
    "module_name": "checkout-vpc",
    "description": "Scaffolder bootstrap",
    "cloud_provider": "aws",
    "provider_services": "s3",
    "owner": "group:platform",
    "include_backstage_catalog": "true"
  }
}
```

When `auth.service_mode` is enabled, the caller must have a `generator` or `admin`
session (browser cookie) or call from an authenticated proxy. See
[`docs/auth-service-mode.md`](auth-service-mode.md).

The portal `POST /generate` form endpoint remains the browser UX. Scaffolder can
use either this JSON API or the CLI in a container action (reuse `deploy/local/Dockerfile`).

### Suggested action inputs

Mirror blueprint inputs (module name, cloud provider, owner, `include_backstage_catalog`,
etc.) as Scaffolder `parameters`, then pass each as `repave generate --input key=value`.

| Scaffolder parameter | repave input | Notes |
| --- | --- | --- |
| `moduleName` | `module_name` | Required for Terraform modules |
| `cloudProvider` | `cloud_provider` | `aws` / `azure` / `gcp` |
| `providerServices` | `provider_services` | Comma-separated catalog services |
| `owner` | `owner` | Backstage entity ref, e.g. `group:platform` |
| `includeBackstageCatalog` | `include_backstage_catalog` | `true` for Terraform/Helm catalog emission |
| `serviceName` | `service_name` | App-service / Helm chart names |

### Full Software Template sketch

Use a **container** or **run:shell`** step with the repave image from `deploy/local/Dockerfile`
(or a published `repave-engine` image). Mount `repave.config.yaml`, blueprint packs, and
`REPAVE_MODULES_ROOT` the same way as local Compose.

```yaml
apiVersion: scaffolder.backstage.io/v1beta3
kind: Template
metadata:
  name: repave-terraform-module
  title: Terraform module (repave)
spec:
  owner: group:platform
  type: service
  parameters:
    - title: Module
      required:
        - moduleName
        - cloudProvider
        - owner
      properties:
        moduleName:
          type: string
        cloudProvider:
          type: string
          enum: [aws, azure, gcp]
        owner:
          type: string
          default: group:platform
  steps:
    - id: generate
      name: repave generate
      action: run:shell
      input:
        command: |
          set -euo pipefail
          repave generate \
            --blueprint blueprints/terraform-module-generic \
            --input "module_name=${{ parameters.moduleName }}" \
            --input "description=Scaffolder bootstrap" \
            --input "cloud_provider=${{ parameters.cloudProvider }}" \
            --input "provider_services=s3" \
            --input "owner=${{ parameters.owner }}" \
            --input "include_backstage_catalog=true" \
            --dry-run \
            --staging-root ./generated
    - id: publish
      name: Publish module repository
      action: run:shell
      input:
        command: |
          repave generate \
            --blueprint blueprints/terraform-module-generic \
            ...same inputs... \
            --no-dry-run
      # Requires GITHUB_TOKEN and repave.config.yaml output.modules_root in the action environment.
  output:
    links:
      - title: Generated tree
        url: ./generated
```

After publish, register a **Location** targeting the new repository’s `catalog-info.yaml`
(when enabled) or add the repo to your org catalog repo.

### Verification checklist

1. `catalog-info.yaml` validates against [`standards/backstage/catalog-standard.md`](../standards/backstage/catalog-standard.md).
2. Repave annotations include blueprint and standard pins for TechInsights-style checks.
3. Dry-run gates pass in CI before `--no-dry-run` publish (same gates as the portal).

## Related docs

- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — merge queue and CI on `main`
- [`concepts.md`](concepts.md) — golden paths and provenance
- [`blueprints/_partials/catalog-inputs.yaml`](../blueprints/_partials/catalog-inputs.yaml) — input reference for authors
