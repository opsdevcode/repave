# Repave state graph: build or buy

**One page for the decision.** Full reasoning in
[ADR 005](adr/005-state-graph-build-vs-buy.md); implementation in
[ADR 004](adr/004-state-custody-and-the-resource-graph.md).

## The decision

Repave now stores Terraform state itself, holds a queryable graph of every resource it
governs, and refuses an apply whose gates do not pass. A vendor sells most of that.
We built it anyway — for the part they cannot sell — and stopped short of the part that
would have cost the most.

## What buying wins

**It is roughly ten times cheaper, every year, forever.** Building Phases 1 through 3 is
20 to 32 engineer-weeks, and full parity including parallel execution is 1.5 to 3
engineer-years plus a standing 0.5 to 1 FTE for maintenance and on-call. Stategraph is
$12k to $25k per year, with a worked example at $31k. There is no version of the
arithmetic where building is the cheaper answer.

Buying also transfers the liability. A state-corruption bug is an outage of a customer's
infrastructure, and a vendor absorbs that under a contract with an SLA. It sidesteps the
Terraform BUSL licensing question. And the exit is cheap: their export returns a plain
state file, so adopting caps the downside at a migration.

## Why we built the first three phases

**One capability cannot be purchased.** The product is not conflict detection — the vendor
does that better. It is that **a commit is refused when repave's own gates fail**, inside
the transaction, before anything is applied. That requires the blueprint provenance and
gate corpus that exist only in repave. Buy the store and the enforcement point moves
outside the transaction, which turns policy back into advice. That is the thing repave is
for.

**Two-thirds of the cost was owed regardless.** Repave could certify a repository as
conformant and could not say what it had built — no inventory, no blast radius, no
infrastructure drift. Those answers required holding the state. They are not speculative
groundwork; they were a gap in the product.

**The vendor is young.** Closed-source, effectively one maintainer, first release January
2026. Making that the tier-0 custodian of customers' state is a real risk today. It is
also the argument most likely to expire, and it should not become a reason to stop
re-examining the decision.

## Why we stopped

Parallel execution — Phase 4 — inverts every one of those reasons. It adds no governance
capability, answers no question we owe, costs more than everything else combined, and its
failure mode is destroyed production infrastructure when the partitioner splits two
resources that were not actually independent. It is gated behind a
[written go/no-go review](state-graph-phase4-review.md) whose default answer is no.

If applies ever need to be faster, splitting configurations into smaller states gets most
of the benefit using a mechanism Terraform already supports.

## What we now own

State custody is tier-0 data. That obligation is real and permanent: point-in-time
recovery, corruption detection, a rehearsed restore, and a named owner for compatibility
with every Terraform and OpenTofu release. Storing state also reverses repave's previous
no-persist posture, mitigated by envelope encryption at rest and schema-driven redaction of
sensitive attributes.

## Revisit if

- A vendor ships blueprint-aware policy hooks that could enforce our gates inside their
  transaction. That removes the one reason that carries this decision.
- Maintenance exceeds 1 FTE, or state custody causes a production incident. Either means
  the estimate was wrong.
