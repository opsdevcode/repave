# Multi-repo extraction targets (v3)

This directory documents the future repository boundaries for
[ADR 007](../docs/adr/007-v3-multi-repo-decomposition.md). Source still lives in the umbrella
monorepo until `git filter-repo` extraction runs.

| Directory | Future GitHub repo | Extraction script |
| --- | --- | --- |
| [repave-corpus](repave-corpus/README.md) | `opsdevcode/repave-corpus` | [`scripts/extract-repos/extract-corpus.sh`](../scripts/extract-repos/extract-corpus.sh) |
| [repave-operator](repave-operator/README.md) | `opsdevcode/repave-operator` | [`scripts/extract-repos/extract-operator.sh`](../scripts/extract-repos/extract-operator.sh) |
| [repave-cli](repave-cli/README.md) | `opsdevcode/repave-cli` | [`scripts/extract-repos/extract-cli.sh`](../scripts/extract-repos/extract-cli.sh) |

Python engine split targets are under [`packages/`](../packages/README.md).

After extraction, the umbrella `opsdevcode/repave` repo retains Helm charts, docs,
[`versions.lock`](../versions.lock), and the integration test harness.
