# repave roadmap

Planning document for repave evolution. The [README](../README.md) keeps a
one-line summary per release; this file holds the detail we use when scoping
work, writing ADRs, and opening issues.

**Current release:** v1.15.0  
**Planning horizon:** v1.16 → v2.0.0 (platform maturity — governed estate at scale)

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
v1.15  today       Ansible role golden path; yamllint/ansible-lint/syntax/molecule gates
  │
  ├─ v1.16–v1.17    multi-artifact    Ansible role standard + policy pack; operator alpha
  ├─ v1.18–v1.20    operate + extend  portal UX; module updates; more golden paths
  ├─ v1.21–v1.25    estate-ready      standards pack; provenance; module CI; operator beta; k8s deploy
  ├─ v1.26–v1.27    service + SSO     authenticated single-tenant service via OIDC
  ├─ v1.29–v1.34    operate + expand  conformance harness; observability; notifications; catalog; Helm + app-service paths
  ├─ v1.35–v1.38    operate in prod   health/HPA; alerts + SLOs; upgrade/rollback; runbooks
  ├─ v1.39          policy-as-code    optional OPA/conftest gate on plan + manifests
  ├─ v1.40          observability     dashboards/alerts/monitors as code (Datadog/Grafana/Prom/OTel)
  │
  v2.0.0             platform GA       operator GA, stable contracts, fleet upgrades; conversational governed AI generation
```

| Theme | Releases | Outcome |
| --- | --- | --- |
| **Governance depth** | v1.11, v1.12, v1.14, v1.21, v1.39 | Standards, Checkov, secrets scan, provenance, and opt-in OPA policy-as-code enforce the module contract, not just document it |
| **Multi-artifact golden paths** | v1.13–v1.16, v1.33–v1.34, v1.40 | Engine decoupled from Terraform; Ansible role, Helm chart, app-service, and observability-as-code paths ship with standards + gates |
| **Self-healing** | v1.17, v1.19, v1.24 | Drift detection and blueprint/standard upgrades via PR |
| **Usability** | v1.18, v1.22 | Portal and CLI usable by non-experts; visible pinned versions |
| **Estate scale** | v1.20, v1.23, v1.25 | Multiple golden paths; generated repos CI themselves; k8s deploy option |
| **Access and multi-user** | v1.26–v1.27 | Authenticated single-tenant service with OIDC SSO and role-based access |
| **Blueprint quality** | v1.29 | Every blueprint is rendered, gated, and snapshot-tested in CI |
| **Operability and audit** | v1.30–v1.32 | Metrics, audit log, notifications, and developer-portal catalog registration |
| **In-cluster operations (Day-2)** | v1.35–v1.38 | Ops teams can run, scale, alert on, upgrade, and troubleshoot the service |
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

### v1.10 — Checkov policy pack

- In-repo custom policies at `examples/checkov/policies`
- Starter YAML policies `CKV2_REPAVE_1`–`CKV2_REPAVE_2` for Terraform version bounds
- Policies copied into generated modules at `policy/checkov/`
- Generated `.checkov.yml` and blueprint `gate_config.checkov`
- Optional `gates.checkov.skip_checks` in `repave.config.yaml`
- PR branch cleanup workflow + `delete_branch_on_merge` on the repo

### v1.11 — Module-standard Checkov rules

- Python policies `CKV2_REPAVE_3`–`CKV2_REPAVE_7` enforce layout, required inputs,
  and shared-local usage in resource scaffolds
- Policy pack v1.1.0; fixture tests under `examples/checkov/tests/`; pack README
- Checkov gate sets `REPAVE_CHECKOV_SCAN_ROOT` for reliable module-root resolution

### v1.12 — Security Checkov pack and secrets gate

- Security policies `CKV2_REPAVE_8`–`CKV2_REPAVE_12` ban credential literals, hardcoded
  secrets, provisioners, and undeclared sensitive outputs
- Dedicated `secrets` gate scans rendered modules with Checkov's secrets framework
- Policy pack v1.2.0; extended fixture coverage and gate tests in `engine/tests/`
- Blueprint and schema gate enum include `secrets` alongside `checkov`

### v1.13 — Gate registry and blueprint gate extensibility

- Replace hard-coded gate dispatch with a **gate registry** (`gate_registry.py`,
  `gate_builtin.py`, `gate_runners.py`); `run_gates()` resolves runners from the registry
- Blueprint `gate_config` extended for `tflint`, `terraform-validate`, and
  `terraform-test`; optional `artifactType` on blueprints drives artifact hygiene
- Artifact paths are **artifact-type aware** (Terraform + Ansible-role placeholders)
- `terraform-test` gate registered (skips when no `.tftest.hcl` files); plugin hook via
  `repave.gates` entry points for org-specific gates without editing core dispatch

### v1.14 — Provenance and standards decoupling

- `repave.yaml` provenance via `engine/src/repave_engine/provenance.py` and
  `schemas/golden-path-artifact.schema.json` (`repave.dev/v1beta1`)
- Artifact-type aware provenance: `terraformModule` block for modules, `ansibleRole`
  for Galaxy roles; Checkov pin only on Terraform artifacts
- `provenance-drift` gate validates presence + JSON Schema; optional via
  `spec.output.provenance.file` on blueprints (enabled on terraform-module-generic)
- Provider catalog validation skipped for non-Terraform `artifactType` values

### v1.15 — Ansible role golden path (current)

- New `blueprints/ansible-role-generic/` producing a Galaxy-compatible role layout
- Inputs: `role_name`, `namespace`, `description`, `min_ansible_version`,
  `target_platforms`
- Template: `meta/main.yml`, `tasks/`, `defaults/`, `handlers/`, `vars/`,
  `molecule/default/`, `README.md`, `.yamllint`, `.ansible-lint`
- Gates: `yamllint`, `ansible-lint`, `ansible-syntax-check`, `molecule`
  (skip-if-not-installed), `docs-drift`, `provenance-drift`
- Output naming: `ansible-role-{role_name}`; provider scope skipped (no catalog)
- Baseline Ansible role standard stub at `examples/standards/ansible-role-standard.md`

---

## Planned

### v1.16 — Ansible role standard + ansible-lint policy pack

**Problem:** The Ansible role path needs an enforceable standard, mirroring the
Terraform module standard + Checkov pack, so generated roles are governed rather
than just scaffolded.

**Approach:**

- Vendor an Ansible role standard under `examples/standards/` (parallel to the
  Terraform module standard), pinned by the blueprint
- Ship an ansible-lint config/ruleset pack copied into generated roles (parallel
  to the Checkov pack at `examples/checkov/policies`)
- Unit-test the ruleset against fixture roles

**Dependencies:** v1.15 Ansible role golden path; v1.13 gate registry.

**Done when:** A generated role fails ansible-lint when the standard is violated;
the blueprint pins the pack version.

---

### v1.17 — Reconciliation operator

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

### v1.18 — Portal and UX hardening

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

### v1.19 — Update existing module repositories

**Problem:** Today repave bootstraps **new** repos; upgrading an existing module
requires manual merge or re-generation.

**Approach:**

- `repave update` (or blueprint flag) targeting an existing module repo path
- Three-way aware merge or PR-only flow that preserves user edits outside scaffold
- Operator integration for fleet-wide upgrades (ties to v1.17)

**Done when:** A module repo created by repave can receive a blueprint version
bump via PR without full manual copy.

---

### v1.20 — Additional golden paths

**Problem:** Beyond the Terraform module and Ansible role paths, platform teams
need more artifact types.

**Candidates (prioritize with product input):**

| Golden path | Output | Notes |
| --- | --- | --- |
| Cloud resource module (single resource) | Thin `tfm-*` wrapper | Subset of generic blueprint |
| Environment stack bootstrap | `env-*` composition repo | Consumes pinned module versions |
| Ansible collection / playbook project | Collection or project repo | Builds on the v1.15 role path (see parking lot) |

**Dependencies:** v1.13 gate registry; v1.14 artifact-type provenance.

**Done when:** At least one new blueprint ships with gates, standards pin, and docs.

---

### v1.21 — Estate standards pack (multi-file)

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

### v1.22 — Generation provenance and version visibility

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
artifact-type-aware provenance (v1.14).

**Done when:** A module repo clearly states its golden-path lineage without reading
repave source.

---

### v1.23 — Generated module CI template

**Problem:** Module repos rely on authors to wire CI; gates run in repave at
generate time but not necessarily on every subsequent PR in the module repo.

**Approach:**

- Render `.github/workflows/terraform-gates.yml` (or similar) into each generated
  module using the same gate list as the blueprint
- Document required secrets/runners (none for fmt/validate/tflint/checkov/test)
- Align workflow toolchain versions with `deploy/local/Dockerfile`

**Dependencies:** v1.10 Checkov config in module root; v1.13 gate registry for the
shared gate-list contract.

**Done when:** A freshly published module runs fmt, validate, tflint, checkov, and
`terraform test` on push without manual workflow authoring.

---

### v1.24 — Operator beta and fleet inventory

**Problem:** v1.17 operator scope is large; teams need a minimal inventory model
before full reconciliation.

**Approach:**

- Define `GoldenPathRepo` CRD (repo URL, pinned blueprint, standard, policy versions)
- Operator **inventory mode**: list/watch registered repos, report drift vs pins
  (read-only, no PRs yet)
- CLI/API `repave register` to add a generated repo to the inventory
- Design doc for upgrade PR flow (feeds v1.17 GA and v1.19 update command)

**Dependencies:** v1.17 CRD design; v1.22 provenance fields.

**Done when:** Operator reports “out of date” repos when blueprint standard/policy
version bumps on `main`.

---

### v1.25 — Kubernetes deploy path

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

### v1.26 — Service mode and authentication (login)

**Problem:** The API and portal are unauthenticated and assume trusted local use.
Running repave as a shared hosted service needs identity and protected endpoints.

**Approach:**

- **Service mode** config flag: local dev stays open (no auth); hosted mode
  requires authenticated sessions
- Session/JWT-backed login; protect all mutating API routes (generate, publish,
  register) and the portal
- Identify the acting user and record it in generation provenance/audit
- Config via `repave.config.yaml` + secrets (ties to v1.25 ConfigMap/secret wiring)

**Scope:** single-tenant (one org per instance); no per-tenant isolation.

**Dependencies:** v1.25 Kubernetes deploy path (hosted service); stable API surface.

**Done when:** A hosted repave instance rejects unauthenticated API/portal access,
and a logged-in user can complete a generation.

---

### v1.27 — SSO via OIDC and role-based access

**Problem:** Enterprises require IdP-managed login (Okta, PingID, Entra, Auth0),
not local accounts.

**Approach:**

- Generic OIDC/OAuth2 authorization-code login (provider-agnostic: issuer URL,
  client id/secret, scopes) so Okta/PingID/Entra/Auth0 all work
- Map IdP group/role claims to repave roles: `viewer` (read/dry-run), `generator`
  (generate/publish), `admin` (register/inventory/config)
- Enforce roles on API endpoints; record the authenticated identity in the
  generation provenance/audit trail

**Dependencies:** v1.26 authentication foundation.

**Done when:** Login is delegated to an OIDC IdP and endpoint access is gated by
mapped role claims; docs show an Okta and a PingID configuration example.

---

### v1.28 — Remote and forked blueprint packs

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

### v1.29 — Blueprint conformance CI harness

**Problem:** Each new golden path (Ansible, Helm, app service) increases the risk
of silent breakage. Today only engine unit tests exist; blueprints are not
systematically rendered and gated in CI, so a template regression can ship
unnoticed.

**Approach:**

- CI job that, for every `blueprints/*/blueprint.yaml`, validates it against
  `schemas/blueprint.schema.json`, renders it with representative fixture inputs,
  runs the blueprint's declared gates, and asserts no unresolved `{{ }}`
  placeholders and that required files are present
- Snapshot (golden-file) tests of rendered output to catch unintended template
  drift, with a `make` target to update snapshots on purpose
- Matrix across artifact types; tool-dependent gates reuse the skip-if-not-installed
  pattern so the harness is green without every CLI installed
- Fixture inputs live alongside each pack (e.g. `blueprints/<name>/tests/`)

**Dependencies:** v1.13 gate registry (uniform gate invocation); existing pytest
infrastructure. Recommended to land alongside v1.13–v1.16 since it guards every
new golden path.

**Done when:** CI fails if any blueprint fails to render or violates its gates,
and snapshot diffs surface template changes during review.

---

### v1.30 — Generation observability and audit log

**Problem:** There is no durable record of who generated what, when, and with
which pins, and no metrics for operating repave as a shared service.

**Approach:**

- Structured audit record per generation: blueprint + version, standard and policy
  pins, inputs summary, output repo, acting user identity (from v1.26 auth), gate
  results, and timestamp, written to a configurable sink (JSONL first, DB later)
- Prometheus-style `/metrics` on the API (generation counts, gate pass/fail,
  durations)
- OpenTelemetry spans across the pipeline stages (validate → render → gates →
  publish) in `engine/src/repave_engine/pipeline.py`, with a configurable exporter
- Correlate audit records with the generated `repave.yaml` provenance

**Dependencies:** v1.26 authentication (acting-user identity); provenance fields
(v1.22).

**Done when:** Every generation emits an audit record and metrics, and a trace
shows per-stage timing.

---

### v1.31 — Outbound notifications

**Problem:** Teams get no push signal when a module is generated or published, or
when drift is detected.

**Approach:**

- Pluggable notifier config in `repave.config.yaml` (Slack webhook, Microsoft
  Teams webhook, generic webhook)
- Events: generation succeeded/failed, PR opened, publish complete; later operator
  drift/remediation events
- Payload includes target repo, blueprint + version, gate summary, and PR link
- Best-effort delivery with retries and secret redaction; never blocks a generation

**Dependencies:** Publish flow (`engine/src/repave_engine/pr.py`,
`engine/src/repave_engine/github.py`); operator events (v1.17/v1.24) for drift.

**Done when:** A successful publish posts a Slack or Teams message with the PR link
and gate summary.

---

### v1.32 — Backstage software catalog integration

**Problem:** Generated repositories are not registered in the organization's
developer portal; many platform teams standardize on Backstage.

**Approach:**

- Optionally render `catalog-info.yaml` into generated repos (component kind,
  owner/system/lifecycle inputs, links, and repave provenance annotations)
- Add owner/system/lifecycle blueprint inputs
- Document a Backstage Scaffolder custom action that calls the repave API
  (dry-run + generate) so repave golden paths appear as Backstage templates
- Annotate with blueprint/standard pins for TechInsights-style checks

**Dependencies:** v1.22 provenance fields; stable API surface.

**Done when:** A generated repo contains a valid `catalog-info.yaml` importable
into Backstage, and docs show the scaffolder action.

---

### v1.33 — Helm chart golden path

**Problem:** Teams deploying to Kubernetes want a governed Helm chart scaffold, not
only IaC modules.

**Approach:**

- New `blueprints/helm-chart-generic/` producing a lint-clean chart (`Chart.yaml`,
  `values.yaml`, `templates/`, `_helpers.tpl`, `NOTES.txt`, `tests/`)
- Inputs: `chart_name`, `app_name`, `description`, image repo/tag, service type,
  ingress toggle
- Gates: `helm-lint`, `helm-template` (render), `yamllint`, optional `kubeconform`,
  `docs-drift`, `provenance-drift` — all declared via the gate registry
- Output naming: `helm-{chart_name}`

**Dependencies:** v1.13 gate registry; v1.14 artifact-type provenance; v1.29
conformance harness.

**Done when:** A chart generates and passes helm lint/template where helm is
present, and skips cleanly where it is absent.

---

### v1.34 — Application service scaffold golden path

**Problem:** New services are bootstrapped inconsistently; teams want a governed
application repository from the same golden-path engine.

**Approach:**

- New `blueprints/app-service-generic/` producing a service repo: `Dockerfile`, CI
  workflow, lint/test config, `README.md`, an optional Helm chart reference (v1.33),
  and `catalog-info.yaml` (v1.32)
- Inputs: `service_name`, `runtime` (enum), `owner`, `port`
- Gates: `docs-drift`, `provenance-drift`, `dockerfile-lint` (hadolint), language
  lint/test (skip-if-not-installed); the generated CI runs the same gates on push
  (reusing the v1.23 module-CI-template pattern)
- Ship one runtime first (e.g. Python or Go); add others as follow-ons

**Dependencies:** v1.13 gate registry; v1.14 provenance; v1.23 CI template pattern;
v1.29 conformance harness.

**Done when:** A service repo generates for at least one runtime with CI wired and
gates green.

---

### v1.35 — Service health, resource management, and autoscaling

**Problem:** The v1.25 deploy installs the API and portal but defines no health
probes, resource guarantees, disruption budget, or autoscaling, so an ops team
cannot run it reliably or plan capacity.

**Approach:**

- Liveness/readiness/startup probes: `/healthz` liveness; `/readyz` readiness that
  checks config/token presence and downstream reachability
- Resource requests/limits with documented sizing guidance
- HorizontalPodAutoscaler on CPU/concurrency with a documented generation-concurrency
  knob
- PodDisruptionBudget and graceful shutdown (drain in-flight generations on SIGTERM,
  bounded `terminationGracePeriodSeconds`)
- Expose all of the above as configurable values in the v1.25 chart / Kustomize

**Dependencies:** v1.25 Kubernetes deploy path; may add health endpoints to the API.

**Done when:** Draining a node or scaling replicas drops no in-flight requests; the
HPA scales under load; probes gate traffic correctly.

---

### v1.36 — Alerting rules, SLOs, and dashboards

**Problem:** v1.30 emits metrics and traces, but ops teams have no alerts, SLOs, or
dashboards to detect and triage problems.

**Approach:**

- Define SLOs (availability, generation success rate, p95 generation latency) with
  error budgets
- Ship `PrometheusRule` alert rules under `deploy/k8s/` (error-rate spike, gate-failure
  spike, latency, HPA saturation, publish/GitHub failures, token near-expiry)
- Ship a Grafana dashboard JSON (generation throughput, success/fail, per-stage timing
  from v1.30, saturation)
- Map alert severities to first-response runbook links (v1.38)

**Dependencies:** v1.30 metrics + traces; v1.35 saturation signals.

**Done when:** Alerts fire in a test cluster on induced failures, and the dashboard
shows throughput, success rate, and per-stage latency.

---

### v1.37 — Zero-downtime upgrade and rollback

**Problem:** There is no documented, safe upgrade/rollback path for the in-cluster
service; upgrades risk dropping requests or breaking on config/schema changes.

**Approach:**

- Versioned Helm releases with a rolling-update strategy (`maxUnavailable`/`maxSurge`)
  leveraging the v1.35 probes and PodDisruptionBudget
- Backward-compatibility policy for API/schema/config within a minor, with migration
  notes for breaking config changes
- Forward-compatible handling and documented migration steps for the v1.30 audit
  sink/inventory when it is backed by a database
- `helm rollback` runbook with image digest pinning and a pre-upgrade smoke check
  (reuse the v1.25 kind smoke test)
- Optional canary via two releases / weighted routing (documented, not required)

**Dependencies:** v1.25 Helm packaging; v1.35 probes/PDB; v1.30 audit sink schema.

**Done when:** An upgrade and a rollback complete with no dropped requests in a test
cluster, following the documented steps.

---

### v1.38 — Operations runbooks and troubleshooting

**Problem:** Ops teams lack runbooks for common failures and routine day-to-day tasks.

**Approach:**

- On-call runbook under `docs/operations/` (service overview, dashboards/alerts,
  escalation)
- Failure playbooks: expired/invalid `GITHUB_TOKEN`, GitHub API rate limiting,
  OIDC/IdP outage (v1.27), missing gate tool in the image, stuck/failed generation,
  audit sink full, PVC/disk pressure
- Routine ops: reading logs/traces/audit records, scaling, rotating secrets,
  draining/cordoning, safe restart
- Link each v1.36 alert to a runbook section

**Dependencies:** v1.30 logs/traces/audit; v1.31 notifications; v1.36 alerts;
v1.27 auth.

**Done when:** Each shipped alert links to a runbook step, and the runbook covers the
top failure modes with concrete commands.

---

### v1.39 — Policy-as-code gate (OPA/conftest)

**Problem:** Governance today is Checkov static scanning of Terraform source files.
Teams want custom policy-as-code (Rego) evaluated against Terraform **plan JSON**
and rendered Helm/Kubernetes manifests — richer than static config scanning for
cross-resource and plan-time rules — as an opt-in gate.

**Approach:**

- Add an `opa` (conftest) gate via the v1.13 gate registry, using the same
  skip-if-not-installed pattern as the other tool gates
- Terraform: evaluate against `terraform plan -json` (or a converted plan file);
  Helm/k8s: evaluate against `helm template` output
- Ship a starter Rego policy pack under `examples/opa/policies/` (parallel to
  `examples/checkov/policies`), copied into generated repos at `policy/opa/`;
  blueprint `gate_config.opa` (policies dir, namespaces, fail severity)
- Unit-test policies with fixture plan JSON and manifests
- Opt-in per blueprint (not a default gate); document how to add org Rego rules

**Dependencies:** v1.13 gate registry; v1.14 artifact-type provenance (Helm plan/
template); Checkov pack pattern (v1.10–v1.12).

**Done when:** A blueprint declaring the `opa` gate fails generation when a Rego
policy denies the plan/manifest, and skips cleanly when conftest/opa is absent.

---

### v1.40 — Observability-as-code golden path

**Problem:** Teams hand-craft dashboards, alerts, monitors, and SLOs
inconsistently and ungoverned. They want compliant observability artifacts for
their own services across Datadog, Grafana, Prometheus, and OpenTelemetry, with
naming, required tags/annotations, severity, and runbook links enforced. (Distinct
from v1.36, which instruments repave itself.)

**Approach:**

- New `blueprints/observability-as-code-generic/` with `artifactType: observability`
  (v1.14)
- Inputs: `service_name`, `backend` (datadog | grafana | prometheus | otel),
  `output_mode` (native | terraform), owner/team, notification target, SLO targets
- **Native mode** emits Grafana dashboard JSON + alert rules, `PrometheusRule` +
  Alertmanager route YAML, OTel Collector config, and Datadog monitor/dashboard/SLO
  JSON
- **Terraform mode** emits Terraform using the Datadog and Grafana providers,
  reusing the existing Terraform engine and terraform-fmt/validate/tflint/checkov
  gates
- Gates via the v1.13 registry: native → `promtool check rules`,
  `amtool check-config`, jsonnet/JSON-schema lint, `datadog validate` (or schema),
  `yamllint`; terraform → existing terraform gates; plus `docs-drift`,
  `provenance-drift`, and opt-in `opa` (v1.39) enforcing policy (every alert has
  severity + runbook annotation; dashboards tagged with owner/service);
  skip-if-not-installed as usual
- Ship an observability standard under `examples/standards/` (naming, required
  tags/annotations, SLO structure, runbook links) pinned by the blueprint

**Dependencies:** v1.13 gate registry; v1.14 artifact-type provenance; v1.39 OPA
(opt-in policy); existing Terraform engine (terraform mode); v1.29 conformance
harness for CI coverage.

**Done when:** The blueprint generates governed dashboards/alerts/monitors for at
least one backend in both native and terraform modes, passing validation gates
where tools are present and skipping cleanly otherwise.

---

## v2.0.0 — Platform GA

**Target:** Repave as the **control plane for golden-path estates** — not only a
generator.

**Planned capabilities (must-have for v2):**

| Capability | Built in releases |
| --- | --- |
| Generate compliant module repos | v1.0–v1.14 (done) |
| Enforce module standard via Checkov | v1.11, v1.12, v1.21 |
| Provenance in generated repos | v1.14 |
| Custom policy-as-code gate (OPA/conftest) | v1.39 |
| Multiple artifact types (Terraform, Ansible, Helm, app service, observability) | v1.13–v1.16, v1.20, v1.33–v1.34, v1.40 |
| Blueprint conformance in CI | v1.29 |
| Self-heal drift and version bumps | v1.17, v1.19, v1.24 |
| Fleet visibility | v1.24 inventory → v2 operator GA |
| Module repos self-govern in CI | v1.23 |
| On-cluster deploy | v1.25 |
| Authenticated single-tenant service (OIDC SSO) | v1.26–v1.27 |
| Operability and audit (metrics, audit log, notifications, catalog) | v1.30–v1.32 |
| Day-2 operability (health, SLOs, upgrades, runbooks) | v1.35–v1.38 |
| Conversational / governed AI generation | v2 (see below) |

**Breaking-change candidates (major bump):**

- Blueprint API `repave.dev/v1beta1` or `v2alpha1` with frozen CRD shapes
- `GoldenPathRepo` / `Blueprint` CRD GA with migration guide from v1 inventory
- Output contract: required `repave.yaml` provenance file in generated repos
- Semantic versioning policy: blueprint `metadata.version` tied to template
  breaking changes

**Non-goals for v2 (remain parking lot or post-v2):**

- **Multi-tenant SaaS repave** — org isolation, per-tenant config/RBAC; the
  multi-tenant follow-on to the single-tenant SSO shipped in v1.26–v1.27
- OPA/Sentinel as a *default/required* gate (v1.39 ships OPA opt-in; making it
  mandatory estate-wide, and Sentinel support, stay post-v2)
- Private blueprint registry over OCI

**Done when:**

1. Operator opens remediation PRs for drift and standard bumps across registered repos.
2. `repave update` upgrades an existing module repo via PR.
3. At least two production golden paths ship with standards + lint/policy packs.
4. Documentation describes fork → customize standards/blueprints → fleet reconcile
   without referring to unreleased features.

### Conversational and governed AI generation

**Problem:** Users want to describe intent in natural language ("generate a script,
module, or dashboard to do X") and receive a compliant artifact — without an
ungoverned AI that bypasses repave's guarantees.

**Approach:**

- Natural-language front-end (chat) over the engine: intent → LLM draft → the draft
  is treated as **candidate** output and must pass the same non-negotiable gates
  (lint, security scan, Checkov, OPA policy from v1.39) before it is ever returned
  or published — governance-by-construction still holds, with no bypass
- Ground drafts in existing blueprint inputs and standards so generation starts from
  governed scaffolds rather than free-form text
- Record provenance (v1.14) and an audit entry (v1.30) for every AI-assisted
  generation — model, prompt hash, and gate results — and explain which gate/policy
  blocked an output when it fails
- Guardrails for prompt injection, secret leakage, cost/rate limits, and
  reproducibility

**Dependencies:** v1.13 gate registry; v1.14 provenance; v1.30 audit log; v1.39 OPA
policy gate; a broad golden-path/standard library (v1.15, v1.33, v1.34, v1.40).

**Why v2:** its safety depends on the mature v1 governance plumbing, so it layers on
top rather than shipping as a v1 golden path.

**Done when:** A user can describe intent conversationally and only receive artifacts
that passed every configured gate and policy, with full provenance and audit trail.

---

## Parking lot

Ideas not yet scheduled for pre-v2 work — promote into [Planned](#planned) when
there is an owner and a target release.

- **Ansible collection golden path** — multi-role collection repo (`galaxy.yml`,
  `roles/`, `plugins/`) building on the v1.15 role path
- **Ansible playbook/project golden path** — `site.yml`, `inventories/`,
  `group_vars/`, `roles/` project scaffold
- **Molecule as a required gate** — make molecule non-skippable once test runners
  are standardized in CI
- **SAML 2.0 IdP support** — enterprise IdPs that prefer SAML over OIDC
- **Auth proxy deployment** — oauth2-proxy / IdP sidecar in front of API/portal as
  an alternative to in-app OIDC
- **Standards diff in portal** — side-by-side standard/policy changes between
  blueprint versions before generate
- **Private blueprint registry** — pull blueprint packs from git tag or OCI artifact
  (beyond local fork paths in v1.28)
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
