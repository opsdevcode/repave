# repave roadmap

Planning document for repave evolution. The [README](../README.md) keeps a
one-line summary per release; this file holds the detail we use when scoping
work, writing ADRs, and opening issues.

**Current release:** v1.10.0

---

## How to use this doc

- Add **future state** items under [Planned](#planned) with enough context to
  estimate and implement (problem, approach, dependencies, acceptance signals).
- Move items to [Shipped](#shipped) when they land on `main` and cut a release.
- Keep speculative ideas in [Parking lot](#parking-lot) until there is a concrete
  next step.

---

## Shipped

### v1.0 — Foundation

- Engine + `terraform-module-generic` golden path
- Mandatory gates (`fmt`, `validate`, `tflint`, `checkov`, docs drift)
- Local run (Docker Compose + API/CLI)
- CI, semantic-release automation, baseline test coverage

### v1.1 — Module repositories

- Generated modules publish to **separate git repos** (not inside repave)
- Release automation on `main`

### v1.2 — Provider scope

- `cloud_provider` and `provider_services` blueprint inputs
- Provider catalog validation and scoped `versions.tf` / README

### v1.3 — GitHub remote publish

- Create target GitHub repo and push initial commit when `GITHUB_TOKEN` is set

### v1.4 — Dry-run preview

- Preview generated file list and contents before publish

### v1.5 — Gate artifact hygiene

- Exclude `.terraform/`, lockfiles, and tflint cache from preview/publish output
- License form input (removed again in v1.6)

### v1.6 — Provider catalogs and toolchain

- Full AWS/Azure/GCP provider service catalogs
- `uv` for engine dependency management
- Simplified blueprint form (license UI removed)

### v1.7 — Per-service resource scope

- `provider_service_scope`: basic capabilities, basic + additional, or custom-only
- Scope validation and README summary of resolved capabilities

### v1.8 — Per-resource Terraform files

- One `.tf` file per scoped provider resource (no monolithic `main.tf`)
- Post-render resource file generation from blueprint partials

### v1.9 — Module standard and `locals.tf`

- In-repo module standard at `examples/standards` (v0.4.0)
- Generated `locals.tf` with `common_tags`, `name_prefix`, normalized services
- Resource scaffolds consume `local.*` for shared context

### v1.10 — Checkov policy pack (current)

- In-repo custom policies at `examples/checkov/policies`
- Policies copied into generated modules at `policy/checkov/`
- Generated `.checkov.yml` and blueprint `gate_config.checkov`
- Optional `gates.checkov.skip_checks` in `repave.config.yaml`
- PR branch cleanup workflow + `delete_branch_on_merge` on the repo

---

## Planned

### v1.11 — Repave-specific Checkov rules (Phase 3)

**Problem:** Starter policies only check Terraform version constraints. The module
standard (layout, locals, tags, naming) is documented but not enforced by policy
scanning.

**Approach:**

- Add YAML/Python rules under `examples/checkov/policies/` aligned with the module
  standard, for example:
  - `locals.tf` present; no resource blocks in `variables.tf`
  - Resources reference `local.common_tags` / `local.name_prefix` where applicable
  - No monolithic `main.tf` with standalone resources
  - Required variables (`environment`, `tags`, `name_prefix`) declared
- Unit-test custom policies with fixture Terraform under `examples/checkov/tests/`
- Bump policy pack version; blueprint pins new version

**Dependencies:** v1.10 policy pack and render copy path (done).

**Done when:** Generated scaffold fails Checkov when a standard rule is violated;
CI documents how to add org-specific rules to the pack.

---

### v1.12 — Reconciliation operator

**Problem:** Generated repos drift from pinned blueprint/standard versions; manual
upgrades across the estate do not scale.

**Approach:**

- Operator SDK reconciler watching `GoldenPathRepo` / `Blueprint` CRDs
- Detect template drift, standard-version bumps, and gate policy pack changes
- Open governed remediation PRs (never direct push to module repos)

**Dependencies:** Stable blueprint + schema contracts; module repos already
external (v1.1+).

**Done when:** A CRD instance for a generated repo triggers an upgrade PR when
blueprint or standard version is bumped in repave.

See also [`operator/README.md`](../operator/README.md).

---

### v1.13 — Portal and UX hardening

**Problem:** Form UX is functional but minimal for large provider catalogs and
multi-step scope selection.

**Approach:**

- Improved scope UX (search, presets, validation feedback)
- Generation history / last-run summary in the portal
- Clearer gate failure surfacing (which gate, stderr excerpt)

**Done when:** Non-expert users can complete a multi-service module without CLI
fallback for common paths.

---

### v1.14 — Update existing module repositories

**Problem:** Today repave bootstraps **new** repos; upgrading an existing module
requires manual merge or re-generation.

**Approach:**

- `repave update` (or blueprint flag) targeting an existing module repo path
- Three-way aware merge or PR-only flow that preserves user edits outside scaffold
- Operator integration for fleet-wide upgrades (ties to v1.12)

**Done when:** A module repo created by repave can receive a blueprint version
bump via PR without full manual copy.

---

### v1.15 — Additional golden paths

**Problem:** Only `terraform-module-generic` exists; platform teams need more
artifact types.

**Candidates (prioritize with product input):**

| Golden path | Output | Notes |
| --- | --- | --- |
| Ansible role | Galaxy-compatible role repo | Shared gates pattern |
| Cloud resource module (single resource) | Thin `tfm-*` wrapper | Subset of generic blueprint |
| Environment stack bootstrap | `env-*` composition repo | Consumes pinned module versions |

**Done when:** At least one new blueprint ships with gates, standards pin, and docs.

---

## Parking lot

Ideas not yet scheduled — capture here before they become planned work.

- **Standards versioning UI** — show pinned standard/policy versions in the portal
  and diff between blueprint releases
- **OPA/Sentinel gate** — optional policy gate alongside Checkov for plan JSON
- **Private blueprint registry** — load blueprints from git URL or OCI artifact
- **Multi-tenant repave** — org-scoped config, standards, and output roots
- **Generated module CI template** — ship a workflow file in each module repo that
  runs the same gates as repave locally

---

## Release mechanics

Releases follow [Conventional Commits](https://www.conventionalcommits.org/) on
`main` via python-semantic-release. See [README § Releases](../README.md#releases).

Roadmap **version numbers** are planning labels; actual semver is driven by
commit types at merge time (`feat` → minor, `fix` → patch).
