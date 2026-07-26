# Quickstart (local)

Run the full generate → gates → preview loop without Kubernetes.

## Docker Compose (recommended)

```bash
cd deploy/local
docker compose up --build
# open http://localhost:8088
```

Compose mounts a `repave-modules` volume at `/modules` and sets `REPAVE_MODULES_ROOT`
so generated modules land outside the repave repo.

## Native `make serve`

From the repo root (requires [uv](https://docs.astral.sh/uv/) in `engine/`):

```bash
make serve
# http://127.0.0.1:8088
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
