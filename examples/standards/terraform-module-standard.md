# Generic Terraform Module Standard (sample)

Version: 0.3.1

This is a **sample** standards document for the repave bring-your-own-standards
model. In production, point blueprints at your authoritative standards source in
git and pin the version they encode.

It combines:

- [HashiCorp Terraform module practices](https://developer.hashicorp.com/terraform/language/modules/develop)
- Common conventions from large-scale platform teams
- Staff platform engineering and Terraform architect patterns for operable,
  composable modules at organizational scale

Use this as a baseline to adopt or fork — not every rule applies to every module
tier. Mark exceptions in the module README with rationale.

---

## Design principles

1. **Composable, not monolithic.** Modules expose a narrow contract and delegate
   cross-cutting concerns (networking, identity, observability) to peer modules.
2. **Opinionated defaults, explicit overrides.** Safe defaults for the 80% case;
   typed variables for the rest. Avoid silent magic in locals.
3. **Governed by construction.** Generated and hand-written code alike must pass
   the configured gate set before publish.
4. **Operability over cleverness.** Prefer readable HCL, predictable naming, and
   destroy-safe patterns over abstraction for its own sake.
5. **Blast-radius awareness.** One module should own one bounded capability.
   Split when lifecycle, IAM, or state boundaries differ.

---

## Module contract (required)

These are enforced by the `terraform-module-generic` blueprint scaffold and
expected of every module in the estate.

- Pin Terraform and provider versions in `versions.tf` using pessimistic
  constraints (`~>`) on providers and an upper bound on Terraform core.
- Declare typed variables with descriptions. Use `nullable = false` where a value
  is truly required at apply time.
- Expose explicit outputs for integration points (IDs, ARNs, names, endpoints).
  Do not export entire resource objects unless consumers need them.
- Place shared module locals in `locals.tf`.
- Put each in-scope provider resource in its own `.tf` file (for example
  `s3_bucket.tf`, `eks_cluster.tf`) instead of a monolithic `main.tf`.
- Include native Terraform tests under `tests/` using `.tftest.hcl`.
- Include a module README with purpose, usage, inputs, outputs, and upgrade
  notes.

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

| Use locals for | Example |
| --- | --- |
| Normalized inputs | `sort(distinct(var.subnets))` |
| Merged tags | `merge(var.tags, { managed_by = "terraform" })` |
| Naming prefixes | `"${var.name}-${var.environment}"` |
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

### Repave scaffold defaults

Generated modules ship with:

- `provider_services` — sorted and deduplicated from `var.provider_services`
- `provider_service_scope` — frozen capability map for selected services
- `common_tags` — caller tags merged with `module`, `environment`, and `managed_by`
- `name_prefix` — `"${var.module_name}-${var.environment}"` for globally unique names

Replace scaffold `null_resource` blocks with real provider resources that consume
these locals.

---

## HashiCorp baseline

Align with HashiCorp's module development guidance:

| Topic | Standard |
| --- | --- |
| **Providers** | Declare in `versions.tf` only. Never configure provider credentials in module code. |
| **Interfaces** | Limit required inputs; prefer sensible defaults for optional behavior. |
| **Outputs** | Output values downstream modules need — not everything the module creates. |
| **Composition** | Call child modules for reusable pieces; do not copy-paste resource blocks. |
| **Counts** | Prefer `for_each` over `count` when resource identity is map-based (safer refactors). |
| **Lifecycle** | Use `lifecycle { prevent_destroy = true }` sparingly and document why. |
| **Documentation** | Follow the [README template pattern](https://developer.hashicorp.com/terraform/language/modules/develop#module-documentation): header, usage, requirements, providers, inputs table, outputs table. |

**Provider configuration**

- Root modules configure providers; child modules inherit.
- Use `configuration_aliases` when a module must target multiple regions,
  accounts, or subscriptions — never hard-code provider blocks with secrets.

**Terraform version**

- Match the organization's supported Terraform release train.
- The repave sample pins `>= 1.8.0, < 2.0.0` to support native tests and modern
  language features.

---

## Platform engineering conventions

Patterns commonly enforced by staff platform teams operating hundreds of modules.

### Tagging

- Accept a `tags` map (or structured tagging object) at the module boundary.
- Merge caller tags with module-managed tags in locals; module keys win on conflict
  only when required for compliance (document overrides).
- Minimum recommended tag keys: `environment`, `owner`, `service` / `app`,
  `managed-by = terraform`.
- Apply tags consistently via provider `default_tags` at the root module when the
  estate standardizes on provider-level tagging — child modules still accept `tags`
  for portability.

### Naming

- Encode environment or scope in resource names only when the cloud API requires
  global uniqueness — not in every label.
- Use a `{org}-{env}-{service}-{purpose}` pattern where platform naming standards
  exist; modules should accept a `name_prefix` or `name` input rather than
  inventing org-specific strings internally.
- Keep Terraform resource names (`resource "aws_s3_bucket" "logs"`) stable and
  semantic; changing them forces replacement.

### Environments

- Modules are environment-agnostic. Environment selection happens in root modules
  or Terragrunt/stack layers via variable values — not `if env == "prod"` forks
  inside shared modules.
- Use feature flags (`enable_*` booleans) instead of environment string matching
  for optional capabilities.

### Ownership and support

- README must state owning team and support channel (Slack, on-call, issue tracker).
- Declare breaking-change policy: semver for module releases, migration notes on
  major bumps.

---

## Architecture patterns (staff / architect)

### Module tiers

| Tier | Purpose | Example |
| --- | --- | --- |
| **Resource** | Thin wrapper around one cloud resource with org defaults | `s3-bucket`, `kms-key` |
| **Composition** | Product of multiple resource modules | `eks-cluster`, `data-platform-cell` |
| **Landing zone** | Account/subscription/project bootstrap | `network-spoke`, `baseline-iam` |

Generated repave modules start as **resource-tier scaffolds** — implement the
real resources, then compose upward.

### State boundaries

- One state per independently lifecycle-managed stack. Do not mix unrelated blast
  radii in one state file.
- Modules never configure backends; callers choose remote state (S3 + DynamoDB,
  GCS + locking, Terraform Cloud, etc.).
- Pass remote state outputs into modules via variables — avoid `terraform_remote_state`
  inside reusable modules (couples modules to stack layout).

### IAM and least privilege

- Create IAM in the same module that creates the resource requiring it — keeps
  permission review colocated with the resource change.
- Prefer managed policies or policy documents built from data sources over
  inline JSON strings in heredocs.
- Document which external principals (roles, service accounts) the module expects
  as inputs vs creates.

### Data sources vs resources

- Use data sources for discovery (existing VPC, current caller identity).
- Never use data sources as a substitute for inputs when the caller should own
  the contract — explicit variables make dependencies visible in plans.

### Error handling and idempotency

- Avoid `null_resource` and local-exec except as a last resort; prefer native
  provider resources (repave scaffolds use `null_resource` only as a placeholder
  until real resources are implemented).
- Design for re-apply safety: imports and drift correction should not require
  manual state surgery.

---

## Variables and outputs

**Variables**

- Use object types for structured input (network config, replica settings) instead
  of many flat primitives.
- Validate with `validation` blocks where constraints are machine-checkable.
- Do not use `provider_service_scope`-style JSON strings in hand-written modules;
  prefer typed objects at the module boundary.

**Outputs**

- Mark sensitive outputs with `sensitive = true`.
- Output stable identifiers (`id`, `arn`, `name`, `endpoint`) rather than derived
  strings that consumers could compute.
- Document which outputs are part of the semver-stable contract vs internal.

---

## Security and compliance

- No secrets in Terraform source, `.tfvars` committed to git, or module defaults.
  Use vault, secrets manager, or CI-injected variables.
- Run static analysis (`checkov`, `tfsec`, or equivalent) on every change — required
  in the gate set below.
- Deny public exposure by default (S3 public access, open SG rules, anonymous IAM).
  Opt-in via explicit `enable_public_*` flags with review.
- Enable encryption-at-rest defaults aligned with org KMS/key vault standards.

---

## Testing

Layer tests the way platform teams run them in production:

| Layer | Tool | Purpose |
| --- | --- | --- |
| **Static** | `terraform fmt`, `validate`, `tflint` | Syntax, types, provider schema |
| **Policy** | `checkov` / OPA / Sentinel | Security and org policy |
| **Unit** | `terraform test` (`.tftest.hcl`) | Module behavior with mock providers / plan assertions |
| **Integration** | Ephemeral env + apply/destroy | End-to-end — run outside module repo CI when costly |

Minimum for modules in this standard: static + policy + at least one `terraform test`
run block asserting plan/apply invariants.

---

## Documentation (README)

Required sections:

1. **Purpose** — what problem the module solves and what it deliberately does not do.
2. **Usage** — copy-pasteable example for root module callers.
3. **Requirements** — Terraform and provider versions.
4. **Inputs / outputs** — table or pointer to `variables.tf` / `outputs.tf`.
5. **Provider scope** — services and resource capabilities in scope (for repave-generated modules).
6. **Upgrade notes** — breaking changes between versions.
7. **Ownership** — team and support path.

Generated modules must not ship with unresolved template placeholders (`{{ ... }}`).

---

## Required CI gates

These gates are wired in repave blueprints and expected in module repository CI:

- `terraform fmt -check -recursive`
- `terraform validate`
- `terraform test`
- `tflint`
- `checkov` (or equivalent policy scanner)
- Docs drift check (README present and fully rendered)

Failed gates block publish — there is no bypass path.

---

## Versioning and lifecycle

- Follow [Semantic Versioning](https://semver.org/) for module releases (`vMAJOR.MINOR.PATCH` tags).
- **MAJOR** — breaking input/output or behavior changes.
- **MINOR** — backward-compatible features.
- **PATCH** — fixes, docs, internal refactors with no contract change.
- Maintain a changelog (`CHANGELOG.md` or GitHub Releases) for consumer upgrades.
- Deprecate inputs/outputs with `deprecated` descriptions for one minor release
  before removal.

---

## References

**HashiCorp**

- [Module development recommendations](https://developer.hashicorp.com/terraform/language/modules/develop)
- [Standard module structure](https://developer.hashicorp.com/terraform/language/modules/develop#standard-module-structure)
- [Provider versioning](https://developer.hashicorp.com/terraform/language/providers/requirements)
- [Tests](https://developer.hashicorp.com/terraform/language/tests)

**Community and industry**

- [Terraform AWS Modules](https://github.com/terraform-aws-modules) — composition and interface patterns
- [Google Cloud Foundation Fabric](https://github.com/GoogleCloudPlatform/cloud-foundation-fabric) — landing-zone module granularity
- [Azure Terraform best practices](https://learn.microsoft.com/en-us/azure/developer/terraform/best-practices)

**Policy and lint**

- [Checkov](https://www.checkov.io/)
- [TFLint](https://github.com/terraform-linters/tflint)

When adopting this sample, replace or extend the references section with your
organization's authoritative runbooks, naming standards, and architecture decision
records (ADRs).
