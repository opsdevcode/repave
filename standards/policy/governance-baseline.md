# Governance baseline (all artifacts)

Version: 1.0.0

Community standards, best practices, and security gates that **every** repave golden path
must wire into its blueprint `spec.gates` list.

## Required on all artifacts

| Gate | Purpose |
| ---- | ------- |
| `secrets` | Block committed credentials and high-risk patterns |
| `docs-drift` | README and usage docs stay aligned with the scaffold |
| `provenance-drift` | `repave.yaml` matches engine provenance contract |

Each blueprint must also pin a **domain standard** (`spec.standard`) at a semver version
(Terraform estate pack, Ansible role/collection/playbook standard, or policy standard).

## Terraform modules and environment stacks

| Gate | Purpose |
| ---- | ------- |
| `terraform-fmt` | Canonical formatting |
| `terraform-validate` | Provider/module configuration validity |
| `tflint` | Lint and provider best practices |
| `checkov` | Static security and misconfiguration scanning (shared Checkov pack) |
| `opa` | Optional plan-time Rego (Conftest); enabled on shipped Terraform blueprints |

## Ansible roles, collections, and playbook projects

| Gate | Purpose |
| ---- | ------- |
| `yamllint` | YAML style and structure |
| `ansible-lint` | Ansible best practices (shared lint pack where applicable) |

Additional gates by artifact:

- **ansible-role:** `ansible-syntax-check`, `molecule`
- **ansible-playbook-project:** `ansible-syntax-check`
- **ansible-collection:** (syntax covered via collection layout + lint)

## Policy artifacts

| Artifact | Gates |
| -------- | ----- |
| `opa-policy` | `opa` + baseline |
| `azure-policy` | `azure-policy` + baseline |

## Provenance

Generated repos record governance in `repave.yaml`:

```yaml
spec:
  governance:
    baseline_source: standards/policy/governance-baseline.md
    baseline_version: "1.0.0"
```
