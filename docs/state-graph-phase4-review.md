# Phase 4 go/no-go review: graph-scoped parallel execution

**Status:** gate is closed. **Decision recorded: No-go** (see [Decision record](#decision-record)).
Phase 4 is not started and must not be started until every condition on this page is met
and an owner signs a later **Go** decision that supersedes this record.

Phases 1 through 3 of [ADR 004](adr/004-state-custody-and-the-resource-graph.md) shipped
custody, a queryable resource graph, and transactions with commit-time conflict detection.
Phase 4 is different in kind, not degree. It partitions one Terraform configuration into
subgraphs and applies them concurrently, which means repave — not Terraform — becomes
responsible for deciding what is safe to run in parallel. Getting that wrong destroys
production infrastructure rather than failing a CI job.

This document is the gate. It exists so that starting Phase 4 is a deliberate, reviewed
decision with a named owner, rather than the next ticket after Phase 3.

## Entry conditions

All must hold before the review is even convened.

| # | Condition | Why |
| - | --------- | --- |
| 1 | Phases 1–3 in production for at least two quarters | Partitioning is built on the graph; the graph must be trusted first |
| 2 | Zero unexplained state divergences in that window | If custody is not already boring, do not add concurrency |
| 3 | A rehearsed, timed restore from PITR | Phase 4's failure mode is corruption; restore is the only floor |
| 4 | Graph source is plan-JSON-configuration-derived, not state-derived | State-derived edges are sufficient for blast radius and wrong for partitioning |
| 5 | A named owner for the version-skew treadmill, funded ongoing | Not a project; permanent maintenance |
| 6 | A written answer to each hard problem below | Not a plan to answer it later |

Condition 4 deserves emphasis, because it is the one most likely to be waved through.
Everything shipped so far derives edges from `depends_on` and plan references, which is
plenty for "what breaks if I touch this." Partitioning needs the configuration graph
including implicit dependencies through expression references, provider configuration,
and `depends_on` at the module level. Reusing the Phase 2 graph for Phase 4 would be
reusing a map drawn for a different purpose.

## The hard problems

None of these have cheap answers. A "we'll handle it" is not an answer; the review needs
the mechanism.

### Serial and lineage synthesis

Materializing a partial state per subgraph means fabricating a `serial` and a `lineage`
for each. Terraform refuses a write when the serial goes backwards or the lineage does not
match, so every recombination must produce a document the next `tofu` run accepts. Two
subgraphs applied concurrently produce two serial sequences that have to merge into one
monotonic sequence over a single lineage.

**What the review needs:** the merge algorithm, and the behavior when one subgraph fails
after another committed. A half-merged state is worse than no parallelism.

### Plan-time indeterminacy

`count = length(data.x.y)` means the true resource set is not knowable before the plan
runs. The graph you partition on is a prediction. A partition that is wrong is not a
performance problem; it is two concurrent applies touching the same resource.

**What the review needs:** the conservative fallback — how indeterminacy is detected, and
the proof that detection failing closed (one partition, sequential apply) is the default
rather than the exception path.

### Cross-subgraph attribute reads

Partitions that look disjoint in the configuration collapse when one reads an attribute
that only exists after the other applies. Terraform's own graph handles this by ordering;
a partitioner that has already split them cannot.

**What the review needs:** whether the partitioner is sound (never splits a real
dependency) and the evidence, not just the intent.

### Correctness cost of being wrong

Every problem above shares a failure mode: concurrent applies to resources that were not
actually independent. The outcome is corrupt state or destroyed infrastructure belonging
to someone who trusted the golden path.

**What the review needs:** the blast radius of a partitioner bug, and whether it is
recoverable without a restore.

### Version-skew treadmill

Every Terraform/OpenTofu release can move the state format, the plan JSON schema, or
provider behavior. Phases 1–3 depend on the state format and plan JSON, which is real
exposure. Phase 4 additionally depends on graph semantics, which is where upstream
changes are least documented and least announced.

**What the review needs:** the named owner from entry condition 5, and what happens to
Phase 4 when that person leaves.

## Alternatives that must be priced first

The review is not "build Phase 4 or nothing." It compares against:

1. **Do nothing.** Phase 3 already delivers the governance differentiator. Parallel apply
   is a speed feature; measure how much time it would actually save on real
   configurations before spending years on it.
2. **Split the configuration.** Smaller states applied independently give most of the
   parallelism with none of the partitioning risk, using a mechanism Terraform already
   supports. This is the boring answer and is usually correct.
3. **Buy it.** See the build-vs-buy memo. Phase 4 is the phase where the cost asymmetry
   becomes overwhelming — realistically 6 to 12 months of a senior engineer who enjoys
   distributed-systems correctness work.

Option 2 should be attempted and shown insufficient before Phase 4 is considered.

## Decision record

| Field | Value |
| ----- | ----- |
| Date | 2026-08-06 |
| Owner | platform (Eric Skaggs) |
| Entry conditions met | **No** — none of 1–6 hold (store still off by default in shared deploys; no production trust window; PITR for state store not rehearsed; plan-JSON config edges not on the write path; treadmill owner and hard-problem answers open) |
| Alternative 2 attempted | **No** — split-the-configuration not shown insufficient; buy option not priced for this estate |
| Decision | **No-go** |
| Revisit | When entry conditions **1–3** hold; conditions **4–6** remain required before any Go. Prefer measuring split-config / buy before reopening. |

### Rationale

Phases 0–3 already deliver custody, inventory/blast radius, and gate-blocked transactions.
Phase 4 only adds apply speed and makes repave responsible for partition correctness; a
partitioner bug destroys infrastructure rather than failing CI. Until the store is boring
in shared production, DR is proven, and plan-JSON configuration edges are the graph source
of truth, starting parallel execution fails the gate by design.

[ADR 005](adr/005-state-graph-build-vs-buy.md) already concludes: build Phases 1–3; do not
build Phase 4 unless this gate is passed. The default remains no-go; absence of a later
**Go** decision is still a no-go.

### Next productive work (not Phase 4)

1. Phases 1–3 shared-deploy enablement — named treadmill owner, platform security sign-off,
   Helm/`REPAVE_STATE_*` / KEK wiring, rehearsed PITR.
2. Wire plan-JSON configuration edges into graph writes (`edges_from_plan_json` is prep only
   today) — entry condition 4.
3. Only after a future **Go**: read-only partition analyzer, then concurrent apply.
