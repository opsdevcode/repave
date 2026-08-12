# Architecture decision records

Lightweight ADRs for repave platform choices. Number files sequentially; link from
[`docs/roadmap.md`](../roadmap.md) and operator docs when a decision affects GA scope.

| ADR | Title |
| --- | --- |
| [001](001-goldenpathrepo-repo-url-inventory.md) | `GoldenPathRepo.spec.repoURL` remote inventory |
| [002](002-v2-service-decomposition.md) | v2 service decomposition and repository strategy |
| [002 addendum](002-addendum-run-artifact-rehydrate.md) | Async run rehydrate: run-record snapshots (default) vs object storage (optional) |
| [003](003-environment-lifecycle-and-live-state.md) | Environment lifecycle and how far repave reaches into live state |
| [004](004-state-custody-and-the-resource-graph.md) | State custody and the resource graph (authoritative Terraform state store) |
| [005](005-state-graph-build-vs-buy.md) | State graph: build vs buy |
| [006](006-service-catalog-and-maturity.md) | Service catalog overlay, maturity, GitOps sandboxes |
| [007](007-v3-multi-repo-decomposition.md) | v3 multi-repo decomposition and per-repo CI |
| [008](008-v3-branching-release-and-testing.md) | v3 branching, release, and testing strategy |
