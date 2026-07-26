# repave

**Governed, repeatable platform engineering — for many, not just the few.**

`repave` lets people who are not platform-engineering experts produce
production-ready automation (Terraform modules and Ansible roles today, more
later) by answering a short form. The output is generated **deterministically** from versioned golden
paths, is forced through **mandatory quality/security gates**, and lands as a
**governed module repository on GitHub** — so the standards set by your platform
team are enforced *by construction*, not by after-the-fact review.

The name says the intent: a **paved road** is how platform teams let many
developers move fast safely; `repave` continuously (re)lays that road — governed,
repeatable, and automated.

> **Status (engine [v1.31.1](https://github.com/opsdevcode/repave/releases/tag/v1.31.1)
> on GitHub).** Generation runs locally or via Docker Compose — no Kubernetes
> required for the engine. The **reconciliation operator** (alpha; v1.17 slices
> 0–4 + kind e2e) reconciles `GoldenPathRepo` and `Blueprint` CRDs. **Portal UX**
> (v1.18 theme) is complete: catalog, forms, results dashboard, and browser
> last-run snippet. See [`operator/`](operator/) and
> [`docs/operator-local-dev.md`](docs/operator-local-dev.md).

## What you can do today

### Generation engine (`engine/`)

- **Golden paths:** Terraform module and Ansible role blueprints (`blueprints/`),
  Copier render, frozen JSON schemas (`schemas/`).
- **Portal + API:** Server-rendered golden-path forms, gate results dashboard, and
  publish flow at `http://localhost:8088` (Compose) or `repave serve`.
- **CLI:** `repave generate`, `repave list`, `repave update` (plan/apply blueprint
  upgrades from `repave.yaml`), gate execution, provenance in `repave.yaml`.
- **Gates (blueprint-configured):** Terraform — `fmt`, `validate`, `tflint`,
  Checkov (policy packs under `policy/checkov/`), secrets scanning; Ansible —
  production-profile **ansible-lint** pack and standards corpus under
  `standards/ansible/`.
- **Publish:** Local git bootstrap or GitHub create/push with `GITHUB_TOKEN`;
  modules live under `REPAVE_MODULES_ROOT`, not inside the repave repo.

### Reconciliation operator (`operator/`, v1.17)

Kubernetes controller for **estate drift and upgrades** (local envtest/kind; no
live GitHub required for default tests):

| Capability | CRD / API | Notes |
| --- | --- | --- |
| Inventory | `GoldenPathRepo` | Read `repave.yaml` from `spec.localPath`; `status.observedPins` |
| Drift detection | `GoldenPathRepo` status | `OutOfDate` when observed ≠ desired pins |
| Upgrade diff | `status.upgradePlan` | `repave plan-upgrade` contract (slice 2) |
| Remediation PR | `spec.remediation` | `repave apply-upgrade` + GitHub client; dry-run without token (slice 3) |
| Catalog pin watch | `Blueprint` + `spec.blueprintRef` | Reconcile GPRs when Blueprint pins change (slice 4) |

`spec.repoURL` (git clone inventory) is not implemented yet; use `localPath` for dev and envtest.

### CI on `main`

- Engine: pytest, Ruff, mypy, Bandit, pip-audit.
- Operator: Go tests + controller-runtime **envtest** on every PR.
- **Release:** Conventional commits → semver bump, `engine/CHANGELOG.md`, GitHub
  Release with wheel (see [Releases](#releases)).

## Why repave

- **Enables many.** A web form maps to a golden path; no one needs to know
  Terraform/HCL to get a compliant module.
- **Governed by construction.** Generated artifacts must pass every configured
  gate before publish. There is no bypass path.
- **Deterministic + repeatable.** The same inputs always render the same
  artifact (Copier templates), so output is reviewable and safe.
- **Bring your own standards.** Point a blueprint at your standards source and
  pin the version it encodes ("housed in one, rendered in many").
- **Runs locally first.** `docker compose up` and open a browser — see the whole
  loop without any cloud account.

## How it works

```text
Web form (inputs)  ->  Engine: render (Copier)  ->  Gates  ->  Module repository  ->  GitHub
                        \_ blueprint.yaml (input schema, standard ref, gate list) _/
```

Each generated module is written to **its own git repository** outside the
repave platform repo — never into `.repave-out/` inside repave.

1. A **blueprint** (`blueprints/<name>/blueprint.yaml`) declares its input
   schema, the standard version it encodes, its Copier template, and the gate
   list it must pass.
2. The **engine** validates inputs, renders the template deterministically, runs
   the gates, and materializes the module in its own local git repository.
3. When `GITHUB_TOKEN` is set and dry-run is disabled, repave **creates the
   GitHub repository** (if needed) and **pushes the initial commit** to `main`.
4. The **portal/API** turns the blueprint's input schema into a form so
   non-experts can drive it without a command line.

Optional **operator** loop (separate from generation):

```text
GoldenPathRepo CR  ->  observe repave.yaml  ->  compare pins  ->  upgrade plan  ->  remediation PR
Blueprint CR       ->  watch  ----------------^ (blueprintRef)
```

## Module repositories

Generated modules never live inside the repave repo. Configure a separate output
root and GitHub organization:

```bash
cp repave.config.yaml.example repave.config.yaml
# edit output.github_org and output.modules_root
```

Or use environment variables:

```bash
export REPAVE_GITHUB_ORG=your-org
export REPAVE_MODULES_ROOT=$HOME/repave-modules
export GITHUB_TOKEN=ghp_...   # repo scope; required for remote publish
```

Each module becomes `$(modules_root)/tf-<cloud_provider>-<module_name>/` — an
independent git repository at
`https://github.com/<org>/tf-<cloud_provider>-<module_name>`.

## Quickstart (local, no Kubernetes)

```bash
cd deploy/local
docker compose up --build
# open http://localhost:8088
```

Docker Compose mounts a `repave-modules` volume at `/modules` and sets
`REPAVE_MODULES_ROOT` so generated modules land outside the repave repo.

Fill the form for a bundled blueprint (`terraform-module-generic` or
`ansible-role-generic`) and submit.
In dry-run mode (default) you'll see gate results and the planned module
repository. Enable **Publish module repository locally** to bootstrap a local git
repo; set `GITHUB_TOKEN` in the server environment to create the GitHub repo and
push the initial commit.

CLI equivalent (for development/CI, not the primary UX):

```bash
repave generate \
  --blueprint blueprints/terraform-module-generic \
  --input module_name=example \
  --input description="Example module" \
  --input cloud_provider=aws \
  --input provider_services=ec2,s3 \
  --no-dry-run
```

Operator (optional):

```bash
cd operator && make test          # envtest
make operator-run                 # against kind/kubeconfig (see operator README)
```

## Repository layout

```text
schemas/       # frozen contracts: blueprint, golden-path artifact, inputs schemas
engine/        # core generation engine (Python + Copier) + API/CLI
blueprints/    # versioned golden paths (reference packs)
standards/     # governed standards corpus (pinned by blueprints)
policy/        # Checkov and ansible-lint packs copied into generated repos
examples/      # pack test fixtures and authoring docs (not in service images)
deploy/local/  # docker compose + kind quickstart
operator/      # reconciliation operator (GoldenPathRepo, Blueprint CRDs)
docs/          # concepts, roadmap, portal design, operator local dev
.cursor/       # Cursor rules/skills for Release CI (contributors using Cursor)
```

## Roadmap

**Current focus:** v1.19 update flow for existing module repos and v1.17 operator
GA close-out ([`docs/roadmap.md`](docs/roadmap.md)). Portal planning and acceptance
criteria live in [`docs/portal-design.md`](docs/portal-design.md) (theme complete).

High-level release history and planning through **v2.0.0** live in
[`docs/roadmap.md`](docs/roadmap.md).

## Releases

Versioning and GitHub releases are automated from
[Conventional Commits](https://www.conventionalcommits.org/) on `main` using
[python-semantic-release](https://python-semantic-release.readthedocs.io/).

- Merge a PR to `main` with a conventional title (`feat:`, `fix:`, etc.).
- The **Release** workflow runs engine + operator tests, then bumps semver,
  updates `engine/CHANGELOG.md`, and opens an admin-merged
  `chore/release/<version>` PR (protected `main` cannot take direct bot pushes).
- After merge, the workflow tags the release commit and publishes a **GitHub
  Release** with `repave-engine` wheel/sdist artifacts via `gh release create`.
- Authenticates with **`REPAVE_RELEASE_TOKEN`** (maintainer Administrator PAT).
- Docs-only merges skip the release job; `docs` / `chore` / `ci` commits do not
  bump version unless they include breaking changes.
- Release CI unsets `GITHUB_OUTPUT` for python-semantic-release CLI calls (see
  `psr()` in `.github/workflows/release.yml`); do not remove that when editing
  the workflow.

Feature PRs must **not** hand-edit `engine/pyproject.toml` version. Preview
changelog on `main`: `make changelog`.

See [CONTRIBUTING.md](CONTRIBUTING.md) for commit format and maintainer setup.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
