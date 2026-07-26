# Local quickstart (kind optional)

## Docker Compose (recommended)

```bash
cd deploy/local
docker compose up --build
```

Open http://localhost:8088

The engine is installed **editable** from `/app/engine`, and compose bind-mounts
the repo at `/app`, so portal CSS/templates update when you refresh (hard-refresh
if the browser cached `/static/repave.css`). Rebuild when `pyproject.toml` or the
Dockerfile changes; a plain restart is enough for template/CSS edits.

The container includes **terraform** (1.9.8), **tflint** (0.55.1), and **checkov** (≥3.2.0)
(policy + secrets scan), so blueprint gates run for real instead of skipping. The same
versions are pinned in generated repositories’ GitHub Actions workflows (`spec.ci.toolchain`
in `repave.yaml`). CI runs `repave gates --path .` from the gate list in `spec.ci.gates`.
Generated modules are written to the `repave-modules`
Docker volume (`/modules` inside the container).

To publish to GitHub from the portal, pass a token when starting compose:

```bash
GITHUB_TOKEN=ghp_... docker compose up --build
```

The token needs permission to create repositories in `REPAVE_GITHUB_ORG`.

## Native Python (development)

Install [uv](https://docs.astral.sh/uv/), then from repo root:

```bash
make install
make serve
```

## kind (optional)

If you want to exercise a Kubernetes workflow later, create a local cluster:

```bash
kind create cluster --name repave-local
kubectl cluster-info --context kind-repave-local
```

Kubernetes is optional for local development. The operator and Helm chart are
planned for a future release.

## Operator (v1.17 alpha)

The reconciliation operator runs on Kubernetes (kind locally). **Local testing
is first-class** — no GitHub for default `make operator-test` (envtest) or kind e2e.

```bash
make operator-test    # unit + envtest (Go only)
make operator-run     # controller against kubeconfig / kind
make operator-e2e     # kind + image + OutOfDate fixture (GA harness)
```

Full guide: [`docs/operator-local-dev.md`](../../docs/operator-local-dev.md).
Overview: [`operator/README.md`](../../operator/README.md).

`make operator-e2e` creates/deletes a `repave-local` kind cluster. For a lasting
dev cluster:

```bash
kind create cluster --name repave-local
kubectl cluster-info --context kind-repave-local
```
