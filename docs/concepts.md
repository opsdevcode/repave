# repave concepts

## Golden path

A versioned, opinionated way to produce a compliant artifact. In repave, a golden
path is a **blueprint**: input schema + standard reference + template + gates +
output contract.

## Blueprint

Declarative pack under `blueprints/<name>/`. The engine reads `blueprint.yaml`,
validates inputs, renders the Copier template, runs gates, and produces output.

## Governance-by-construction

Generated artifacts must pass every configured gate. There is no bypass path.
This is how platform standards scale to users who are not automation experts.

## Housed in one, rendered in many

Standards are authoritative in one git home and rendered read-only in multiple
surfaces (portal docs, enterprise doc pipelines, etc.). Blueprints pin the
standard version they encode.

## Remote publish

When dry-run is disabled and `GITHUB_TOKEN` is set, repave creates the target
GitHub repository (org or user account) if needed and pushes the bootstrapped
module to `main`.

## Provenance (`repave.yaml`)

Blueprints may declare `spec.output.provenance.file` (typically `repave.yaml`).
The engine writes a `GoldenPathArtifact` document after render with pinned
blueprint and standard versions, generation metadata, and artifact-type-specific
fields (`terraformModule` or `ansibleRole`). Ansible roles also record the pinned
ansible-lint pack (`ansibleLint`). The `provenance-drift` gate validates
the file against `schemas/golden-path-artifact.schema.json`.

## Ansible standards and policy pack

Ansible golden paths pin a multi-file standard under `standards/ansible/`
(role, collection, playbook-project, security appendix). The production-profile
ansible-lint pack at `policy/ansible-lint/pack/` is copied into generated roles
at render time (parallel to Checkov policies for Terraform modules).

## Terraform standards pack

Terraform module blueprints pin `standards/terraform-standards/` (engineering
standard + module layout). The monolithic `standards/terraform-module-standard.md`
file is superseded but retained for diff reference. Generated module READMEs cite
the pack version recorded in `repave.yaml`.

## Backstage Software Catalog

Optional or required `catalog-info.yaml` in generated repos registers components in
[Backstage](https://backstage.io/) with Repave lineage annotations (`repave.dev/*`).
See [`docs/backstage.md`](backstage.md) and
[`standards/backstage/catalog-standard.md`](../standards/backstage/catalog-standard.md).

## Portal

The bundled web UI maps blueprint inputs to generation and shows gate results on
a shared night-ops shell (home catalog, governance-aware forms, results dashboard).
Layout, components, and acceptance criteria are in
[`docs/portal-design.md`](portal-design.md). Browser-local last-run summary uses
`sessionStorage`; fleet-wide history is planned with audit (v1.30).

## Self-healing (planned)

An Operator SDK reconciler will detect drift and standard-version bumps across
the generated estate and open remediation PRs automatically. Development follows
[`docs/operator-standards.md`](operator-standards.md) and
[`docs/operator-local-dev.md`](operator-local-dev.md). See also
[`docs/roadmap.md`](roadmap.md#v117--reconciliation-operator-alpha) and
[`operator/README.md`](../operator/README.md).

