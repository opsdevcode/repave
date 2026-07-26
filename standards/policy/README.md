# Policy golden paths

Repave treats **policy** as its own artifact family alongside Terraform and Ansible.

| Standard | Artifact type | Purpose |
| -------- | ------------- | ------- |
| [governance-baseline.md](governance-baseline.md) | All | Required gates, standards pins, and security hygiene |
| [checkov.md](checkov.md) | `checkov-policy` | Checkov custom policy pack repos |
| [opa.md](opa.md) | `opa-policy` | Conftest / Rego on plan JSON or fixtures |
| [azure.md](azure.md) | `azure-policy` | Azure Policy definition repos |

Every golden-path blueprint must satisfy the governance baseline (enforced in engine tests).

## Customization

See [customization.md](customization.md) for policy profiles, the rule catalog, portal UX, provenance, and platform `repave.config.yaml` floors.
