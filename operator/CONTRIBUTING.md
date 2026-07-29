# Contributing to the repave operator

Go code under `operator/` follows Kubernetes and Kubebuilder community practices.
Read these before opening a PR:

1. **[Operator and CRD standards](../docs/operator-standards.md)** — required
2. **[Operator local development](../docs/operator-local-dev.md)** — testing and fixtures
3. **Cursor Go rules/skills** — [`.cursor/rules/golang-standards.mdc`](../.cursor/rules/golang-standards.mdc), [`.cursor/skills/repave-golang/SKILL.md`](../.cursor/skills/repave-golang/SKILL.md) (style, lint, security; all **`*.go`** in the repo)

## Quick commands

```bash
make operator-test    # from repo root
make operator-lint
cd operator && make manifests generate   # after API changes
```

## PR checklist

Use the checklist at the bottom of
[`docs/operator-standards.md`](../docs/operator-standards.md#checklist-copy-into-operator-prs).
