# Policy golden paths

Repave ships two first-class **policy** artifacts under `standards/policy/`:

| Blueprint | Artifact type | Enforcement |
| --------- | ------------- | ----------- |
| `opa-policy-generic` | `opa-policy` | Conftest / Rego (`opa` gate) |
| `azure-policy-generic` | `azure-policy` | Definition JSON validation (`azure-policy` gate) |

Terraform module and stack blueprints still vend `policy/opa/policies` for plan-time Rego
via the shared `opa` gate.

Every golden path (Terraform, Ansible, and policy) must satisfy
`standards/policy/governance-baseline.md`: `secrets`, `docs-drift`, and
`provenance-drift`, plus domain-specific security gates (Checkov, ansible-lint, etc.).

Provenance in generated repos records:

```yaml
spec:
  governance:
    baseline_source: standards/policy/governance-baseline.md
    baseline_version: "1.0.0"
```
