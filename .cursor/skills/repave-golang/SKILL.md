---
name: repave-golang
description: >-
  Go development in opsdevcode/repave operator: Kubebuilder, golangci-lint, envtest,
  CRD generation, and security patterns. Use when editing operator/**/*.go, go.mod,
  operator CI failures, or plan-upgrade/apply-upgrade JSON contracts.
---

# repave Go (operator) development

**Scope:** all Go in the monorepo — **`operator/`** today; any future **`**/*.go`** paths use the same rules.

Follow **`.cursor/rules/golang-standards.mdc`** and **`.cursor/rules/golang-security.mdc`**.

## Source of truth

| Topic | Location |
|-------|----------|
| golangci-lint | `operator/.golangci.yml` |
| Make targets | `operator/Makefile`, root `make operator-test` / `operator-lint` |
| CI | `.github/workflows/operator.yml`, `operator-e2e.yml` |
| Product standards | `docs/operator-standards.md` |
| Local dev | `docs/operator-local-dev.md` |
| Deep reference | [reference.md](reference.md) |

## Quality workflow

From repo root:

```bash
make operator-lint
make operator-test
```

After **API or RBAC marker** changes:

```bash
cd operator && make manifests generate
git diff --exit-code config/crd/bases config/rbac api/
```

CI **`operator-test`** runs **`make test`** and **`make lint`**, then verifies generated manifests are committed.

## Conventions (summary)

- Reconcilers in **`internal/controller/`**; business logic in **`internal/<pkg>/`** with unit tests.
- **Spec vs status** — users edit spec only; conditions carry operability.
- **Remote repos:** shallow clone, resync interval, **`Ready=False`** on fetch failure — see existing **`GoldenPathRepo`** reconciler.
- **JSON contracts** for **`plan-upgrade`** / **`apply-upgrade`**: stable unless versioned; note in PR if changed.

## Security (summary)

- Context-aware HTTP, no secret logging, **`CommandContext`** for git/shell.
- RBAC markers match actual API access.

See **[reference.md](reference.md)** for checklist and community links.

## Related

- Python engine: `.cursor/skills/repave-python/SKILL.md`
- Portal JS: `.cursor/skills/repave-javascript/SKILL.md`
