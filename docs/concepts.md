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

Ansible golden paths pin a multi-file standard under `examples/standards/ansible/`
(role, collection, playbook-project, security appendix). The production-profile
ansible-lint pack at `examples/ansible-lint/pack/` is copied into generated roles
at render time (parallel to Checkov policies for Terraform modules).

## Self-healing (planned)

An Operator SDK reconciler will detect drift and standard-version bumps across
the generated estate and open remediation PRs automatically. See
[`docs/roadmap.md`](roadmap.md) (reconciliation operator) and
[`operator/README.md`](../operator/README.md).

