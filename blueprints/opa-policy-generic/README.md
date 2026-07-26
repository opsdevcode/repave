# opa-policy-generic

Golden path for **`opa-policy`** artifacts: Conftest-evaluated Rego under `policy/`.

Output repo name: `opa-policy-{organization}-{policy_name}`.

The engine copies the monorepo starter pack from `policy/opa/policies/` when Terraform
blueprints enable the `opa` gate; this blueprint scaffolds a standalone policy repo.

Standard: `standards/policy/opa.md` and `standards/policy/governance-baseline.md`.
