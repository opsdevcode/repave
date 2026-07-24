# Local quickstart (kind optional)

## Docker Compose (recommended)

```bash
cd deploy/local
docker compose up --build
```

Open http://localhost:8088

The container includes **terraform**, **tflint**, and **checkov** (policy + secrets
scan), so blueprint gates run for real instead of skipping. Generated modules are written to the `repave-modules`
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

## Operator (v1.17, planned)

The reconciliation operator will run on Kubernetes (kind locally). **Local
testing is a first-class deliverable** — you will not need GitHub for default
`make operator-test` (envtest) or the basic dev loop.

When the Go scaffold lands under `operator/`:

```bash
make operator-test    # unit + envtest (Go only)
make operator-run     # controller against kubeconfig / kind
make operator-e2e     # kind + fixtures (pre-GA)
```

Full guide: [`docs/operator-local-dev.md`](../../docs/operator-local-dev.md).
Overview: [`operator/README.md`](../../operator/README.md).

Create the shared kind cluster once:

```bash
kind create cluster --name repave-local
kubectl cluster-info --context kind-repave-local
```
