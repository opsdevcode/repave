# v2.0.0 migration guide (in progress)

v2.0.0 introduces breaking contracts for blueprints and generated module
repositories. This guide tracks what is landing before the v2.0.0 release tag.

## Blueprint API v1beta1

**Breaking:** New blueprints should use `apiVersion: repave.dev/v1beta1`.

| v1alpha1 | v1beta1 |
| --- | --- |
| No provenance output contract | Requires `spec.output.provenance.file` |
| Gates optional for provenance | Must include `provenance-drift` gate |
| `metadata.version` is blueprint pack semver | `metadata.version` **1.0.0+** signals v1beta1 template contract |

`repave.dev/v1alpha1` blueprints continue to load for existing packs.

### Example output block

```yaml
spec:
  output:
    type: pull_request
    provenance:
      file: repave.yaml
    repository:
      name_template: "tf-{cloud_provider}-{module_name}"
```

## Generated module `repave.yaml`

**Breaking:** v1beta1 blueprints emit a required **`repave.yaml`** provenance
file in every generated module repository.

The file uses `kind: GoldenPathArtifact` and records:

- Blueprint name and version
- Pinned standard source and version
- Checkov policy pack (when configured)
- Engine version and generation timestamp
- Module identity (`module_name`, `cloud_provider`, `provider_services`)

Schema: [`schemas/golden-path-artifact.schema.json`](../schemas/golden-path-artifact.schema.json)

The `provenance-drift` gate validates this file before publish.

## GoldenPathRepo CRD

**Breaking (operator):** Fleet inventory uses
[`operator/crd/goldenpathrepo.yaml`](../operator/crd/goldenpathrepo.yaml).

Each CR instance references a module repo URL and the pinned blueprint/standard
versions from `repave.yaml`. Operator reconciliation (planned) compares live
provenance to current repave pins.

## Migrating an existing blueprint

1. Set `apiVersion: repave.dev/v1beta1`.
2. Add `spec.output.provenance.file: repave.yaml`.
3. Add `provenance-drift` to `spec.gates`.
4. Bump `metadata.version` to `1.0.0` if template output changed materially.
5. Regenerate or run `repave update` (planned) on existing module repos to add
   `repave.yaml`.

## Migrating an existing module repository

Module repos generated before v1beta1 do not contain `repave.yaml`. Options:

- Re-generate with a v1beta1 blueprint (new repo or overwrite via planned update flow).
- Hand-author `repave.yaml` from the schema and pin values matching your blueprint.
