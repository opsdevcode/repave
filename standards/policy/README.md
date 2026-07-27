# Policy golden paths

Repave treats **policy** as its own artifact family alongside Terraform and Ansible.

| Standard | Artifact type | Purpose |
| -------- | ------------- | ------- |
| [governance-baseline.md](governance-baseline.md) | All | Required gates, standards pins, and security hygiene |
| [checkov.md](checkov.md) | `checkov-policy` | Checkov custom policy pack repos |
| [opa.md](opa.md) | `opa-policy` | Conftest / Rego on plan JSON or fixtures |
| [azure.md](azure.md) | `azure-policy` | Azure Policy definition repos |

Every golden-path blueprint must satisfy the governance baseline (enforced in engine tests).

**Dry-run preview:** Portal and CLI dry-run generation set `require_run` on gates — missing
tooling fails instead of skipping so the preview matches CI. See
[`policy/PACKS.md`](../../policy/PACKS.md#dry-run-preview-and-gates).

## Pack registry

Definitions, pack sources, physical directories, and golden-path defaults:
[`policy/PACKS.md`](../../policy/PACKS.md). Machine-readable registry:
[`policy/catalog.json`](../../policy/catalog.json).

## Customization

See [customization.md](customization.md) for policy profiles, the rule catalog, portal UX, provenance, and platform `repave.config.yaml` floors.
