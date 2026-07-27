# repave-engine

Core generation engine for [repave](../README.md).

## Install (development)

Install [uv](https://docs.astral.sh/uv/), then:

```bash
uv sync --extra dev
```

Or from repo root: `make install`

## CLI

Dry-run (default):

```bash
repave generate \
  --blueprint ../blueprints/terraform-module-generic \
  --input module_name=example \
  --input description="Example module" \
  --input cloud_provider=aws \
  --input provider_services=ec2,s3 \
  --dry-run
```

Dry-run runs every blueprint gate. Missing tools (Terraform, Checkov, Conftest, …) **fail**
instead of skipping. Use [`deploy/local`](../deploy/local/README.md) Docker compose for the
pinned toolchain, or install the same CLIs locally.

Publish locally and push to GitHub:

```bash
export GITHUB_TOKEN=ghp_...
repave generate \
  --blueprint ../blueprints/terraform-module-generic \
  --input module_name=example \
  --input description="Example module" \
  --input cloud_provider=aws \
  --input provider_services=ec2,s3 \
  --no-dry-run
```

`GITHUB_TOKEN` needs permission to create repositories in the configured org (or
your user account when `github_org` is a username).

## Upgrade an existing module repository

Re-render from `repave.yaml` provenance and diff against a checkout (default dry-run):

```bash
repave update --path /path/to/tf-aws-example --repo-root ..
```

Apply files and commit on a branch (local PR prep):

```bash
repave update --path /path/to/tf-aws-example --repo-root .. \
  --no-dry-run --git-branch repave/blueprint-upgrade
```

Operator integration continues to use `plan-upgrade` and `apply-upgrade` with the
same JSON `--format` output.

## Quality and security (local)

```bash
make quality   # ruff lint/format check + mypy
make security  # bandit + pip-audit
make test
```

Set module output location before serving or generating:

```bash
export REPAVE_GITHUB_ORG=your-org
export REPAVE_MODULES_ROOT=$HOME/repave-modules
export GITHUB_TOKEN=ghp_...
```

## API (local portal backend)

```bash
repave serve --repo-root .. --host 0.0.0.0 --port 8088
```

Open http://localhost:8088 for the bundled web portal (catalog, blueprint forms,
results dashboard). Set `GITHUB_TOKEN` in the server environment to enable remote
publish when dry-run is disabled in the form.
