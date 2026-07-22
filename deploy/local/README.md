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

## Native Python (development)

From repo root:

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

v1.0 does not require Kubernetes. The operator and Helm chart arrive in v1.1.
