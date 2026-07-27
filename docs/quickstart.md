# Quickstart (local)

Run the full generate → gates → preview loop without Kubernetes.

**Gate tools (Terraform, Checkov, Conftest, tflint, Helm, Ansible linters) ship in the
[Docker Compose](#docker-compose-recommended) image.** You do not install them on the host.
That is the supported path on **macOS, Linux, and Windows** (Docker Desktop).

## Docker Compose (recommended)

From the repo root:

```bash
make compose-up
# or: cd deploy/local && docker compose up --build
```

Open **http://localhost:8088** (use this URL — not `127.0.0.1:8088` while debugging port
conflicts with native serve on macOS).

Compose mounts a `repave-modules` volume at `/modules` and sets `REPAVE_MODULES_ROOT`
so generated modules land outside the repave repo.

### Windows

1. Install [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/).
2. Clone the repo (Git for Windows or WSL is fine).
3. In PowerShell or Git Bash from the repo root:

   ```powershell
   cd deploy\local
   docker compose up --build
   ```

4. Open **http://localhost:8088** in the browser.

No WSL toolchain install is required for portal dry-run — gates run **inside** the Linux
container. Use WSL or native Linux only if you are hacking on the engine with `make serve`
without Docker.

## Five-minute demo (portal)

Use this script when showing repave to someone new. Everything is dry-run unless
noted. Start with **Docker Compose** above so gates run in-container. For the **full six-act live demo** (catalog → Terraform → upgrade → OPA →
Backstage), see **[Seven-minute demo (acts 1–6)](seven-minute-demo.md)**. For live
calls and stakeholder-specific talking points, see [Sales demo runbook](sales-demo.md).

1. **Start:** [Docker Compose](#docker-compose-recommended) → http://localhost:8088
2. **Plan:** **terraform-module-generic** → module `demo`, description, AWS → **Next** →
   scope **ec2 + s3** → **Dry run preview** (sticky footer; or **Next** → **Plan (validate only)** →
   **Scaffold repository**). Confirm **Plan only**, gate dashboard, and **Generated files**.
3. **OPA block (optional):** **opa-policy-generic** → set **plan demo** to
   `destructive_delete` → dry-run → **opa** fails with **Publish blocked** (see
   [examples/policy](../examples/policy/README.md)).
4. **Repave an existing repo:** **Update repo** → **Use terraform-minimal** →
   **Preview upgrade** → copy **Apply locally** or **Open remediation PR**.
5. **Backstage (optional):** on the Terraform form, set **Include Backstage
   catalog** to `true` and **owner** `group:platform` → dry-run → open
   `catalog-info.yaml` in the file preview.

Maintainers: [Demo verification checklist](demo-verification.md) before releases or screenshot updates.

## Native `make serve` (engine dev only)

Optional: edit Python/templates without rebuilding the image. **Does not guarantee the full
gate toolchain on your laptop** — use Compose for Plan/dry-run demos.

From the repo root (requires [uv](https://docs.astral.sh/uv/) in `engine/`):

```bash
make serve
# http://127.0.0.1:8089  (8089 avoids clashing with Compose on 8088)
```

`make serve` sets `REPAVE_GITHUB_ORG` (default `opsdevcode`) and
`REPAVE_MODULES_ROOT` (default `~/repave-modules`). Override with env vars or
[`repave.config.yaml`](../repave.config.yaml.example).

## First generate (portal)

1. Pick **terraform-module-generic** or **ansible-role-generic**.
2. Leave **Dry-run preview** enabled (default) — gate results and file preview
   without writing to disk.
3. Submit.

To bootstrap a local git repo, enable **Publish module repository locally**.
Set `GITHUB_TOKEN` on the server to create the GitHub repo and push `main`.

## CLI (CI and power users)

```bash
cd engine
export REPAVE_GITHUB_ORG=your-org
export REPAVE_MODULES_ROOT=$HOME/repave-modules

uv run repave generate \
  --repo-root .. \
  --blueprint blueprints/terraform-module-generic \
  --input module_name=example \
  --input description="Example module" \
  --input cloud_provider=aws \
  --input provider_services=ec2,s3
```

Publish locally or to GitHub:

```bash
uv run repave generate ... --no-dry-run
```

See [Module repositories](module-repositories.md) for naming and config.

## Operator (optional)

```bash
cd operator && make test    # envtest
make operator-run           # kind / kubeconfig — see operator/README
```
