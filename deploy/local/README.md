# Local quickstart (kind optional)

## Docker Compose (recommended)

```bash
cd deploy/local
docker compose up --build
```

Open http://localhost:8088

The container includes **terraform**, **tflint**, and **checkov**, so blueprint gates
run for real instead of skipping. Generated modules are written to the `repave-modules`
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
