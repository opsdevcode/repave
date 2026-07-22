# repave

**Governed, repeatable platform engineering — for many, not just the few.**

`repave` lets people who are not platform-engineering experts produce
production-ready automation (Terraform modules today, more later) by answering a
short form. The output is generated **deterministically** from versioned golden
paths, is forced through **mandatory quality/security gates**, and lands as a
**governed pull request** — so the standards set by your platform team are
enforced *by construction*, not by after-the-fact review.

The name says the intent: a **paved road** is how platform teams let many
developers move fast safely; `repave` continuously (re)lays that road — governed,
repeatable, and automated.

> Status: **v1.0.0.** The generation loop runs locally with no Kubernetes
> required. The self-healing reconciliation operator is planned for v1.1 (see
> [`operator/`](operator/)).

## Why repave

- **Enables many.** A web form maps to a golden path; no one needs to know
  Terraform/HCL to get a compliant module.
- **Governed by construction.** Generated artifacts must pass every configured
  gate (`fmt`, `validate`, `tflint`, `checkov`, docs) before a PR is mergeable.
  There is no bypass path.
- **Deterministic + repeatable.** The same inputs always render the same
  artifact (Copier templates), so output is reviewable and safe.
- **Bring your own standards.** Point a blueprint at your standards source and
  pin the version it encodes ("housed in one, rendered in many").
- **Runs locally first.** `docker compose up` and open a browser — see the whole
  loop without any cloud account.

## How it works

```text
Web form (inputs)  ->  Engine: render (Copier)  ->  Gates  ->  Module repository
                        \_ blueprint.yaml (input schema, standard ref, gate list) _/
```

Each generated module is written to **its own git repository** outside the
repave platform repo — never into `.repave-out/` inside repave.

1. A **blueprint** (`blueprints/<name>/blueprint.yaml`) declares its input
   schema, the standard version it encodes, its Copier template, and the gate
   list it must pass.
2. The **engine** validates inputs, renders the template deterministically, runs
   the gates, and materializes the module in its own repository.
3. The **portal/API** turns the blueprint's input schema into a form so
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
```

Each module becomes `$(modules_root)/tf-<module_name>/` — an independent git
repository planned for `https://github.com/<org>/tf-<module_name>`.

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
repository. Turn off dry-run to bootstrap a local git repo under your modules
root.

CLI equivalent (for development/CI, not the primary UX):

```bash
repave generate \
  --blueprint blueprints/terraform-module-generic \
  --input module_name=example \
  --input description="Example module" \
  --dry-run
```

## Repository layout

```text
schemas/       # frozen contracts: blueprint.schema.json, inputs.schema.json
engine/        # core generation engine (Python + Copier) + API/CLI
blueprints/    # versioned golden paths (reference packs)
examples/      # generic sample standards (bring-your-own-standards model)
deploy/local/  # docker compose + kind quickstart
operator/      # v1.1 placeholder: self-healing reconciliation (Operator SDK)
docs/          # concept docs
```

## Roadmap

- **v1.0** (current) — engine + `terraform-module-generic` golden path + gates +
  local run + CI, release automation, and test coverage.
- **v1.1** — reconciliation operator (`GoldenPathRepo` / `Blueprint` CRDs) that
  detects drift and standard-version bumps and opens remediation PRs across the
  generated estate (the "self-healing" headline).
- **v1.2+** — more golden paths (Ansible role, cloud resource modules), portal
  hardening, richer observability/SLOs, and wired GitHub PR creation.

## Releases

Versioning and GitHub releases are automated from
[Conventional Commits](https://www.conventionalcommits.org/) on `main` using
[python-semantic-release](https://python-semantic-release.readthedocs.io/).

- Merge a PR to `main` with a conventional commit title (`feat:`, `fix:`, etc.).
- CI runs tests; the release workflow then bumps the version, updates the
  changelog, tags, and publishes a GitHub Release with wheel artifacts.
- `docs`, `chore`, and `ci` commits do not trigger a release unless they
  include breaking changes.

No separate release PR is required.

See [CONTRIBUTING.md](CONTRIBUTING.md) for commit message format.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
