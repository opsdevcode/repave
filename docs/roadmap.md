# repave roadmap

Planning document for repave evolution. The [README](../README.md) keeps a
one-line summary per release; this file holds the detail we use when scoping
work, writing ADRs, and opening issues.

**Current release:** v1.10.0  
**Planning horizon:** v1.11 → v2.0.0 (platform maturity — governed estate at scale)

---

## How to use this doc

- Add **future state** items under [Planned](#planned) with enough context to
  estimate and implement (problem, approach, dependencies, acceptance signals).
- Move items to [Shipped](#shipped) when they land on `main` and cut a release.
- Keep speculative ideas in [Parking lot](#parking-lot) until there is a concrete
  next step.
- Use [Path to v2.0.0](#path-to-v200) for the big-picture sequence and what v2
  means; individual releases below expand each step.

---

## Path to v2.0.0

v2.0.0 is the **mature platform** milestone: repave governs a fleet of generated
repositories end-to-end — bootstrap, standards, policy, upgrade, and drift
remediation — not just one-shot module creation.

```text
v1.10  today       generate + gates + publish + Checkov policy pack
  │
  ├─ v1.11          enforce           module-standard Checkov rules
  ├─ v1.12–v1.15    multi-artifact    gate registry; provenance decoupling; Ansible role path + standard
  ├─ v1.16–v1.19    operate + extend  operator alpha; portal UX; module updates; more golden paths
  ├─ v1.20–v1.24    estate-ready      standards pack; provenance; module CI; operator beta; k8s deploy
  ├─ v1.25–v1.26    service + SSO     authenticated single-tenant service via OIDC
  │
  v2.0.0             platform GA       operator GA, stable contracts, fleet upgrades
```

| Theme | Releases | Outcome |
| --- | --- | --- |
| **Governance depth** | v1.11, v1.20 | Standards and Checkov enforce the module contract, not just document it |
| **Multi-artifact golden paths** | v1.12–v1.15 | Engine decoupled from Terraform; Ansible role path ships with standard + lint pack |
| **Self-healing** | v1.16, v1.18, v1.23 | Drift detection and blueprint/standard upgrades via PR |
| **Usability** | v1.17, v1.21 | Portal and CLI usable by non-experts; visible pinned versions |
| **Estate scale** | v1.19, v1.22, v1.24 | Multiple golden paths; generated repos CI themselves; k8s deploy option |
| **Access and multi-user** | v1.25–v1.26 | Authenticated single-tenant service with OIDC SSO and role-based access |
| **v2.0.0** | — | Closed loop: generate → govern → detect drift → remediate across the fleet |

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

### v1.12 — Gate registry and blueprint gate extensibility (Ansible prereq)

**Problem:** Gate behavior is hard-coded in `engine/src/repave_engine/gates.py`
(`_GATE_RUNNERS` plus special-cased checkov/provenance branches). Adding a new
tool means editing the engine, and artifact hygiene only knows Terraform paths
(`.terraform`, `.tflint.d`). New artifact types (Ansible) cannot register gates.

**Approach:**

- Replace the hard-coded runner map with a **gate registry** keyed by gate name;
  gates declare how they run and what they skip on when tools are absent
- Blueprint-declared `gate_config` for non-checkov gates (e.g. tflint config path,
  `terraform-validate` var files, future yamllint/ansible-lint config paths)
- Make artifact hygiene **artifact-type aware** (add molecule ephemeral dirs,
  `*.retry`, `.ansible` alongside the Terraform entries)
- Extend the schema gate enum so new gates are declarable without engine edits
- Consider `terraform test` as a first-class gate (not just scaffolded tests)

**Dependencies:** Stable gate names in `schemas/blueprint.schema.json` (since v1.0).

**Done when:** A blueprint adds a gate via the registry + schema enum + template
artifacts without core engine changes. (Supersedes and generalizes the former
standalone gate-extensibility item.)

---

### v1.13 — Provenance and standards decoupling (Ansible prereq)

**Problem:** The provenance document and `schemas/golden-path-artifact.schema.json`
assume Terraform: they hard-code `cloud_provider`, `provider_services`, and
`checkov`. A non-Terraform artifact (Ansible role) cannot emit valid provenance.

**Approach:**

- Introduce `spec.artifactType` on the blueprint (`terraform-module` default,
  `ansible-role`), keeping `repave.dev/v1alpha1` back-compat
- Make the provenance artifact block **artifact-type aware**: Terraform keeps
  `cloud_provider`/`provider_services`; Ansible records galaxy namespace, role
  name, and minimum Ansible version
- Generalize standards-pin handling so a non-Terraform standard can be referenced
  and rendered the same way

**Dependencies:** v1.12 gate registry; existing provenance work
(`engine/src/repave_engine/provenance.py`).

**Done when:** An Ansible blueprint emits a schema-valid provenance file with
Ansible-shaped metadata, and the Terraform path is unchanged.

---

### v1.14 — Ansible role golden path

**Problem:** Only Terraform artifacts exist; platform teams also govern
configuration management and want a compliant, Galaxy-compatible Ansible role
scaffold from the same golden-path engine.

**Approach:**

- New `blueprints/ansible-role-generic/` producing a Galaxy-compatible role
- Inputs: `role_name`, `namespace`, `description`, `min_ansible_version`,
  target platforms
- Template: `meta/main.yml`, `tasks/main.yml`, `defaults/main.yml`,
  `handlers/main.yml`, `vars/`, `molecule/default/`, `README.md.jinja`, `.yamllint`
- Gates: `yamllint`, `ansible-lint`, `ansible-syntax-check`, `molecule`
  (skip-if-not-installed pattern like tflint/checkov), `docs-drift`,
  `provenance-drift`
- Output naming: `ansible-role-{role_name}` (or `{namespace}.{role_name}`)
- Provider scope is skipped automatically (no `provider-catalog.json` in the pack)

**Dependencies:** v1.12 gate registry; v1.13 provenance decoupling.

**Done when:** A role repo generates, passes gates where the tools are present,
and skips cleanly where they are absent.

---

### v1.15 — Ansible role standard + ansible-lint policy pack

**Problem:** The Ansible role path needs an enforceable standard, mirroring the
Terraform module standard + Checkov pack, so generated roles are governed rather
than just scaffolded.

**Approach:**

- Vendor an Ansible role standard under `examples/standards/` (parallel to the
  Terraform module standard), pinned by the blueprint
- Ship an ansible-lint config/ruleset pack copied into generated roles (parallel
  to the Checkov pack at `examples/checkov/policies`)
- Unit-test the ruleset against fixture roles

**Dependencies:** v1.14 Ansible role golden path; v1.12 gate registry.

**Done when:** A generated role fails ansible-lint when the standard is violated;
the blueprint pins the pack version.

---

### v1.16 — Reconciliation operator

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

### v1.17 — Portal and UX hardening

**Problem:** Form UX is functional but minimal for large provider catalogs and
multi-step scope selection.

**Approach:**

- Improved scope UX (search, presets, validation feedback)
- Generation history / last-run summary in the portal
- Clearer gate failure surfacing (which gate, stderr excerpt)
- Group the blueprint catalog by artifact type (Terraform, Ansible)

**Done when:** Non-expert users can complete a multi-service module without CLI
fallback for common paths.

---

### v1.18 — Update existing module repositories

**Problem:** Today repave bootstraps **new** repos; upgrading an existing module
requires manual merge or re-generation.

**Approach:**

- `repave update` (or blueprint flag) targeting an existing module repo path
- Three-way aware merge or PR-only flow that preserves user edits outside scaffold
- Operator integration for fleet-wide upgrades (ties to v1.16)

**Done when:** A module repo created by repave can receive a blueprint version
bump via PR without full manual copy.

---

### v1.19 — Additional golden paths

**Problem:** Beyond the Terraform module and Ansible role paths, platform teams
need more artifact types.

**Candidates (prioritize with product input):**

| Golden path | Output | Notes |
| --- | --- | --- |
| Cloud resource module (single resource) | Thin `tfm-*` wrapper | Subset of generic blueprint |
| Environment stack bootstrap | `env-*` composition repo | Consumes pinned module versions |
| Ansible collection / playbook project | Collection or project repo | Builds on the v1.14 role path (see parking lot) |

**Dependencies:** v1.12 gate registry; v1.13 artifact-type provenance.

**Done when:** At least one new blueprint ships with gates, standards pin, and docs.

---

### v1.20 — Estate standards pack (multi-file)

**Problem:** Module standard lives in a single sample file (`examples/standards/
terraform-module-standard.md`). Estate teams want the full Terraform standards
corpus in-repo (engineering standard + module layout) with blueprint and scaffold
aligned to a pinned version.

**Approach:**

- Vendor `terraform-standards.md` and `terraform-module-layout.md` under
  `examples/standards/terraform-standards/` (no summary files)
- Pin blueprint at `examples/standards/terraform-standards` v1.1.0
- Align scaffold: `variable "name_prefix"` with `coalesce` fallback; `common_tags`
  per layout standard
- Retire or supersede the monolithic sample standard file

**Dependencies:** v1.9 locals/layout scaffold.

**Done when:** Generated README cites the multi-file standard path; blueprint and
docs reference one authoritative in-repo standards directory.

---

### v1.21 — Generation provenance and version visibility

**Problem:** Generated modules do not record which blueprint, standard, and policy
pack versions produced them; the portal does not surface pins before generate.

**Approach:**

- Embed provenance in generated README and/or `repave.yaml` metadata file:
  `blueprint`, `blueprint_version`, `standard_source`, `standard_version`,
  `checkov_policy_version`, generation timestamp
- Portal form shows pinned standard and Checkov policy versions for the selected
  blueprint
- Optional: label/tag GitHub repos on publish with blueprint version

**Dependencies:** Blueprint already carries standard and checkov pins (v1.9–v1.10);
artifact-type-aware provenance (v1.13).

**Done when:** A module repo clearly states its golden-path lineage without reading
repave source.

---

### v1.22 — Generated module CI template

**Problem:** Module repos rely on authors to wire CI; gates run in repave at
generate time but not necessarily on every subsequent PR in the module repo.

**Approach:**

- Render `.github/workflows/terraform-gates.yml` (or similar) into each generated
  module using the same gate list as the blueprint
- Document required secrets/runners (none for fmt/validate/tflint/checkov/test)
- Align workflow toolchain versions with `deploy/local/Dockerfile`

**Dependencies:** v1.10 Checkov config in module root; v1.12 gate registry for the
shared gate-list contract.

**Done when:** A freshly published module runs fmt, validate, tflint, checkov, and
`terraform test` on push without manual workflow authoring.

---

### v1.23 — Operator beta and fleet inventory

**Problem:** v1.16 operator scope is large; teams need a minimal inventory model
before full reconciliation.

**Approach:**

- Define `GoldenPathRepo` CRD (repo URL, pinned blueprint, standard, policy versions)
- Operator **inventory mode**: list/watch registered repos, report drift vs pins
  (read-only, no PRs yet)
- CLI/API `repave register` to add a generated repo to the inventory
- Design doc for upgrade PR flow (feeds v1.16 GA and v1.18 update command)

**Dependencies:** v1.16 CRD design; v1.21 provenance fields.

**Done when:** Operator reports “out of date” repos when blueprint standard/policy
version bumps on `main`.

---

### v1.24 — Kubernetes deploy path

**Problem:** Local Docker Compose is the only first-class deploy story; platform
teams want repave API/portal on-cluster alongside the future operator.

**Approach:**

- Helm chart or Kustomize under `deploy/k8s/` for engine API + portal
- Config via `repave.config.yaml` mounted ConfigMap + secrets for `GITHUB_TOKEN`
- Document co-install with operator (same namespace, shared config)
- kind-based smoke test in CI (optional, non-blocking initially)

**Dependencies:** Stable API surface; output config via env/ConfigMap (exists).

**Done when:** `helm install` (or documented kustomize apply) serves the blueprint
form on-cluster with dry-run generation working.

---

### v1.25 — Service mode and authentication (login)

**Problem:** The API and portal are unauthenticated and assume trusted local use.
Running repave as a shared hosted service needs identity and protected endpoints.

**Approach:**

- **Service mode** config flag: local dev stays open (no auth); hosted mode
  requires authenticated sessions
- Session/JWT-backed login; protect all mutating API routes (generate, publish,
  register) and the portal
- Identify the acting user and record it in generation provenance/audit
- Config via `repave.config.yaml` + secrets (ties to v1.24 ConfigMap/secret wiring)

**Scope:** single-tenant (one org per instance); no per-tenant isolation.

**Dependencies:** v1.24 Kubernetes deploy path (hosted service); stable API surface.

**Done when:** A hosted repave instance rejects unauthenticated API/portal access,
and a logged-in user can complete a generation.

---

### v1.26 — SSO via OIDC and role-based access

**Problem:** Enterprises require IdP-managed login (Okta, PingID, Entra, Auth0),
not local accounts.

**Approach:**

- Generic OIDC/OAuth2 authorization-code login (provider-agnostic: issuer URL,
  client id/secret, scopes) so Okta/PingID/Entra/Auth0 all work
- Map IdP group/role claims to repave roles: `viewer` (read/dry-run), `generator`
  (generate/publish), `admin` (register/inventory/config)
- Enforce roles on API endpoints; record the authenticated identity in the
  generation provenance/audit trail

**Dependencies:** v1.25 authentication foundation.

**Done when:** Login is delegated to an OIDC IdP and endpoint access is gated by
mapped role claims; docs show an Okta and a PingID configuration example.

---

### v1.27 — Remote and forked blueprint packs

**Problem:** Blueprints live only under `blueprints/` in the repave repo; enterprises
want to fork repave and add paths, or pull read-only blueprint packs from git.

**Approach:**

- `repave.config.yaml` `blueprints_root` or `blueprint_sources[]` (local paths)
- CLI/API `--blueprint` accepts absolute path or `file://` under configured roots
- Document fork workflow: copy repave, add `blueprints/my-org-*`, pin org standards
- Defer git/OCI remote fetch to parking lot unless needed for v2

**Dependencies:** Blueprint loader and schema validation (stable since v1.0).

**Done when:** A forked repave repo loads an additional blueprint from its own
tree without patching engine code.

---

## v2.0.0 — Platform GA

**Target:** Repave as the **control plane for golden-path estates** — not only a
generator.

**Planned capabilities (must-have for v2):**

| Capability | Built in releases |
| --- | --- |
| Generate compliant module repos | v1.0–v1.10 (done) |
| Enforce module standard via Checkov | v1.11, v1.20 |
| Multiple artifact types (Terraform + Ansible) | v1.12–v1.15, v1.19 |
| Self-heal drift and version bumps | v1.16, v1.18, v1.23 |
| Fleet visibility | v1.23 inventory → v2 operator GA |
| Module repos self-govern in CI | v1.22 |
| On-cluster deploy | v1.24 |
| Authenticated single-tenant service (OIDC SSO) | v1.25–v1.26 |

**Breaking-change candidates (major bump):**

- Blueprint API `repave.dev/v1beta1` or `v2alpha1` with frozen CRD shapes
- `GoldenPathRepo` / `Blueprint` CRD GA with migration guide from v1 inventory
- Output contract: required `repave.yaml` provenance file in generated repos
- Semantic versioning policy: blueprint `metadata.version` tied to template
  breaking changes

**Non-goals for v2 (remain parking lot or post-v2):**

- **Multi-tenant SaaS repave** — org isolation, per-tenant config/RBAC; the
  multi-tenant follow-on to the single-tenant SSO shipped in v1.25–v1.26
- OPA/Sentinel plan-time policy as default gate
- Private blueprint registry over OCI

**Done when:**

1. Operator opens remediation PRs for drift and standard bumps across registered repos.
2. `repave update` upgrades an existing module repo via PR.
3. At least two production golden paths ship with standards + lint/policy packs.
4. Documentation describes fork → customize standards/blueprints → fleet reconcile
   without referring to unreleased features.

---

## Parking lot

Ideas not yet scheduled for pre-v2 work — promote into [Planned](#planned) when
there is an owner and a target release.

- **Ansible collection golden path** — multi-role collection repo (`galaxy.yml`,
  `roles/`, `plugins/`) building on the v1.14 role path
- **Ansible playbook/project golden path** — `site.yml`, `inventories/`,
  `group_vars/`, `roles/` project scaffold
- **Molecule as a required gate** — make molecule non-skippable once test runners
  are standardized in CI
- **SAML 2.0 IdP support** — enterprise IdPs that prefer SAML over OIDC
- **Auth proxy deployment** — oauth2-proxy / IdP sidecar in front of API/portal as
  an alternative to in-app OIDC
- **Standards diff in portal** — side-by-side standard/policy changes between
  blueprint versions before generate
- **OPA/Sentinel gate** — optional policy gate on plan JSON after `terraform plan`
- **Private blueprint registry** — pull blueprint packs from git tag or OCI artifact
  (beyond local fork paths in v1.27)
- **Multi-tenant repave** — org-scoped config, standards, output roots, RBAC
- **Catalog automation** — regenerate `provider-catalog.json` on provider release
  webhook or scheduled workflow
- **Real resource scaffolds** — optional blueprint mode that emits provider resources
  instead of `null_resource` placeholders (per cloud/resource type)
- **License/policy pack** — optional LICENSE and compliance metadata generation
  (revisit v1.5 license UI with standards-driven templates)

---

## Release mechanics

Releases follow [Conventional Commits](https://www.conventionalcommits.org/) on
`main` via python-semantic-release. See [README § Releases](../README.md#releases).

Roadmap **version numbers** are planning labels; actual semver is driven by
commit types at merge time (`feat` → minor, `fix` → patch).
