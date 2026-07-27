# Local quickstart (kind optional)

## Docker Compose (recommended)

```bash
cd deploy/local
docker compose up --build
```

Open http://localhost:8088

The engine is installed **editable** from `/app/engine`, and compose bind-mounts
the repo at `/app`. The service runs `repave serve --reload`, so Python changes
under `engine/src/` apply after a few seconds without rebuilding the image.
Templates and `/static/repave.*` are read from the mount; URLs are cache-busted
with the engine version query string — a normal refresh is usually enough after
portal edits.

**Rebuild the image** only when `engine/pyproject.toml`, `uv.lock`, or the
Dockerfile changes. For template/CSS/JS-only work: `docker compose restart repave`
(or save a `.py` file and wait for reload).

### Plan (dry-run) smoke test

On branch with the latest portal stepper fixes, after `docker compose up --build`:

1. Open **terraform-module-generic** — page source should include `Dry run preview` and
   `data-dry-run-run` (and `data-form-stepper`). If you only see a hidden **Scaffold** button,
   the browser or container is still on old static JS — hard refresh or restart the service).
2. **Identity:** module name + description → **Next**.
3. **Services:** pick at least one service (e.g. **Compute + storage**) → **Dry run preview**
   (or **Next** to Delivery, leave **Plan (validate only)**, **Scaffold repository**).
4. Result should show **Plan only** and **Generated files**.

The container includes **terraform** (1.9.8), **tflint** (0.55.1), **checkov** (≥3.2.0),
and **conftest** (0.56.0 for OPA gates), so blueprint gates run for real instead of
skipping. Policy demos ([policy golden paths](../../docs/policy-golden-paths-demo.md))
need compose for **destructive_delete** OPA blocks. The same toolchain versions are
pinned in generated repositories’ GitHub Actions workflows (`spec.ci.toolchain`
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

## Operator (v1.17 GA)

The reconciliation operator runs on Kubernetes (kind locally). **Local testing
is first-class** — no GitHub for default `make operator-test` (envtest) or kind e2e.

GA scope: [`docs/operator-ga.md`](../../docs/operator-ga.md).

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
