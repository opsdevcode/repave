# repave

**Governed, repeatable platform engineering — for many, not just the few.**

`repave` lets people who are not platform-engineering experts produce
production-ready automation (Terraform modules today, more later) by answering a
short form. The output is generated **deterministically** from versioned golden
paths, is forced through **mandatory quality/security gates**, and lands as a
**governed module repository on GitHub** — so the standards set by your platform
team are enforced *by construction*, not by after-the-fact review.

The name says the intent: a **paved road** is how platform teams let many
developers move fast safely; `repave` continuously (re)lays that road — governed,
repeatable, and automated.

> Status: **v1.14.** The generation loop runs locally with no Kubernetes
> required. Generated modules publish to separate git repositories and can be
> pushed to GitHub with `GITHUB_TOKEN`. Each scoped provider resource is
> rendered to its own `.tf` file; shared context lives in `locals.tf` against
> the in-repo module standard. Generated modules include layout and security
> Checkov policies (pack v1.2.0), a dedicated secrets gate, `.checkov.yml`,
> and a `repave.yaml` provenance file validated by the `provenance-drift` gate.
> The self-healing reconciliation operator is planned next
> (see [`operator/`](operator/)).

## Why repave

- **Enables many.** A web form maps to a golden path; no one needs to know
  Terraform/HCL to get a compliant module.
- **Governed by construction.** Generated artifacts must pass every configured
  gate (`fmt`, `validate`, `tflint`, `checkov`, `secrets`, `provenance-drift`, docs) before publish.
  There is no bypass path.
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

Fill the form for the bundled `terraform-module-generic` blueprint and submit.
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

## Repository layout

```text
schemas/       # frozen contracts: blueprint, golden-path artifact, inputs schemas
engine/        # core generation engine (Python + Copier) + API/CLI
blueprints/    # versioned golden paths (reference packs)
examples/      # sample standards and Checkov policy packs
deploy/local/  # docker compose + kind quickstart
operator/      # planned: self-healing reconciliation (Operator SDK)
docs/          # concept docs and [roadmap](docs/roadmap.md)
```

## Roadmap

**Current:** v1.14 — gate registry, artifact-type-aware `repave.yaml` provenance,
and `provenance-drift` gate on the terraform-module golden path.

High-level release history and detailed future planning (through **v2.0.0**) live in
[`docs/roadmap.md`](docs/roadmap.md). Add new future-state items there when
scoping work; keep this section as a short pointer only.

## Releases

Versioning and GitHub releases are automated from
[Conventional Commits](https://www.conventionalcommits.org/) on `main` using
[python-semantic-release](https://python-semantic-release.readthedocs.io/).

- Merge a PR to `main` with a conventional commit title (`feat:`, `fix:`, etc.).
- CI runs tests; the release workflow then bumps the version, updates the
  changelog, tags, and publishes a GitHub Release with wheel artifacts.
- Releases authenticate with the `REPAVE_RELEASE_TOKEN` repository secret so
  version commits can push to protected `main`.
- `docs`, `chore`, and `ci` commits do not trigger a release unless they
  include breaking changes.

No separate release PR is required.

See [CONTRIBUTING.md](CONTRIBUTING.md) for commit message format.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
