# Contributing to the repave operator

Go code under `operator/` follows Kubernetes and Kubebuilder community practices.
Read these before opening a PR:

1. **[Operator and CRD standards](../docs/operator-standards.md)** — required
2. **[Operator local development](../docs/operator-local-dev.md)** — testing and fixtures

## Quick commands

```bash
make operator-test    # from repo root
make operator-lint
cd operator && make manifests generate   # after API changes
```

## PR checklist

Use the checklist at the bottom of
[`docs/operator-standards.md`](../docs/operator-standards.md#checklist-copy-into-operator-prs).
