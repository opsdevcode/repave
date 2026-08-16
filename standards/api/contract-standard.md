# API contract standard v1.0.0

Version: 1.0.0

Governed OpenAPI and AsyncAPI specification repositories from the
`api-contract-generic` golden path.

## Naming

- Repository name: `api-contract-{organization}-{spec_name}` (from blueprint).
- Spec file is `openapi.yaml` or `asyncapi.yaml` at the repo root.
- Baseline copy lives under `baseline/` with the same filename.

## Required files

| File | Purpose |
| --- | --- |
| `openapi.yaml` or `asyncapi.yaml` | Published contract |
| `baseline/<same>` | Last published revision for breaking-change detection |
| `.spectral.yaml` | Spectral ruleset (`spectral:oas` or `spectral:asyncapi`) |
| `README.md` | Usage and **Provenance** (repave lineage) |

## Validation

Generate and consumer CI run:

- **spectral** — lint the spec (`--fail-severity=error`)
- **oasdiff** — `oasdiff breaking baseline/<spec> <spec>` (OpenAPI only; AsyncAPI skips)
- **secrets**, **docs-drift**, **provenance-drift**

A Spectral error or an oasdiff breaking change fails the gate. Update the
baseline only when the breaking change is intentional and versioned.

## Provenance

Lineage is recorded in `repave.yaml` (`artifactType: api-contract`).
