# Supply chain posture

How repave pins third-party dependencies in CI, container images, and Helm deploys.
Complements [GitHub App authentication](github-app-auth.md) for short-lived publish credentials.

## GitHub Actions

Workflows under `.github/workflows/` reference marketplace actions by **commit SHA**, not
mutable tags. Allowed SHAs live in [`.github/action-pins.json`](../.github/action-pins.json).

CI runs [`scripts/check-action-pins.py`](../scripts/check-action-pins.py) in the Python quality
job. When bumping an action:

1. Resolve the target tag's commit SHA (for example from the action's release page).
2. Update the workflow `uses:` line **and** the matching entry in `action-pins.json`.
3. Run `python3 scripts/check-action-pins.py` locally before pushing.

Local composite actions (`.github/actions/*`) are exempt from the pin file.

## Container base images

[`deploy/local/Dockerfile`](../deploy/local/Dockerfile) pins:

- `python:3.12-slim@sha256:…`
- `ghcr.io/astral-sh/uv:0.11.33@sha256:…` (when `UV_SOURCE=registry`)

[`deploy/local/Dockerfile.corpus`](../deploy/local/Dockerfile.corpus) pins `alpine:3.21`.

Bump base digests deliberately — re-run `make chart-smoke` or `make chart-smoke-decomposed`
after changing them.

## Published engine images

[`.github/workflows/container.yml`](../.github/workflows/container.yml) builds and pushes
digest-pinned images to GHCR on `main` and semver tags:

| Image | Purpose |
| --- | --- |
| `ghcr.io/opsdevcode/repave-engine` | Gate-toolchain worker |
| `ghcr.io/opsdevcode/repave-engine-portal` | Portal/API (no gate CLIs) |
| `ghcr.io/opsdevcode/repave-corpus` | Generation corpus OCI artifact |
| `ghcr.io/opsdevcode/repave-operator` | Kubernetes reconciliation operator |

Per-image documentation: [`deploy/packages/`](../deploy/packages/README.md).

Each push publishes `type=sha` tags alongside semver tags so operators can pin by digest.

Resolve a digest before deploy:

```bash
crane digest ghcr.io/opsdevcode/repave-engine:v1.126.0
# ghcr.io/opsdevcode/repave-engine@sha256:…
```

## Helm digest pinning

The portal chart supports `image.digest`, `workerImage.digest`, and `corpus.digest`. When set,
the chart renders `repository@digest` and ignores the tag field — see
[`deploy/k8s/chart/templates/_helpers.tpl`](../deploy/k8s/chart/templates/_helpers.tpl).

Example overlay: [`values-digest-pinned.yaml`](../deploy/k8s/chart/values-digest-pinned.yaml).

```bash
helm upgrade --install repave ./deploy/k8s/chart \
  -f deploy/k8s/chart/values.yaml \
  -f deploy/k8s/chart/values-decomposed-day2.yaml \
  -f deploy/k8s/chart/values-digest-pinned.yaml \
  --set image.digest=sha256:abc... \
  --set workerImage.digest=sha256:def... \
  --set corpus.digest=sha256:ghi...
```

The operator chart supports `image.digest` the same way
([`deploy/k8s/operator-chart/values.yaml`](../deploy/k8s/operator-chart/values.yaml)).

See [Upgrade and rollback](operations/upgrade-and-rollback.md) for the pre-upgrade smoke
checklist.

## Related

- [Durability — container images](durability.md) — decomposed portal/worker/corpus layout
- [Engine hardening A1](roadmap.md#a1--one-source-of-truth-for-gate-toolchain-pins) — gate CLI version pins inside images
