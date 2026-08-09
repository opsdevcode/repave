# repave roadmap

Planning document for repave evolution. The [README](../README.md) keeps a
one-line summary per release; this file holds the detail we use when scoping
work, writing ADRs, and opening issues.

**Current release:** v2.39.2  

**In progress:** [Platform as a product](#platform-as-a-product-v2x) follow-on (v1.89);
[FinOps enablement](#finops-enablement-v2x) (v1.92–v1.94) paused after estimate policy.
Fine-grained Auth0 FGA stays in the [parking lot](#parking-lot). v3 themes under
[beyond v2.0.0](#beyond-v200--autonomous-estate-and-lifecycle-control-plane).
**Shipped on `main`:** **Guided / Advanced forms (v1.88)** — progressive disclosure on
`terraform-module-generic` and `ansible-role-generic` (`InputField.advanced`, form depth toggle;
freeform TF/Ansible extras deferred) ([`docs/portal-design.md`](portal-design.md));
**Platform stakeholder interfaces (v1.87)** — `/platform/compliance`,
`/platform/value-stream`, `GET /api/v2/platform/compliance|value-stream`
([`docs/platform-metrics.md`](platform-metrics.md)); **FinOps estimate policy (v1.91)** — `gates.infracost` org floor
(`required` / `max_monthly_usd`), estimate in audit + PR evidence, upgrade/import cost delta
([`docs/finops.md`](finops.md)); **FinOps tag governance (v1.90)** — required allocation tags on terraform/helm
golden paths, Checkov `CKV2_REPAVE_13`, OPA `allocation_tags`, `portal.cost_allocation.tag_keys`,
scorecard fail on incomplete tags ([`docs/finops.md`](finops.md)); **Platform feedback loop (v1.86)** — CSAT + friction capture on result/run-console,
`/platform/feedback`, `GET|POST /api/v2/platform/feedback` ([`docs/platform-metrics.md`](platform-metrics.md));
**Platform adoption / DX metrics (v1.85)** — `/platform/adoption`,
`GET /api/v2/platform/metrics`, `repave metrics adoption`, snapshot CronJob
([`docs/platform-metrics.md`](platform-metrics.md)); **State store shared-deploy Helm knobs** (`repave.stateStore` +
[`state-store-enablement.md`](operations/state-store-enablement.md); still off by default);
**plan-JSON config edges** on transaction preview/commit (`edges_from_plan_json` →
`replace_graph` `extra_edges`); **GitHub repository provisioning goldpath** (`github-repo-generic` —
template or selection create, org team grants, Platform catalog family, `repave create-repo`,
`GET /api/v2/github/teams` — [github-repo-goldpath](github-repo-goldpath.md); phase 2:
`default-pr` rulesets, additive membership sync from a source org team, fleet register →
`GoldenPathRepo`); **State custody and the resource graph** — authoritative Terraform
state store, queryable resource graph, and gate-blocked transactions
([ADR 004](adr/004-state-custody-and-the-resource-graph.md),
[ADR 005](adr/005-state-graph-build-vs-buy.md),
[`docs/state-graph.md`](state-graph.md)); off by default, Phase 4 **no-go** recorded
([`state-graph-phase4-review.md`](state-graph-phase4-review.md));
**Auth0 portal access** — engine/Helm hardening plus operator runbook
([`docs/operations/auth0-portal.md`](operations/auth0-portal.md), Action
[`post-login-groups.js`](../deploy/k8s/auth0/post-login-groups.js),
[`values-auth0.yaml`](../deploy/k8s/chart/values-auth0.yaml)); tenant secrets and hosted
EKS wiring live in private infra, not this repo. **in-cluster K8s cost allocation**
(`portal.cost_reader: k8s`); **Composite paved roads (v1.84)** — `microservice-full` bundle (app, Helm, GitOps,
dashboards, monitors, SLO), `service-stack` Terraform module member, portal bundle preset chips;
**App-service layout archetypes** (`appService.layout` on
`app-service-generic`: `worker`, `scheduled-job`, `grpc` for Python, Go, Node.js, Java, and .NET;
`buf-lint` gate for grpc — [v1.83](#v183--runtime-and-archetype-breadth)); **Multi-component brownfield add** (`repave add`, `spec.components[]`
in provenance, per-component verify, portal add action on service detail,
`POST /api/v2/components/plan|apply` — [v1.82](#v182--repave-add-paved-roads-for-existing-repositories),
[`docs/add.md`](add.md)); **GitOps delivery golden path** (`gitops-deployment-generic` — Argo CD
`Application` / Flux `HelmRelease`, `gitops` artifact family, exact-pin and sync-policy OPA
rules — [v1.79](#v179--gitops-delivery-golden-path)); **environment lifecycle Phase 3
follow-ups** (catalog/API cost badges for
vended environments, post-merge registry finalize on reclaim); **environment vending** (`kind: environment_vend`, portal request-environment,
JSONL registry + catalog merge, sandbox TTL auto-reclaim, non-sandbox draft decommission PRs,
`repave environments reclaim`, `POST /api/v2/environments/reclaim`, Helm reclaim CronJob —
[ADR 003](adr/003-environment-lifecycle-and-live-state.md) Phase 3); **deployment status** (`portal.deployment_reader` url/argocd/flux,
[ADR 003](adr/003-environment-lifecycle-and-live-state.md) Phase 1); **live plan** async run
(`kind: live_plan`, worker/Job + OPA on plan JSON, optional PR body attachment); engine hardening group A (A1–A6)
and **group B** maintainability (gate_runners
package, API/CLI splits, gate helpers, Python 3.12 floor, provenance gate exceptions); durability Phase 1–3 (including
**SQL OIDC sessions** when `database_url` is set); service decomposition Phase 0–4
(including CRD `repave.dev/v1beta1` + conversion webhook, publish idempotency,
per-run Kubernetes Jobs, decomposed chart CI smoke, **multi-replica portal chart smoke**,
**bundle async in worker mode**); **v2 contract freeze** (complete — `/api/v2` read models,
[`docs/api-v1-migration.md`](api-v1-migration.md) sunset, [`docs/repave-config-v1.md`](repave-config-v1.md),
hosted SQL requirement, **provenance required on publish**, [`docs/blueprint-versioning.md`](blueprint-versioning.md));
**Postgres DR** ([`docs/operations/postgres-backup-restore.md`](operations/postgres-backup-restore.md),
`make postgres-dr-drill`); **GitHub App authentication** for
publish/remediation; **day-2 chart operability** (`values-day2.yaml`, ServiceMonitor,
PrometheusRule, runbooks); **repo import to golden path** (Phase 1–3: overrides, trees-API
preview, batch import, rate-limit backoff — `repave import`, `/import`, `/import/batch`,
`/api/v2/imports/*`); **operator production Helm chart** (`deploy/k8s/operator-chart/`,
`values-day2.yaml`, `kind-co-install` Helm path, `chart-validate` operator checks);
**operator fleet campaigns** (`UpgradeCampaign` CRD, Blueprint controller, bounded
remediation PR concurrency, drift SLO metrics, campaign webhook summaries,
GitHub rate-limit parity); **governed PR conventions** (`pull_requests` in
`repave.config.yaml`, shared labels/branch prefixes, gate evidence checklist); **estate control
fleet sync + GPR prune**; **durability retry/reclaim + run list API**; **supply chain digest
pins** (GitHub Actions SHAs, base images, chart `image.digest`); **portal day-2 follow-ups**
(shared fleet PVC, worker HPA, CI action-pin gate); **portal live governance Tier 2**
(estate map polish, upgrade unified diffs, governance preflight hardening, bundle topology on
results, presenter mode); **developer portal surfaces** (library catalog, fleet scorecard
rollup, remote GitHub docs, upgrade/provenance rendering, owner filter, SLO health panel);
**cost visibility** (Infracost gate + CI, URL/AWS/Azure actuals, library tile badges, Cloud spend
scorecard).
**Platform console** (admin `/platform/*`: fleet register/unregister, ops health, standards
blast radius with **confirm-drift** async runs, operator campaign snapshot v2 with **in-portal
pause/resume**); **Helm fleet operator snapshot CronJob**
(`fleetOperatorSnapshot.cronJob`, `values-fleet-shared.yaml` — keeps `/platform/campaigns` fresh;
portal ServiceAccount **patch** on `upgradecampaigns` for campaign actions).
**Planning horizon:** v1.19 → v2.0.0 (platform maturity — governed estate at scale)
→ [beyond v2.0.0](#beyond-v200--autonomous-estate-and-lifecycle-control-plane)

Operator GA scope: [`operator-ga.md`](operator-ga.md).

Package tags follow conventional commits on `main`. The v1.18 **portal UX theme**
is complete as of v1.25.0 (see [Shipped — v1.18 portal](#v118--portal-ux-theme)).

**Doc version pointers:** `README.md`, `docs/roadmap.md` (**Current release** and
path `today` line), `docs/portal-design.md`, `docs/demo-verification.md`, and
`docs/operator-ga.md` are updated automatically on each engine release via
`scripts/sync_doc_versions.py` in the Release workflow. Run `make sync-doc-versions`
locally after bumping `engine` `__version__`.

---

## How to use this doc

- Add **future state** items under [Planned](#planned) with enough context to
  estimate and implement (problem, approach, dependencies, acceptance signals).
- Do **not** edit **Current release** in feature PRs (Release owns it; leave the blank
  line after it). Update **In progress** / **Shipped on `main`** and section status only.
- **Name open entries by theme, not by version.** Engine tags come from semantic-release
  on `main` and **align with major roadmap milestones** — see
  [Release mechanics](#release-mechanics) and [`docs/releases.md`](releases.md#roadmap-milestones-and-engine-semver).
  Planning labels (v1.72, v2.0.0) describe themes; the tag on GitHub is authoritative.
- Move items to [Shipped](#shipped) when they land on `main` and cut a release.
- Keep speculative ideas in [Parking lot](#parking-lot) until there is a concrete
  next step.
- Use [Path to v2.0.0](#path-to-v200) for the big-picture sequence and what v2
  means; individual releases below expand each step.
- [Beyond v2.0.0](#beyond-v200--autonomous-estate-and-lifecycle-control-plane) holds the
  next **major** theme only — a boundary marker, not a backlog. Entries there stay
  directional until they are promoted into [Planned](#planned) with a real
  problem/approach/done-when, and nothing lands from that section before v2 GA.
- Keep **tech debt** in [Engine hardening and tech debt](#engine-hardening-and-tech-debt)
  with the same problem/approach/done-when shape as features, and cite the file that
  carries the debt so the entry stays checkable.
- **Sunset / removal is product work.** Removing a capability (or dead UI surface) needs a
  roadmap entry or parking-lot note, a deprecation window when integrators depend on it, and
  the same problem/approach/done-when shape as features. Prefer deleting unused code over
  leaving half-wired surfaces — see [Platform as a product](#platform-as-a-product-v2x).
- Portal **visual and layout** planning: [`portal-design.md`](portal-design.md)
  (implements primarily under v1.18).
- Operator **local development and testing**: [`operator-local-dev.md`](operator-local-dev.md)
  (required for v1.17 GA / e2e and any operator change).
- Operator **CRD and controller standards**: [`operator-standards.md`](operator-standards.md)
  (required for every change under `operator/`).

---

## Path to v2.0.0

v2.0.0 is the **mature platform** milestone: repave governs a fleet of generated
repositories end-to-end — bootstrap, standards, policy, upgrade, and drift
remediation — not just one-shot module creation.

The ladder below runs one rung past that milestone. v2 is where the contracts freeze, so
it is also where the next major theme becomes definable — see
[beyond v2.0.0](#beyond-v200--autonomous-estate-and-lifecycle-control-plane) for what v3
means and why it cannot be pulled forward.

```text
v1.64.0+ today     dry-run runs real gates; policy/PACKS.md; observability OPA pack (catalog v1.3.0)
  │
  ├─ v1.67          Ansible role patterns   linux-service / windows-service catalog + portal picker
  ├─ v1.17 GA       operator-e2e CI; localPath inventory GA (repoURL landed later, v1.72–v1.73)
  ├─ v1.18–v1.22    operate + extend  portal UX; module updates; Ansible collection (shipped)
  ├─ v1.21–v1.26    estate-ready      standards pack; provenance; module CI; operator; k8s deploy
  ├─ v1.27–v1.28    service + SSO     authenticated single-tenant service via OIDC
  ├─ v1.31–v1.32    k8s artifacts     Helm chart + app-service golden paths (accelerated)
  ├─ v1.29–v1.34    operate + expand  conformance harness; observability; notifications; catalog
  ├─ v1.35–v1.38    operate in prod   health/HPA; alerts + SLOs; upgrade/rollback; runbooks (shipped)
  ├─ v1.39          policy-as-code    optional OPA/conftest gate on plan + manifests
  ├─ v1.40          observability     dashboards/alerts/monitors as code (Datadog/Grafana/Prom/OTel)
  ├─ v1.69–v1.70    ansible patterns  cross-platform role + pinned-roles rollout (shipped)
  ├─ v1.72–v1.73    remote inventory  operator observes and plans spec.repoURL repos (Phases A–B)
  │
  │  theme status at Platform GA cut line (shipped unless noted open on v2.0.0)
  │
  ├─ hardening       shipped — toolchain pin unification, subprocess timeouts, coverage in CI
  ├─ estate control  shipped — fleet registry + `repave register`; remote inventory + remediation
  ├─ k8s deploy      shipped — Helm chart + day-2 operability (portal + operator charts)
  ├─ durability      shipped — SQL store; async queue; DLQ + replay + portal /runs
  ├─ service split   shipped — portal / worker / corpus; operator on /api/v2 (portal/API split deferred)
  ├─ supply chain    shipped — GitHub App auth, governed PR, digest-pinned CI/images/chart
  ├─ fleet scale     shipped — Blueprint controller; upgrade campaigns; drift SLO metrics
  ├─ portal surfaces shipped — catalog, rendered docs, scorecards, observability read
  ├─ reach           shipped — repave verify; repo import; repave add; composite golden paths
  ├─ usability       shipped — `repave doctor`; queryable audit history
  ├─ cost            shipped — Infracost + actuals readers; library cost badges
  ├─ v2 contract     /api/v2 freeze, v1 migration docs, config v1, provenance-on-publish, blueprint schema (shipped)
  ├─ v2 resilience   Postgres DR runbook + `make postgres-dr-drill` (shipped)
  │
  v2.0.0             platform GA       contract freeze + DR → engine tag v2.0.0
  │
  v2.1+              environments      deployment status → gated plan on live state → vending (ADR 003)
  │
  v1.79–v1.84        paved roads       GitOps delivery + deploy pipeline; SLOs/runbooks shipped; `repave add` shipped; runtimes; bundles
  │
  v1.85–v1.89        platform-as-product  adoption/DX metrics → feedback → stakeholder views → cognitive load → roadmap evidence
  │
  v1.90–v1.94        FinOps enablement tag governance → estimate policy → showback/budgets → thin FOCUS → chargeback export
  │
  v3.0.0             autonomous        low-risk auto-merge, mandatory policy, fleet SLOs, lifecycle control plane, governed conversational AI
```

| Theme | Releases | Outcome |
| --- | --- | --- |
| **Governance depth** | v1.11, v1.12, v1.14, v1.21, v1.39 | Standards, Checkov, secrets scan, provenance, and OPA/conftest plan-time policy |
| **Multi-artifact golden paths** | v1.13–v1.16, v1.20, v1.22, v1.31–v1.32, v1.40 | Engine decoupled from Terraform; Ansible role/collection/playbook, Helm, app-service, observability paths |
| **Self-healing** | v1.17, v1.19, v1.24 | Drift detection and blueprint/standard upgrades via PR; local envtest/kind required |
| **Usability** | v1.18, v1.23 | Portal visual system and CLI usable by non-experts; visible pinned versions |
| **Estate scale** | v1.20, v1.24, v1.26 | Multiple golden paths; generated repos CI themselves; k8s deploy option |
| **Access and multi-user** | v1.27–v1.28 | Authenticated single-tenant service with OIDC SSO and role-based access |
| **Blueprint quality** | v1.29 | Every blueprint is rendered, gated, and snapshot-tested in CI |
| **Operability and audit** | v1.30–v1.32 | Metrics, audit log, notifications, and developer-portal catalog registration |
| **In-cluster operations (Day-2)** | shipped | Chart HPA/PDB/drain; `values-day2.yaml` monitoring overlay; runbooks in [`docs/operations/`](../docs/operations/) |
| **Estate control plane** | v1.72–v1.73+ shipped | Remote observe/plan/remediate; fleet registry; operator continuous fleet sync + GPR prune |
| **Reach and usability** | verify + import shipped | Adopt existing repos into a golden path via PR; composite paths; `repave doctor`; audit queries |
| **Brownfield onboarding** | shipped (Phase 1–3) | `repave import` + batch portal/API; per-file overrides; trees-API preview; GitHub rate-limit backoff for fleet-scale REST |
| **Hardening** | shipped (groups A–B) | Group A: toolchain pins, subprocess timeouts, coverage gate, docs; group B: gate_runners package, API/CLI splits, Python 3.12 floor |
| **Hosted durability** | shipped | Unified SQL store; async queue + DLQ/replay + list runs (v1/v2 API, portal `/runs`); external workers |
| **Service decomposition** | shipped (Phase 0–4) | Split portal/worker/corpus images, Postgres queue, per-run Jobs, v1beta1 operator HTTP; portal/API Deployment split deferred |
| **Supply chain** | shipped | GitHub App auth, governed PR conventions, SHA-pinned Actions, digest-pinned base images, chart `image.digest` |
| **Developer portal surfaces** | shipped | Catalog/library, scorecards (incl. deployment dimension), in-portal docs, observability embed + SLO panel; **platform console** (`/platform/*` — fleet, ops, standards blast radius + confirm drift, campaigns with pause/resume) |
| **Portal live governance** | shipped (tier 2) | Tier 1 + estate map, diff viewer, annotation previews, preflight, bundle topology, presenter |
| **Cost awareness** | shipped | Infracost gate + CI; URL/AWS/Azure actuals; library badges; scorecard dimension |
| **v2 contract freeze** | shipped | `/api/v2`, [`api-v1-migration.md`](api-v1-migration.md), [`repave-config-v1.md`](repave-config-v1.md), provenance on publish, blueprint schema policy, bundle async in worker mode |
| **Postgres DR** | shipped | [`postgres-backup-restore.md`](operations/postgres-backup-restore.md), `make postgres-dr-drill` |
| **v2.0.0 Platform GA** | shipped | Contract freeze + DR on `main`; engine tagged **`v2.0.0`** |
| **v2.1+ environment lifecycle** | Shipped | Deployment status, live plan, environment vending/reclaim, cost badges, and post-merge registry finalize ([ADR 003](adr/003-environment-lifecycle-and-live-state.md)) |
| **Developer paved roads** | Shipped (v1.79–v1.84) | GitOps delivery, SLOs/runbooks, `repave add`, runtimes and layout archetypes, composite bundles ([developer paved roads](#developer-paved-roads-v2x)) |
| **Platform as a product** | Partial (v1.85–v1.88 shipped; v1.89 open) | Treat the IDP as a product: adoption/DX metrics, feedback, stakeholder views, and Guided/Advanced forms shipped; roadmap evidence open ([platform as a product](#platform-as-a-product-v2x)) |
| **FinOps enablement** | Partial (v1.90–v1.91 shipped; v1.92–v1.94 open) | Hybrid FinOps: tags + estimate policy shipped; showback/budgets, thin FOCUS ingest, chargeback export — not a billing warehouse ([FinOps enablement](#finops-enablement-v2x), [`docs/finops.md`](finops.md)) |
| **State custody / resource graph** | Phases 0–3 shipped; Phase 4 **no-go** | Authoritative store + graph + gate-blocked tx ([ADR 004](adr/004-state-custody-and-the-resource-graph.md)); parallel apply gated ([phase4 review](state-graph-phase4-review.md)) |
| **v3.0.0** | — | Autonomous low-risk remediation, mandatory policy, estate lifecycle control, [conversational governed AI](#conversational-and-governed-ai-generation) |

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

- In-repo module standard at `standards/` (v0.4.0; was `examples/standards` pre-v1.30 layout)
- Generated `locals.tf` with `common_tags`, `name_prefix`, normalized services
- Resource scaffolds consume `local.*` for shared context

### v1.10 — Checkov policy pack

- In-repo custom policies at `policy/checkov/policies`
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

### v1.15 — Ansible role golden path

- New `blueprints/ansible-role-generic/` producing a Galaxy-compatible role layout
- Inputs: `role_name`, `namespace`, `description`, `min_ansible_version`,
  `target_platforms`
- Template: `meta/`, `tasks/`, `defaults/`, `handlers/`, `vars/`,
  `molecule/default/`, `README.md`
- Gates: `yamllint`, `ansible-lint`, `ansible-syntax-check`, `molecule`,
  `docs-drift`, `provenance-drift` (skip-if-not-installed where tools absent)
- Output naming: `ansible-role-{role_name}`; provider scope skipped (no catalog)

### v1.16 — Ansible standards + ansible-lint policy pack

- Multi-file standards under `standards/ansible/` (role, collection,
  playbook-project, security appendix) pinned at v1.0.0
- Production-profile ansible-lint pack at `policy/ansible-lint/pack/` copied
  into generated roles at render time; pinned via `spec.ansible_lint`
- Role scaffold upgraded: FQCN, `meta/argument_specs.yml`, single-entry-point
  tasks, Galaxy metadata, production `.ansible-lint` / `.yamllint`
- `secrets` gate extended to `ansible-role` artifact type
- Fixture-tested pack (`examples/ansible-lint/tests/fixtures/`)

### v1.17 — Reconciliation operator (alpha)

Operator SDK reconciler for estate drift and governed upgrades. Slices 0–4 are
on `main` (engine **v1.17.0** / tag path through **v1.18.0**):

| Slice | Outcome | Local verification |
| --- | --- | --- |
| 0 | Scaffold, CRDs, no-op reconciler | `make operator-test` in CI |
| 1 | Inventory / drift in `GoldenPathRepo` status | envtest + `operator/testdata/` |
| 2 | Upgrade diff via `repave` CLI contract | Local git fixtures, no GitHub |
| 3 | Remediation PR | `GitHubClient` mock; dry-run without token |
| 4 | React to Blueprint / pin config changes | envtest (`spec.blueprintRef`) |

Also shipped with this line: Release CI hardening (`upload_to_vcs_release = false`,
`psr()` / unset `GITHUB_OUTPUT`) so automated versioning stays reliable on
protected `main`.

**GA path:** `make operator-e2e` (`operator/hack/e2e.sh`) uses the slim
`operator/Dockerfile` plus an in-cluster portal (`config/e2e/portal.yaml`) calling
`/api/v2` (kind + fixture hostPath) and asserts `OutOfDate`, `UpgradePlanned`, and a
non-empty `status.upgradePlan`. CI: `.github/workflows/operator-e2e.yml`
(nightly, `workflow_dispatch`, and on main when operator/engine/blueprint paths
change). **`spec.localPath` inventory is GA**; `spec.repoURL` git inventory remains
future work. See [`operator-ga.md`](operator-ga.md) for the GA checklist and scope.

Docs: [`operator-local-dev.md`](operator-local-dev.md),
[`operator-standards.md`](operator-standards.md),
[`operator/README.md`](../operator/README.md).

### v1.18.0 — Engine package release

- Conventional-commit release of the monorepo engine package after v1.17 operator
  work and Release workflow fixes
- GitHub Release + wheel artifacts; changelog via python-semantic-release

### v1.19.0 — Operator kind e2e

- `make operator-e2e` kind harness asserting `GoldenPathRepo` `OutOfDate` for a
  stale pin (no `GITHUB_TOKEN`)
- GA close-out: slim operator + portal `/api/v2`; e2e asserts
  `UpgradePlanned` and `status.upgradePlan`; CI via `operator-e2e` workflow
- Roadmap/status docs aligned after the v1.18.0 cut

### v1.19 — Module repository updates (engine + portal)

- `repave update` UX over `plan-upgrade` / `apply-upgrade`
- `--open-pr` for GitHub remediation PRs after apply
- Portal **Update repo** plan preview
- `--preserve-local` for hand-edited scaffold files
- Operator `spec.remediation.preserveLocal` passes `--preserve-local` on apply-upgrade;
  host e2e smoke in `operator/hack/e2e.sh` covers the terraform-minimal fixture

### Estate control — fleet registry and GitOps manifests (engine v1.73+)

- JSONL fleet store, `repave register` / `unregister` / `fleet list`, REST API, portal
  **Fleet** route ([`docs/fleet-registry.md`](fleet-registry.md))
- `repave fleet-manifests` renders `GoldenPathRepo` YAML for GitOps (optional when
  continuous operator sync is enabled — see [`docs/fleet-registry.md`](fleet-registry.md))
- kind co-install: `make kind-co-install`, [`values-kind.yaml`](../deploy/k8s/chart/values-kind.yaml),
  sample [`fleet-registry.jsonl`](../deploy/k8s/testdata/fleet-registry.jsonl),
  `make chart-smoke-fleet-snapshot` for register→sync→unregister→GPR prune and campaign pause in CI

### Kubernetes deploy — Helm chart (engine v1.74+)

- [`deploy/k8s/chart/`](../deploy/k8s/chart/): portal/API on-cluster; `chart-validate`,
  `chart-smoke`, `chart-smoke-decomposed`, and `chart-smoke-multi-replica` required checks
  (path-gated skip on unrelated PRs; full smoke on `main`)
- **Day-2 operability:** [`values-day2.yaml`](../deploy/k8s/chart/values-day2.yaml) (HPA,
  ServiceMonitor, PrometheusRule), runbooks in [`docs/operations/`](../docs/operations/)
- **Multi-replica smoke:** [`values-multi-replica-smoke.yaml`](../deploy/k8s/chart/values-multi-replica-smoke.yaml),
  [`chart-smoke-multi-replica.sh`](../deploy/k8s/hack/chart-smoke-multi-replica.sh)
- **Operator chart:** [`deploy/k8s/operator-chart/`](../deploy/k8s/operator-chart/) —
  GoldenPathRepo/Blueprint reconciliation, conversion webhook TLS + CRD install,
  `values-day2.yaml` (leader election, metrics, ServiceMonitor), `values-kind.yaml` for
  `kind-co-install`; validated in `chart-validate` CI
- **OCI publish:** [`chart-publish.yml`](../.github/workflows/chart-publish.yml) pushes
  `oci://ghcr.io/opsdevcode/charts/repave` and `repave-operator` on semver tags; chart
  `version` and `appVersion` match the engine release. After GHCR image tags exist, the
  workflow dispatches `repave-release` to private `opsdevcode/repave-aws-infra` (secret
  `INFRA_DEPLOY_TOKEN`) for prod pin bump + deploy

### GitHub App authentication (engine v1.105+)

- Engine `github_auth.py` + `resolve_github_access_token()`; operator installation-token cache;
  Helm secret keys — see [`docs/github-app-auth.md`](github-app-auth.md)
- PAT remains supported for local development and break-glass

**Still open:** none — engine REST (`github_rate_limit.py`) and operator HTTP client +
campaign deferral both track `X-RateLimit-*` and backoff on low quota / HTTP 429.

### `repave verify` — local path (engine v1.75+)

- CLI, portal **Verify repo**, `POST /api/v1/verify` ([`docs/verify.md`](verify.md))
- Local paths and shallow git clone for remote URLs (PAT or GitHub App for private HTTPS)

### Repo import to golden path

**Status:** Shipped on `main` (Phase 1–3 — `repave import`, portal `/import` and `/import/batch`,
`/api/v2/imports/*`). Detail: [`docs/import.md`](import.md).

Brownfield onboarding: adopt a repository repave did not generate by rearranging its files
into a golden path layout, adding the governance scaffold it lacks, and opening a pull
request on the source repo.

- **Detection** — `detect_blueprint_candidates()` scores every catalog blueprint against the
  repo's marker files (nesting-tolerant) and pre-selects the best match with the matched
  paths as visible evidence
- **Destination rules** — `spec.import` in `blueprint.yaml` (schema-validated) with
  per-family defaults in `import_rules.py`, so all 14 blueprints import before any are
  annotated
- **Content safety** — files move via `git mv`; every move is SHA-256 verified; the repo's
  own primary content always wins over generated resources; competing destinations fail the
  plan
- **Reviewable PR** — commit 1 is pure moves (`git show --numstat` reports `0 0`), commit 2
  adds scaffold, and the move SHA lands in `.git-blame-ignore-revs`
- **Preview shows the outcome** — before/after scorecard plus real gate results on the
  reorganized tree; failing gates open the PR as a draft
- **Pre-flight guards** — already-governed routes to `/update`; no-op, duplicate open PR, and
  token push-permission checks run before any expensive work
- **Closing the loop** — `import` audit event in `/activity`; remote targets registered in the
  fleet so they land in the library; `spec.import.pre_import_layout_hash` recorded in
  `repave.yaml` as a drift baseline
- **Clone depth** — `git_clone.shallow_clone(depth=0)` now expresses a full clone, and the
  import push path unshallows and retries once when a remote rejects a shallow update
- **Per-file overrides (Phase 2)** — fix a bad classification in the preview; overrides persist
  to `spec.import.overrides` in `repave.yaml` (portal, CLI `--overrides`, API `overrides`)
- **Trees-API preview (Phase 2)** — remote `github.com` URLs plan without cloning; apply
  shallow-clones for scorecard and gates (`preview_limited`; `--force-clone` for full local preview)
- **Batch import (Phase 3)** — plan or open PRs for many repos via `/import/batch`, CLI
  `--batch-file`, or `/api/v2/imports/batch/*`; org/topic discovery on GitHub
- **Rate-limit backoff** — per-installation `X-RateLimit-*` tracking for batch import and fleet
  campaigns (429 retry with backoff)

### `repave add` — multi-component brownfield (engine v1.82+)

**Status:** Shipped on `main` ([#453](https://github.com/opsdevcode/repave/pull/453)).
Detail: [`docs/add.md`](add.md).

Layer a second (or third) golden-path artifact onto a repository that already carries
`repave.yaml` — the brownfield counterpart to generate-time bundles.

- **Governed repos only** — missing `repave.yaml` routes to [`repave import`](#repo-import-to-golden-path)
- **Multi-component provenance** — primary blueprint stays top-level in `repave.yaml`; added
  artifacts append to `spec.components[]` with their own pins and CI gates
- **Plan/apply** — conflict detection for paths the new blueprint would write; `--force` for
  scaffold overwrites; shared governance files (`README.md`, `RUNBOOK.md`, gate workflow) are
  skipped when already present
- **Input inference** — helm/gitops components derive names from an app-service primary when
  inputs are omitted
- **Verify** — JSON report includes a `components[]` array with per-component gate and pin
  results (primary remains in the top-level gate list)
- **Surfaces** — `repave add`, `POST /api/v2/components/plan|apply`, portal **Add component**
  on `/services/{entity_id}` (local checkout under `REPAVE_MODULES_ROOT`)

**Still open:** remote `--open-pr` publish; per-component `plan-upgrade` / `update`; fleet library
multi-blueprint pin display.

### v1.18 — Portal UX (theme)

Night-ops web portal across home, blueprint form, and generation result (engine
tags **v1.21.0–v1.25.0**). Detail: [`portal-design.md`](portal-design.md).

- **Foundation:** `base.html`, `/static/repave.css`, design tokens, app shell
- **Catalog:** artifact-type groups, blueprint cards (version, gates, standard pins)
- **Form:** governance card (standard + Checkov/ansible-lint pins); Terraform split
  layout with scope filter, presets, inline validation; Ansible multi-select
  platforms (including Windows) and min Ansible version enum
- **Results:** status hero, gate table with expandable failure output, repo card,
  file tree + preview, collapsible publish plan
- **Polish:** visual v2 home hero; browser **last-run** snippet (`repave.js` +
  sessionStorage); fleet-wide history deferred to v1.30 audit
- **Follow-on (v1.25–v1.62):** platform engineering copy (Scaffold repository, Plan vs
  Apply); multi-step forms with sticky **Dry run preview** from any step; generation
  results dashboard; update-repo and standards pin diff; portal UI contract tests in
  `engine/tests/test_api.py` (see `.cursor/rules/portal-ui-behavior.mdc`)

**Done when:** Non-expert users complete common Terraform/Ansible paths without CLI
fallback; three routes share one visual system (acceptance in portal-design).

---

## Planned

### v1.19 — Update existing module repositories

**Status:** Shipped on `main` (engine `repave update`, portal update flow,
`--open-pr`, `--preserve-local`). Operator continues to use stable
`plan-upgrade` / `apply-upgrade` JSON.

**Follow-up (shipped):** Operator remediation uses `--preserve-local` via
`spec.remediation.preserveLocal` (engine `repave apply-upgrade --preserve-local`).
Host e2e smoke exercises the flag on the `terraform-minimal` fixture.

### v1.22.0 — Ansible collection golden path

- `blueprints/ansible-collection-generic/` v0.1.0 → `ansible-collection-{namespace}-{name}`
- Pin `standards/ansible/collection-standard.md` v1.0.0
- Scaffold: `galaxy.yml`, `meta/runtime.yml`, `roles/sample/`, changelog, ansible-lint pack
- Gates: `yamllint`, `ansible-lint`, `secrets`, `docs-drift`, `provenance-drift`
- `GoldenPathArtifact.spec.ansibleCollection` provenance; portal Ansible family ordering

### Policy golden paths (OPA and Azure Policy) — shipped early (roadmap v1.39)

- Policy family under `standards/policy/` with governance baseline for every artifact
- `checkov-policy`, `opa-policy`, and `azure-policy` artifacts with matching `-generic` blueprints
- `opa` gate (Conftest / Rego); `azure-policy` gate for definition JSON; Checkov pack gate
- Terraform blueprints vend `policy/opa/policies` for plan-time Rego
- Portal customization via `policy/catalog.json`; demo [policy-golden-paths-demo.md](policy-golden-paths-demo.md)
- Conformance snapshots for policy blueprints; Docker Compose ships **conftest** for OPA demos
- Operator estate notes: [operator-policy-estate.md](operator-policy-estate.md)
- `policy/PACKS.md` catalog narrative; portal dry-run **`require_run`** (gates fail when CLIs missing); CI/local gate toolchain via `deploy/local/install-gate-toolchain.sh`
- Observability blueprint: `repave-observability-pack`, profile `observability-default`, selective OPA vendoring (catalog v1.3.0)

### v1.21.0 — Estate Terraform standards pack (multi-file)

- Vendored `terraform-standards.md` and `terraform-module-layout.md` under
  `standards/terraform-standards/` (v1.1.0)
- `terraform-module-generic` v0.9.0 and `terraform-module-resource` v0.2.0 pin
  `spec.standard.source: standards/terraform-standards`
- Scaffold: optional `name_prefix` with `coalesce` fallback; README cites the pack
- Superseded monolithic `standards/terraform-module-standard.md` (legacy body retained)

### v1.20.0 — Additional golden paths

- `terraform-module-resource`, `terraform-environment-stack`, and
  `ansible-playbook-project` blueprints with gates, standards pins, and repo naming
- Portal catalog groups Terraform and Ansible families (v1.18 follow-on)

**Done when:** At least one new blueprint ships with gates, standards pin, and docs.

---

### v1.20 — Additional golden paths

**Status:** Shipped on `main` (see [v1.20.0 — Additional golden paths](#v1200--additional-golden-paths)).

---

### v1.22 — Ansible collection golden path

**Status:** Shipped on `main` (see [v1.22.0 — Ansible collection golden path](#v1220--ansible-collection-golden-path)).

---

### v1.67 — Ansible role patterns (Linux + Windows)

**Problem:** `ansible-role-generic` shipped layout, lint pack, and Molecule wiring but
**placeholder tasks** (`debug` only)—no runnable automation for Linux or Windows estates.

**Approach:**

- **`ansible/catalog.json`** with **`role_patterns`** (like observability monitor packs)
- Engine **`ansible_pattern.py`**: materialize Jinja fragments, platform-aware default
  (`linux-service` / `windows-service`), `requirements.yml` for collections
- Patterns: **`linux-service`**, **`windows-service`**, opt-in **`repave-baseline`**
- Windows: static CI (**ansible-lint** + **syntax-check** with `ansible.windows`);
  optional **`molecule/windows/`** delegated scenario (not run by default gate)
- Portal pattern picker filtered by Linux/Windows toggles; provenance
  `role_pattern_source` + `required_collections`
- Gate toolchain installs **`ansible/requirements-gate-collections.yml`**

**Done when:** Default generate produces idempotent Linux or Windows tasks; Molecule
verify asserts package/service state on Linux; Windows-only roles skip Docker Molecule
without failing CI.

**Status:** Shipped on `main` (catalog, patterns, portal, standards v1.1.0, gate collections).

**Follow-ups:** Collection sample role wired from the same catalog; richer playbook patterns
(pinned Galaxy rollout shipped in v1.70).

---

### v1.70 — Pinned Galaxy roles playbook pattern

**Problem:** Playbook projects could pin roles in `requirements.yml` but **`site.yml`** only
exercised pins via the Copier placeholder loop (ping tasks), not a serial production rollout play.

**Approach:**

- **`pinned-roles-rollout`** in **`ansible/catalog.json`** with ping + `roles:` play
- Validate at least one **`pinned_roles`** entry when the pattern is selected
- **`group_vars/all/vars.yml`** exposes `playbook_rollout_serial` tuning

**Status:** Shipped on `main` (`pinned-roles-rollout` in `ansible/catalog.json`
`playbook_patterns`).

---

### v1.69 — Cross-platform Ansible role pattern

**Problem:** Mixed Linux + Windows roles defaulted to **linux-service**, which ignores
Windows automation unless operators hand-author tasks.

**Approach:**

- **`managed-local-account`** pattern with **`platform: cross`** in `ansible/catalog.json`
- Portal/API expose the pattern only when **both** Linux and Windows are selected
- Linux `user` + Windows `win_user` tasks with shared defaults; Molecule verify on Linux

**Status:** Shipped on `main` (`managed-local-account` in `ansible/catalog.json`
`role_patterns`).

---

### v1.68 — Ansible playbook patterns

**Problem:** `ansible-playbook-project` scaffolded inventory and a ping-only `site.yml` without
operational play content for Linux or Windows fleets.

**Approach:**

- Extend **`ansible/catalog.json`** with **`playbook_patterns`**
- Materialize **`site.yml`** and environment **`hosts.yml`** from `ansible/playbooks/`
- Patterns: **`linux-patch-baseline`**, **`windows-update-baseline`**, opt-in **`repave-baseline`**
- Portal pattern picker + Linux/Windows toggles; provenance `playbook_pattern_source`
- Merge pattern **`required_collections`** into Copier-generated **`requirements.yml`**

**Status:** Shipped on `main` (catalog, engine, portal, standards v1.1.0).

---

### v1.23 — Generation provenance and version visibility

**Problem:** Operators need generated modules and the portal to show which blueprint,
standard, and policy pack versions apply. Provenance in `repave.yaml` shipped in
v1.14; the portal **governance card** surfaces pins before generate (v1.18).

**Approach:**

- Embed provenance in generated README and/or `repave.yaml` metadata file:
  `blueprint`, `blueprint_version`, `standard_source`, `standard_version`,
  `checkov_policy_version`, generation timestamp
- Portal form shows pinned standard and Checkov policy versions for the selected
  blueprint (governance card layout in [`portal-design.md`](portal-design.md))
- Optional: label/tag GitHub repos on publish with blueprint version

**Dependencies:** Blueprint already carries standard and checkov pins (v1.9–v1.10);
artifact-type-aware provenance (v1.14).

**Done when:** A module repo clearly states its golden-path lineage without reading
repave source.

**Status:** Shipped on `main` (README `## Provenance` sync on generate, `docs-drift`
requires Provenance + `repave.yaml`, portal governance **Lineage** row with engine version).

---

### v1.24 — Generated module CI template

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

**Status:** Shipped on `main` (`.github/workflows/terraform-gates.yml` / `repave-gates.yml`
from blueprint gates, `spec.ci` in `repave.yaml`, `repave gates` CLI, toolchain pins
aligned with `deploy/local/Dockerfile`).

---

### Operator beta and fleet inventory (superseded)

*Planning label: v1.25 (roadmap numbering only).*

**Problem:** v1.17 operator scope is large; teams need a minimal inventory model
before full reconciliation.

**Approach:**

- Define `GoldenPathRepo` CRD (repo URL, pinned blueprint, standard, policy versions)
- Operator **inventory mode**: list/watch registered repos, report drift vs pins
  (read-only, no PRs yet)
- CLI/API `repave register` to add a generated repo to the inventory
- Design doc for upgrade PR flow (feeds v1.17 GA and v1.19 update command)
- Reuse **v1.17 slice 1** fixtures and `make operator-test` / envtest harness
  ([`operator-local-dev.md`](operator-local-dev.md))

**Dependencies:** v1.17 CRD design and local test scaffold; v1.23 provenance fields.

**Done when:** Operator reports “out of date” repos when blueprint standard/policy
version bumps on `main`.

**Status:** Not started. `spec.localPath` inventory is GA (v1.17), but there is no
registry of managed repos and no `repave register`. Split into [operator remote git inventory](#operator-remote-git-inventory) and
[fleet registry and `repave register`](#fleet-registry-and-repave-register).

---

### Kubernetes deploy path (superseded)

*Planning label: v1.26 (roadmap numbering only).*

**Problem:** Local Docker Compose is the only first-class deploy story; platform
teams want repave API/portal on-cluster alongside the future operator.

**Approach:**

- Helm chart or Kustomize under `deploy/k8s/` for engine API + portal
- Config via `repave.config.yaml` mounted ConfigMap + secrets for `GITHUB_TOKEN`
- Document co-install with operator (same namespace, shared config)
- kind-based smoke test in CI (optional, non-blocking initially); reuse operator
  e2e harness from [`operator-local-dev.md`](operator-local-dev.md)

**Dependencies:** Stable API surface; output config via env/ConfigMap (exists).

**Done when:** `helm install` (or documented kustomize apply) serves the blueprint
form on-cluster with dry-run generation working.

**Status:** **Superseded** — implemented as
[Kubernetes deploy path (Helm chart)](#kubernetes-deploy-path-helm-chart) with day-2
operability on `main`. Historical note: `deploy/k8s/` held observability starters before the
chart landed.

---

### v1.27 — Service mode and authentication (login)

**Problem:** The API and portal are unauthenticated and assume trusted local use.
Running repave as a shared hosted service needs identity and protected endpoints.

**Approach:**

- **Service mode** config flag: local dev stays open (no auth); hosted mode
  requires authenticated sessions
- Session/JWT-backed login; protect all mutating API routes (generate, publish,
  register) and the portal
- Identify the acting user and record it in generation provenance/audit
- Config via `repave.config.yaml` + secrets (ties to v1.26 ConfigMap/secret wiring)

**Scope:** single-tenant (one org per instance); no per-tenant isolation.

**Dependencies:** v1.26 Kubernetes deploy path (hosted service); stable API surface.

**Done when:** A hosted repave instance rejects unauthenticated API/portal access,
and a logged-in user can complete a generation.

**Status:** Foundation shipped on `main` (OIDC authorization-code flow, session
roles, protected generate/update/API; [`docs/auth-service-mode.md`](auth-service-mode.md)).

---

### v1.28 — SSO via OIDC and role-based access

**Problem:** Enterprises require IdP-managed login (Okta, PingID, Entra, Auth0),
not local accounts.

**Approach:**

- Generic OIDC/OAuth2 authorization-code login (provider-agnostic: issuer URL,
  client id/secret, scopes) so Okta/PingID/Entra/Auth0 all work
- Map IdP group/role claims to repave roles: `viewer` (read/dry-run), `generator`
  (generate/publish), `admin` (register/inventory/config)
- Enforce roles on API endpoints; record the authenticated identity in the
  generation provenance/audit trail

**Dependencies:** v1.27 authentication foundation.

**Done when:** Login is delegated to an OIDC IdP and endpoint access is gated by
mapped role claims; docs show an Okta and a PingID configuration example.

**Status:** Shipped with v1.27 foundation (group → role mapping, generator/admin
gates on mutating routes).

---

### Forked and remote blueprint packs

*Planning label: v1.29 (roadmap numbering only).*

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

**Status:** Not started. Blueprint discovery is still hardcoded to `repo_root / "blueprints"`
in `cli.py` and `api.py`; `settings.py` has no `blueprints_root` / `blueprint_sources` key.

---

### v1.30 — Blueprint conformance CI harness

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

**Status:** Shipped on `main` (`blueprint_conformance.py`, per-blueprint
`conformance.yaml`, pytest matrix, `make blueprint-conformance-update` for optional
manifest snapshots).

---

### v1.30 — Audit log, metrics, and traces

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

**Status:** Shipped on `main` (`audit.py` JSONL sink, `/metrics` Prometheus
endpoint, pipeline spans and `repave_generation_*` counters; configure via
`repave.config.yaml` `audit` and `REPAVE_ACTING_USER`). **Traces:** install the
[`otel` extra](../engine/pyproject.toml) and configure OTLP per [`docs/tracing.md`](tracing.md).

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

**Status:** Shipped on `main` (`repave.config.yaml` `notifications`, Slack/Teams/
generic webhooks, publish and generation events; best-effort delivery from the
generation pipeline). Operator drift/remediation uses the same webhook URLs via
`REPAVE_OPERATOR_NOTIFY_*` environment variables.

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

**Status:** Shipped on `main` (`backstage_catalog.py`, optional catalog on Terraform/Helm,
required on app-service, `standards/backstage/catalog-standard.md`, [`docs/backstage.md`](backstage.md)
with Scaffolder template sketch, parameter mapping, and `POST /api/v1/generate`).

---

### v1.31 — Helm chart golden path (**accelerated**; was v1.33)

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

**Status:** Shipped on `main` (`helm-chart-generic`, `helm-lint` / `helm-template`
gates, `standards/helm/chart-standard.md`).

---

### v1.32 — Application service scaffold golden path (**accelerated**; was v1.34)

**Problem:** New services are bootstrapped inconsistently; teams want a governed
application repository from the same golden-path engine.

**Approach:**

- New `blueprints/app-service-generic/` producing a service repo: `Dockerfile`, CI
  workflow, lint/test config, `README.md`, an optional Helm chart reference (v1.31),
  and `catalog-info.yaml` (v1.32)
- Inputs: `service_name`, `runtime` (enum), `owner`, `port`
- Gates: `docs-drift`, `provenance-drift`, `dockerfile-lint` (hadolint), language
  lint/test (skip-if-not-installed); the generated CI runs the same gates on push
  (reusing the v1.24 module-CI-template pattern)
- Ship one runtime first (e.g. Python or Go); add others as follow-ons

**Dependencies:** v1.13 gate registry; v1.14 provenance; v1.24 CI template pattern;
v1.30 conformance harness.

**Done when:** A service repo generates for at least one runtime with CI wired and
gates green.

**Status:** Shipped on `main` (`app-service-generic` v0.3.0, Python and Go runtimes,
`dockerfile-lint` / language lint-test gates, portal Backstage catalog fields,
engine-written `catalog-info.yaml`).

---

### Day-2 operability (shipped)

Engine and chart work for v1.35–v1.38:

- **Service health** — [`readiness.py`](../engine/src/repave_engine/readiness.py),
  `/readyz` 503 with `checks`, queue drain via `REPAVE_SHUTDOWN_DRAIN_SECONDS`
- **Alerts** — chart `PrometheusRule` template + [`deploy/k8s/prometheus-rules.yaml`](../deploy/k8s/prometheus-rules.yaml)
  (generation, async runs, queue backlog, dead letter, JSONL export)
- **Monitoring overlay** — [`values-day2.yaml`](../deploy/k8s/chart/values-day2.yaml) (HPA,
  ServiceMonitor, PrometheusRule, session secret + GitHub readiness)
- **Upgrade/rollback** — [`docs/operations/upgrade-and-rollback.md`](operations/upgrade-and-rollback.md)
- **Runbooks** — [`docs/operations/README.md`](operations/README.md)

---

### Service health, resource management, and autoscaling

*Planning label: v1.35 (roadmap numbering only).*

**Problem:** The deploy path installs the API and portal but defines no health
probes, resource guarantees, disruption budget, or autoscaling, so an ops team
cannot run it reliably or plan capacity.

**Approach:**

- Liveness/readiness/startup probes: the API already serves `/health` (liveness) and
  `/readyz`; wire both into the Helm chart and extend `/readyz` to check config/token
  presence and downstream reachability
- Resource requests/limits with documented sizing guidance
- HorizontalPodAutoscaler on CPU/concurrency with a documented generation-concurrency
  knob
- PodDisruptionBudget and graceful shutdown (drain in-flight generations on SIGTERM,
  bounded `terminationGracePeriodSeconds`)
- Expose all of the above as configurable values in the Helm chart / Kustomize

**Dependencies:** [Kubernetes deploy path (Helm chart)](#kubernetes-deploy-path-helm-chart).

**Done when:** Draining a node or scaling replicas drops no in-flight requests; the
HPA scales under load; probes gate traffic correctly.

**Status:** **Shipped on `main`** — see [Day-2 operability (shipped)](#day-2-operability-shipped).

---

### Alerting rules, SLOs, and dashboards

*Planning label: v1.36 (roadmap numbering only).*

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

**Status:** **Shipped on `main`** — starter pack plus queue/dead-letter alerts; see
[Day-2 operability (shipped)](#day-2-operability-shipped).

---

### Zero-downtime upgrade and rollback

*Planning label: v1.37 (roadmap numbering only).*

**Problem:** There is no documented, safe upgrade/rollback path for the in-cluster
service; upgrades risk dropping requests or breaking on config/schema changes.

**Approach:**

- Versioned Helm releases with a rolling-update strategy (`maxUnavailable`/`maxSurge`)
  leveraging the service-health probes and PodDisruptionBudget
- Backward-compatibility policy for API/schema/config within a minor, with migration
  notes for breaking config changes
- Forward-compatible handling and documented migration steps for the v1.30 audit
  sink/inventory when it is backed by a database
- `helm rollback` runbook with image digest pinning and a pre-upgrade smoke check
  (reuse the kind smoke test)
- Optional canary via two releases / weighted routing (documented, not required)

**Dependencies:** Helm packaging; service-health probes/PDB; v1.30 audit sink schema.

**Done when:** An upgrade and a rollback complete with no dropped requests in a test
cluster, following the documented steps.

**Status:** **Shipped on `main`** — [`docs/operations/upgrade-and-rollback.md`](operations/upgrade-and-rollback.md).

---

### Operations runbooks and troubleshooting

*Planning label: v1.38 (roadmap numbering only).*

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

**Status:** **Shipped on `main`** — [`docs/operations/README.md`](operations/README.md).

---

### v1.39 — Policy-as-code gate (OPA/conftest)

**Status:** Shipped on `main` (see [Policy-as-code golden paths](#policy-golden-paths-opa-and-azure-policy--shipped-early-roadmap-v139)).
Helm charts run conftest against `helm template` output via the `opa` gate (`kubernetes_workload.rego` baseline).

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
- Ship an observability standard under `standards/` (naming, required
  tags/annotations, SLO structure, runbook links) pinned by the blueprint

**Dependencies:** v1.13 gate registry; v1.14 artifact-type provenance; v1.39 OPA
(opt-in policy); existing Terraform engine (terraform mode); v1.29 conformance
harness for CI coverage.

**Done when:** The blueprint generates governed dashboards/alerts/monitors for at
least one backend in both native and terraform modes, passing validation gates
where tools are present and skipping cleanly otherwise.

**Status:** Shipped on `main` (v1.40 complete): native and Terraform modes for Datadog,
Grafana, Prometheus, and OTel observability; dashboards native + Terraform with community
packs; `amtool`, `datadog-api-validate`, and native/Terraform `opa` gates.

---

### Operator remote git inventory

*Planning label: v1.72 (roadmap numbering only).*

**Problem:** The operator can only observe repos that already exist on local disk.
`ObservePins` (`operator/internal/inventory/observe.go`) returns
`ErrRemoteRepoNotSupported` for `spec.repoURL`, so "fleet drift detection" in practice
means "drift detection on whatever was mounted into the pod". This is the last GA gap
called out in [`operator-ga.md`](operator-ga.md).

**Approach:**

- Shallow clone/fetch `spec.repoURL` at `spec.ref` into a work dir, then reuse the existing
  `localPath` observation path unchanged so drift logic stays single-sourced
- Credentials via secret ref (`spec.secretRef`) for HTTPS token and SSH key; reuse the token
  plumbing already in `operator/internal/git/push.go`
- Cache clones with a resync interval and back-off; surface fetch failures as a distinct
  status condition rather than silent `Unknown`
- Extend `plan-upgrade` / `apply-upgrade` remediation to the cloned work dir (the JSON
  contract to the engine is unchanged)
- envtest coverage with a local bare-repo fixture; extend `operator/hack/e2e.sh` with a
  `repoURL` case alongside the existing `terraform-minimal` local fixture

**Dependencies:** v1.17 operator slices 1–3; existing `GitHubClient` mock harness.

**Done when:** A `GoldenPathRepo` with only `spec.repoURL` reports `OutOfDate` and a
non-empty `status.upgradePlan` against a stale pin, with no local checkout.

**Status:** **Phases A–B shipped** — `internal/git/clone.go` shallow-clones remotes into an
`inventory.Workspace` that is materialized once per reconcile and reused for both
observation and `repave plan-upgrade`, so `spec.repoURL` populates `status.observedPins`
**and** `status.upgradePlan`. Token material is redacted from git errors; clone failures set
`RemoteFetchFailed` and requeue; remote repos re-reconcile on
`REPAVE_OPERATOR_REMOTE_RESYNC` (default 10m). **Phase C shipped** — remediation runs against
the materialized clone when `spec.localPath` is empty; push/PR reuse `spec.repoURL` and
`GITHUB_TOKEN`. Design:
[ADR 001](adr/001-goldenpathrepo-repo-url-inventory.md).

---

### Fleet registry and `repave register`

*Planning label: v1.73 (roadmap numbering only).*

**Problem:** There is no list of repos repave manages. Every `GoldenPathRepo` is
hand-authored, the engine CLI has no `register`, and `repave list` lists blueprints rather
than repos — so nobody can answer "how much of the estate is on the current standard?"

**Approach:**

- Registry store keyed by repo URL: blueprint + version, standard/policy pins, owner,
  last observed drift, last remediation PR — JSONL behind an interface, same pattern as the
  v1.30 audit sink, with the database backend deferred to
  [durability and concurrency](#durability-and-concurrency-for-hosted-use) rather than
  chosen here
- `repave register <repo-url>` / `repave unregister`, plus `repave fleet list` reading pins
  from each repo's `repave.yaml` provenance (v1.14)
- API: `GET /api/v1/fleet`, `POST /api/v1/fleet` (admin role from v1.28)
- Portal **Fleet** route: table of managed repos with pin versions, drift state, and a link
  to the open remediation PR; reuses the `/activity` presentation pattern
- Optional operator sync: emit a `GoldenPathRepo` per registry entry so the CR set stops
  being hand-maintained

**Dependencies:** v1.14 provenance; v1.28 roles; v1.72 remote inventory for live drift state.

**Done when:** A registered repo appears in the portal fleet view with its pins and drift
state, and the operator picks it up without hand-written CRs.

**Status:** **Shipped on `main`** (store, CLI, API, portal **Fleet**, `fleet-manifests`,
kind co-install). **Polish shipped:** portal operator status via snapshot file, GitOps bundle
flags (`--kustomization`, `--prune`, `--gitops-readme`, `--enable-remediation`),
`repave fleet-operator-snapshot` (v2 snapshot includes UpgradeCampaign rows), and admin
**platform console** at `/platform/fleet`, `/platform/ops`, `/platform/standards`,
`/platform/campaigns` (in-portal **pause/resume** for `UpgradeCampaign`; **Confirm drift** on
the standards index → `fleet_drift_confirm` async run). **Day-2:** Helm
`fleetOperatorSnapshot.cronJob` on the shared fleet PVC
(`values-fleet-shared.yaml`) refreshes the snapshot for the platform console without manual CLI;
fleet snapshot RBAC grants portal **`patch`** on `upgradecampaigns` for campaign actions.
**Shipped:** operator continuous registry sync (`REPAVE_FLEET_SYNC_*`, Helm `fleetSync.*`)
with GPR prune on unregister — validated by `make chart-smoke-fleet-snapshot` (includes
platform campaign pause/resume via `/platform/campaigns`).

---

### Kubernetes deploy path (Helm chart)

*Planning label: v1.74 (roadmap numbering only).*

**Problem (resolved):** Docker Compose was the only first-class deploy story; day-2
operability (v1.35–v1.38) needed a chart to attach probes, HPA, and monitoring CRs to.
Realizes [v1.26](#kubernetes-deploy-path-superseded).

**Approach:**

- Chart under `deploy/k8s/chart/`: Deployment, Service, Ingress, ServiceAccount,
  ConfigMap from `repave.config.yaml`, Secret refs for `GITHUB_TOKEN` and OIDC client secret
- Probes wired to the existing `/health` and `/readyz` endpoints
- Values for image digest pinning, replica count, resources, gate-toolchain image variant,
  and audit sink volume
- Document co-install with the operator (shared namespace and config)
- kind smoke test reusing `operator/hack/e2e.sh` infrastructure; non-blocking in CI initially

**Dependencies:** Stable API surface; v1.27 auth config; audit sink path config (v1.30).

**Relationship to durability:** the chart can ship first and serve single-replica traffic, but
scaling replicas is only meaningful once
[durability and concurrency](#durability-and-concurrency-for-hosted-use) has moved run state and
sessions out of process. Add the worker/Job template and database values here; the execution
model itself belongs to that entry.

**Done when:** `helm install` serves the blueprint form on-cluster with dry-run generation
working and probes gating traffic.

**Status:** **Shipped on `main`** — see [Shipped — Helm chart](#kubernetes-deploy--helm-chart-engine-v174)
and [operator chart](../deploy/k8s/operator-chart/README.md).

---

### `repave verify` for existing repositories

*Planning label: v1.75 (roadmap numbering only).*

**Problem:** Governance only applies to repos repave generated. A platform team adopting
repave cannot measure the repos they already have, which makes the first conversation about
migration rather than value.

**Approach:**

- `repave verify <path|repo-url> --blueprint <name>` (or inferred from `repave.yaml` when
  present) runs the blueprint's declared gates against an existing tree via the v1.13 gate
  registry — no rendering, no publish
- Conformance report: which gates passed, which standard clauses are unmet, and the diff
  between the repo's current pins and the blueprint's
- `--report json` for CI use, plus a portal **Verify** route accepting a repo URL
- Skip-if-not-installed semantics match generation gates; `require_run` honored
- Feeds the v1.73 registry so an unmanaged repo can be scored before it is registered

**Dependencies:** v1.13 gate registry; v1.14 provenance; v1.73 registry for scoring.

**Done when:** Pointing `repave verify` at a repo repave never generated produces a gate
report and a pin-drift summary without modifying the repo.

**Status:** **Shipped on `main`** — local paths and remote URL shallow clone; see
[Shipped — verify](#repave-verify--local-path-engine-v175).

---

### Composite golden paths (bundles)

*Planning label: v1.76 (roadmap numbering only).*

**Status:** **Shipped on `main`** — `schemas/bundle.schema.json`, `blueprints/bundles/service-stack/`
v0.2.0 (app + Helm + dashboards + Terraform module), `blueprints/bundles/microservice-full/`
(six-member full stack), `repave generate --bundle`, portal **Composite bundles** catalog with
preset chips and `/bundles/{name}` form with combined plan result.

**Problem:** Every blueprint emits exactly one artifact, but a real service needs a
Terraform module, a Helm chart, an app-service repo, and observability. All four paths exist
and there is no way to emit them together with shared naming, tags, owner, and
cross-references — so users re-enter the same inputs four times and wire them by hand.

**Approach:**

- Bundle manifest (`blueprints/bundles/*.yaml`) listing member blueprints, a shared input
  set, and per-member input mapping
- Engine composes existing blueprint renders; shared `service_name`, `owner`, tags, and
  naming flow to every member; members cross-reference (chart references the image from the
  app service; observability targets the service name)
- One dry-run preview and one gate summary across all members; publish creates each repo and
  records a single bundle provenance entry
- Portal presents a bundle as one multi-step form with a combined preview
- Ship one bundle first (app service + chart + observability), Terraform module as a follow-on

**Dependencies:** v1.30 conformance harness; v1.31 Helm path; v1.32 app-service path;
v1.40 observability path; v1.14 provenance.

**Done when:** One form submission produces a consistent, gate-green set of repos whose
cross-references resolve without hand editing.

---

### `repave doctor` toolchain preflight

*Planning label: v1.77 (roadmap numbering only).*

**Problem:** Gate-toolchain drift between the Compose image, CI, and local machines keeps
producing "gate skipped" and missing-CLI surprises; the portal banner and
`deploy/local/install-gate-toolchain.sh` treat the symptom, not the diagnosis.

**Approach:**

- `repave doctor` reports each registered gate, whether its CLI is present, the detected
  version, whether that version matches the pin in `deploy/local/Dockerfile`, and the install
  hint when missing
- `--blueprint <name>` narrows to the gates one path actually needs
- Non-zero exit under `--strict` so CI and the container build can assert a complete toolchain
- Shares the detection table with the portal missing-toolchain banner so both agree

**Dependencies:** v1.13 gate registry; existing toolchain installer.

**Done when:** `repave doctor --strict` passes in the Compose image and CI, and fails locally
with actionable output when a gate CLI is absent or mismatched.

**Status:** **Shipped on `main`** — `repave doctor` CLI (`--blueprint`, `--strict`, `--all-pins`),
pin checks via `deploy/local/gate-toolchain-pins.env`, **`make gate-doctor`**, CI gate-toolchain
action, and Compose **`docker build`** verification.

---

### Queryable audit history

*Planning label: v1.78 (roadmap numbering only).*

**Problem:** `audit.py` appends JSONL and `/activity` renders recent entries, but there is no
filtering by repo, blueprint, user, or gate outcome and no API — so the audit trail cannot
answer a compliance question without grepping a file.

**Approach:**

- `GET /api/v1/audit` with filters (blueprint, repo, acting user, outcome, time range) and
  pagination; admin/viewer roles from v1.28
- Portal activity view gains the same filters and a per-generation detail panel showing pins,
  gate results, and the resulting PR link
- Filters run against the indexed store from
  [durability and concurrency](#durability-and-concurrency-for-hosted-use), with JSONL
  retained as the append-only source of truth — this entry consumes that store, it does not
  pick its own
- `repave audit query` CLI over the same filters for offline use

**Dependencies:** v1.30 audit sink; v1.28 roles;
[durability and concurrency](#durability-and-concurrency-for-hosted-use) for the indexed
store (a JSONL-scan implementation is acceptable as a first cut, but the API contract should
not assume it).

**Done when:** An operator can answer "every generation of blueprint X by user Y that failed a
gate last month" from the portal or one CLI call.

**Status:** **Shipped on `main`** — `GET /api/v1/audit`, `/activity` filter form,
`repave audit query`, SQL + JSONL backends via `query_audit_entries`.

---

## Engine hardening and tech debt

Debt inventoried against `main` at engine v1.74.0. Each row names the file that carries the
debt so the entry can be re-checked instead of re-argued. Group A is correctness and safety
and should land before the hosted-service themes below; group B is maintainability that can
land opportunistically alongside feature work in the same files.

### A1 — One source of truth for gate toolchain pins

**Problem:** Gate CLI versions must not drift between the local installer, generated-repo CI
workflows, and `repave doctor`. Floating Checkov pins make gate results non-reproducible.

**Approach:**

- Single pin file (`deploy/local/gate-toolchain-pins.env`) consumed by `ci_toolchain.py`, the
  installer script, Docker image, and doctor
- Exact Checkov pin (`checkov==…`) shared with generated CI workflows
- Regression tests assert installer URLs, `ci_toolchain`, doctor, and rendered workflows agree

**Done when:** One edit changes a gate CLI version everywhere, and a deliberately mismatched
pin fails a test.

**Status:** **Shipped on `main` follow-up** — `gate-toolchain-pins.env`, `ci_toolchain.load_pin_file`,
`test_toolchain_pins.py`, installer URL assertions, explicit `CHECKOV_PIP_SPEC`.

### A2 — Subprocess timeouts on every gate and git invocation

**Problem:** `run_command` in `gate_runners.py` calls `subprocess.run` with no `timeout`, and so
do the git/CLI helpers in `module_inventory.py`, `target_repo.py`, `standards_diff.py`,
`upgrade_plan.py`, and `gate_toolchain.py`. A hung `terraform init`, a credential prompt, or a
slow registry wedges the request — and once generation runs on a shared service, one hung run
holds a worker indefinitely. Bandit's `B603`/`B404` skips in `pyproject.toml` mean nothing flags
this today.

**Approach:**

- Default per-gate timeout with a per-gate override, killing the process group on expiry and
  reporting a distinct `timeout` gate outcome rather than a generic failure
- Same treatment for git and `repave` CLI subprocesses used by inventory and upgrade planning
- Narrow the Bandit skips to the call sites that need them

**Done when:** A gate that sleeps past its budget is reported as timed out and the request
returns, with no orphaned child process.

**Status:** **Shipped on `main` follow-up** — `subprocess_run.run_subprocess` with env-configured
timeouts (`REPAVE_SUBPROCESS_TIMEOUT_SECONDS`, `REPAVE_GIT_TIMEOUT_SECONDS`), process-group kill
on expiry, git/inventory/upgrade paths migrated, `gate_outcome` returns `timeout`, per-gate
`timeout_seconds` blueprint override supported via `gate_timeout_seconds`.

### A3 — Coverage and required checks in CI

**Problem:** `make test` enforces `--cov-fail-under=75`, but `.github/workflows/ci.yml` runs
`uv run pytest` with no coverage flags, so the threshold is advisory on PRs. `operator-e2e` is
not in the required-check list in `.github/rulesets/main-branch.json`, and the ruleset-sync step
in `release.yml` is `continue-on-error: true`, so branch-protection drift is silent.

**Approach:**

- Run the same coverage invocation in CI as in `make test`; add `[tool.coverage]` config so the
  policy lives in `pyproject.toml` rather than the Makefile
- Require `operator-e2e` on operator/engine/blueprint paths, or alert on nightly failure
  instead of leaving it advisory
- Fail closed on ruleset sync, or move it to a workflow whose failure is visible

**Done when:** A PR that drops coverage below the threshold fails, and a red `operator-e2e`
blocks or pages.

**Status:** **Shipped on `main`** — CI and Release pytest use `[tool.coverage.report] fail_under`;
`operator-e2e` is a required check (path-gated skip on PRs; full run on `main` push and nightly);
Release ruleset sync fails closed.

### A4 — Concurrent-safe audit and fleet stores

**Problem:** `audit.py` appends JSONL best-effort with no lock and never raises; `fleet.py`
folds a JSONL file with an 8 MB soft cap. Two simultaneous writers can interleave partial
lines, and a failed write is invisible. This is the same store the fleet registry and queryable
audit entries build on, so it is worth fixing before they land.

**Approach:** locked appends behind the existing sink interface, keeping JSONL as the file
format — this is the **interim** fix, deliberately scoped so it can ship on its own. Choosing a
database is [durability and concurrency](#durability-and-concurrency-for-hosted-use); this entry
only stops today's file store from corrupting under concurrent writers.

- Advisory lock around appends in `audit.py` and `fleet.py`
- Surface write failures as a metric instead of swallowing them
- Concurrency test that writes from multiple processes and asserts every record parses

**Done when:** Parallel generations produce a store where every record round-trips, and a write
failure is observable.

**Status:** **Shipped on `main` follow-up** — `jsonl_lock.append_jsonl_line` with `fcntl` advisory
locks, audit/fleet wired through the helper, `repave_jsonl_append_failures_total` metric,
multiprocess regression tests for audit and fleet stores.

### A5 — Honest changelog and version pointers

**Problem:** `engine/CHANGELOG.md` ends at `0.2.0` while `engine/src/repave_engine/__init__.py`
reports `1.74.0`, so the changelog is unusable for anyone consuming the package.
`docs/concepts.md` still calls audit history and self-healing "planned" although both shipped,
`docs/sales-demo.md` implies `spec.repoURL` is GA when Phase C is open, and
`docs/operator-ga.md` records a last-verified engine of v1.63.0.

**Approach:**

- Rebuild changelog history from tags, or declare GitHub Releases the source of truth and make
  the file point there
- Refresh `concepts.md`, `sales-demo.md`, and `operator-ga.md`; extend
  `scripts/sync_doc_versions.py` to the pointers it currently misses and add a `--check` mode CI
  can run

**Done when:** `make sync-doc-versions --check` passes in CI and no shipped feature is described
as planned.

**Status:** **Shipped on `main`** — `CHANGELOG.md` points to GitHub Releases; `concepts.md`,
`sales-demo.md`, and `operator-ga.md` refreshed; `sync_doc_versions.py --check` runs in CI.

### A6 — Traces are real or not claimed

**Problem:** `engine/pyproject.toml` depends on `opentelemetry-api` only — no SDK, no exporter —
so `tracing.py` is a no-op unless a host installs a provider, while the v1.30 entry reports
traces as shipped.

**Approach:** Add an optional `otel` extra with the SDK and an OTLP exporter plus configuration
docs, or scope the shipped claim down to metrics and audit.

**Done when:** A documented configuration produces spans in a collector, or the roadmap and
docs stop promising them.

**Status:** **Shipped on `main`** — optional `otel` extra (SDK + OTLP/HTTP), `tracing` config and
OTEL env vars, [`docs/tracing.md`](tracing.md).

### B — Maintainability (opportunistic)

| Item | Evidence | Fix |
| --- | --- | --- |
| `gate_runners.py` is a 1354-line multi-domain module holding every gate CLI | `engine/src/repave_engine/gate_runners/` | **Shipped** — split into domain modules (`_core`, `terraform`, `policy`, `drift`, `observability`, `helm`, `app`, `ansible`); registry unchanged |
| `api.py` mixes portal HTML, JSON API, and auth middleware; mypy has an `arg-type` carve-out for it | `engine/src/repave_engine/api.py`, `pyproject.toml` mypy overrides | **Shipped** — `/api/v1`, `/api/v2`, `/auth`, and ops routes in separate routers; portal HTML stays in `api.py`; mypy override dropped |
| `cli.py` (576 lines) owns every command | `engine/src/repave_engine/cli/` | **Shipped** — `cli/` package with one module per command group |
| Gate-outcome summarization implemented four times with drifting empty/passed/failed semantics | `generate_api.py`, `api.py`, `pipeline.py`, `notifications.py` | **Shipped** — `gate_summary` / `all_gates_passed` in `gates.py` |
| Blueprint root `repo_root / "blueprints"` hardcoded in a dozen places | `api.py`, `cli.py`, `generate_api.py` | **Shipped** — `blueprints_dir()` helper |
| Actions pinned to mutable tags; `uv:latest` in the portal image | `.github/workflows/*.yml`, `deploy/local/Dockerfile` | **Shipped** — `.github/action-pins.json`, SHA-pinned workflows, digest-pinned base images |
| No tests for `generate_api`, `auth_context`, `tracing`, `gate_builtin` | `engine/tests/` | **Shipped** — focused unit tests under `engine/tests/` |
| Operator apply integration test skips unconditionally | `operator/internal/repave/apply_test.go` | **Shipped** — dead skip test removed (e2e covers preserve-local) |
| Python floor is 3.10 but CI only runs 3.12 | `engine/pyproject.toml`, CI workflows | **Shipped** — `requires-python >=3.12`; mypy `python_version = 3.12`; CI runs 3.12 only |
| `.tmp-staging/` is not ignored, so rendered fixtures show up as untracked noise | `.gitignore` | **Shipped** — pattern in root `.gitignore` |
| Broad `except Exception` around the provenance gate masks bugs as gate failures | `gate_runners/drift.py` | **Shipped** — catch `FileNotFoundError`, `jsonschema.ValidationError`, `yaml.YAMLError`, `ValueError`, `OSError` only |

**Done when (group B):** All maintainability table rows closed — **done on `main`** (this closeout aligns mypy/docs with the 3.12 floor and documents provenance exception narrowing).

**Done when (group A):** All six A entries closed — **done on `main`**.

---

### Durability and concurrency for hosted use

**Problem:** Generation is synchronous inside async request handlers — `api.py` calls
`generate_from_blueprint` directly, so a single multi-minute run with real gates blocks the
event loop and every other request with it. Audit, fleet, and run state are JSONL files, the
session secret falls back to a per-process random value, and Prometheus counters are per-process
so replicas cannot be aggregated. None of that survives a shared multi-user instance.

**Why this is on the v1 path and not deferred:** v2 GA promises an authenticated multi-user
service and freezes the config contract around it. Every open entry that stores state —
[fleet registry](#fleet-registry-and-repave-register),
[queryable audit history](#queryable-audit-history),
[portal surfaces](#developer-portal-surfaces-catalog-docs-scorecards-observability-read),
[fleet campaigns](#operator-fleet-campaigns-and-blueprint-controller) — otherwise picks its own
backend, and the store choice becomes a v2 breaking change rather than a v1 decision. It is one
decision made once, before four features encode the answer.

**Approach:**

- **Phase 1 (no k8s required):** run generation off the event loop in-process — a queue with
  per-run records, worker threads, and status polling or streaming to the portal instead of one
  long request. This alone fixes the blocking problem for the Compose deployment
- **Phase 2:** store behind the existing sink interfaces for audit, fleet, sessions, and run
  records — SQLite locally, PostgreSQL for hosted mode; JSONL retained as export
- **Phase 3 (hosted only):** distribute execution as Kubernetes Jobs using the chart's worker
  template, once the chart exists
- Concurrency limit plus queue-depth metrics; idempotency key on the client request id so a
  retried submit does not double-publish
- Retry with backoff and a dead-letter store with admin replay for runs that fail
  infrastructurally rather than on gates
- Reclaim stale `running` runs after worker loss; list/filter runs via `GET /api/v1/runs`
- Require an explicit session secret outside local mode; aggregate metrics across replicas

**Dependencies:** [Engine hardening A2](#a2--subprocess-timeouts-on-every-gate-and-git-invocation)
(a queued run with no timeout is a permanently occupied worker) and
[A4](#a4--concurrent-safe-audit-and-fleet-stores) as the interim file-store fix; v1.30 audit sink
interface. Phase 3 only needs the [Helm chart](#kubernetes-deploy-path-helm-chart) — phases 1 and
2 do not, so this entry is **not** blocked behind the deploy path.

**Done when:** Ten concurrent dry-runs from distinct users complete without blocking the API, run
status is visible while a run is in flight, and a killed worker's run is replayable.

**Status:** **Phase 1 shipped on `main`** — SQLite run store, in-process worker queue,
`/api/v1/runs` + async `POST /api/v1/generate`, idempotency keys, replay for dead-letter runs,
metrics — see [`docs/durability.md`](durability.md). **Phase 2 shipped on `main`** — unified SQL
store (`database_url`) for audit, fleet, runs, and **OIDC sessions** (server-side when
`database_url` is set) with optional JSONL export mirrors; PostgreSQL via
`repave-engine[postgres]` (included in portal/worker container images). **Phase 3 shipped on
`main`** — `repave run-worker`, Helm worker Deployment, and `REPAVE_EXTERNAL_WORKERS` /
`worker_mode: external` for distributed execution. **Retry/reclaim shipped on `main`** (#363) —
exponential backoff before `dead_letter`, stale `running` reclaim, `GET /api/v1/runs` and
`GET /api/v2/runs` list/filter, portal **`/runs`** index with admin replay, Helm
`maxRunAttempts` / `runStaleSeconds` / `runRetryBaseSeconds` values.

---

### GitHub App authentication for publish and remediation

**Problem:** Publish and operator remediation both authenticate with a long-lived
`GITHUB_TOKEN` PAT. On a shared cluster that means broad, non-expiring, hard-to-attribute write
access in a Secret, and rate limits are shared across everything the token touches.

**Approach:**

- GitHub App credentials (app id + installation id + private key) as an alternative to the PAT in
  `github.py`, with installation tokens minted per operation and cached until expiry
- Same option for the operator's push path; secret refs rather than inline tokens
- Per-installation rate-limit awareness so fleet campaigns can back off correctly
- PAT remains supported for local development; docs cover App installation scoping

**Dependencies:** Existing `github.py` / `pr.py` publish flow; operator `internal/git/push.go`.

**Done when:** A publish and an operator remediation PR both succeed with no PAT present, and
token material never appears in logs or error strings.

**Status:** **Shipped on `main`** — engine `github_auth.py` +
`resolve_github_access_token()`, operator installation-token cache, Helm secret keys,
and per-installation rate-limit tracking for remediation and fleet campaigns; see
[`docs/github-app-auth.md`](github-app-auth.md).

---

### Governed PR conventions

**Problem:** Generated and remediation PRs carry a title and body but no organizational metadata,
so teams bolt on branch naming, labels, reviewers, and evidence checklists by hand — and the
operator's PRs look nothing like the ones humans open.

**Approach:**

- Configurable PR convention template in `repave.config.yaml`: branch prefix, label set, PR body
  sections, and an evidence checklist rendered from the gate results
- Optional `CODEOWNERS` snippet emitted with generated repos so review routing exists from the
  first commit
- Operator remediation PRs render the same template, so drift PRs are indistinguishable in shape
  from generated ones
- Conventions are data, not code: an organization supplies its own template without patching the
  engine

**Dependencies:** `pr.py`; operator remediation; v1.24 CI template pattern.

**Done when:** One config change makes every generated and remediation PR carry the
organization's branch prefix, labels, and evidence checklist.

**Status:** **Shipped on `main`** — `pull_requests` block in `repave.config.yaml`, engine
`pr_conventions.py` (import/upgrade/generate paths, labels, evidence checklist), operator env
parity (`REPAVE_PR_*`).

---

### Supply chain digest pins

**Problem:** Mutable GitHub Action tags, floating container base images, and semver-only Helm
deploys let supply-chain drift slip in between builds — especially on a shared cluster where
publish credentials and generation images must be attributable and reproducible.

**Approach:**

- Pin marketplace Actions to commit SHAs in `.github/action-pins.json`; CI rejects drift via
  `scripts/check-action-pins.py`
- Pin Docker base images (`python:3.12-slim`, `uv`, `alpine`) by digest in `deploy/local/Dockerfile*`
- Publish digest-tagged engine images from `.github/workflows/container.yml`
- Helm `image.digest`, `workerImage.digest`, and `corpus.digest` render `repository@digest`
- Short-lived GitHub App installation tokens for publish/remediation (see
  [GitHub App authentication](#github-app-authentication-for-publish-and-remediation))

**Dependencies:** [Engine hardening A1](#a1--one-source-of-truth-for-gate-toolchain-pins);
[service decomposition](#service-decomposition-for-hosted-scale) split images.

**Done when:** CI enforces action pins, production docs show digest-pinned Helm installs, and
operators can deploy portal/worker/corpus without mutable `:latest` tags.

**Status:** **Shipped on `main`** — see [`docs/supply-chain.md`](supply-chain.md),
[`values-digest-pinned.yaml`](../../deploy/k8s/chart/values-digest-pinned.yaml).

---

### Operator fleet campaigns and Blueprint controller

**Problem:** A standard bump means every registered repo is out of date at once, and the operator
has no way to bound the resulting PR storm — nor a controller for the `Blueprint` CRD, so
blueprint versions are not a queryable fleet target.

**Approach:**

- `Blueprint` controller: register available blueprint versions and publish the current pin target
  in status, so repos can be compared against a declared target rather than a scan
- Upgrade **campaigns**: a bounded rollout with max concurrent open PRs, pause/resume, and a
  stop condition on repeated gate failures
- Drift SLO metrics: number of out-of-date repos, age of the oldest drift, remediation MTTR
- Campaign summaries through the existing notification webhooks

**Dependencies:** [Fleet registry](#fleet-registry-and-repave-register);
[GitHub App auth](#github-app-authentication-for-publish-and-remediation) for rate limits;
operator remote inventory Phase C.

**Done when:** A standard bump across a registry of repos opens a bounded set of remediation PRs,
can be paused mid-flight, and reports drift MTTR.

**Status:** **Shipped on `main`** — `Blueprint` controller publishes `status.targetPins`;
`UpgradeCampaign` CRD with pause, max concurrent open PRs, stop-after-failures gate on
remediation (label GPRs with `repave.dev/upgrade-campaign`), drift SLO status fields
(`outOfDateCount`, `oldestDriftAgeSeconds`, `averageRemediationMTTRSeconds`), Prometheus
metrics (`repave_fleet_*`, `repave_remediation_mttr_seconds`), campaign webhook events
(`campaign_summary`, `campaign_paused`, `campaign_stopped`, `campaign_capacity_reached`,
`campaign_rate_limited`), and GitHub REST rate-limit tracking with remediation deferral
when quota is low (parity with engine `github_rate_limit`).

---

### Portal live governance surfaces

**Problem:** The portal still blocks on synchronous `POST /generate` with a busy overlay whose
stage labels rotate on a timer. Durability Phase 1 shipped an async run queue and `/api/v1/runs`,
but no HTML route consumes it — so mandatory gates are only visible after the page reloads.

**Approach (eight candidates; Tier 1 ships on v1):**

1. **Live run console (Tier 1 — ship)** — SSE `/api/v1/runs/{id}/events` streams stage and
   per-gate events; portal `/runs/{id}` shows a gate table and log pane, then links to full
   `result.html`.
2. **Command palette (Tier 1 — ship)** — Cmd/Ctrl-K (and `/`) fuzzy jump to blueprints,
   bundles, primary nav, and “resume last run” from sessionStorage.
3. **Estate map** — Fleet rows become a freshness-colored tile grid with drift-age sparklines.
4. **Real diff viewer** — Split/word-level diffs on upgrade preview (extends deferred standards
   diff).
5. **Governance annotations** — Syntax-highlighted file preview with gutter markers to standard
   / policy clauses.
6. **Governance preflight** — Form-side preview of gates, policy packs, resolved repo name, and
   missing gate CLIs (pairs with `repave doctor`).
7. **Bundle topology graph** — Live cross-reference diagram on bundle form and result.
8. **Presenter mode + shareable receipt** — `?presenter=1` demo density and exportable lineage
   card for sales/demo flows.

**Dependencies:** [Durability and concurrency](#durability-and-concurrency-for-hosted-use) Phase 1
(run queue, shipped); v1.18 portal shell; [fleet registry](#fleet-registry-and-repave-register)
for the estate map; [queryable audit history](#queryable-audit-history) for server-side run history.

**Done when:** Items 1–8 are on `main` with portal contract tests covering run console, command
palette, estate map, diff viewer, annotations, preflight, bundle topology, and presenter mode.

**Status:** **Shipped on `main`** — Tier 1 (live run console, command palette) and Tier 2 (estate
map `/estate`, standards diff viewer on blueprint and upgrade preview, governance annotation
previews, governance preflight panel, bundle topology graph on form and result, presenter mode
`?presenter=1` with shareable lineage receipt).

---

### Developer portal surfaces: catalog, docs, scorecards, observability read

**Problem:** The portal generates and updates repos but cannot answer "what do I own, is it
healthy, and is it current?" — so teams still need a separate developer-portal product for
discovery even though repave already holds the provenance that would populate it.

**Approach:**

- **Catalog:** scan the org for `catalog-info.yaml` and `repave.yaml`, build entity pages with
  owner, blueprint and standard pins, links, and last remediation; reuse the fleet registry as
  the backing store
- **Docs:** render markdown from generated repos (README, upgrade notes, provenance) in-portal,
  linking out rather than duplicating org-wide documentation
- **Scorecards:** pin freshness, last gate status, provenance completeness, and runbook presence
  per entity, aggregated to a fleet view
- **Observability read:** embed an existing dashboard and show an SLO summary per entity from a
  configurable read-only source — repave displays, it does not own the data

**Dependencies:** v1.32 Backstage catalog rendering (same `catalog-info.yaml` contract);
[fleet registry](#fleet-registry-and-repave-register); v1.40 observability path.

**Done when:** A developer finds a service they own in the catalog and sees its pins, gate status,
scorecard, and a health panel without leaving the portal.

**Status:** **Shipped on `main`** — `/library` grouped catalog with owner filter and fleet scorecard
rollup; entity detail pages with pins, per-entity scorecard (including **Deployment** when
`portal.deployment_reader` is configured), last generation, README/runbook/
upgrade/provenance docs (local checkout or GitHub fetch), Grafana dashboard embed, and optional
JSON SLO health panel (`portal.observability_slo_url`).

### Cost visibility

**Problem:** Nothing in the generate flow tells a user what an artifact will cost, and nothing in
the catalog tells them what it does cost — so cost enters the conversation after provisioning.

**Approach:**

- **Estimate:** Infracost gate on Terraform dry-run and in generated-repo CI, reporting a delta on
  the generation result page; warn by default, blockable per blueprint
- **Actuals:** pluggable cloud cost reader (provider cost API, cached server-side with an `as-of`
  timestamp) scoped by the tag keys the blueprints already require, mapped to catalog entities via
  `repave.yaml` / `catalog-info.yaml` service name
- Cost panel on catalog tiles and a cost dimension in scorecards
- Optional in-cluster allocation source for Kubernetes workloads when one is deployed
- Credentials read-only and server-side; documented lag, currency, and tag-coverage caveats

**Dependencies:** v1.13 gate registry (Infracost as a gate); portal catalog surfaces; tag
requirements on Terraform blueprints.

**Done when:** A Terraform dry-run shows a cost delta, and a catalog entity with complete tags
shows last-30-day actual spend with its as-of time.

**Status:** **Shipped on `main`** — `infracost` gate and generated-repo CI; `portal.cost_reader`
(`url`, `aws`, `azure`, `k8s` OpenCost-compatible); service detail and **library tile** cost
badges (L30D actuals or local `.repave/cost-estimate.json`); **Cloud spend** scorecard dimension.

**Follow-on:** [FinOps enablement (v1.90–v1.94)](#finops-enablement-v2x) promotes showback,
budgets, and FOCUS-shaped ingest on top of this foundation — see [`docs/finops.md`](finops.md).

---

### Service decomposition for hosted scale

**Problem:** v2 promises an authenticated multi-user service, but the runtime is one portal
process that renders HTML, serves the JSON API, and runs multi-minute gate subprocesses in the
same container. `engine/src/repave_engine/api.py` imports the pipeline, gates, fleet, audit,
auth, and every catalog, so nothing can be scaled or hardened independently. The portal image
carries the whole gate toolchain (terraform, tflint, checkov, conftest, helm, ansible-lint,
molecule) that only `gates.run_gates` executes, and the operator ships a Python venv plus a
monorepo corpus purely to exec `repave plan-upgrade`. Freezing contracts at v2 on top of that
shape locks in the coupling.

**Approach:** roles of one codebase, not separate codebases — the full loop must still run on a
laptop. Design in [ADR 002](adr/002-v2-service-decomposition.md).

**Status:** **Shipped on `main` (Phase 0–4)** — split portal/worker/corpus images,
Postgres claim queue, worker Deployment and per-run Jobs, `/api/v2` operator HTTP,
`repave.dev/v1beta1` CRDs, decomposed and multi-replica chart CI smoke. **Still open:**
optional separate portal vs API Deployments when scaling profiles diverge (see Phase 4 note).

- **Phase 0 (no split visible):** Postgres store for runs, audit, fleet, and sessions
  ([durability](#durability-and-concurrency-for-hosted-use) Phase 2); subprocess timeouts
  ([A2](#a2--subprocess-timeouts-on-every-gate-and-git-invocation)); unified toolchain pins
  ([A1](#a1--one-source-of-truth-for-gate-toolchain-pins)); digest-pinned container images
  published from CI ([`.github/workflows/container.yml`](../../.github/workflows/container.yml))
- **Phase 1:** replace the in-process `ThreadPoolExecutor` in `run_queue.py` with a
  Postgres-backed queue (`FOR UPDATE SKIP LOCKED`); add a `worker` role and chart Deployment
  behind `execution.mode: inprocess | worker`; the API stops running gates in-request
- **Phase 2:** toolchain-free portal/API image; corpus as OCI artifact; optional object store for
  full staging-tree retention — **no shared RWX volume between roles**
- **Phase 2b:** bounded `rendered_files` snapshot in `result_json` for portal rehydrate (default);
  object storage optional — [addendum](adr/002-addendum-run-artifact-rehydrate.md)
- **Phase 3:** promote the CRDs to `repave.dev/v1beta1` with a conversion webhook and have the
  operator call `/api/v2` instead of exec'ing the CLI, dropping `operator/Dockerfile.e2e`
- **Phase 4:** per-run Kubernetes Jobs (`worker_mode: job`) — **shipped on `main`**; portal
  creates a batch Job per enqueued run (`values-decomposed-job.yaml`); optional portal/API
  Deployment split deferred until scaling profiles diverge
- Extend the `client_request_id` idempotency key through publish, keyed on target repo plus
  content hash, so a retried run cannot double-publish to GitHub — **shipped on `main`**
  (`publish_receipts` store + `PublishIdempotencyStore`)
- **Repository strategy:** stay a monorepo through v2 and make it split-ready; revisit at v3 on
  a concrete trigger (independent release cadence, external contributors, another language)

**Non-goals:** gates as a service separate from the pipeline (they need the staging tree on
local disk); fleet/audit/registry as services (read models over Postgres); splitting the CLI;
multi-tenancy.

**Dependencies:** [durability and concurrency](#durability-and-concurrency-for-hosted-use)
Phase 2 is a hard prerequisite — nothing splits while state is on local disk;
[Helm chart](#kubernetes-deploy-path-helm-chart) for the worker template; `/api/v2` from the
[v2 contract freeze](#v200--platform-ga).

**Done when:** `helm install` runs portal and worker Deployments where the portal image
contains no gate binaries, a generation submitted in the portal is executed by the worker, a
killed worker's run is replayable and visible from a second portal replica, and
`docker compose up` still completes a full generate → gates → publish loop with no Postgres.

---

### Environment lifecycle and deployment awareness

**Status:** **Phase 1–3 shipped on `main`** — deployment status, `kind: live_plan`,
environment vending (`environment_vend`), JSONL registry + catalog, sandbox TTL auto-reclaim,
non-sandbox draft decommission PRs, CLI/API reclaim, optional Helm reclaim CronJob, catalog cost
badges for vended environments, and post-merge registry finalize
([ADR 003](adr/003-environment-lifecycle-and-live-state.md)).

**Problem:** repave governs **repositories** and stops at the pull request. It cannot answer
"is my change live", its policy runs against repo shape rather than the effect of a change,
and "drift" means pin drift rather than infrastructure divergence. The
`terraform-environment-stack` blueprint generates a repo that *describes* an environment;
nothing requests, owns, bounds the cost of, or reclaims a real one. That is the gap between a
governed generator and a platform.

**Approach:** climb from read to plan to vend, so each rung earns the credentials the next
one needs. Design and boundaries in [ADR 003](adr/003-environment-lifecycle-and-live-state.md).

| Phase | Content | Risk added |
| --- | --- | --- |
| **1 — deployment status** | Read Argo CD / Flux state (sync, health, revision, last synced) into `CatalogEntity` via a `deployment_reader` following the existing cost/SLO enrichment pattern; optional snapshot for list views; portal and `/api/v2` detail | Read-only token; degrades to "unknown" on outage |
| **2 — governed plan on live state** | Real `terraform plan` against a configured backend in a worker Job; OPA on **plan JSON**; summary + verdict on the run record (`POST /api/v2/runs` `kind: live_plan`, portal button); optional PR body attachment via `pull_request` / `pull_request_url` | State + cloud read credentials, scoped per environment; plan output treated as sensitive |
| **3 — environment vending** | Request an environment from a governed blueprint; repave writes desired state to a **GitOps repo** and the existing CD toolchain applies it; environment records carry owner, class, TTL, cost, status; expiry reclaims sandboxes and opens decommission PRs elsewhere | Environment ownership and TTL enforcement; no apply credentials in repave |

**Non-goals:** repave running `terraform apply` against production credentials; writing to
Argo CD or Flux (sync, rollback, refresh stay with the GitOps controller); estate-wide
infrastructure drift detection (revisit after Phase 2 proves credential scoping); auto-merge
of any environment change outside the sandbox class, which stays
[v3 work](#autonomous-governed-remediation).

**Dependencies:** catalog read model (`entity_catalog.py`, `portal_context.py`) and the
enrichment precedents in `cost_actuals.py` / `observability_slo.py`; worker role and per-run
Jobs from [service decomposition](#service-decomposition-for-hosted-scale) for Phase 2;
`terraform-environment-stack` blueprint and standard for Phase 3.

**Done when (Phase 1):** an entity backed by an Argo CD application shows sync state, health,
deployed revision, and last-synced time in the portal and on
`GET /api/v2/catalog/entities/{id}`; catalog responses are unchanged when no reader is
configured; an unreachable GitOps API renders unknown status instead of an error.

**Done when (Phase 2):** `kind: live_plan` runs in the async queue / Job with optional
per-environment Secret `envFrom`; OPA failure surfaces as `gates_outcome: failed`; plan JSON
never appears in the run result, provenance, or audit; portal offers **Plan against live state**
when the entity is configured under `live_plan.environments`; optional `pull_request` /
`pull_request_url` on submit merges summary + OPA verdict into the PR body.

**Done when (Phase 3):** an environment request opens a reviewable GitOps commit and the vended
stack appears in the catalog with owner, class, TTL, and status; expired sandboxes are
auto-reclaimed via decommission PR; expired non-sandbox classes open draft decommission PRs;
operators can schedule reclaim via Helm CronJob or `repave environments reclaim`; catalog list
and library tiles show cloud spend when `portal.cost_reader` is configured; merged decommission
pull requests remove expired environments from the registry on the next reclaim pass.

---

## v2.0.0 — Platform GA

**Target:** Repave as the **control plane for golden-path estates** — not only a
generator.

**Status:** **Shipped** — contract freeze and Postgres DR are on `main`, and the engine is
tagged **`v2.0.0`**. [Environment lifecycle](#environment-lifecycle-and-deployment-awareness)
(Phases 1–3) and v2 read models are on `main`. [Conversational governed AI](#conversational-and-governed-ai-generation)
is deferred to **v3.0.0** (see [beyond v2.0.0](#beyond-v200--autonomous-estate-and-lifecycle-control-plane)).
**Shipped:** v2 read models for `/api/v2/estate` and `/api/v2/governance/annotations/*`
(parity with legacy v1 JSON).

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
| Fleet visibility | v1.72–v1.73+ remote inventory + fleet registry (portal + manifests) → v2 operator GA (shipped) |
| Govern repos repave did not generate | [`repave verify`](#repave-verify-for-existing-repositories) (shipped) |
| Add a second blueprint to a governed repo | [`repave add`](#repave-add--multi-component-brownfield-engine-v182) (shipped) |
| Composite multi-artifact paths | [composite golden paths](#composite-golden-paths-bundles) (shipped) |
| Module repos self-govern in CI | v1.23 |
| On-cluster deploy | [Helm chart](#kubernetes-deploy-path-helm-chart) + [day-2 overlay](../deploy/k8s/chart/values-day2.yaml) (shipped) |
| Authenticated single-tenant service (OIDC SSO) | v1.26–v1.27 (shipped) |
| Operability and audit (metrics, audit log, notifications, catalog) | v1.30–v1.32 (shipped) |
| Day-2 operability (health, SLOs, upgrades, runbooks) | v1.35–v1.38 (shipped) |
| GitHub App auth (publish/remediation) | [GitHub App authentication](#github-app-authentication-for-publish-and-remediation) (shipped) |
| Durable multi-user service (SQL store, async runs) | [durability and concurrency](#durability-and-concurrency-for-hosted-use) (shipped) |
| Independently scaled portal / API / gate worker on k8s | [service decomposition](#service-decomposition-for-hosted-scale) (shipped Phase 0–4) |
| Portal discovery surfaces (catalog, docs, scorecards, health) | [portal surfaces](#developer-portal-surfaces-catalog-docs-scorecards-observability-read) (shipped) |
| Cost at generate time and in the catalog | [cost visibility](#cost-visibility) (shipped) |
| Bounded fleet upgrade campaigns | [fleet campaigns](#operator-fleet-campaigns-and-blueprint-controller) (shipped) |
| Contract freeze (HTTP, config, schema, provenance) | See table below (shipped → **`v2.0.0` tag**) |
| Postgres backup/restore for hosted SQL | [`postgres-backup-restore.md`](operations/postgres-backup-restore.md) (shipped) |

**Contract freeze at v2.0.0**

**Status:** **Shipped on `main`** — integrators can build against the v2 line; v1 deprecation
windows are published for v3 removals.

v2 is the point where integrators can build against repave without expecting the ground
to move. That means declaring what is stable and what it costs to migrate — and opening the
deprecation windows for the removals listed under
[breaking at v3.0.0](#breaking-at-v300), since a sunset notice has to ship with the freeze
rather than after it:

| Change | Migration | Status |
| --- | --- | --- |
| **`/api/v2`** is the stable HTTP surface; `/api/v1` deprecated with a published sunset | v1 clients get a documented deprecation window before removal | **Shipped** — [`docs/api-v1-migration.md`](api-v1-migration.md); v1 `Deprecation`/`Sunset` headers |
| **`GoldenPathRepo` / `Blueprint`** promoted to `repave.dev/v1beta1` with frozen shapes | Conversion webhook plus a `kubectl`-level migration guide from `v1alpha1` | **Shipped** |
| **`repave.yaml` provenance required** on every publish | Operator flags non-compliant repos instead of silently skipping them | **Shipped** — publish fails without valid `repave.yaml`; GPR `ProvenanceMissing` |
| **`repave.config.yaml` gains `apiVersion`** | Config loader accepts the unversioned form for one minor with a warning | **Shipped** — [`docs/repave-config-v1.md`](repave-config-v1.md) |
| **Durable store required in service mode** (JSONL becomes export-only) | Documented external-database setup; local mode keeps the file store | **Shipped** — [`docs/repave-config-v1.md`](repave-config-v1.md), startup validation |
| **Blueprint JSON Schema frozen** for the v2 line; `metadata.version` policy documented | Template breaking changes must bump blueprint minor/major | **Shipped** — [`docs/blueprint-versioning.md`](blueprint-versioning.md) |

### Resilience and disaster recovery

**Status:** **Shipped** on `main` — Postgres backup/restore runbook, automated local drill
(`make postgres-dr-drill`), RPO/RTO targets, and [`docs/operations/dr-drill-log.md`](operations/dr-drill-log.md).
Multi-region active/passive failover remains a follow-on.

**Problem:** The hosted service has no documented recovery objective. The control plane
(blueprints, standards, config, manifests) lives in git and is trivially re-deployable, but the
durable store introduced for hosted mode is the first piece of state that can actually be lost.

**Approach:**

- Backup and restore procedure for the durable store, with a tested restore — not just a
  configured backup
- Active/passive second-region option for the API and store, with a documented failover
  procedure and a recovery-time objective (target: hours, not days)
- Periodic failover drill recorded in `docs/operations/`
- Generated repos are unaffected by definition; recovery covers audit, fleet, and run history

**Done when:** A recorded drill restores the service and its audit/fleet history within the
documented objective — see
[`docs/operations/postgres-backup-restore.md`](operations/postgres-backup-restore.md) and
[`docs/operations/dr-drill-log.md`](operations/dr-drill-log.md) (`make postgres-dr-drill` baseline).

**Non-goals for v2** — scoped in
[beyond v2.0.0](#beyond-v200--autonomous-estate-and-lifecycle-control-plane) or left in the
[parking lot](#parking-lot):

- **Multi-tenant SaaS repave** — org isolation, per-tenant config/RBAC; the
  multi-tenant follow-on to the single-tenant SSO shipped in v1.26–v1.27
- OPA/Sentinel as a *default/required* gate (v1.39 ships OPA opt-in; making it
  mandatory estate-wide is a v3 breaking change, and Sentinel support stays unscheduled)
- Private blueprint registry over OCI
- **Autonomous merge of any kind** — v2 keeps a human on every remediation PR by design; the
  low-risk tier is what v3 has to earn

**Done when:**

1. Operator opens remediation PRs for drift and standard bumps across registered repos. **Met.**
2. `repave update` upgrades an existing module repo via PR. **Met.**
3. At least two production golden paths ship with standards + lint/policy packs. **Met** (Terraform,
   Ansible, Helm, app-service, observability paths on `main`).
4. Documentation describes fork → customize standards/blueprints → fleet reconcile
   without referring to unreleased features. **Met** for shipped v2 themes.
5. The conversational and form paths produce byte-identical gated output for the same
   blueprint and inputs. **Deferred to v3.0.0** — [conversational governed AI](#conversational-and-governed-ai-generation).
6. CRD conversion runs in a non-production cluster with no data loss, and a recovery drill
   meets the documented objective — see
   [`docs/operations/crd-conversion-recovery.md`](operations/crd-conversion-recovery.md)
   (automated baseline in `make operator-e2e`). **Met.**
7. Postgres backup/restore drill meets documented RPO/RTO — see
   [`docs/operations/postgres-backup-restore.md`](operations/postgres-backup-restore.md)
   (`make postgres-dr-drill` baseline). **Met.**

---

## Developer paved roads (v2.x)

**Target (planning labels v1.79–v1.84, on the v2.x line):** repave paves the creation of an
artifact and stops there. A developer receives a repo with a Dockerfile, tests, gate CI, and a
Backstage entry — then hand-writes everything that makes the service actually run: the deploy
pipeline, the GitOps wiring, the SLOs, the runbook they will be paged against. This cluster
finishes the journey, then widens it.

Planning labels continue the roadmap sequence from v1.78 and are **not** engine tags; engine
versions come from semantic-release and are already on the 2.x line.

Two structural gaps set the order below.

1. **Every road ends at `git init`.** The engine already *reads* Argo and Flux live state
   (`deployment_status.py`) and already *writes* GitOps PRs for environment vending
   (`environment_vend.py`). The write side for services is the missing half, and it stays
   git-only — no new credential surface against the
   [ADR 003](adr/003-environment-lifecycle-and-live-state.md) boundary.
2. **Every road is generate-time only (partially addressed).** `generate`, `import`, and
   `update` still assume one blueprint per repository for upgrades, but **`repave add`**
   ([v1.82](#v182--repave-add-paved-roads-for-existing-repositories)) layers additional
   components onto governed repos and `verify` scores each component independently.
   Bundles still compose only at creation time.

Critical path is the delivery path → deploy pipeline → composite bundles. Reliability,
`repave add`, and runtime breadth are independently shippable and can be reordered.

---

### GitHub repository provisioning goldpath

**Status:** **Shipped on `main`** — `blueprints/github-repo-generic/` (`github-repo` artifact
type, Platform catalog family), engine template/selection create + team grants,
`repave create-repo`, `GET /api/v2/github/teams`,
[`docs/github-repo-goldpath.md`](github-repo-goldpath.md). Phase 2: `ruleset_profile`
(`default-pr`), additive membership sync from `membership_source_team` (create destination
teams if missing), fleet register after apply so fleetsync / `fleet-manifests` emit
`GoldenPathRepo`, `GET /api/v2/github/teams/{slug}/members`. Ops validation:
[`docs/operations/github-repo-fleet-validation.md`](operations/github-repo-fleet-validation.md)
(`make validate-github-repo-fleet`, `make chart-smoke-fleet-snapshot`).

**Problem:** Org repos are still created by hand or via ad-hoc scripts: template copy,
visibility, topics, and team permissions are inconsistent, and existing golden paths only
create empty public repos as a side effect of artifact publish.

**Approach:**

- Thin Copier overlay (`README`, `repave.yaml`, optional `CODEOWNERS`) plus GitHub REST
  provision (template generate or selection create, ruleset profile, team sync, grants)
- Portal form with create-mode toggle, org team listing, membership sync toggle,
  source-team member preview, and ruleset profile select
- Fleet register on successful apply (no kubectl from the engine)
- Still out of scope: cross-org/IdP SCIM, purging extra members, legacy branch protection
  API, auto-applying a second artifact blueprint

**Done when:** Operators can dry-run and apply a governed GitHub repo from portal/CLI/API
with optional rulesets, membership sync, team grants, and fleet → `GoldenPathRepo`, with
no live GitHub calls in CI.

### v1.79 — GitOps delivery golden path

*Planning label: v1.79 (roadmap numbering only).*

**Status:** **Shipped on `main`** — `blueprints/gitops-deployment-generic/` (Argo CD
`Application` and Flux `HelmRelease`), `gitops-deployment` artifact type and `gitops` family,
`standards/gitops/deployment-standard.md`, and `policy/opa/policies/gitops_deployment.rego`
enforcing exact chart pins, explicit prune/self-heal, and scoped destinations.
`helm-template` against the referenced chart is **deferred** — it needs network access to the
chart repository from the gate runner.

**Problem:** [Helm chart](#v131--helm-chart-golden-path-accelerated-was-v133) and
[app-service](#v132--application-service-scaffold-golden-path-accelerated-was-v134) paths emit
the artifact to deploy but nothing that deploys it. Operators hand-write the Argo CD
`Application` or Flux `Kustomization` per environment, so the pinning discipline every other
path enforces is absent exactly where a bad pin reaches production.

**Approach:**

- New blueprint `gitops-deployment-generic`; artifact type `gitops-deployment`; new
  `gitops` artifact family in `artifact_family()`, the blueprint schema enum, import
  markers, and portal grouping
- Renders an Argo CD `Application` or Flux `Kustomization` per environment, pinned to a chart
  repository and version
- New standards pack `standards/gitops/deployment-standard.md`
- Policy rules: no `targetRevision: HEAD` or floating tag, automated sync requires an explicit
  prune and self-heal decision, destination and project must be scoped
- Gates: `yamllint`, `opa`, `secrets`, `docs-drift`, `provenance-drift`; `helm-template`
  against the referenced chart is a follow-on (needs chart-repository network access)

**Dependencies:** v1.31 Helm path; `deployment_status.py` readers (environment lifecycle
Phase 1); v1.39 OPA gate.

**Done when:** A generated manifest round-trips through `deployment_status.py`, kind smoke
deploys it, and `docs/module-repositories.md` documents the repository naming convention.

**Follow-ons:** `helm-template` against `chart_repo_url`; kind smoke that applies the generated
manifest to a cluster running Argo CD; `gitops-deployment` as a `microservice-full` bundle
member ([composite paved roads](#v184--composite-paved-roads)).

---

### v1.80 — Deploy pipeline path

*Planning label: v1.80 (roadmap numbering only).*

**Status:** **Shipped on `main` (partial)** — `actionlint` gate shipped; deploy workflow
generation (`repave-deploy.yml`), delivery inputs, OIDC trust docs, and GitOps promotion PR
path shipped for `helm-chart-generic` and container build/push for `app-service-generic`.
Cloud OIDC trust runbook: [`docs/operations/deploy-pipeline-oidc.md`](operations/deploy-pipeline-oidc.md).

**Problem:** Generated repos gate themselves ([v1.24](#v124--generated-module-ci-template)) but
ship no delivery pipeline. Teams write their own, and the recurring failure is a long-lived
cloud credential in a repository secret — the one thing the supply-chain theme spent a release
eliminating everywhere else.

**Approach:**

- New partial `blueprints/_partials/delivery-inputs.yaml` consumed by `app-service-generic`
  and `helm-chart-generic`
- Generates a reusable GitHub Actions deploy workflow, environment protection and approval
  configuration, and the cloud trust-policy snippet an operator applies once
- Deploy step updates the v1.79 GitOps manifest rather than invoking `helm upgrade` directly,
  so promotion stays a reviewable commit
- New gate `actionlint` with a pin in `deploy/local/gate-toolchain-pins.env` and a
  `repave doctor` entry — **shipped** on `helm-chart-generic`, `app-service-generic`, and
  `gitops-deployment-generic`
- Policy rules: SHA-pinned actions, least-privilege `permissions:`, no static cloud
  credentials in workflow files

**Dependencies:** v1.79 delivery path; [supply chain](#supply-chain-digest-pins) pinning
conventions; v1.13 gate registry.

**Done when:** Generated workflows pass `actionlint` and the new policy pack, `repave doctor`
reports the new gate, and a runbook covers wiring the cloud trust relationship.

---

### v1.81 — Reliability path: SLOs as code and runbooks

*Planning label: v1.81 (roadmap numbering only).*

**Status:** **Shipped on `main`** — `slo-as-code-generic` blueprint,
`RUNBOOK.md` templates for app/helm/SLO paths, `docs-drift` section enforcement, and
scorecard `has-slo` / `has-runbook` dimensions ([#450](https://github.com/opsdevcode/repave/pull/450)).

**Problem:** [Dashboards and monitors](#v140--observability-as-code-golden-path) are paved, but
the objective those alerts defend is not, so alert thresholds are picked by hand and drift from
whatever the service actually promises. Generated repos also ship no runbook, so the
[operations runbooks](#operations-runbooks-and-troubleshooting) discipline that repave itself
follows never reaches the fleet.

**Approach:**

- New blueprint `slo-as-code-generic` in the observability family: OpenSLO or Sloth
  specifications compiled to Prometheus recording rules and multi-window burn-rate alerts,
  with optional Datadog SLO resources via Terraform
- `RUNBOOK.md` template added to `app-service-generic`, `helm-chart-generic`, and the new
  blueprint; `docs-drift` enforces required sections (owner, escalation, dashboard links,
  rollback procedure, game-day checklist)
- Scorecard gains `has-slo` and `has-runbook` dimensions
- Gates: `promtool` and `opa` are already registered, so the alerting half needs no new
  runner — this is the cheapest entry in the cluster

**Dependencies:** v1.40 observability paths; [portal scorecards](#developer-portal-surfaces-catalog-docs-scorecards-observability-read).

**Done when:** Generated burn-rate rules pass `promtool`, the scorecard reports both new
dimensions across the fleet, and the monitors and dashboards standards cross-link the path.

---

### v1.82 — `repave add`: paved roads for existing repositories

*Planning label: v1.82 (roadmap numbering only).*

**Status:** **Shipped on `main`** — multi-component `repave.yaml` (`spec.components[]`),
`repave add` CLI, `POST /api/v2/components/plan|apply`, per-component verify, and portal
add action on service detail ([#453](https://github.com/opsdevcode/repave/pull/453)).
Operator doc: [`docs/add.md`](add.md).

**Follow-ons:** remote `--open-pr` publish (parity with `repave import --open-pr`); per-component
`plan-upgrade` / `update` selector; fleet/catalog multi-blueprint pins in library UI.

**Problem:** [`repave import`](#repo-import-to-golden-path) adopts a whole repository into one
golden path and `repave update` bumps its pins, but there is no way to add a *second* artifact
to a repository that already exists. Bundles compose only at generate time. The practical
effect is that every blueprint is available only to greenfield work.

**Approach:**

- `repave add <repo> --blueprint <name>`, `POST /api/v2/components/plan|apply`, and a
  portal action on the repository detail page
- Reuses `repo_import.py` and `import_rules.py` for overlay and conflict reporting, and the
  `apply-upgrade` branch-and-commit path for publishing
- **`repave.yaml` becomes multi-component**, recording each added blueprint and its pins
  separately so `verify`, `update`, and `plan-upgrade` operate per component instead of
  assuming one repository equals one blueprint — this is the load-bearing design decision
- Never overwrites a file that is not generator-owned without `--force`; every add records an
  audit entry and a governed PR

**Dependencies:** Repo import Phase 1–3; `apply-upgrade`; v1.14 provenance;
[governed PR conventions](#governed-pr-conventions).

**Done when:** Adding `helm-chart-generic` to an existing app-service repository produces a
local branch commit with both components' scaffold, and `verify` reports on each component
independently. Remote governed PR publish is a follow-on (see **Follow-ons** above).

---

### v1.83 — Runtime and archetype breadth

*Planning label: v1.83 (roadmap numbering only).*

**Status:** Shipped on `main` ([#457](https://github.com/opsdevcode/repave/pull/457),
[#460](https://github.com/opsdevcode/repave/pull/460), [#461](https://github.com/opsdevcode/repave/pull/461)) —
`appService.layout` on `app-service-generic` (`http-api`, `worker`, `scheduled-job`, `grpc`) for
Python, Go, Node.js, Java, and .NET; `buf-lint` gate and grpc proto templates; dry-run coverage
for every runtime × layout pair.

**Follow-ons (optional):** ~~conformance manifest snapshots per runtime/layout pair~~ **Shipped on `main`** — `app-service-generic/conformance.yaml` declares 20 runtime×layout variants (gates + required files); golden manifests for `python-http-api`, `go-grpc`, and `nodejs-scheduled-job`.

**Problem:** `app-service-generic` covers Python and Go over HTTP. Every other runtime and every
non-HTTP shape — queue consumers, scheduled jobs, gRPC services — falls off the paved road
entirely, and `gate_builtin.py` has no linters or test runners outside Python, Go, and Docker.

**Approach:**

- Runtimes: Node/TypeScript and Java on `app-service-generic`, each requiring a gate runner
  (`node-lint`, `node-test`, `java-build`), a toolchain pin, a schema enum entry, and a
  `repave doctor` line
- Archetypes as an `appService.layout` knob, mirroring `terraform-module-resource`'s
  `layout: single-resource`: `http-api` (default), `worker` (queue consumer with dead-letter
  handling, idempotency, graceful drain), `scheduled-job` (CronJob with backoff and a
  missed-run alert), `grpc` (proto, `buf-lint`, generated stubs)
- Each layout composes with the v1.79–v1.81 delivery and reliability paths

**Dependencies:** v1.32 app-service path; v1.13 gate registry; v1.29 conformance harness for
per-layout snapshots.

**Done when:** Every runtime and layout combination renders a gate-green repository in the
conformance harness and carries its own delivery, SLO, and runbook artifacts.

---

### v1.84 — Composite paved roads

*Planning label: v1.84 (roadmap numbering only).*

**Status:** Shipped on `main` — `microservice-full` bundle (app-service, helm-chart,
gitops-deployment, dashboards, monitors, SLO), `service-stack` v0.2.0 Terraform module member,
portal catalog preset chips, bundle conformance fixtures, and dry-run tests.

**Problem:** [`service-stack`](#composite-golden-paths-bundles) proved bundles work with three
members, and its own follow-on (a Terraform module member) is still open. Once delivery and
reliability paths exist, a service needs six coordinated repositories and the bundle catalog
offers one.

**Approach:**

- `service-stack` gains the Terraform module member noted as a follow-on
- New bundle `microservice-full`: app-service, helm-chart, gitops-deployment, dashboards,
  monitors, and SLO, sharing service name, owner, tags, and one provenance lineage
- Portal preset chips for common bundles (see [`portal-design.md`](portal-design.md) Phase 5)

**Dependencies:** v1.79 delivery path; v1.81 reliability path; existing bundle schema and
`blueprint_conformance.py`.

**Done when:** One portal request registers every member in the fleet registry under a single
bundle lineage, and conformance CI validates the cross-repository pins.

---

### Deferred from this cluster

Recorded here rather than in the [parking lot](#parking-lot) because each is scoped enough to
promote without new discovery:

- **API contract path** — OpenAPI/AsyncAPI specification repository with `spectral` lint and
  `oasdiff` breaking-change detection. Valuable and fully standalone, but needs two new gate
  runners and unblocks nothing else in the cluster.
- **Database migration path** — Alembic/Flyway/Atlas layout with a destructive-DDL policy and
  a rollback plan. Needs its own policy design before scoping.
- **Component-level self-service vending** — request a managed database, bucket, or queue
  through the same GitOps PR flow as `environment_vend`. This is Phase 4 of
  [environment lifecycle](#environment-lifecycle-and-deployment-awareness) and warrants an ADR.
- **Organization blueprint packs** — [forked and remote blueprint packs](#forked-and-remote-blueprint-packs)
  is the one item that lets adopters pave roads this cluster does not; pull it ahead of
  everything above if external demand appears, since nothing here substitutes for it.

---

## Platform as a product (v2.x)

Repave is an internal developer platform. Adoption problems kill platforms more often than
technical gaps. This cluster adopts the five [product management principles for
IDPs](https://platformengineering.org/blog/five-product-management-principles-for-internal-developer-platforms)
so we treat developers as customers, measure outcomes (not only infrastructure outputs), and
evolve continuously — including sunsetting unused surfaces.

**Principles**

1. **Treat internal developers as customers, not captive users** — they have alternatives;
   discover needs via workflow observation, usage data, and outcome-focused interviews.
2. **Design for developer outcomes, not infrastructure outputs** — adoption, satisfaction,
   and value-stream improvement over raw generation counts and uptime.
3. **Commit to continuous evolution over fixed project delivery** — living roadmap, dedicated
   ownership, and the discipline to remove features.
4. **Build golden paths that enable autonomy** — opinionated workflows that reduce cognitive
   load; CLI / portal / API personas over one shared surface.
5. **Measure success through developer experience metrics** — satisfaction as a leading
   indicator, golden-path adoption rates, continuous feedback loops.

**Maturity self-assessment** (re-score when a theme in this cluster ships):

| Principle | Score | Notes |
| --- | --- | --- |
| 1 Customers | Partial | Bypass list shipped with v1.85; CSAT/friction capture shipped with v1.86 |
| 2 Outcomes | Strong | Adoption + funnel gauges + stakeholder compliance/value-stream views (v1.87) |
| 3 Continuous evolution | Strong | Living roadmap + deprecation windows; sunset policy added |
| 4 Golden paths | Strong | Blueprints, bundles, gates, CLI/UI/API; Guided/Advanced on TF + Ansible role forms (v1.88) |
| 5 DX metrics | Partial | Adoption ratio, funnel, TTF shipped; feedback loop shipped with v1.86 |

Planning labels **v1.85–v1.89** continue the paved-roads numbering on the 2.x line and are
**not** engine tags.

### v1.85 — Golden path adoption and DX metrics

*Planning label: v1.85 (roadmap numbering only).*

**Problem:** Platform teams (including this project) can see generation counts and queue depth
but not whether developers choose golden paths, where plan→apply drops off, or how long
first success takes. Without those outcomes, roadmap priority stays guesswork.

**Approach:**

- Pure core `dx_metrics.py`: adoption ratio (governed / eligible), plan→apply funnel, time to
  first artifact, service creation time, gate friction
- Eligible denominator from configured GitHub org/topic search; governed set from the fleet
  registry; non-governed remainder is the bypass list (shadow-IT signal)
- `platform_metrics` config block, snapshot store (JSONL + SQL) + Helm CronJob for trends
- Surfaces: `GET /api/v2/platform/metrics`, `/platform/adoption`, Prometheus gauges,
  `repave metrics adoption`
- Degrade gracefully when audit is off (same pattern as `/activity` and `/estate`)

**Done when:** An admin can see adoption ratio, funnel drop-off by blueprint, and trend
sparklines from portal/API/CLI without hand-querying audit JSONL; docs cover config and
baselines.

**Status:** **Shipped on `main`** — `dx_metrics.py` + snapshot store (JSONL/SQL),
`GET /api/v2/platform/metrics`, `/platform/adoption`, `repave metrics adoption`, Prometheus
gauges, Helm CronJob (`platformMetricsSnapshot`), [`docs/platform-metrics.md`](platform-metrics.md).

**Follow-ons:** v1.86 feedback loop shipped — CSAT correlates against this denominator.

### v1.86 — Feedback loop

*Planning label: v1.86 (roadmap numbering only).*

**Problem:** There is no in-portal CSAT or friction capture, so principle 1 has no continuous
discovery instrument beyond raw audit rows.

**Approach:** Lightweight CSAT + friction capture on result and run-console pages, tied to
`blueprint@version` and gates outcome; `/platform/feedback` rollup for admins.

**Done when:** Feedback events land in the same store family as adoption snapshots and appear
on an admin rollup within one release of capture.

**Status:** Shipped — `feedback.py` / `feedback_store.py`, `feedback_events` SQL table,
`POST|GET /api/v2/platform/feedback`, `/platform/feedback`, result/run-console capture
([`docs/platform-metrics.md`](platform-metrics.md)).

**Depends on:** v1.85 (denominator and store patterns).

### v1.87 — Stakeholder interfaces

*Planning label: v1.87 (roadmap numbering only).*

**Problem:** Security/compliance and leadership need clear interfaces over platform outcomes
without competing for the developer surface (principle 2).

**Approach:** Read-only views over the metrics store — compliance posture (gate pass rate,
bypass list size) and leadership value-stream summary — behind existing platform-admin roles.

**Done when:** Secondary stakeholders get dedicated pages or API slices that do not add fields
to the developer catalog/library chrome.

**Status:** Shipped on `main` (v1.87 — `/platform/compliance`, `/platform/value-stream`,
admin API slices; no catalog/library chrome changes).

**Depends on:** v1.85.

### v1.88 — Cognitive load reduction

*Planning label: v1.88 (roadmap numbering only).*

**Problem:** Blueprint forms are creation-heavy (large steppers and governance rails). Funnel
drop-off from v1.85 should name which paths to simplify first (principle 4).

**Approach:** Guided vs Advanced progressive disclosure on `blueprint_form.html` for
`terraform-module-generic` and `ansible-role-generic`. Optional `InputField.advanced` drives
which fields hide under Guided; Advanced reveals the full declared field set (policy, catalog,
Galaxy platforms, service scope). Freeform TF/Ansible paste is an explicit non-goal for this
slice — see [`portal-design.md`](portal-design.md).

**Done when:** At least one high-drop-off golden path ships a guided mode that reduces
required fields without removing expert escape hatches.

**Status:** Shipped on `main` (v1.88 — Guided default + Advanced toggle on terraform-module and
ansible-role generic forms; freeform extras deferred).

**Depends on:** v1.85 funnel data.

### v1.89 — Roadmap evidence loop

*Planning label: v1.89 (roadmap numbering only).*

**Problem:** Roadmap themes record status but not who asked or whether shipped work was
adopted (principle 3).

**Approach:** Adoption evidence and requesting-team attribution on themes; sunset candidates
surfaced from low-adoption golden paths.

**Done when:** At least one theme update cites adoption evidence from `/platform/adoption`, and
one low-adoption path is marked for sunset or simplification with a dated window.

**Status:** Not started.

**Depends on:** v1.85; optionally v1.86.

---

## FinOps enablement (v2.x)

Repave already ships **cost awareness** — Infracost at plan time, pluggable actuals readers,
library badges, and a Cloud spend scorecard ([cost visibility](#cost-visibility)). That is not
yet a FinOps practice. This cluster adopts [FinOps Foundation Framework
2025](https://www.finops.org/insights/2025-finops-framework/) capabilities that belong in an
IDP, plus a thin [FOCUS](https://focus.finops.org/focus-specification/) ingest path — without
turning repave into a billing warehouse.

**Role (hybrid):** enablement first (tags, estimate policy, showback/budgets), then thin
FOCUS-compatible ingest and chargeback export. Commitment discounts, RI/SP engines, multi-year
CUR warehouses, and cluster idle allocation stay in external FinOps tools (OpenCost/Kubecost,
cloud FOCUS exports, commercial platforms).

**Operator guide:** [`docs/finops.md`](finops.md).

**Principles (Inform → Optimize → Operate)**

1. **Inform** — allocate spend to the teams that own it (tags, showback).
2. **Optimize** — put cost in the path of change (estimate-at-plan, budgets, anomalies).
3. **Operate** — continuous accountability (exports, notifications), not one-off reports.

**Maturity self-assessment** (re-score when a theme in this cluster ships):

| Capability | Score | Notes |
| --- | --- | --- |
| Planning & estimating | Strong | Infracost + optional `max_monthly_usd`; org floor is v1.91 |
| Allocation | Partial | v1.90 gate-enforced tags; CE/OpenCost tag filters |
| Reporting & analytics | Weak | Single L30D snapshot — v1.92 trends/budgets |
| Data ingestion / FOCUS | Absent | v1.93 thin adapter |
| Anomaly / chargeback | Absent | v1.94 lightweight hooks + export |
| Rate optimization | Out of scope | External FinOps tools |

Planning labels **v1.90–v1.94** continue the paved-roads numbering on the 2.x line and are
**not** engine tags. Sequence after [platform adoption / DX metrics (v1.85)](#v185--golden-path-adoption-and-dx-metrics)
so showback can reuse the same trend store shape.

### v1.90 — Allocation foundations (tag governance)

*Planning label: v1.90 (roadmap numbering only).*

**Problem:** Cost actuals depend on owner/service tags, but golden paths only *recommend*
them — allocation fails silently (`tag_coverage` warn).

**Approach:**

- Harden terraform/app/helm standards: required cost-allocation tags (`owner`, `service`,
  `environment`, `cost-center` or org-configured keys)
- OPA/Checkov rules that fail generate when required tags are missing
- Config: `portal.cost_allocation.tag_keys` so tag names are org-owned
- Scorecard: fail (not warn) when a cost reader is configured and tags are incomplete

**Done when:** Default terraform and app-service generates fail gates without allocation tags;
[`docs/finops.md`](finops.md) explains mapping to Cost Explorer / OpenCost filters.

**Status:** Shipped on `main` (v1.90 tag governance — Checkov/OPA gates, `portal.cost_allocation.tag_keys`, scorecard fail).

### v1.91 — Estimate and cost policy at plan time

*Planning label: v1.91 (roadmap numbering only).*

**Problem:** Infracost is skip-friendly; hard caps are per-blueprint only; no shared policy
floor.

**Approach:**

- Platform floor in `repave.config.yaml` `gates.infracost` (require when terraform gates are
  present; org `max_monthly_usd` default)
- Surface estimate delta vs previous pin on upgrade/import previews
- Persist estimate summary into audit `extra` for outcome correlation
- Cost annotation on governed PR body checklist (`pull_requests.evidence_checklist`)

**Done when:** An org can require Infracost plus a default monthly cap without editing every
blueprint; estimate appears in audit and PR evidence.

**Status:** Shipped on `main` (v1.91 estimate policy — `gates.infracost` floor, audit/PR
evidence, upgrade/import cost delta).

**Depends on:** [cost visibility](#cost-visibility) (shipped).

### v1.92 — Showback: trends and budgets

*Planning label: v1.92 (roadmap numbering only).*

**Problem:** Catalog shows a single L30D number — no budget, no trend, no platform rollup.

**Approach:**

- Cost snapshot store (JSONL + SQL) of per-entity actuals over time (mirror adoption metrics
  snapshot patterns)
- Entity budgets in config or catalog metadata (`monthly_budget_usd`)
- Portal: sparkline + budget vs actual on service detail; `/platform/finops` admin rollup
- Prometheus gauges with cardinality-safe aggregate labels only

**Done when:** An admin sees fleet cost vs budget rollup; entity detail shows trend vs budget
without external BI.

**Status:** Not started.

**Depends on:** v1.90; [v1.85 adoption/DX metrics](#v185--golden-path-adoption-and-dx-metrics)
snapshot patterns.

### v1.93 — Thin FOCUS ingest

*Planning label: v1.93 (roadmap numbering only).*

**Problem:** Multi-cloud actuals stay vendor-shaped; adopters cannot feed a normalized billing
export into showback.

**Approach:**

- New reader `portal.cost_reader: focus` for a FOCUS-shaped JSON/Parquet path or HTTPS export
  (supported column subset documented in [`docs/finops.md`](finops.md))
- Map FOCUS rows → existing `CostActualsSummary` (+ rollup dimensions)
- Ingest FOCUS *produced elsewhere* (cloud FOCUS export or converter); repave does not run
  full CUR → FOCUS ETL

**Done when:** A FOCUS sample fixture drives entity actuals and platform rollup in tests; ops
doc lists the supported column subset.

**Status:** Not started.

**Depends on:** v1.92.

### v1.94 — Chargeback export and anomaly hooks

*Planning label: v1.94 (roadmap numbering only).*

**Problem:** Finance needs exports; ops needs “spend jumped” signals without a full anomaly
product.

**Approach:**

- `GET /api/v2/platform/finops/export` (CSV/JSON) of owner × service × period × cost —
  chargeback handoff, not invoicing
- Simple anomaly: WoW / MoM % threshold on snapshot series → audit event + optional
  notification webhook
- Explicit non-goals: RI/SP purchase, invoice reconciliation, commitment discount optimization

**Done when:** Export uses FOCUS-friendly column names where possible; anomaly fires a
notification in a unit test with synthetic spikes.

**Status:** Not started.

**Depends on:** v1.92; optionally v1.93.

---

## State custody and the resource graph (v2.x)

**Status:** Phases 0–3 shipped on `main`. Phase 4 **no-go** recorded
([`state-graph-phase4-review.md`](state-graph-phase4-review.md)). Shared-deploy Helm knobs
and plan-JSON config edges on the transaction write path shipped; store defaults stay off.
Next: security sign-off, treadmill owner, PITR drill — not Phase 4 code.

**Design:** [ADR 004](adr/004-state-custody-and-the-resource-graph.md) ·
**Build vs buy:** [ADR 005](adr/005-state-graph-build-vs-buy.md) ·
**Operator guide:** [`docs/state-graph.md`](state-graph.md) ·
**Exec memo:** [`docs/state-graph-exec-memo.md`](state-graph-exec-memo.md) ·
**Phase 4 gate:** [`docs/state-graph-phase4-review.md`](state-graph-phase4-review.md)

Repave could certify that a repository was conformant and could not say what it had built:
no inventory, no blast radius, no infrastructure drift. Holding the state is what makes
those answers possible, and it is the only way policy becomes preventative at apply time
rather than descriptive at render time.

The store is **off by default**. With no `state_store` block, behavior is byte-identical to
before, and `repave-tf state export` returns plain `.tfstate` at any time, so adopting it
does not trap an estate.

| Phase | Status | What it delivers |
| ----- | ------ | ---------------- |
| 0 — foundations | Shipped | `tofu` preferred over `terraform`, versioned migration runner, `repave-cli` package, frozen `/api/state/v1` |
| 1 — authoritative store | Shipped | Terraform `http` backend, byte-exact blobs, serial/lineage guards, whole-state locking, reversible import/export |
| 2 — normalization and graph | Shipped | Resources, instances, edges; inventory, blast radius, drift, timeline, Infracost join |
| 3 — transactions | Shipped | `repave-tf tf plan\|apply`, optimistic commit-time conflict detection with `409`, **gate-blocked commit** |
| 4 — parallel execution | **Gated / no-go** | Decision recorded 2026-08-06 — [go/no-go review](state-graph-phase4-review.md); revisit when entry conditions 1–3 hold |

Phase 3 is the differentiator: a commit is refused when repave's own gates do not pass,
inside the transaction, before anything is applied. That needs the blueprint provenance and
gate corpus, which is why [ADR 005](adr/005-state-graph-build-vs-buy.md) concludes that the
store was worth building and parallel execution is not.

The architecture is a credential boundary. The server holds state and never holds cloud
credentials; the client holds credentials and never holds a database connection. A boundary
test fails the build if `repave_cli` imports database code.

**Still open (Phases 1–3 enablement, not Phase 4):** a named owner for the Terraform/OpenTofu
compatibility treadmill and a platform security sign-off on the persistence posture
reversal, both required before the store is enabled in any shared deployment. Transaction
commits merge plan-JSON `reference` edges; direct backend/import writes stay state-derived.

---

## Beyond v2.0.0 — autonomous estate and lifecycle control plane

**Target (v3.0.0):** At v2 every remediation still waits for a human. At fleet scale that
human is the bottleneck, and the changes they rubber-stamp are overwhelmingly mechanical
version bumps. v3 earns trust for the mechanical tier and extends repave from "repositories"
to the **lifecycle** around them — environments, deployments, and cost.

**Why this section exists here.** Not to schedule work — nothing below is committed. It exists
because the [contract freeze at v2.0.0](#v200--platform-ga) has to be designed against a known
next major. Removing `/api/v1`, promoting CRDs to `v1`, and making policy gates mandatory are all
v3 changes, so v2 has to open the deprecation windows for them; a v2 that freezes contracts
without knowing what breaks next just breaks them again later. This section is the smallest thing
that makes those v2 decisions checkable.

**Discipline for this section:**

- Entries stay one paragraph or less. Detail is earned by promotion into
  [Planned](#planned), not written speculatively here
- Nothing here starts before v2 GA. If something turns out to be needed sooner, it moves up to
  [Planned](#planned) and stops being a v3 item
- The only content that must stay accurate is the
  [breaking-change list](#breaking-at-v300), because v2 deprecation notices point at it

### Autonomous governed remediation

- **Auto-merge for low-risk remediation:** blueprints declare a risk class per change type;
  a pin bump with all gates green, no open waiver, and a healthy error budget can merge
  without review. Anything touching resources, policy, or a higher risk class still routes
  to a human
- Instant-revert runbook and a kill switch that demotes the whole fleet back to
  review-required in one config change
- **Admission webhooks** on `GoldenPathRepo` and `Blueprint` — reject invalid pins and
  missing required metadata at apply time rather than at reconcile time
- **Policy gates mandatory** on regulated blueprint families, with waivers expressed as data
  and an **enforced expiry** so no waiver becomes permanent
- **Suggested fixes on gate failure:** a proposed diff only, re-gated like any other change,
  never auto-applied outside the low-risk tier
- **Fleet SLOs:** drift MTTR p95 and percentage of repos on the current blueprint patch,
  reported in the portal and alertable

### Lifecycle control plane

- **Environments as a service** and **deployment health** — **promoted** into
  [environment lifecycle and deployment awareness](#environment-lifecycle-and-deployment-awareness)
  on the v2.x line ([ADR 003](adr/003-environment-lifecycle-and-live-state.md)); only the
  autonomous tier below stays v3
- **Graph-scoped planning:** blast-radius view and graph-scoped plan/apply for large state,
  surfaced as a registry tool rather than a repave-owned engine
- **Cost showback:** **Promoted** to [FinOps enablement (v1.90–v1.94)](#finops-enablement-v2x).
  Remaining v3 only if org-wide invoicing or a full billing warehouse is required beyond the
  hybrid enablement path ([`docs/finops.md`](finops.md))
- Optional promotions from the parking lot: **multi-tenant** config namespacing and an **OCI
  blueprint registry**

### Conversational and governed AI generation

**Status:** **Not started — v3.0.0** (moved from v2.1+; ships with the next major, not as a
v2.x minor).

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
- Preferred flow is **intent → validated blueprint inputs → the existing deterministic
  pipeline**, with the user confirming the resolved inputs before generate; free-form
  artifact drafting is the narrow fallback, not the default
- Retrieval over the in-repo standards, policy packs, and blueprint docs with **citations
  required** on every answer, filtered by the caller's role so chat cannot surface what the
  portal would deny
- A **service registry** describing what the assistant may read and call — knowledge corpora
  paths and read-only tools (fleet state, drift, gate history, cost summary) — so capabilities
  are configuration rather than hardcoded integrations
- Record provenance (v1.14) and an audit entry (v1.30) for every AI-assisted
  generation — model id, prompt hash, confirmed inputs, and gate results — and explain which
  gate/policy blocked an output when it fails; the PR body carries the same footer
- Guardrails for prompt injection, secret leakage, cost/rate limits, and
  reproducibility
- **Hard-blocked:** AI evaluating gate or policy outcomes, and autonomous merge to a
  protected branch

**Dependencies:** v2 contract freeze and shipped governance plumbing (gates, provenance,
audit, OPA opt-in); v3 **mandatory policy** tier for regulated families before autonomous
merge and conversational publish share a trust model.

**Why v3:** conversational generation and low-risk auto-merge both need the same bar —
gated output, audit trail, and policy enforcement at estate scale — so they ship together on
the v3 major rather than as v2.x follow-ons.

**Done when:** A user can describe intent conversationally and only receive artifacts
that passed every configured gate and policy, with full provenance and audit trail.

### Breaking at v3.0.0

| Change | Migration |
| --- | --- |
| CRDs promoted to `repave.dev/v1`; `v1alpha1` removed | One-way upgrade job, deprecation announced at v2 |
| Policy gates cannot be disabled on regulated blueprint families | Documented waiver process plus a blueprint pin bump |
| `/api/v1` removed | Sunset announced with the v2 `/api/v2` freeze — see [`docs/api-v1-migration.md`](api-v1-migration.md) (1 Aug 2027) |
| Blueprint schema v2 | `repave migrate-blueprint` CLI; deprecation window opens during v2.x |

**Done when:**

1. Low-risk auto-merge runs in a test organization with a demonstrated revert.
2. The fleet SLO dashboard holds green for a sustained window in production.
3. A graph-scoped plan is demonstrated for one large state boundary.
4. `/api/v1` is removed and every known integrator has migrated.
5. Conversational and form paths produce byte-identical gated output for the same blueprint
   and inputs — see [conversational governed AI](#conversational-and-governed-ai-generation).

---

## Parking lot

Ideas not yet scheduled for pre-v2 work — promote into [Planned](#planned) when
there is an owner and a target release. Two of these (**multi-tenant repave** and the
**private blueprint registry**) are named as optional promotions in
[beyond v2.0.0](#beyond-v200--autonomous-estate-and-lifecycle-control-plane); they stay here
until someone owns them, since a v3 mention is not a commitment.

- **Portal white-label** — custom logo URL and accent color override via config
  (deferred from v1.18 Phase 5; target v2 theming)
- **SAML 2.0 IdP support** — enterprise IdPs that prefer SAML over OIDC
- **Auth proxy deployment** — oauth2-proxy / IdP sidecar in front of API/portal as
  an alternative to in-app OIDC
- **Standards diff in portal** — side-by-side standard/policy changes between
  blueprint versions before generate (see [`portal-design.md`](portal-design.md)
  Phase 5)
- **Private blueprint registry** — pull blueprint packs from git tag or OCI artifact
  (beyond local fork paths in v1.28)
- **Multi-tenant repave** — org-scoped config, standards, output roots, RBAC
- **Auth0 FGA / fine-grained authorization** — relationship checks on catalog,
  generate, and environment actions (Auth0 FGA or OpenFGA), wrapping today's
  `require_role` coarse RBAC; does **not** block day-1 Auth0 portal login
- **Catalog automation** — regenerate `provider-catalog.json` on provider release
  webhook or scheduled workflow
- **Real resource scaffolds** — optional blueprint mode that emits provider resources
  instead of `null_resource` placeholders (per cloud/resource type)
- **License/policy pack** — optional LICENSE and compliance metadata generation
  (revisit v1.5 license UI with standards-driven templates)
- **Chat-platform parity** — Slack/Teams bot over the same governed generation flow as the
  v3 portal assistant, if portal chat proves out

---

## Release mechanics

Releases follow [Conventional Commits](https://www.conventionalcommits.org/) on
`main` via python-semantic-release. See [README § Releases](../README.md#releases)
and [`docs/releases.md`](releases.md#roadmap-milestones-and-engine-semver).

**Roadmap ↔ semver:** major roadmap themes map to engine **major** versions. **v2.0.0
Platform GA** (contract freeze) → **`v2.0.0` tag** via `feat!:` / `BREAKING CHANGE:`.
v2.x minors ship stabilization and lifecycle follow-ons (environment vending, platform
console, fleet ops). **v3.0.0** → **`v3.0.0` tag** when breaking removals land and v3
themes (autonomous remediation, mandatory policy, [conversational governed AI](#conversational-and-governed-ai-generation)) ship.

Release automation updates **Current release** above and doc version pointers — feature
PRs must not hand-edit them. Between milestones, `feat:` → minor and `fix:` → patch on
the current major line.
