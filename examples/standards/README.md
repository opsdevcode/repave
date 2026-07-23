# Standards (repave)

Repave does not maintain a fork of Terraform module standards in this repository.

**Authoritative source:** [opsdevcode/sn — `docs/standards/terraform-standards`](https://github.com/opsdevcode/sn/tree/main/docs/standards/terraform-standards)

| Document | Purpose |
| --- | --- |
| [terraform-standards.md](https://github.com/opsdevcode/sn/blob/main/docs/standards/terraform-standards/terraform-standards.md) | Estate-wide Terraform engineering standard |
| [terraform-module-layout.md](https://github.com/opsdevcode/sn/blob/main/docs/standards/terraform-standards/terraform-module-layout.md) | Module file layout and `locals.tf` conventions |
| `*-summary.md` | Companion summaries for governance reviews |

Blueprints pin a `standard.source` and `standard.version` that reference this
location. Generated modules record the pinned standard in their README.

When the sn standard changes, bump the version in `blueprint.yaml` and regenerate
or upgrade affected modules through the normal PR workflow.
