# Terraform module layout standard

Version: 1.1.0

File layout and `locals.tf` conventions for repave Terraform modules. Read together
with [terraform-standards.md](terraform-standards.md) (engineering standard).

Blueprints pin `standards/terraform-standards` at version **1.1.0**.

---

## Repository layout

Recommended file layout for root and child modules:

```text
.
├── README.md
├── versions.tf          # terraform + required_providers blocks
├── variables.tf         # input contract
├── outputs.tf           # output contract
├── locals.tf            # shared derived values
├── {service}_{resource}.tf   # one primary resource (or logical group) per file
├── data.tf              # optional: shared data sources
├── providers.tf         # optional: provider aliases / configuration
└── tests/
    └── *.tftest.hcl
```

**File naming**

- Use lowercase with underscores: `s3_bucket.tf`, not `S3Bucket.tf`.
- Prefix with service when the resource name alone is ambiguous across providers.
- Keep `variables.tf`, `outputs.tf`, `versions.tf`, and `locals.tf` at repo root
  for discoverability (HashiCorp module structure convention).

**When to split further**

- Separate `iam.tf` when IAM policies/roles are non-trivial.
- Separate `data.tf` when data sources are shared across multiple resources.
- Avoid `main.tf` as a junk drawer; if the file exists, it should contain only
  wiring with no standalone resources.

---

## `locals.tf` conventions

HashiCorp's [standard module structure](https://developer.hashicorp.com/terraform/language/modules/develop#standard-module-structure)
includes a dedicated `locals.tf` for **derived** values. This matches how
large module registries (for example terraform-aws-modules) and platform teams
structure production code.

### What belongs in `locals.tf`

| Pattern | Example |
| --- | --- |
| Normalized inputs | `sort(distinct(var.subnets))` |
| Merged tags | `merge(var.tags, { managed_by = "terraform" })` |
| Naming prefixes | `coalesce(var.name_prefix, "${var.module_name}-${var.environment}")` |
| Parsed or frozen scope maps | Service/resource capability maps |
| Repeated expressions | Common filters, CIDR calculations, ARN formats |

### What does not belong in `locals.tf`

- **Raw passthrough without purpose.** Avoid `local.foo = var.foo` unless it
  establishes the module's internal boundary (all resources read `local.*` for
  shared context so normalization can be added later without touching every
  resource file).
- **Provider configuration or resources.** Locals hold values, not infrastructure.
- **Secrets or credentials.** Pass through variables from secure stores at apply time.

### How resource files should use locals

- `{service}_{resource}.tf` files reference **`local.common_tags`**, **`local.name_prefix`**,
  and scope maps — not ad hoc `var.tags` or repeated string formats.
- One-off resource logic stays in that resource's file; anything shared across
  two or more files moves to `locals.tf`.
- Outputs may expose `local.*` values when they represent the module's canonical
  contract (for example merged tags or normalized service lists).

---

## Repave scaffold defaults

Generated modules ship with:

- `provider_services` — sorted and deduplicated from `var.provider_services`
- `provider_service_scope` — frozen capability map for selected services (generic blueprint)
- `common_tags` — caller `var.tags` merged with `module`, `environment`, and `managed_by`
- `name_prefix` — `coalesce(var.name_prefix, "${var.module_name}-${var.environment}")`
  so callers may override naming without forking the module

**`variables.tf` (naming)**

```hcl
variable "name_prefix" {
  type        = string
  description = "Optional naming prefix; when null, defaults to module_name-environment."
  default     = null
  nullable    = true
}
```

**`locals.tf` (naming and tags)**

```hcl
locals {
  name_prefix = coalesce(var.name_prefix, "${var.module_name}-${var.environment}")

  common_tags = merge(
    var.tags,
    {
      module      = var.module_name
      environment = var.environment
      managed_by  = "terraform"
    },
  )
}
```

Replace scaffold `null_resource` blocks with real provider resources that consume
these locals.
