# Policy packs (monorepo)

Shared policy content vendored into generated repositories. Artifact-specific standards
live under [`standards/policy/`](../standards/policy/README.md).

**What packs are, pack sources, profiles, and blueprint defaults:** see **[PACKS.md](PACKS.md)**.

| Path | Used by |
| ---- | ------- |
| [`checkov/`](checkov/policies/) | Terraform modules, environment stacks, and `checkov-policy` artifacts |
| [`opa/`](opa/policies/) | `opa-policy` artifacts and Terraform plan-time Rego |
| [`opa/fixtures/`](opa/fixtures/) | Create-only Terraform plan JSON for module CI (`conftest`) when live plan is unavailable |
| [`azure/`](azure/definitions/) | `azure-policy` artifacts (audit storage, HTTPS, public blob, tags samples) |
| [`ansible-lint/`](ansible-lint/pack/) | Ansible roles, collections, and playbook projects |

Golden-path blueprints for **Policy** (`checkov-policy-generic`, `opa-policy-generic`, `azure-policy-generic`) appear
together under the **Policy** heading in the portal catalog.

## Catalog and portal

[`catalog.json`](catalog.json) is the source of truth for pack sources, profiles, and
selectable rules. The portal loads it via `GET /blueprints/{name}/policy-catalog`.

## Community standards watch

[`standards-watch.json`](standards-watch.json) lists external URLs (Checkov, Conftest,
Terraform, Azure Policy) monitored for drift. Run:

```bash
make policy-standards-watch
```

GitHub Actions workflow **Policy standards watch** (weekly) refreshes
[`standards-watch.snapshot.json`](standards-watch.snapshot.json) and opens a PR when
hashes change so maintainers can update the catalog and pack pins.
