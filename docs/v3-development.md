# Developing on the v3 line

Working guide for the `next/v3` branch. Branching: [ADR 008](adr/008-v3-branching-release-and-testing.md).
Multi-repo split: [ADR 007](adr/007-v3-multi-repo-decomposition.md).

## Where work goes

| Change | Branch | Result |
| --- | --- | --- |
| v2.x feature or fix | `feat/*` → `main` | v2.x minor or patch |
| v3 feature | `feat/v3-*` → `next/v3` | `3.0.0-rc.N` prerelease |
| Breaking removal | `feat/v3-*` → `next/v3`, held to end | Part of merge-back |

Sync weekly: `git merge origin/main` on `next/v3` (merge, never rebase).

## Multi-repo layout (ADR 007)

| Future repo | Monorepo path today | Local test |
| --- | --- | --- |
| `repave-corpus` | `blueprints/`, `standards/`, `policy/`, … | corpus-conformance workflow |
| `repave-core` | `packages/repave-core/MANIFEST.yaml` | `make test-core` |
| `repave-server` | `packages/repave-server/MANIFEST.yaml` | `make test-portal` |
| `repave-worker` | `packages/repave-worker/MANIFEST.yaml` | `make test-slow` |
| `repave-cli` | `cli/` | `make cli-test` |
| `repave-operator` | `operator/` | `make operator-test` |
| Umbrella `repave` | charts, docs, `integration/`, `versions.lock` | `make integration-test` |

Extract with [`scripts/extract-repos/`](../scripts/extract-repos/README.md).

## Testing

```bash
make test-core COV=1    # unit shard + coverage
make test-portal        # portal/API shard
make test-slow          # conformance + slow gates (needs gate toolchain)
make test-v3            # post-flip v3 marker tests
make integration-test   # versions.lock contract matrix
make test               # full suite before merge-back
```

CI: parallel `engine-unit`, `engine-portal`, `engine-slow` jobs.

## Related

- [ADR 007](adr/007-v3-multi-repo-decomposition.md)
- [ADR 008](adr/008-v3-branching-release-and-testing.md)
- [`versions.lock`](../versions.lock)
