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

GitHub **default branch is `next/v3`**. New clones and PRs land there. `main` stays
the v2.x Release line — do not retarget `release.yml`.

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
`engine/tests/test_v3_foundation.py`, `engine/tests/test_developer_lab.py`, and `make test-v3`.

## Developer lab (v3)

**Opt-in** (`v3.developer_lab.enabled: true` **and** `v3.enabled: true`). `v3.enabled`
alone does not expose `/home` or `/lab` (ADR 008: default-off). Lab without `v3.enabled`
fails closed and names the fix.

Lab wires **catalog** paths from bundled `examples/platform-dev` fixtures when no
`service_catalog` block is set. It does **not** invent a GitOps repo or turn on
environment vending. The published container image does **not** include `examples/`
(see `.dockerignore`); hosted installs mount catalog YAML and set
`repave.serviceCatalog.enabled`.

| Surface | Route | Backing config |
| --- | --- | --- |
| My services | `/home` | Bundled maturity + initiatives paths |
| Developer lab | `/lab` (alias `/sandbox`) | Workload profiles + deployment sets |
| Sandbox vending | `POST /sandbox/request` | Explicit `environment_vending` (still required) |

Missing fixtures fail closed with a path in the error. Explicit `service_catalog`
blocks still override the bundled paths. `v3.developer_lab.enabled: false` keeps
today's `/sandbox` label when catalog is configured some other way.

**Async runs** (`durability.async_generation: true`) are required for live sandbox
requests — the lab UI is plan-only without them. For the full platform console
walkthrough, keep using `make platform-dev-setup`
([`examples/platform-dev/README.md`](../examples/platform-dev/README.md)).

Helm (flags only; catalog files are operator-provided):

```bash
helm upgrade --install repave ./deploy/k8s/chart \
  --set repave.v3.enabled=true \
  --set repave.v3.developerLab.enabled=true \
  --set repave.serviceCatalog.enabled=true \
  --set repave.output.githubOrg=your-org
```

Combine with
[`values-environment-vending.yaml`](../deploy/k8s/chart/values-environment-vending.yaml)
for live GitOps PRs.

### FGA gate (hosted My services)

**My services is a UX filter today, not enforcement.** `/home` matches your email against
`entity.owner` substrings; `/library` and `/services/{id}` do not hide other teams' entities.
Hosted portals default to login-only coarse RBAC (every user gets `admin` until
`coarse_rbac_enabled: true`).

Before advertising developer lab + My services on a **multi-team hosted** portal, ship
fine-grained authorization (**ADR 010+**, parking lot): OpenFGA-compatible checks on entity
read, team pages, sandbox vend, and generate. Local demos and single-team pilots can stay on
FGA-off heuristics.

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
