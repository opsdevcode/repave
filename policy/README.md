# Policy packs (monorepo)

Shared policy content vendored into generated repositories. Artifact-specific standards
live under [`standards/policy/`](../standards/policy/README.md).

| Path | Used by |
| ---- | ------- |
| [`checkov/`](checkov/policies/) | Terraform modules and environment stacks |
| [`opa/`](opa/policies/) | `opa-policy` artifacts and Terraform plan-time Rego |
| [`azure/`](azure/definitions/) | `azure-policy` artifacts |
| [`ansible-lint/`](ansible-lint/pack/) | Ansible roles, collections, and playbook projects |

Golden-path blueprints for **Policy** (`opa-policy-generic`, `azure-policy-generic`) appear
together under the **Policy** heading in the portal catalog.
