# Operator and CRD development standards

Authoritative conventions for the repave **Kubernetes operator** (`operator/`).
Every API change, controller patch, and release slice must follow this document
alongside [`operator-local-dev.md`](operator-local-dev.md).

**References (community norms we adopt):**

- [Kubernetes API conventions](https://github.com/kubernetes/community/blob/master/contributors/devel/sig-architecture/api-conventions.md)
- [Kubebuilder Book](https://book.kubebuilder.io/) (project layout, markers, envtest)
- [Controller Runtime](https://pkg.go.dev/sigs.k8s.io/controller-runtime) patterns
- [Operator Framework](https://sdk.operatorframework.io/docs/) reconciliation guidance
- [CNCF Operator Maturity Model](https://github.com/operator-framework/operator-sdk/blob/master/doc/maturity-model/maturity-model.md) (target: Level 2+ for v1.17 GA)

---

## Principles

1. **Spec is user intent; status is operator truth.** Never require users to edit
   status. Controllers only write status (and managed finalizers).
2. **Conditions are the standard status signal.** Use `metav1.Condition` with
   `meta.SetStatusCondition`; keep `phase` only as an optional summary for `kubectl`
   columns until GA review.
3. **Validate at the API boundary.** OpenAPI / CEL rules on CRDs first; admission
   webhooks when rules need cluster context (post-v1.17).
4. **Least-privilege RBAC.** Generate rules from `+kubebuilder:rbac` markers; audit
   `config/rbac` on each PR.
5. **Idempotent reconcile.** Safe to re-run; use `controller-runtime` `Reconcile`
   contract; patch status to reduce conflict.
6. **Test like the community.** Unit tests for pure logic, envtest for API +
   controller integration, kind e2e before GA (see local dev doc).
7. **Version consciously.** `v1alpha1` may break; promote to `v1beta1` only with
   conversion strategy and downstream notice.

---

## Project layout

Follow Kubebuilder v4 / Operator SDK layout (see `operator/PROJECT`):

| Path | Purpose |
| --- | --- |
| `api/<version>/` | CRD Go types, kubebuilder markers, deepcopy generated |
| `internal/controller/` | Reconcilers only; no business logic heavy lifting |
| `internal/<domain>/` | Pure packages (e.g. `drift`, `git`) — unit-testable |
| `cmd/main.go` | Manager setup, schemes, health probes |
| `config/crd/bases/` | Generated CRDs — **commit and CI-verify** |
| `config/rbac/` | Generated ClusterRole from RBAC markers |
| `config/dev/` | Sample manifests; not installed by default |
| `testdata/` | Fixture repos and `repave.yaml` for tests |

Do not add parallel CRD YAML hand-edits; change Go types and run `make manifests`.

---

## CRD and API design

### Naming and scope

- Group: `repave.dev`; kinds are PascalCase; plural lowercase (`goldenpathrepos`).
- Resources are **namespaced** unless a future cluster-scoped inventory CRD is
  explicitly designed otherwise.
- Short names sparingly (`gpr`); document in CRD description.

### Spec fields

- CamelCase JSON; document every field with a Go comment (becomes OpenAPI description).
- Required user input: mark with validation (`+kubebuilder:validation:Required`,
  `MinLength`, enums) — not only Go struct tags.
- Optional fields: `+optional` and `omitempty`.
- Cross-field rules: `+kubebuilder:validation:XValidation` (CEL) on the struct, e.g.
  require `repoURL` or `localPath`.

### Status fields

- **`conditions`**: required pattern for operability (Ready, InvalidSpec,
  DriftDetected, RemediationPRPending, etc.).
- **`observedGeneration`**: set when status reflects current `metadata.generation`.
- Avoid duplicating spec in status except **observed** drift (e.g. pins read from
  `repave.yaml`).
- Use `+kubebuilder:subresource:status` always.

### Printer columns

- Only stable, scannable fields (`phase`, repo location, age). Prefer conditions for
  detail (`kubectl describe`).

### Provenance alignment

- Observed pins in status must match semantics of `repave.yaml` /
  `schemas/golden-path-artifact.schema.json` — same field meanings as the engine.

---

## Controller conventions

### Reconcile loop

```text
Get → (deleted?) → validate spec → compute → patch status → (requeue?)
```

- Return `(Result{}, nil)` on success; use `RequeueAfter` for polling backoffs.
- NotFound: stop without error.
- Update status with **patch** (`client.MergeFrom`) where possible.
- Log with `log.FromContext(ctx)` at info for state changes, error for failures.

### Finalizers

- Add a domain finalizer (`repave.dev/goldenpathrepo-finalizer`) before external
  side effects (git push, PR create) in slices 2–3.
- Remove only after cleanup completes.

### Errors

- User misconfiguration → condition `InvalidSpec`, `Reason` set, no infinite retry
  unless spec can change.
- Transient GitHub/git errors → condition false, requeue with backoff.

### Manager

- Leader election **on** in cluster; default **off** for local `make operator-run`.
- Health probes: `healthz` / `readyz` (already in scaffold).
- Run as non-root (`USER 65532` in Dockerfile).

---

## Code quality

| Check | Command |
| --- | --- |
| Test | `make operator-test` |
| Lint | `make operator-lint` (golangci-lint) |
| Generate | `make manifests generate` — diff must be empty in CI |
| Build | `make -C operator build` |

CI (`operator-test`, `operator-lint`) runs on every change under `operator/**`.

### RBAC markers

Keep on reconciler types:

```go
// +kubebuilder:rbac:groups=repave.dev,resources=goldenpathrepos,verbs=get;list;watch
// +kubebuilder:rbac:groups=repave.dev,resources=goldenpathrepos/status,verbs=get;update;patch
```

Add verbs only when controller needs them.

---

## Testing requirements (per PR)

| Change type | Required tests |
| --- | --- |
| API / CRD | Regenerated manifests; envtest create + status update |
| `internal/*` pure logic | Go unit tests (table-driven) |
| Reconciler behavior | envtest and/or envtest + direct `Reconcile()` calls |
| GitHub / git integration | Mocks in CI; no live token |

---

## Release and compatibility

- **v1alpha1**: breaking changes allowed with changelog note.
- Before **v1beta1**: publish conversion webhook or single-version migration doc.
- CRD storage version: one stored version per GA kind; old versions served only if
  conversion exists.

---

## Checklist (copy into operator PRs)

- [ ] API comments and validation markers updated
- [ ] `make manifests generate` run; CRD/RBAC committed
- [ ] Status uses conditions + `observedGeneration`
- [ ] RBAC markers minimal; `config/rbac/role.yaml` reviewed
- [ ] `make operator-test` and `make operator-lint` pass
- [ ] Sample under `config/dev/` updated if spec changed
- [ ] [`operator-local-dev.md`](operator-local-dev.md) updated if workflow changed

---

## Related docs

- [Operator local development](operator-local-dev.md)
- [Roadmap v1.17](roadmap.md#v117--reconciliation-operator)
- [`operator/README.md`](../operator/README.md)
- [`operator/CONTRIBUTING.md`](../operator/CONTRIBUTING.md)
