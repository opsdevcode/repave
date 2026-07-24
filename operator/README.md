# repave operator (v1.17)

Kubernetes reconciliation for generated golden-path repositories: detect drift
and pinned-version bumps, then open **governed remediation pull requests** (never
direct pushes to module repos).

**Slice 0 (scaffold):** `GoldenPathRepo` CRD (`repave.dev/v1alpha1`), baseline
reconciler, `make operator-test` with envtest.

**Slice 1 (inventory):** read `repave.yaml` from `spec.localPath`, populate
`status.observedPins`, set `OutOfDate` + `DriftDetected` when pins differ from
`spec.desiredPins`. `spec.repoURL` returns `RemoteRepoUnsupported` until git
inventory lands.

**Local development and testing are first-class.** See
[`docs/operator-local-dev.md`](../docs/operator-local-dev.md).

**Standards (required for all operator PRs):**
[`docs/operator-standards.md`](../docs/operator-standards.md) and
[`operator/CONTRIBUTING.md`](CONTRIBUTING.md).

Scope and release sequencing: [`docs/roadmap.md`](../docs/roadmap.md#v117--reconciliation-operator).

---

## What it does

Watch registered generated repos and reconcile them against pinned blueprint,
standard, and policy pack versions when:

- rendered content or docs drift from the blueprint contract, or
- pins in repave move forward and the estate should upgrade.

```text
GoldenPathRepo CR  →  read repave.yaml + repo tree
                    →  compare to spec + repave catalog
                    →  optional: repave CLI re-render diff
                    →  GitHub PR (or local/mock in dev)
```

---

## Planned CRDs

| Resource | Role |
| --- | --- |
| `GoldenPathRepo` | One generated artifact: repo location, desired pins, observed status |
| `Blueprint` | Golden path registry (name, version, artifact type) — optional cluster mirror of `blueprints/` |

Contracts align with `repave.yaml` (`GoldenPathArtifact`,
`schemas/golden-path-artifact.schema.json`) and blueprint pins in-repo.

---

## Framework

[Operator SDK](https://sdk.operatorframework.io/) (Go reconciler). Ansible/Helm
operator flavors remain optional for contributors who prefer those runtimes.

---

## v1.17 slices (implementation order)

| Slice | Deliverable | Local proof |
| --- | --- | --- |
| 0 | Scaffold, CRDs, no-op reconcile | `make operator-test` + CI |
| 1 | Inventory / drift status (overlaps v1.24) | envtest + testdata |
| 2 | Re-render diff via `repave` CLI | Local git fixtures |
| 3 | Remediation PR | Mock GitHub in CI |
| 4 | Watch Blueprint / pin config | envtest |

Details: [`docs/operator-local-dev.md`](../docs/operator-local-dev.md#v117-delivery-slices).

---

## Local commands (once scaffold lands)

From repository root:

```bash
make operator-test      # unit + envtest (no kind)
make operator-run       # controller against current kubeconfig
make operator-e2e       # kind + fixtures (optional in CI until GA)
```

Generate fixture module repos with the same engine path as production:

```bash
make generate
```

```bash
kind create cluster --name repave-local
kubectl apply -f config/crd/bases/
kubectl apply -f config/dev/goldenpathrepo-sample.yaml
make operator-run
```

See [deploy/local/README.md](../deploy/local/README.md#kind-optional).

---

## Testing summary

| Layer | Command | Needs |
| --- | --- | --- |
| Unit + envtest | `make operator-test` | Go only |
| Dev loop | `make operator-run` + kubectl | kind or cluster |
| E2E | `make operator-e2e` | kind, Docker |

GitHub.com is **not** required for default CI or the 15-minute contributor path.

---

## Baseline from generation (v1.14+)

The operator builds on contracts already enforced at generate time:

```text
form → render → gates → module repo → (optional) GitHub push
```

Generated repos include `repave.yaml` provenance (Terraform `terraformModule`,
Ansible `ansibleRole` + lint pack pins). Drift detection must match what the
`provenance-drift` gate already validates.

---

## Directory map (target)

```text
operator/
  api/ controllers/ internal/drift/ internal/git/
  config/crd/ config/dev/ testdata/ test/e2e/ hack/
  Makefile
```

Contributors: [`docs/operator-local-dev.md`](../docs/operator-local-dev.md).
**Slice 2:** `repave plan-upgrade` + `status.upgradePlan` when pins drift.
Next slice: remediation PRs (slice 3).
