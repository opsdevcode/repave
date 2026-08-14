# Developing on the v3 line

Working guide for the `next/v3` branch. Branching: [ADR 008](adr/008-v3-branching-release-and-testing.md).
Multi-repo split: [ADR 007](adr/007-v3-multi-repo-decomposition.md).

## Where work goes

**v3 is the primary product line.** New product work targets `next/v3`, not `main`.

| Change | Branch | Result |
| --- | --- | --- |
| New product work (v3) | `feat/v3-*` → `next/v3` | `3.0.0-rc.N` prerelease |
| v2.x fix or backport | `feat/*` → `main` | v2.x patch or minor |
| Breaking removal | `feat/v3-*` → `next/v3`, held to end | Part of merge-back |

Identity policy ([ADR 009](adr/009-v3-product-identity.md)) is accepted: display name
**repave**, platform-layer mark, tagline *The intelligent platform layer*. Foundation,
developer lab, and extract-repos use that shell.

GitHub **default branch stays `main`** (v2.x releases). Do not retarget Release.

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

## Foundation slice (default-off)

Modules under `engine/src/repave_engine/`:

| Module | Purpose |
| --- | --- |
| `deprecations.py` | `V3_DEPRECATIONS` registry + HTTP Sunset headers |
| `risk_class.py` | `RiskClass` enum and `classify_change()` |
| `waivers.py` | JSONL waiver load + expiry evaluation |
| `v3_foundation.py` | `v3:` block in `repave.config.yaml` (off until flip) |

Enable with `v3.enabled: true` in config (see `repave.config.yaml.example`). Tests:
`engine/tests/test_v3_foundation.py` and `make test-v3`.

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
