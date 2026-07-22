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

> Status: **v0.1 (pre-release).** The generation loop runs locally with no
> Kubernetes required. The self-healing reconciliation operator is planned for
> v0.2 (see [`operator/`](operator/)).

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
Web form (inputs)  ->  Engine: render (Copier)  ->  Gates  ->  Governed PR
                        \_ blueprint.yaml (input schema, standard ref, gate list) _/
```

1. A **blueprint** (`blueprints/<name>/blueprint.yaml`) declares its input
   schema, the standard version it encodes, its Copier template, and the gate
   list it must pass.
2. The **engine** validates inputs, renders the template deterministically, runs
   the gates, and (optionally) opens a governed pull request.
3. The **portal/API** turns the blueprint's input schema into a form so
   non-experts can drive it without a command line.

## Quickstart (local, no Kubernetes)

```bash
cd deploy/local
docker compose up --build
# open http://localhost:8080
```

Fill the form for the bundled `terraform-module-generic` blueprint and submit.
In dry-run mode (default) you'll see the rendered files and gate results. Provide
a GitHub token to enable the governed-PR output.

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
operator/      # v0.2 placeholder: self-healing reconciliation (Operator SDK)
docs/          # concept docs
```

## Roadmap

- **v0.1** — engine + `terraform-module-generic` golden path + gates + local run.
- **v0.2** — reconciliation operator (`GoldenPathRepo` / `Blueprint` CRDs) that
  detects drift and standard-version bumps and opens remediation PRs across the
  generated estate (the "self-healing" headline).
- **v0.3+** — more golden paths (Ansible role, cloud resource modules), portal
  hardening, richer observability/SLOs.

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
