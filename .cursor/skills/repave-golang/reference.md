# repave Go — reference

## Commands

| Goal | Command |
|------|---------|
| Unit + envtest | `make operator-test` |
| golangci-lint | `make operator-lint` |
| Regenerate CRDs/RBAC | `cd operator && make manifests generate` |
| Local manager | `make operator-run` |
| kind e2e | `make operator-e2e` |

## golangci-lint (enabled linters)

From **`operator/.golangci.yml`**: **errcheck**, **gosimple**, **govet**, **ineffassign**, **staticcheck**, **unused**, **misspell**, **unconvert**.

**goimports** local prefix: **`github.com/opsdevcode/repave/operator`** (see **`linters-settings`**; run **`goimports -local github.com/opsdevcode/repave/operator -w`** when reorganizing imports).

## Testing map

| Layer | Where | Tooling |
|-------|--------|---------|
| Pure logic | `internal/*_test.go` | `go test` |
| Controller + API | `internal/controller/*_test.go` | envtest (`KUBEBUILDER_ASSETS`) |
| Fixtures | `operator/testdata/` | Real `repave.yaml` + module trees |
| E2E | `hack/e2e.sh` | kind + Docker (CI **`operator-e2e`**) |

## API change checklist

1. Edit types under **`operator/api/v1alpha1/`** with kubebuilder markers.
2. **`make manifests generate`** — commit CRD, RBAC, deepcopy diffs.
3. Update envtest coverage for new fields or conditions.
4. Document user-facing behavior in **`docs/operator-standards.md`** if conventions change.

## Security checklist

- [ ] No secrets in source, samples, or test logs
- [ ] HTTP clients use context + timeout
- [ ] Git/subprocess: fixed argv, no user shell interpolation
- [ ] RBAC verbs minimal; **`config/rbac/role.yaml`** regenerated
- [ ] **`go mod tidy`** if imports changed

## Community references

- [Effective Go](https://go.dev/doc/effective_go)
- [Kubebuilder Book](https://book.kubebuilder.io/)
- [Kubernetes API conventions](https://github.com/kubernetes/community/blob/master/contributors/devel/sig-architecture/api-conventions.md)
- [Go security best practices (Go team)](https://go.dev/doc/security/best-practices)
