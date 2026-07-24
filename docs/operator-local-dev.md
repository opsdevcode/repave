# Operator local development and testing

Planning and day-one requirements for the **v1.17 reconciliation operator**.
Local verification is a **first-class deliverable**: every operator slice ships
with tests and documented commands before it is considered done.

Related: [roadmap — v1.17](roadmap.md#v117--reconciliation-operator),
[`operator/README.md`](../operator/README.md).

---

## Principles

1. **No production GitHub required** for default developer and CI flows.
2. **Reuse the engine** for render/diff semantics (`repave` CLI or a stable
   reconcile subcommand) — do not fork golden-path logic inside Go.
3. **Three layers:** fast unit/envtest (every PR), local controller loop (kind),
   optional e2e with mocks or Gitea.
4. **Same contracts** as generation: `repave.yaml`, `schemas/golden-path-artifact.schema.json`,
   blueprint pins in `blueprints/`.

```text
  Every PR          make operator-test     Go unit + controller-runtime envtest
  Dev loop          make operator-run      kind (or kubeconfig) + sample CRs
  Pre-GA confidence make operator-e2e     kind + fixtures + mock GitHub
```

---

## Prerequisites

| Tool | Purpose |
| --- | --- |
| Go (version pinned in `operator/go.mod` when scaffold lands) | Build and test operator |
| [uv](https://docs.astral.sh/uv/) + engine dev deps | Generate fixture module repos |
| [kind](https://kind.sigs.k8.io/) | Optional local cluster for `operator-run` / e2e |
| kubectl | Apply CRs and inspect status |
| Docker | kind nodes; operator image build |

Kubernetes is **not** required for `make operator-test` (envtest only).

---

## Repository layout (target)

Created incrementally with v1.17; paths are the contract for docs and Make targets.

```text
operator/
  api/                      # CRD Go types + kubebuilder markers
  controllers/              # Reconcilers
  internal/drift/           # Pin comparison (unit-tested, no K8s)
  internal/git/             # Local repos + GitHub client interface
  config/crd/               # CRD bases (kustomize)
  config/dev/               # kind overlay, sample GoldenPathRepo manifests
  testdata/                 # Mini module repos + repave.yaml fixtures
  test/e2e/                 # kind tests (build tag e2e)
  hack/                     # kind-up, load-image, seed-fixtures scripts
  Makefile                  # test, run, docker-build, e2e

docs/operator-local-dev.md  # this file
```

Root `Makefile` exposes `operator-test`, `operator-run`, and `operator-e2e`
wrappers once the scaffold exists.

---

## v1.17 delivery slices

Each slice merges with its own tests and doc updates.

| Slice | Behavior | Local verification |
| --- | --- | --- |
| **0 — Scaffold** | Operator SDK project, CRDs, no-op reconciler | `make operator-test` in CI; envtest installs CRDs |
| **1 — Inventory** | `GoldenPathRepo` status from `repave.yaml` vs spec pins | Unit fixtures; envtest status updates |
| **2 — Re-render diff** | Invoke repave to compute upgrade diff | Git repos under `operator/testdata/`; no network |
| **3 — Remediation PR** | Open PR on drift | `GitHubClient` mock; optional real token for manual smoke |
| **4 — Pin watch** | React to Blueprint / config pin bumps | envtest + sample Blueprint CR |

**v1.17 done when:** a `GoldenPathRepo` triggers an upgrade PR when blueprint or
standard version bumps in repave. **Slices 0–2** should be usable locally without
GitHub before PR automation lands.

---

## Testing layers

### Unit tests (no cluster)

Package `internal/drift` (name illustrative) compares:

- `GoldenPathRepo.spec` desired pins
- `repave.yaml` observed pins in the registered repo
- Optional: catalog pins from the repave checkout (blueprint `metadata.version`)

Use table-driven tests and trees under `operator/testdata/modules/` (Terraform
and Ansible samples copied or generated via `make generate`).

### envtest (default CI Kubernetes)

[Controller-runtime envtest](https://book.kubebuilder.io/reference/envtest.html)
runs a real API server in-process — **no kind, no Docker** for `go test`.

Covers: CRD apply, reconcile loop, status subresource, requeue.

```bash
make operator-test
```

CI job `operator-test` runs on changes under `operator/**` (see roadmap v1.17).

### Local controller (`make operator-run`)

1. Create a module repo locally:

   ```bash
   make generate
   # or portal / compose; note path under REPAVE_MODULES_ROOT
   ```

2. Start kind (optional but recommended for full loop):

   ```bash
   kind create cluster --name repave-local
   # future: make operator-kind-up
   ```

3. Install CRDs and run the controller locally (leader election off for dev):

   ```bash
   make operator-run
   ```

4. Apply a dev manifest:

   ```bash
   kubectl apply -f operator/config/dev/goldenpathrepo-sample.yaml
   kubectl describe goldenpathrepo <name>
   ```

5. Change pins in repave or edit fixture `repave.yaml` → watch status and logs.

### Git and GitHub

| Mode | When |
| --- | --- |
| **Local path / file URL** | Default dev; reconcile reads working tree or clone under `/tmp` |
| **Bare repos in testdata** | Unit and envtest; scripts commit pin changes |
| **httptest mock** | CI for PR creation payloads |
| **Gitea in compose** | Optional later (`deploy/local`); real push/PR without github.com |
| **`GITHUB_TOKEN`** | Manual smoke only; document in hack/README, never required in CI |

### kind e2e (`make operator-e2e`)

- Build tag `e2e`; not required on every PR initially, required before v1.17 GA.
- Flow: kind up → load operator image → apply fixtures → assert status within timeout.
- Shares cluster naming with [deploy/local kind](../deploy/local/README.md#kind-optional).

---

## Fixture workflow

1. Generate a fresh artifact:

   ```bash
   make generate
   ```

2. Copy or symlink into `operator/testdata/...` when adding new test cases (keep
   fixtures small — trim provider scope as needed).

3. Ensure `repave.yaml` validates against `schemas/golden-path-artifact.schema.json`
   (same bar as `provenance-drift` gate).

4. Register in a `GoldenPathRepo` manifest with `spec.repoURL` or local path field
   as defined by the CRD (document exact field in `operator/README.md` when frozen).

---

## CI expectations

| Job | Trigger | Notes |
| --- | --- | --- |
| `operator-test` | PR touching `operator/**` | envtest + unit; no kind |
| `operator-lint` | Same | golangci-lint |
| `operator-e2e` | Nightly or pre-release | kind; may start as optional |

Docs-only PRs use [ci-paths](../.github/actions/ci-paths/) like engine workflows.

---

## Acceptance criteria (local testing first-class)

1. **`make operator-test`** passes on a laptop with Go only (one-time envtest
   asset setup documented in `operator/README.md`).
2. **New contributor path ≤ 15 minutes** to: apply sample `GoldenPathRepo` → see
   status reflect fixture drift **without** `GITHUB_TOKEN`.
3. **At least one e2e** (before v1.17 GA): stale standard pin → `OutOfDate` status
   or mock PR recorded.
4. **Engine subprocess contract** documented: which `repave` CLI flags the
   operator calls for dry-run upgrade diff (aligns with v1.19 `repave update`).

---

## Related roadmap items

- **v1.24** — inventory-only mode is slice 1; same local fixtures.
- **v1.25** — Helm/k8s deploy co-install; kind smoke reuses operator e2e harness.
- **v1.19** — `repave update` becomes the preferred local diff driver for slice 2+.
