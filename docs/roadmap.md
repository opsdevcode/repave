# repave roadmap

Planning document for repave evolution. The [README](../README.md) keeps a
one-line summary per release; this file holds open work, the path overview, and
major-boundary themes. Full shipped writeups live in
[`docs/roadmap-archive.md`](roadmap-archive.md).

**Current release:** v3.60.0  

**In progress:** conversational assistant (read-only fleet/drift/audit tools)

HTML is the hosted workbench; Backstage is the catalog IDP
([`docs/ui-surfaces.md`](ui-surfaces.md), [ADR 011](adr/011-hosted-backstage-idp.md)).
Mandatory policy on regulated families shipped.
Service catalog env/`enabled: true` defaults maturity + initiatives paths.
Public landing shipped in 3.1.0. Identity
([ADR 009](adr/009-v3-product-identity.md)): **repave** + platform-layer mark.
Fine-grained Auth0 FGA stays in the [parking lot](#parking-lot) until ADR 010+.
v3 themes land on `main` ([ADR 008](adr/008-v3-branching-release-and-testing.md)
superseded, [ADR 007](adr/007-v3-multi-repo-decomposition.md),
[`docs/v3-development.md`](v3-development.md)). Stategraph / graph-scoped
execution under [beyond v3.0.0](#beyond-v300--stategraph-and-graph-scoped-execution).

**Shipped on `main` (recent):**
**Policy pack side-by-side**
(Checkov/OPA/Azure/ansible-lint pin diffs on generate and upgrade, matching standards);
**Operator Kubernetes stack**
(controller-runtime 0.24.1 / k8s.io 0.36.3 / envtest 1.36);
**Generate catalog handoff**
(result page **View in catalog** when `portal.backstage_url` is set);
**CI security scanning**
(CodeQL, Trivy on publish, gosec/govulncheck, yarn audit, Dependabot, dependency review);
**Standards diff side-by-side**
(blueprint form pinned vs HEAD);
**Catalog closeout**
(auto slug/k8s id, GitHub org discovery, guest identity, TechDocs addons, lineage
View source, expanded HTML catalog preview, Scaffolder catalog fields, ClusterRole
opt-in, `catalog_domain`, conformance manifest guard);
**Catalog depth**
(GitHub slug/source-location, consumesApis/subcomponentOf/tags/links,
Helm + app-service Scaffolder, Domain `demo`, in-cluster Kubernetes Role);
**Catalog org and Kubernetes**
(Group/User cards, Kubernetes tab, `catalog_kubernetes_id` /
`catalog_kubernetes_namespace` on generate);
**Catalog graph, search, API docs, and import**
(Backstage plugins + `catalog_depends_on` / `catalog_provides_apis` on generate);
**Hosted TechDocs local generator**
(`runIn: local` + pinned `mkdocs-techdocs-core` in the Backstage image; no DinD);
**Catalog TechDocs**
(entity Docs tab; `tf-aws-demo` + `techdocs-ref` when generated repos have `docs/`);
**One product chrome**
(HTML **Golden paths** + Backstage **Catalog**; night-ops theme and shared top
bar; same-host `/idp` `app.baseUrl`; no iframe);
**UI split by job**
(HTML workbench + Backstage catalog/lineage/Scaffolder; plugin clones removed;
[`docs/ui-surfaces.md`](ui-surfaces.md));
**OCI blueprint pack pull**
(`blueprint_packs.sources[]` `oci://` + tag/digest via `oras pull`);
**Azure/GCP component stubs**
(`azurerm_*` / `google_*` for database, bucket, and queue; no `null_resource`);
**HTML portal pages restored for local-first**
(nav, generate, upgrade, verify, import, platform, runs, sandbox, and results
are the hosted workbench; Backstage is catalog-only);
**HTML landing and signup stay**
(public splash when auth is on; Sign in → `/auth/login`, Create account → `/signup`);
**HTML catalog and library pages restored**
(`GET /` and `/library` stay real pages);
**Real RDS/S3/SQS component stubs** ([ADR 013](adr/013-component-self-service-vending.md));
**Service catalog Helm default-on**;
**Hosted Backstage generate form** (`/generate` → `POST /api/v2/generate`);
**Hosted Backstage GHCR image** (`ghcr.io/opsdevcode/repave-backstage` on `main`/tags);
**Hosted Backstage chart-smoke** (kind boots the image);
**Hosted Backstage Phases 1–3** (app, parity plugins, HTML sunset + ingress split);
**Hosted Backstage Phase 2** (My services, sandbox, runs, upgrade preview);
**Hosted Backstage fleet page** (`/fleet` → `/api/v2/fleet`);
**Hosted Backstage import page** (`/import` → `/api/v2/imports/plan`);
**Hosted Backstage verify + estate pages** (`/verify`, `/estate`);
**Hosted Backstage platform pages** (`/adoption`, `/activity`, `/maturity`);
**Hosted Backstage platform ops** (`/compliance`, `/value-stream`, `/feedback`, `/finops`);
**Hosted Backstage batch import** (`/import/batch`);
**Hosted Backstage org scan** (`/import/batch` → `/api/v2/github/org-scan`);
**Hosted Backstage roadmap evidence** (`/roadmap` → `/api/v2/platform/roadmap-evidence`);
**Hosted Backstage initiative writes** (`/maturity` create/edit/deactivate);
**Hosted Backstage environment reclaim** (`/reclaim` → `/api/v2/environments/reclaim`);
**Hosted Backstage add component** (`/add` → `/api/v2/components/plan`);
**Hosted Backstage feedback submit** (`/feedback` → `POST /api/v2/platform/feedback`);
**Hosted Backstage run replay** (`/runs` → `POST /api/v2/runs/{id}/replay`);
**Hosted Backstage default-on** (owner: Eric Skaggs; kind/smoke stay off);
**Forked blueprint packs** (local extra catalog roots);
**API contract path** (Spectral + oasdiff);
**Database migration path** (destructive DDL policy, [ADR 012](adr/012-destructive-ddl-policy.md));
**Component self-service vending** (`POST /api/v2/components/vend`, [ADR 013](adr/013-component-self-service-vending.md));
**Hosted Backstage component vend** (`/vend` → `/api/v2/components/vend`);
**Component TTL reclaim** (`POST /api/v2/components/reclaim`, [ADR 013](adr/013-component-self-service-vending.md));
**Hosted Backstage component reclaim** (`/reclaim` → `/api/v2/components/reclaim`);
**Kind-specific component blueprints** (`terraform-component-database` / `-bucket` / `-queue`);
**Git URL blueprint pack fetch** (`blueprint_packs` url + ref);
**Hosted Backstage ops / standards / campaigns** (`/ops`, `/standards`, `/campaigns`);
**Hosted Backstage builder pages** (`/generate`, `/bundles`, `/library`, `/teams`, `/services`, `/run-console`);
**GitHub auto-merge** for Allowed mechanical pin bumps
([runbook](operations/auto-merge-revert.md));
**Mandatory policy** on regulated families
([runbook](operations/mandatory-policy.md));
**Service catalog maturity** ([ADR 006](adr/006-service-catalog-and-maturity.md),
[`docs/service-catalog.md`](service-catalog.md));
**mass GitHub org import** ([`docs/import.md`](import.md));
**FinOps enablement** (tags → estimate policy → showback → FOCUS → chargeback —
[`docs/finops.md`](finops.md));
**Converge brand** + portal white-label ([`docs/brand/`](brand/README.md));
**state custody Phases 0–3** (store off by default —
[`docs/state-graph.md`](state-graph.md)).
Full history: [`roadmap-archive.md`](roadmap-archive.md).

**Planning horizon:** v2.x stabilization and enablement →
[beyond v2.0.0](#beyond-v200--autonomous-estate-and-lifecycle-control-plane) (v3) →
[beyond v3.0.0](#beyond-v300--stategraph-and-graph-scoped-execution) (v4 Stategraph).

Operator GA scope: [`operator-ga.md`](operator-ga.md).

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
- When work ships on `main`, move the full writeup to
  [`roadmap-archive.md`](roadmap-archive.md), leave a one-line status in the
  [theme table](#path-to-v200) / [Shipped index](#shipped), and keep **Shipped on `main`**
  in the header to a short rolling list (not a dump). Do **not** leave
  `**Status:** Shipped` under [Planned](#planned).
- Keep speculative ideas in [Parking lot](#parking-lot) until there is a concrete
  next step.
- Use [Path to v2.0.0](#path-to-v200) for the big-picture sequence; historical detail is in
  the [archive](roadmap-archive.md).
- [Beyond v2.0.0](#beyond-v200--autonomous-estate-and-lifecycle-control-plane) holds the
  **v3** major theme — a boundary marker, not a backlog. Entries there stay
  directional until they are promoted into [Planned](#planned) with a real
  problem/approach/done-when, and nothing lands from that section before v2 GA.
- [Beyond v3.0.0](#beyond-v300--stategraph-and-graph-scoped-execution) holds the **v4**
  Stategraph / graph-scoped execution theme the same way — directional until promoted;
  nothing starts there before v3 GA and the Phase 1–3 enablement gates.
- **Sunset / removal is product work.** Removing a capability needs a roadmap entry or
  parking-lot note, a deprecation window when integrators depend on it, and the same
  problem/approach/done-when shape as features.
- Portal **visual and layout** planning: [`portal-design.md`](portal-design.md).
- Operator **local development and testing**: [`operator-local-dev.md`](operator-local-dev.md).
- Operator **CRD and controller standards**: [`operator-standards.md`](operator-standards.md).

---

## Path to v2.0.0

v2.0.0 is the **mature platform** milestone: repave governs a fleet of generated
repositories end-to-end — bootstrap, standards, policy, upgrade, and drift
remediation — not just one-shot module creation. That milestone shipped; the ladder
below is the sequence that got there and what comes next.

```text
v3.60.0 today      platform GA line on main (contract freeze + DR shipped)
  │
  ├─ (history)     golden paths, operator, portal, SSO, day-2, OPA, observability
  ├─ (history)     estate control, k8s deploy, durability, service split, supply chain
  ├─ (history)     verify / import / add, doctor, cost awareness, portal surfaces
  │
  v2.0.0           platform GA       contract freeze + DR → engine tag v2.0.0
  │
  v2.1+            environments      deployment status → live plan → vending (ADR 003)
  ├─ paved roads   GitOps, deploy pipeline, SLOs, repave add, runtimes, bundles
  ├─ platform product  adoption/DX → feedback → stakeholders → guided forms → evidence
  ├─ FinOps        tags → estimate policy → showback → FOCUS → chargeback
  ├─ state custody Phases 0–3 shipped (off by default); Phase 4 → v4
  │
  v3.0.0           autonomous        low-risk auto-merge, mandatory policy, lifecycle AI
  │
  v4.0.0           Stategraph        graph-scoped plan/apply (buy preferred)
```

| Theme | Status | Outcome |
| --- | --- | --- |
| **Governance depth** | Shipped | Standards, Checkov, secrets scan, provenance, OPA/conftest |
| **Multi-artifact golden paths** | Shipped | Terraform, Ansible, Helm, app-service, observability paths |
| **Self-healing / estate control** | Shipped | Operator, fleet registry, remote inventory, campaigns |
| **Access and multi-user** | Shipped | OIDC SSO, roles; Auth0 portal runbook |
| **In-cluster / day-2** | Shipped | Helm charts, HPA/PDB, monitoring, runbooks |
| **Hosted durability** | Shipped | SQL store, async queue, DLQ/replay, `/runs` |
| **Service decomposition** | Shipped (portal/API Deployment split deferred) | portal/worker/corpus; operator on `/api/v2` |
| **Supply chain** | Shipped | GitHub App auth, governed PR, digest pins |
| **Developer portal surfaces** | Shipped | Catalog, scorecards, platform console, live governance |
| **Cost awareness + FinOps** | Shipped | Infracost, actuals, tags, showback, FOCUS, chargeback |
| **Brownfield reach** | Shipped | `verify`, `import` (+ org scan), `repave add`, bundles |
| **v2 contract freeze + DR** | Shipped | `/api/v2`, config v1, provenance-on-publish, Postgres DR |
| **v2.1+ environment lifecycle** | Shipped | Deployment status, live plan, vending/reclaim ([ADR 003](adr/003-environment-lifecycle-and-live-state.md)) |
| **Developer paved roads** | Shipped | [archive](roadmap-archive.md#developer-paved-roads-v2x) |
| **Platform as a product** | Shipped | [archive](roadmap-archive.md#platform-as-a-product-v2x) |
| **Service catalog maturity** | Shipped | [ADR 006](adr/006-service-catalog-and-maturity.md), [`service-catalog.md`](service-catalog.md) |
| **State custody / resource graph** | Phases 0–3 shipped; Phase 4 → **v4** | Enablement gates still open ([below](#state-custody-and-the-resource-graph-v2x)) |
| **Hosted Backstage IDP** | Catalog + chrome | Owner Eric Skaggs; HTML is the workbench; Backstage is catalog + lineage + Scaffolder with night-ops chrome ([ADR 011](adr/011-hosted-backstage-idp.md), [`ui-surfaces.md`](ui-surfaces.md)) |
| **Forked blueprint packs** | Shipped | Local roots + git URL fetch + OCI `oras pull` (read-only cache) |
| **API contract path** | Shipped | OpenAPI/AsyncAPI repo with Spectral + oasdiff gates |
| **Database migration path** | Shipped | Alembic/Flyway/Atlas + destructive-DDL policy ([ADR 012](adr/012-destructive-ddl-policy.md)) |
| **Component self-service vending** | Shipped | Vend, reclaim, Backstage UI, kind-specific AWS/Azure/GCP modules ([ADR 013](adr/013-component-self-service-vending.md)) |
| **v3.0.0** | — | Autonomous remediation, mandatory policy, conversational governed AI |
| **v4.0.0** | — | Stategraph / graph-scoped plan/apply |

---

## Planned

Open work only. Shipped theme writeups are in [`roadmap-archive.md`](roadmap-archive.md).

### Hosted Backstage IDP

**Status:** Catalog IDP closeout shipped; Backstage is maintenance + upstream bumps
(owner: Eric Skaggs;
[ADR 011](adr/011-hosted-backstage-idp.md),
[`docs/ui-surfaces.md`](ui-surfaces.md)).
Kind/smoke overlays keep the flag off. HTML is the hosted and local workbench
(**Golden paths**). Backstage is catalog ingest, lineage, My services, and
optional Scaffolder (**Catalog**), with the night-ops top bar and TechDocs on
the entity Docs tab, catalog graph, search, API docs, catalog import, org
(Group/User), Kubernetes, Domain, and Scaffolder Terraform/Helm/app-service.
Generate emits GitHub slug, tags, links, and remaining relations. Hosted
image uses an in-cluster Kubernetes locator plus a namespace Role.
Hosted image generates Docs with `runIn: local` (no Docker-in-Docker).
Plugin clones of generate/ops/platform pages are removed.
Hosted overlay keeps `portal.html: true`
and sends `/idp` to Backstage (`app.baseUrl` = `https://<host>/idp`). Do not
iframe `/idp`. Generate result **View in catalog** links to the entity page when
`portal.backstage_url` is set.

**Problem:** Cloning every `/api/v2` page into Backstage created a second full
portal without the night-ops look.

**Approach:** Grow the HTML workbench. Keep Backstage for catalog, ownership,
and `repave:generate`. Shared nav + night-ops tokens. Handoff via
`portal.backstage_url` and `repave.portalBaseUrl`. CLI remains the offline path.

**Done when:** one growing UI (HTML) and a catalog IDP that does not mirror it —
**met**. Apply stays CLI and operator. Chart-smoke and GHCR publish stay.

---

### Forked and remote blueprint packs

*Planning label: v1.29 (roadmap numbering only).*

**Problem:** Blueprints live only under `blueprints/` in the repave repo; enterprises
want to fork repave and add paths, or pull read-only blueprint packs from git.

**Approach:**

- `repave.config.yaml` `blueprints_root` or `blueprint_sources[]` (local paths)
- `blueprint_packs.sources[]` with `url` + `ref` (shallow clone into
  `data/blueprint-packs`; reuse cache until the folder is deleted)
- `oci://registry/repository` + tag or `sha256:` digest (`oras pull`)
- CLI/API `--blueprint` accepts absolute path or `file://` under configured roots
- Document fork workflow: copy repave, add `blueprints/my-org-*`, pin org standards

**Dependencies:** Blueprint loader and schema validation (stable since v1.0).

**Done when:** A forked repave repo loads an additional blueprint from its own
tree without patching engine code — **met**. Git URL and OCI packs also load
as extra catalog roots.

**Status:** Shipped — local extra catalog roots, git URL + ref fetch, and OCI
artifact pull.

---

### API contract path

**Status:** Shipped on `main` — `api-contract-generic` plus `spectral` /
`oasdiff` gates. Git/OCI remote fetch stays parking-lot.

**Problem:** Teams keep OpenAPI and AsyncAPI documents in ad-hoc repos with no
shared lint or breaking-change gate.

**Approach:**

- New `api-contract` artifact type and `blueprints/api-contract-generic/`
- `spectral` lint (`--fail-severity=error`) and `oasdiff breaking` versus
  `baseline/` (OpenAPI only; AsyncAPI skips oasdiff)
- Generated CI installs pinned Spectral and oasdiff, then `repave gates`

**Done when:** `repave generate` produces a spec repo that fails on Spectral
errors and on oasdiff breaking changes versus the baseline.

---

### Database migration path

**Status:** Shipped on `main` — `db-migration-generic` plus `migration-policy` /
`migration-rollback` ([ADR 012](adr/012-destructive-ddl-policy.md)).

**Problem:** Schema migrations live in ad-hoc repos; destructive DDL reaches
production without a recorded reason, expiry, or paired rollback.

**Approach:**

- Alembic, Flyway, or Atlas layout from one blueprint
- In-process scan of **forward** files for DROP/TRUNCATE/rename; waiver file
  with `expires_at` (fail closed)
- Rollback pairing: Alembic `downgrade`, Flyway `U*`, Atlas `*.down.sql`

**Done when:** `repave generate` produces a migration repo that fails on
unwaived destructive DDL and on a missing rollback.

---

### Component-level self-service vending

**Status:** Shipped — vend, reclaim, Backstage `/vend` + `/reclaim`, and
kind-specific blueprints (`terraform-component-database` / `-bucket` / `-queue`)
([ADR 013](adr/013-component-self-service-vending.md)). Stubs emit AWS
(`aws_db_instance` / `aws_s3_bucket` / `aws_sqs_queue`), Azure
(`azurerm_postgresql_flexible_server` / `azurerm_storage_account` /
`azurerm_servicebus_queue`), and GCP (`google_sql_database_instance` /
`google_storage_bucket` / `google_pubsub_topic`).

**Problem:** Builders request a managed database, bucket, or queue by hand or
ticket; the write never becomes gated GitOps lineage.

**Approach:**

- Same GitOps PR flow as `environment_vend` (no `terraform apply`)
- Built-in kinds `database` / `bucket` / `queue` (override via
  `component_vending.kinds`)
- Kind-specific blueprints with AWS, Azure, and GCP stub modules
- Registry + catalog entity; Backstage `/vend` for the request
- TTL reclaim via `POST /api/v2/components/reclaim` / `repave components reclaim`
  and Backstage `/reclaim`

**Done when:** a builder can request a managed component and get a reviewable
GitOps PR, same shape as environment vending — **met** for the request path.

---

### Paved-road follow-ons

Scoped enough to promote without new discovery (was deferred from the developer paved-roads
cluster — detail for shipped paved roads is in the [archive](roadmap-archive.md#developer-paved-roads-v2x)):

- **Organization blueprint packs** — local extra roots, git URL fetch, and OCI
  pull are
  [forked and remote blueprint packs](#forked-and-remote-blueprint-packs).



### State custody enablement (shared deploy)

**Status:** Phases 0–3 code shipped; store **off by default**. These enablement gates are
required before shared-deploy on and before the v4 Stategraph theme can start.

**Still open:**

- Named owner for the Terraform/OpenTofu compatibility treadmill
- Platform security sign-off on the persistence posture reversal
- PITR drill for the state store in shared deploy
  ([`state-store-enablement.md`](operations/state-store-enablement.md))

**Design / ops:** [ADR 004](adr/004-state-custody-and-the-resource-graph.md) ·
[ADR 005](adr/005-state-graph-build-vs-buy.md) ·
[`docs/state-graph.md`](state-graph.md) ·
[phase4 review](state-graph-phase4-review.md) ·
full historical writeup in the [archive](roadmap-archive.md#state-custody-and-the-resource-graph-v2x).

---

## Shipped

Index only — detail in [`roadmap-archive.md`](roadmap-archive.md).

- **Foundation → v1.18** — engine, golden paths, operator alpha, portal UX
  ([archive — Shipped](roadmap-archive.md#shipped))
- **Estate + k8s + import + add** — fleet registry, Helm deploy, GitHub App,
  `verify` / `import` / `repave add`
  ([archive](roadmap-archive.md#estate-control--fleet-registry-and-gitops-manifests-engine-v173))
- **Platform GA** — contract freeze, Postgres DR
  ([archive — v2.0.0](roadmap-archive.md#v200--platform-ga))
- **Hardening + durability + supply chain + decomposition**
  ([archive — Engine hardening](roadmap-archive.md#engine-hardening-and-tech-debt))
- **Developer paved roads** (GitOps, deploy pipeline, SLOs, add, runtimes, bundles)
  ([archive](roadmap-archive.md#developer-paved-roads-v2x))
- **Platform as a product** (adoption, feedback, stakeholders, guided forms, evidence)
  ([archive](roadmap-archive.md#platform-as-a-product-v2x))
- **FinOps enablement** (v1.90–v1.94)
  ([archive](roadmap-archive.md#finops-enablement-v2x))
- **Service catalog maturity**
  ([archive](roadmap-archive.md#service-catalog-maturity-v2x))
- **State custody Phases 0–3**
  ([archive](roadmap-archive.md#state-custody-and-the-resource-graph-v2x))

---

## State custody and the resource graph (v2.x)

**Status:** Phases 0–3 shipped on `main`. Phase 4 parallel execution remains **no-go** for
v2/v3 ([`state-graph-phase4-review.md`](state-graph-phase4-review.md)); graph-scoped
execution is the **v4.0.0** theme
([beyond v3.0.0](#beyond-v300--stategraph-and-graph-scoped-execution)). Store defaults
**off**. Enablement work is under [Planned](#state-custody-enablement-shared-deploy).

**Design:** [ADR 004](adr/004-state-custody-and-the-resource-graph.md) ·
**Build vs buy:** [ADR 005](adr/005-state-graph-build-vs-buy.md) ·
**Operator guide:** [`docs/state-graph.md`](state-graph.md) ·
**Phase 4 gate:** [`docs/state-graph-phase4-review.md`](state-graph-phase4-review.md)

| Phase | Status | What it delivers |
| ----- | ------ | ---------------- |
| 0 — foundations | Shipped | `tofu` preferred, migrations, `repave-cli`, frozen `/api/state/v1` |
| 1 — authoritative store | Shipped | Terraform `http` backend, locking, import/export |
| 2 — normalization and graph | Shipped | Inventory, blast radius, drift, timeline |
| 3 — transactions | Shipped | Gate-blocked `repave-tf` plan/apply |
| 4 — parallel execution | **Deferred to v4** | Buy preferred ([ADR 005](adr/005-state-graph-build-vs-buy.md)) |

Full problem/approach history:
[archive — state custody](roadmap-archive.md#state-custody-and-the-resource-graph-v2x).

---

## Beyond v2.0.0 — autonomous estate and lifecycle control plane

**Target (v3.0.0):** At v2 every remediation still waits for a human. At fleet scale that
human is the bottleneck, and the changes they rubber-stamp are overwhelmingly mechanical
version bumps. v3 earns trust for the mechanical tier and extends repave from "repositories"
to the **lifecycle** around them — environments, deployments, and cost.

**Why this section exists here.** Not to schedule work — nothing below is committed. It exists
because the [contract freeze at v2.0.0](roadmap-archive.md#v200--platform-ga) has to be designed against a known
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

**Where v3 work happens:** `main` is the product line (`v3.0.0+`). [ADR 008](adr/008-v3-branching-release-and-testing.md)
`next/v3` branching is superseded. See [ADR 007](adr/007-v3-multi-repo-decomposition.md)
for the multi-repo split and [`docs/v3-development.md`](v3-development.md) for the
working guide.
Identity policy ([ADR 009](adr/009-v3-product-identity.md)): display name **repave**,
new platform-layer mark, CLI/package stay `repave`. The foundation slice (risk classes,
waiver expiry, deprecation registry) lands in `repave-core` before autonomous
remediation themes.

### Autonomous governed remediation

**Status:** Plan/upgrade and the portal upgrade preview show an auto-merge
verdict. `apply-upgrade --open-pr` squash-merges when Allowed; the operator
does the same after opening a remediation PR. Kill switch and revert:
[`docs/operations/auto-merge-revert.md`](operations/auto-merge-revert.md).
Live test-org demo still optional. Mandatory policy
(`v3.mandatory_policy.enabled`) refuses `enable_policy: false` on regulated
families; waivers use `gate_id: mandatory-policy`
([runbook](operations/mandatory-policy.md)).

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
  [environment lifecycle and deployment awareness](roadmap-archive.md#environment-lifecycle-and-deployment-awareness)
  on the v2.x line ([ADR 003](adr/003-environment-lifecycle-and-live-state.md)); only the
  autonomous tier below stays v3
- **Graph-scoped planning / Stategraph** — **moved** to
  [beyond v3.0.0](#beyond-v300--stategraph-and-graph-scoped-execution) (v4.0.0); not a v3
  deliverable
- **Cost showback:** **Promoted** to [FinOps enablement (v1.90–v1.94)](roadmap-archive.md#finops-enablement-v2x).
  Remaining v3 only if org-wide invoicing or a full billing warehouse is required beyond the
  hybrid enablement path ([`docs/finops.md`](finops.md))
- Optional promotions from the parking lot: **multi-tenant** config namespacing.
  OCI blueprint pack pull shipped under
  [forked and remote blueprint packs](#forked-and-remote-blueprint-packs).

### Conversational and governed AI generation

**Status:** **Partial** — catalog intent resolve, corpus citations, optional
input-only model draft, Open-form query prefills, optional extractive FTS
(`v3.assistant.retrieval: fts`, default `memory`), cited excerpt synthesis, and
optional gated candidate files (`v3.assistant.artifacts.enabled`, default-off)
are shipped as default-off. Artifact drafts run the matched blueprint gates and
are never published. Resolve can cite fleet, pin drift, and gate history the
caller could already see (`fleet.reads` / `fleet.drift` / `audit.history`).
Guided identity JS keeps allowlisted query prefills. FTS
is adapted from [opsdevcode/relay](https://github.com/opsdevcode/relay).
Generate still uses the existing form and gates for the happy path. Autonomous
merge of assistant output is not started.

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
  portal would deny; `memory` token scoring by default, `fts` for extractive chunks
  (in-process SQLite FTS5, or Postgres when durability is PostgreSQL)
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
3. `/api/v1` is removed and every known integrator has migrated.
4. Conversational and form paths produce byte-identical gated output for the same blueprint
   and inputs — see [conversational governed AI](#conversational-and-governed-ai-generation).

---


## Beyond v3.0.0 — Stategraph and graph-scoped execution

**Target (v4.0.0):** Phases 0–3 already give custody, inventory/blast radius, and
gate-blocked transactions. v4 is where large-state **graph-scoped plan/apply** and any
revisit of Phase 4 parallel execution live — preferably by buying Stategraph (or an
equivalent) rather than building a partitioner inside repave ([ADR 005](adr/005-state-graph-build-vs-buy.md)).

**Why this section exists here.** Same discipline as
[beyond v2.0.0](#beyond-v200--autonomous-estate-and-lifecycle-control-plane): a boundary
marker so v3 does not absorb Stategraph scope by accident. Nothing below is committed
engineering until it is promoted into [Planned](#planned) with an owner after v3 GA.

**Discipline for this section:**

- Entries stay one paragraph or less until promoted into [Planned](#planned)
- Nothing here starts before v3 GA, Phases 1–3 shared-deploy enablement gates
  ([`state-store-enablement.md`](operations/state-store-enablement.md)), and a boring
  production trust window for the store
- Phase 4 build remains **no-go** until the
  [go/no-go gate](state-graph-phase4-review.md) records a later **Go**; buy and
  split-the-configuration must be priced first

### Stategraph / graph-scoped planning

- **Buy preferred:** integrate Stategraph (or equivalent) for graph-scoped plan/apply and
  resource-level conflict detection on large states, keeping repave's gate-blocked commit
  as the governance boundary ([ADR 005](adr/005-state-graph-build-vs-buy.md))
- **Blast-radius and inventory** already ship in Phases 1–3; v4 surfaces graph-scoped
  execution as a registry/platform tool, not a second state store
- **Split-the-configuration** (smaller independent states) remains the boring alternative
  that must be shown insufficient before building a partitioner
- **Build Phase 4** (graph-scoped parallel apply inside repave) only after a **Go** that
  supersedes the 2026-08-06 no-go — entry conditions, hard-problem answers, and named
  treadmill owner required ([phase4 review](state-graph-phase4-review.md))

**Dependencies:** Phases 1–3 enabled in shared deploy; security sign-off; PITR drill;
named treadmill owner; preferably two quarters with zero unexplained state divergences.

**Done when:**

1. A graph-scoped plan/apply path is demonstrated for one large state boundary (buy or
   split-config first).
2. Fleet apply prefers `repave-tf` transactions so plan-JSON config edges stay on the
   write path.
3. If Phase 4 is ever built, a recorded **Go** supersedes the no-go and the partitioner
   fails closed under plan-time indeterminacy.

---


## Parking lot

Ideas not yet scheduled — promote into [Planned](#planned) when there is an owner and a
concrete next step. **Multi-tenant repave** is named as an optional promotion in
[beyond v2.0.0](#beyond-v200--autonomous-estate-and-lifecycle-control-plane); it stays here
until someone owns it. Stategraph / graph-scoped execution is under
[beyond v3.0.0](#beyond-v300--stategraph-and-graph-scoped-execution), not here.

- **SAML 2.0 IdP support** — enterprise IdPs that prefer SAML over OIDC
- **Auth proxy deployment** — oauth2-proxy / IdP sidecar in front of API/portal as
  an alternative to in-app OIDC
- **Multi-tenant repave** — org-scoped config, standards, output roots, RBAC
- **Auth0 FGA / fine-grained authorization** — relationship checks on catalog,
  generate, and environment actions (Auth0 FGA or OpenFGA), wrapping today's
  `require_role` coarse RBAC. Lands as **ADR 010+**. Required for multi-team hosted
  My services; does **not** block local developer lab or day-1 Auth0 login
- **Catalog automation** — regenerate `provider-catalog.json` on provider release
  webhook or scheduled workflow
- **Real resource scaffolds** — optional blueprint mode that emits provider resources
  instead of `null_resource` placeholders (per cloud/resource type)
- **License/policy pack** — optional LICENSE and compliance metadata generation
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
**v4.0.0** → **`v4.0.0` tag** when the
[Stategraph / graph-scoped execution](#beyond-v300--stategraph-and-graph-scoped-execution)
theme ships (buy preferred; Phase 4 build only after go/no-go **Go**).

Release automation updates **Current release** above and doc version pointers — feature
PRs must not hand-edit them. Between milestones, `feat:` → minor and `fix:` → patch on
the current major line.

