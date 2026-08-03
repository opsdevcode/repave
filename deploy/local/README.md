# Local quickstart (kind optional)

## Docker Compose (recommended)

```bash
cd deploy/local
docker compose up --build
```

Open **http://localhost:8088**

Gate CLIs (Terraform, tflint, Checkov, Conftest, Helm, Ansible lint) are **installed in
this image** during `docker compose build` via [`install-gate-toolchain.sh`](install-gate-toolchain.sh).
You do **not** install them on macOS, Linux, or **Windows** — only [Docker Desktop](https://docs.docker.com/desktop/) (or another Docker engine) on the host.

**Do not run `make serve` at the same time on macOS.** Compose binds `0.0.0.0:8088` while
`make serve` uses **http://127.0.0.1:8089** so the two do not fight for the same port.
If you open **http://127.0.0.1:8088** while Compose is up, you may hit a different process
than **http://localhost:8088** and see macOS staging paths (`/var/folders/...`) with missing
gate tools. For demos, use **http://localhost:8088** only and stop native `make serve`.

### Compose environment variables

With **no variables set**, `docker compose up --build` uses the secure defaults in the table
below. Prefix a command (`VAR=value docker compose up --build`) or put the same keys in
`deploy/local/.env` (optional; Compose loads it automatically from this directory).

| Variable | Phase | Default | Purpose |
| -------- | ----- | ------- | ------- |
| `UV_SOURCE` | **build** | `registry` | `registry` copies pinned **uv** from `ghcr.io`; use `pip` when that registry is blocked. |
| `REPAVE_TLS_INSECURE` | **build** | `0` | `1` disables TLS verification for toolchain downloads (last resort). |
| `INSTALL_ANSIBLE_COLLECTIONS` | **build** | `1` | `0` skips `ansible-galaxy collection install` (offline builds). |
| `INSTALL_GATE_TOOLCHAIN` | **build** | `1` | `0` skips gate CLIs (portal-only Kubernetes image; see `deploy/k8s/chart/values-portal.yaml`). |
| `GITHUB_TOKEN` | **runtime** | *(empty)* | GitHub PAT for portal **publish** (create/push module repos). |
| *(files)* [`certs/*.crt`](certs/) | **build** | *(none)* | Corporate root CA PEM files; trusted during the image build. |

Build-time variables are baked into the image. Change them only with **`docker compose up --build`**
(or `docker compose build`); a plain `docker compose up` reuses the existing image.

Step-by-step guidance for proxies and TLS inspection:
[Enterprise proxies and TLS inspection](#enterprise-proxies-and-tls-inspection).

### Windows laptops

From PowerShell or Git Bash (repo cloned anywhere Docker can access):

```powershell
cd deploy\local
docker compose up --build
```

Then **http://localhost:8088**. Verify tools inside the container:

```powershell
docker compose exec repave sh -c "terraform version; checkov --version"
curl http://localhost:8088/readyz
```

Expect `"runtime": { "in_container": true, ... }` and `"gate_tools"` all `true`.

### Enterprise proxies and TLS inspection

Use the [build-time variables](#compose-environment-variables) above. If `docker compose up --build`
fails while downloading Terraform, Helm, Python packages, or Ansible collections, the build is
almost certainly behind a TLS-inspecting proxy or cannot reach `ghcr.io`. Work through these in
order.

**1. Trust your corporate CA (preferred).** Copy your root CA as a PEM `*.crt` file into
[`certs/`](certs/) and rebuild. It is registered with `update-ca-certificates` in the image, so
curl, pip/uv, ansible-galaxy, and git all trust it. Certificates there are gitignored. See
[`certs/README.md`](certs/README.md).

**2. Install uv from PyPI when `ghcr.io` is blocked.** The image copies a pinned uv binary from
`ghcr.io/astral-sh/uv` by default; switch the source without changing the version:

```bash
UV_SOURCE=pip docker compose up --build
```

**3. Skip Galaxy collections** for an otherwise offline build (`ansible-lint` and `yamllint` are
still installed, so Ansible **gates** relying on collections may fail):

```bash
INSTALL_ANSIBLE_COLLECTIONS=0 docker compose up --build
```

**4. Last resort — disable TLS verification.** Only if the CA is genuinely unobtainable. This
turns off certificate checking for `curl`, `ansible-galaxy`, **and** pip/uv, so tool binaries are
fetched unverified. It is never on by default and prints a warning during the build:

```bash
REPAVE_TLS_INSECURE=1 docker compose up --build
```

The same variables work when running
[`install-gate-toolchain.sh`](install-gate-toolchain.sh) directly on a host.

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

The container installs the **gate toolchain** via [`install-gate-toolchain.sh`](install-gate-toolchain.sh):

During **`docker compose build`**, the image also runs **`repave doctor --strict`**
so Terraform, tflint, Checkov, Conftest, and Helm match the pin file before the
image is tagged.

| Tool | Golden paths | Notes |
| ---- | ------------- | ----- |
| **terraform** 1.9.8 | Terraform module / stack | fmt, validate, test, plan for OPA |
| **tflint** 0.55.1 | Terraform | |
| **checkov** ≥3.2 | Terraform, Checkov policy | `secrets` gate too |
| **conftest** 0.68.2 | Terraform, OPA policy | plan-time Rego |
| **ansible-lint**, **yamllint**, **ansible-playbook** | Ansible role / playbook | `molecule` not in image (optional gate) |
| **helm** 3.14.4 | Helm chart | lint + template gates |
| **actionlint** 1.7.12 | Helm chart, app service, GitOps delivery | lints `.github/workflows/` |

Dry-run preview **fails** (does not skip) when a blueprint gate’s CLI is missing **inside the
process serving the portal**. In Compose, all tools below are in the image; on the host,
use Compose instead of installing tools locally.

**Native `make serve` on macOS** often has Terraform/tflint but not **checkov**, **conftest**, or **helm** — use Compose on Windows/macOS/Linux rather than:

```bash
bash scripts/install-gate-tools-macos.sh   # optional; prefer Docker Compose
```

`make test` prepends `.gate-tools/bin` to `PATH` when present. Helm chart conformance tests need **helm** on the host (or run tests inside compose).

Not shipped in the local image (gates may still **skip** when N/A): **promtool**, **amtool**, **hadolint**, **go**, **molecule**, **ruff** / **pytest** (app-service / observability extras).
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
