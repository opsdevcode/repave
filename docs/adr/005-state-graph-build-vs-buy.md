# ADR 005: State graph — build vs buy

**Status:** Accepted — build Phases 1 through 3, buy or skip Phase 4.
  Phase 4 / Stategraph revisit is a **v4.0.0** roadmap theme
  ([beyond v3.0.0](../roadmap.md#beyond-v300--stategraph-and-graph-scoped-execution)).
**Date:** 2026-08-04
**Scope:** the decision behind [ADR 004](004-state-custody-and-the-resource-graph.md);
no code of its own.
**Related:** [`docs/state-graph-phase4-review.md`](../state-graph-phase4-review.md),
[`docs/state-graph-exec-memo.md`](../state-graph-exec-memo.md) (one-page summary),
[`docs/roadmap.md`](../roadmap.md#beyond-v300--stategraph-and-graph-scoped-execution)

## Context

[ADR 004](004-state-custody-and-the-resource-graph.md) makes repave the authoritative
custodian of Terraform state and builds a queryable resource graph on top of it. That is a
large, permanent commitment in a category where a vendor already exists: Stategraph sells
state-as-a-database with graph-aware execution, resource-level conflict detection, and
queryable infrastructure.

This ADR records why repave built Phases 1 through 3 anyway, and why the same reasoning
does not extend to Phase 4. It is deliberately written to be uncomfortable, because the
cost case for buying is strong and the honest answer is that it wins on most axes.

## Decision

**Build Phases 1 through 3. Do not build Phase 4 on the v2/v3 line.** Schedule any
Stategraph buy or Phase 4 build revisit as the **v4.0.0** theme
([roadmap](../roadmap.md#beyond-v300--stategraph-and-graph-scoped-execution)). Revisit
Phase 4 only through the [go/no-go gate](../state-graph-phase4-review.md), whose default
is no-go, and price buying against it at that point rather than now.

## The case for buying, stated at full strength

**Cost asymmetry.** Phases 1 through 3 are roughly 20 to 32 engineer-weeks. Phase 4 is
realistically 6 to 12 months of a senior engineer who enjoys distributed-systems
correctness work. Call the whole thing 1.5 to 3 engineer-years to parity, plus a standing
0.5 to 1 FTE forever for the version treadmill and tier-0 on-call. Stategraph is
$11,988/yr Starter, $17,988/yr Professional, $25k/yr Enterprise, with volume packs at
$1.20 to $1.80 per billable unit past 10,000 included; their own worked example is $31k/yr
at Professional and 25,000 BIUs. **The build costs roughly an order of magnitude more than
the buy, every year, forever.** No amount of enthusiasm changes that arithmetic.

**Differentiation.** Repave's moat is governed golden paths — blueprints, gates,
provenance, fleet upgrade campaigns, the operator. State-as-a-database is undifferentiated
heavy lifting for repave and the entire company for Stategraph. Their whole roadmap
velocity goes where repave can spare a fraction of one engineer.

**Risk transfer.** A state-corruption bug is an outage of someone else's production
infrastructure. Buying moves that liability to a vendor with a contract and an SLA. Building
keeps it, and repave's blast radius is every repository it governs.

**Legal.** Buying sidesteps the BUSL question entirely, because the vendor owns that
exposure. Building means being careful about Terraform 1.6+ forever (see below).

**Bounded lock-in.** `stategraph states export` returns plain `.tfstate`, so the downside
of adopting is capped at a migration, not a rewrite.

## Why build anyway

Three reasons, in descending order of confidence.

### 1. The gate-blocked transaction cannot be bought

Phase 3's actual product is not conflict detection; that is table stakes and Stategraph
does it better. It is that **a commit is refused when repave's own gates do not pass**. That
requires the blueprint provenance, the gate corpus, and the golden-path definitions that
only exist inside repave. An external state vendor can tell you two applies collided. It
cannot tell you an apply violates the golden path the repository was generated from,
because it has never seen the blueprint.

Buying the store and keeping the gates means the enforcement point moves outside the
transaction, which turns policy back into advice. That is the capability repave is for.

### 2. Custody was already required, independently

Phases 1 and 2 are not speculative infrastructure for Phase 3. Repave could describe a
repository as conformant and could not say what it built: no inventory, no blast radius, no
infrastructure drift. Those are answers the product owed regardless of who stores the state,
and the cheapest way to get them is to hold the state. Roughly two-thirds of the build cost
buys capability that would have been needed anyway.

### 3. Vendor maturity is the strongest honest argument on this side

Stategraph is a very young, closed-source, effectively single-maintainer company — releases
repository created January 2026, one contributor. Making it the tier-0 dependency for the
custody of customers' infrastructure state is a real risk, and the bounded lock-in above
mitigates the exit but not an outage or an abandonment. This argument is genuine, and it is
also the one most likely to expire: it gets weaker every quarter they survive. It should not
be reused as a reason to avoid revisiting the decision.

## Why the same reasoning stops at Phase 4

Every reason above is about governance, and none of them are about parallelism.

- Phase 4 adds no gate-blocking capability. It makes applies faster.
- It is not required for any answer repave already owes.
- Its failure mode is corrupt or destroyed infrastructure from a partitioner that split
  two resources that were not actually independent.
- Its cost is the majority of the total build, and it carries the permanent graph-semantics
  version treadmill on top of the state-format one.

That inverts the calculus completely: highest cost, highest risk, least differentiation.
If parallel apply becomes necessary, splitting configurations into smaller states gets most
of the benefit with a mechanism Terraform already supports, and buying gets the rest without
owning the correctness problem. The [go/no-go gate](../state-graph-phase4-review.md)
enforces this by defaulting to no.

## Consequences

**Accepted.** Repave owns state custody, a tier-0 durability obligation, and a permanent
compatibility treadmill against Terraform/OpenTofu state format and plan JSON. That
obligation needs a named owner, PITR, corruption detection, and a rehearsed restore
extending [`docs/operations/postgres-backup-restore.md`](../operations/postgres-backup-restore.md).

**Accepted.** ADR 004 reverses repave's no-persist posture for state and plan JSON. The
mitigations — envelope encryption at rest, provider-schema-driven redaction of the
normalized attributes — are in ADR 004 and are load-bearing, not decoration.

**Accepted.** OpenTofu (MPL-2.0) is the default binary, with Terraform as a fallback the
operator selects. Terraform 1.6+ is BUSL, and its Additional Use Grant prohibits offering
it to third parties on a hosted or embedded basis in a paid product that significantly
overlaps HashiCorp's paid versions. State storage plus remote runs plus policy plus cost
plus RBAC is a description of Terraform Cloud, so if repave is ever sold, OpenTofu is the
defensible choice. `hashicorp/hcl` remained MPL-2.0 and is safe either way.

**Rejected consequence.** This ADR does not claim building is cheaper. It is not. It claims
the expensive part buys a capability that cannot be purchased, and it stops before the part
that does not.

## Revisit when

- The **v4.0.0** Stategraph theme is promoted into Planned (after v3 GA and Phases 1–3
  enablement), or the Phase 4 gate is convened for any reason.
- Stategraph or an equivalent ships blueprint-aware policy hooks that could enforce
  repave's gates inside their transaction. That would remove reason 1, which is the load
  bearing one.
- The standing maintenance cost exceeds 1 FTE, or state custody causes a production
  incident. Either is evidence the estimate was wrong.
