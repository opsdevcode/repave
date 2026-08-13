# repave roadmap

Planning document for repave evolution. The [README](../README.md) keeps a
one-line summary per release; this file holds open work, the path overview, and
major-boundary themes. Full shipped writeups live in
[`docs/roadmap-archive.md`](roadmap-archive.md).

**Current release:** v2.66.0  

**In progress:** fine-grained Auth0 FGA stays in the [parking lot](#parking-lot).
v3 themes under
[beyond v2.0.0](#beyond-v200--autonomous-estate-and-lifecycle-control-plane) land on
the long-lived `next/v3` branch ([ADR 008](adr/008-v3-branching-release-and-testing.md),
[ADR 007](adr/007-v3-multi-repo-decomposition.md), [`docs/v3-development.md`](v3-development.md))
and do not affect the v2.x line on `main`. Stategraph / graph-scoped execution under
[beyond v3.0.0](#beyond-v300--stategraph-and-graph-scoped-execution).

**Shipped on `main` (recent):**
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
v2.66.0 today      platform GA line on main (contract freeze + DR shipped)
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
| **v3.0.0** | — | Autonomous remediation, mandatory policy, conversational governed AI |
| **v4.0.0** | — | Stategraph / graph-scoped plan/apply |

---

## Planned

Open work only. Shipped theme writeups are in [`roadmap-archive.md`](roadmap-archive.md).

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


### Paved-road follow-ons

Scoped enough to promote without new discovery (was deferred from the developer paved-roads
cluster — detail for shipped paved roads is in the [archive](roadmap-archive.md#developer-paved-roads-v2x)):

- **API contract path** — OpenAPI/AsyncAPI specification repository with `spectral` lint and
  `oasdiff` breaking-change detection. Valuable and fully standalone, but needs two new gate
  runners and unblocks nothing else in the cluster.
- **Database migration path** — Alembic/Flyway/Atlas layout with a destructive-DDL policy and
  a rollback plan. Needs its own policy design before scoping.
- **Component-level self-service vending** — request a managed database, bucket, or queue
  through the same GitOps PR flow as `environment_vend`. This is Phase 4 of
  [environment lifecycle](roadmap-archive.md#environment-lifecycle-and-deployment-awareness)
  and warrants an ADR.
- **Organization blueprint packs** — same demand as
  [forked and remote blueprint packs](#forked-and-remote-blueprint-packs); pull ahead of the
  items above if external demand appears.



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

**Where v3 work happens:** the long-lived `next/v3` branch, versioned as `3.0.0-rc.N` and
merged back to `main` in one `feat!:` PR when the deprecation windows close — see
[ADR 008](adr/008-v3-branching-release-and-testing.md) for branching,
[ADR 007](adr/007-v3-multi-repo-decomposition.md) for the multi-repo split, and
[`docs/v3-development.md`](v3-development.md) for the working guide. The foundation slice
(risk classes, waiver expiry, deprecation registry) lands in `repave-core` before autonomous
remediation themes.

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
  [environment lifecycle and deployment awareness](roadmap-archive.md#environment-lifecycle-and-deployment-awareness)
  on the v2.x line ([ADR 003](adr/003-environment-lifecycle-and-live-state.md)); only the
  autonomous tier below stays v3
- **Graph-scoped planning / Stategraph** — **moved** to
  [beyond v3.0.0](#beyond-v300--stategraph-and-graph-scoped-execution) (v4.0.0); not a v3
  deliverable
- **Cost showback:** **Promoted** to [FinOps enablement (v1.90–v1.94)](roadmap-archive.md#finops-enablement-v2x).
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
concrete next step. Two of these (**multi-tenant repave** and the
**private blueprint registry**) are named as optional promotions in
[beyond v2.0.0](#beyond-v200--autonomous-estate-and-lifecycle-control-plane); they stay here
until someone owns them. Stategraph / graph-scoped execution is under
[beyond v3.0.0](#beyond-v300--stategraph-and-graph-scoped-execution), not here.

- **SAML 2.0 IdP support** — enterprise IdPs that prefer SAML over OIDC
- **Auth proxy deployment** — oauth2-proxy / IdP sidecar in front of API/portal as
  an alternative to in-app OIDC
- **Standards diff in portal** — side-by-side standard/policy changes between
  blueprint versions before generate (see [`portal-design.md`](portal-design.md)
  Phase 5)
- **Private blueprint registry** — pull blueprint packs from git tag or OCI artifact
  (beyond local fork paths)
- **Multi-tenant repave** — org-scoped config, standards, output roots, RBAC
- **Auth0 FGA / fine-grained authorization** — relationship checks on catalog,
  generate, and environment actions (Auth0 FGA or OpenFGA), wrapping today's
  `require_role` coarse RBAC; does **not** block day-1 Auth0 portal login
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

