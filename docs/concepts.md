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

## Remote publish (v1.2)

When dry-run is disabled and `GITHUB_TOKEN` is set, repave creates the target
GitHub repository (org or user account) if needed and pushes the bootstrapped
module to `main`.

## Self-healing (v1.3)

An Operator SDK reconciler will detect drift and standard-version bumps across
the generated estate and open remediation PRs automatically.
