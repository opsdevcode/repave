# Policy packs

Version: 1.0.0 (narrative; machine-readable data is in [`catalog.json`](catalog.json))

Repave **policy packs** are vendored rule content under this directory plus the **catalog**
that describes how teams select them at generate time. This document defines terms and lists
pack sources; when anything disagrees with the catalog, **`catalog.json` wins**.

Related: [customization](../standards/policy/customization.md) · [policy README](README.md) ·
[examples/policy](../examples/policy/README.md)

---

## Terms

| Term | Meaning |
| ---- | ------- |
| **Physical pack** | Files on disk under `policy/checkov/`, `policy/opa/`, `policy/azure/`, or `policy/ansible-lint/` copied (or symlinked) into generated repositories during render. |
| **Pack source** | A catalog row in `pack_sources`. Chooses which artifact types a registry entry applies to and which **profile** is the default when the portal or blueprint does not override `policy_profile`. |
| **Profile** | A named bundle of **rule IDs** in `profiles` (for example `estate-default`, `security`). Wildcards such as `checkov:*` expand to all Checkov rules in the catalog. |
| **Rule** | One enforceable item with a stable ID (`checkov:CKV2_REPAVE_1`, `opa:destructive_changes`, `azure:sample_audit_storage`). Rules declare `artifact_types` so only relevant checks appear per blueprint. |
| **Selection** | Resolved `{pack source, profile, optional rule toggles}` written to `.repave/policy-selection.json` and used by gates (Checkov skips, OPA file list, Azure definition list). |

A **policy pack** in product language usually means either the **physical pack** (the repo content)
or a **pack source** (the catalog entry teams pick in the portal). Pack sources often point at the
same monorepo files with different default profiles.

---

## Physical packs (on disk)

| Directory | Engine family | What gets vendored | Typical generated paths |
| --------- | ------------- | ------------------ | ------------------------ |
| [`checkov/policies/`](checkov/policies/) | Checkov | Python custom checks + YAML helpers (`CKV2_REPAVE_*`) | `policy/checkov/` in module, stack, or `checkov-policy` repos |
| [`opa/policies/`](opa/policies/) | OPA / Conftest | Rego (plan-time and optional observability/K8s samples) | `policy/*.rego` or `policy/` tree; modules also get [`opa/fixtures/plan-create-only.json`](opa/fixtures/plan-create-only.json) for CI without cloud plan |
| [`azure/definitions/`](azure/definitions/) | Azure Policy | Sample definition JSON | `policy/definitions/` in `azure-policy` repos |
| [`ansible-lint/pack/`](ansible-lint/pack/) | ansible-lint | `.ansible-lint`, `.yamllint`, ignore file | Ansible role/collection/playbook repos (not in `catalog.json` rule IDs today) |

Checkov rules in the catalog map to implementations in `repave_module_layout.py`, `repave_security.py`,
`repave_null_resource_locals.py`, and bundled YAML policies.

---

## Pack sources (catalog registry)

These are the values for blueprint input **`policy_pack_source`**. Each row sets
**`default_profile`** when **`policy_profile`** is left at blueprint defaults.

| ID | Label | Default profile | Artifact types | Intent |
| -- | ----- | --------------- | -------------- | ------ |
| `repave-default` | Repave community pack | `estate-default` | `terraform-module`, `terraform-environment-stack`, `checkov-policy`, `opa-policy`, `azure-policy` | One registry row for mixed estates: curated Checkov + OPA for Terraform, full paths for dedicated policy repos. |
| `repave-terraform-strict` | Repave Terraform — strict profile | `strict` | `terraform-module`, `terraform-environment-stack` | All catalog Checkov, OPA, and Azure rules that apply to Terraform artifacts. |
| `repave-terraform-layout` | Repave Terraform — layout profile | `layout` | `terraform-module`, `terraform-environment-stack` | Module layout and required-variable conventions only. |
| `repave-terraform-security` | Repave Terraform — security profile | `security` | `terraform-module`, `terraform-environment-stack` | Credential, secret, provisioner, and sensitive output checks. |
| `repave-opa-pack` | Repave OPA / Conftest pack | `opa-focused` | `opa-policy`, `terraform-module`, `terraform-environment-stack` | Plan-time Rego; default profile is OPA-only (no optional Checkov toggles via profile). |
| `repave-azure-samples` | Repave Azure Policy samples | `azure-community` | `azure-policy` | All sample Azure definition JSON files under `policy/azure/definitions/`. |
| `repave-checkov-pack` | Repave Checkov policy pack | `checkov-full` | `checkov-policy`, `terraform-module`, `terraform-environment-stack` | Full repave Checkov custom policy pack for dedicated Checkov repos or strict module CI. |

Reference URLs and longer descriptions for each row live in `catalog.json` → `pack_sources`.

---

## Blueprint defaults (golden paths)

Recommended **`policy_pack_source`** / **`policy_profile`** pairs (see also
[`blueprints/_partials/policy-inputs.yaml`](../blueprints/_partials/policy-inputs.yaml)):

| Blueprint | Pack source | Profile |
| --------- | ----------- | ------- |
| `terraform-module-generic`, `terraform-module-resource`, `terraform-environment-stack` | `repave-default` | `estate-default` |
| `checkov-policy-generic` | `repave-checkov-pack` | `checkov-full` |
| `opa-policy-generic` | `repave-opa-pack` | `opa-focused` |
| `azure-policy-generic` | `repave-azure-samples` | `azure-community` |

Teams can override pack source, profile, or (with profile **`custom`**) individual rules in the
portal **Policy** section or via generate API fields documented in
[customization.md](../standards/policy/customization.md).

---

## Profiles (summary)

Full rule membership is in `catalog.json` → `profiles`. Short guide:

| Profile | Use when |
| ------- | -------- |
| `estate-default` | Balanced community defaults for Terraform (version pin, layout basics, core security, plan-time OPA). |
| `strict` | Enable every catalog rule for the artifact family. |
| `layout` | Terraform module structure and required inputs. |
| `security` | IaC secret and credential hygiene. |
| `terraform-full` | All Checkov + OPA for Terraform. |
| `opa-focused` | Rego / Conftest only. |
| `azure-community` | All shipped Azure sample definitions. |
| `checkov-full` | All repave Checkov custom policies. |
| `custom` | Explicit per-rule toggles; **required** catalog rules stay on. |

---

## Rules (families)

| Prefix | Count (catalog v1.2.0) | Required examples |
| ------ | ---------------------- | ----------------- |
| `checkov:` | 12 (`CKV2_REPAVE_1` … `12`) | `CKV2_REPAVE_1` (required_version declared) |
| `opa:` | 1 in default estate pack | `destructive_changes` (plan-time deny destructive deletes) |
| `azure:` | 4 samples | `sample_audit_storage` |

Additional Rego under `policy/opa/policies/` (observability, Kubernetes) may ship in the physical pack
for extension repos; the **catalog** controls which files gates enforce for a given selection.

---

## Custom and future packs

- **Org registries:** Add rows to `pack_sources` (and rules/profiles as needed) without changing
  generated repo layouts; point `reference_url` at your fork or internal catalog.
- **Platform floors:** `repave.config.yaml` can enforce minimum profiles or required rules estate-wide
  (see [customization.md](../standards/policy/customization.md)).
- **Versioning:** Bump `catalog.json` → `version` when profiles, pack sources, or rules change; engine
  tests load the catalog from the monorepo at generate time.

---

## Dry-run preview and gates

Portal **Dry run preview** and `repave generate --dry-run` set **`require_run`** on the gate
pipeline. Blueprint gates listed in `spec.gates` must **execute**:

- Missing CLI tools (Terraform, Checkov, Conftest, and similar) produce **FAIL**, not **SKIP**.
- Skips that mean “nothing to validate for this artifact” (for example no Prometheus rules in a
  Datadog-only observability pack) may still appear as **SKIP**.

Install the same toolchain as [`deploy/local/Dockerfile`](../deploy/local/Dockerfile) locally, or run
the portal via Docker compose so dry-run matches CI and generated-repo workflows.
