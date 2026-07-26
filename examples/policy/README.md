# Policy golden paths

Repave ships three first-class **policy** artifacts under `standards/policy/` (grouped as **Policy**
in the portal catalog):

| Blueprint | Kind | Artifact type | Enforcement |
| --------- | ---- | ------------- | ----------- |
| `checkov-policy-generic` | Checkov | `checkov-policy` | Custom Checkov pack + fixtures (`checkov` gate) |
| `opa-policy-generic` | OPA | `opa-policy` | Conftest / Rego (`opa` gate) |
| `azure-policy-generic` | Azure Policy | `azure-policy` | Definition JSON validation (`azure-policy` gate) |

Terraform module and stack blueprints still vend `policy/checkov/` and `policy/opa/policies` for
module-time scanning and plan-time Rego via the shared gates.

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
