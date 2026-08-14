# Contributing to repave

Thanks for your interest in `repave`. **v1.14** added artifact-type-aware
`repave.yaml` provenance and the `provenance-drift` gate; **v1.17** will add the
reconciliation operator with mandatory local test docs — see
[`docs/roadmap.md`](docs/roadmap.md), [`docs/operator-local-dev.md`](docs/operator-local-dev.md),
and [`docs/operator-standards.md`](docs/operator-standards.md).
The most valuable contributions now are feedback on contracts, golden paths, and
operator design.

## Ground rules

- **Keep the core cloud-agnostic.** Nothing cloud-specific belongs in `engine/`.
  Clouds live only in `blueprints/`.
- **The gates are not optional.** Do not add a code path that lets generated
  output skip its configured gates.
- **Contracts are stable.** JSON Schemas under `schemas/` are frozen for the v2
  line; see [`docs/blueprint-versioning.md`](docs/blueprint-versioning.md) for
  `metadata.version` bump rules and schema change policy. Incompatible schema
  edits require discussion and a v3 migration plan — do not silently rename or
  remove required fields during v2.
- **Deterministic generation.** Rendering must be reproducible for the same
  inputs; avoid nondeterministic template logic.

## Development

**Product work targets `main`.** `v3.0.0` is the current line; [ADR 008](docs/adr/008-v3-branching-release-and-testing.md)
`next/v3` branching is superseded. Working guide: [`docs/v3-development.md`](docs/v3-development.md).
Identity: [ADR 009](docs/adr/009-v3-product-identity.md).

Install [uv](https://docs.astral.sh/uv/), then from repo root:

```bash
make install
make test
```

For day-to-day edits, **`make test-fast`** runs pytest with `-m "not slow"` and no
coverage (skips blueprint conformance and full generate + gate toolchain tests).
Run **`make test`** before you push; CI runs the full suite with **`pytest -n auto`**
(parallel workers) and enforces the **`fail_under = 75`** coverage threshold from
`engine/pyproject.toml` (`[tool.coverage.report]`). Optional **`make test-parallel`**
matches CI parallelism locally.

### Gate toolchain (CI, Compose, local)

CI and Release install pinned CLIs **and** app-service runtimes (Temurin 21,
.NET 10, Maven) via
[`.github/actions/gate-toolchain`](.github/actions/gate-toolchain), then run
**`repave doctor --strict`** (same pins as `deploy/local/gate-toolchain-pins.env`).
Do **not** add Java/.NET/Maven only in `ci.yml` — Release must use the same
composite or tags (and downstream EKS deploys) stall. `scripts/check_release_test_toolchain.py`
enforces that. The Compose image runs the same CLI check at **`docker build`** when
`INSTALL_GATE_TOOLCHAIN=1`.

Locally, after [`deploy/local/install-gate-toolchain.sh`](deploy/local/install-gate-toolchain.sh):

```bash
make gate-doctor
```

### Blueprint conformance

Every golden path under `blueprints/*/blueprint.yaml` must ship a sibling
`conformance.yaml` with fixture `inputs` and `required_files`. CI runs
`tests/test_blueprint_conformance.py` (render, gates, template hygiene). Optional `snapshot: true` enables `conformance.manifest.json`; refresh with
`make blueprint-conformance-update` when blueprint output changes (not on every engine release — manifest hashes ignore pinned `repave-engine==`, provenance engine version lines, and `repave.dev/{engine,blueprint,standard}-version` in `catalog-info.yaml`). Bump `metadata.version` per [`docs/blueprint-versioning.md`](docs/blueprint-versioning.md) when template output changes.

Or from `engine/`:

```bash
uv sync --extra dev
uv run pytest
```

When changing dependencies in `engine/pyproject.toml`, refresh the lockfile:

```bash
make lock
```

From repo root, quality and security checks:

```bash
make quality    # ruff lint + format check + mypy
make security   # bandit + pip-audit
make test
```

### Python quality and security tooling

#### Coding standards and security (all Python)

Every **`.py`** file in this repository follows the same conventions — not only
`engine/` and `scripts/`, but any Python added elsewhere in the monorepo.

| Resource | Purpose |
| --- | --- |
| [`.cursor/rules/python-standards.mdc`](.cursor/rules/python-standards.mdc) | Ruff, mypy, pytest, modern 3.12+ idioms |
| [`.cursor/rules/python-security.mdc`](.cursor/rules/python-security.mdc) | Subprocess, secrets, safe parsing, HTTP, dependencies |
| [`.cursor/skills/repave-python/SKILL.md`](.cursor/skills/repave-python/SKILL.md) | Local workflow, CI alignment, check commands |
| [`.cursor/skills/repave-python/reference.md`](.cursor/skills/repave-python/reference.md) | Detailed patterns and checklists |

Tool versions and Ruff/mypy/pytest settings live in **`engine/pyproject.toml`**.

CI runs Ruff, mypy, Bandit, and pip-audit on **`engine/src`** and
**`engine/tests`**. When you change Python under **`scripts/`** or other paths,
run the same tools on those files before opening a PR:

```bash
cd engine
uv run ruff check ../scripts
uv run ruff format ../scripts
uv run bandit -r ../scripts -c pyproject.toml   # when security-relevant
```

Packaged engine changes: use repo-root **`make format`**, **`make quality`**,
**`make security`**, and **`make test`** as below.

#### Coding standards and security (all JavaScript)

Every **`.js`**, **`.mjs`**, and **`.cjs`** file follows the same conventions — portal
static **`repave.js`**, **`.github/commitlint.config.mjs`**, and any future JS paths.

| Resource | Purpose |
| --- | --- |
| [`.cursor/rules/javascript-standards.mdc`](.cursor/rules/javascript-standards.mdc) | Portal IIFE patterns, ESLint, portal UI contracts |
| [`.cursor/rules/javascript-security.mdc`](.cursor/rules/javascript-security.mdc) | XSS-safe DOM, storage, no eval |
| [`.cursor/skills/repave-javascript/SKILL.md`](.cursor/skills/repave-javascript/SKILL.md) | Local workflow and CI |
| [`.cursor/skills/repave-javascript/reference.md`](.cursor/skills/repave-javascript/reference.md) | DOM XSS checklist, event contracts |

Lint config: root **`eslint.config.js`** and **`package.json`**.

```bash
npm ci
make js-lint
```

ESLint runs in CI inside **Python quality and security** when the change is not
docs-only. Portal behavior changes: run **`make test-fast`** (or **`make test`**) — see
**`engine/tests/test_api.py`**.

Hosted Backstage (`backstage/`) is a separate Yarn/TypeScript app
([ADR 011](docs/adr/011-hosted-backstage-idp.md)). Portal no-bundler rules do
not apply. After changing that tree:

```bash
make backstage-lint
cd backstage && yarn test --watch=false
```

CI: [`.github/workflows/backstage.yml`](.github/workflows/backstage.yml).
See [`.cursor/skills/repave-backstage/SKILL.md`](.cursor/skills/repave-backstage/SKILL.md).

#### Coding standards and security (all Go)

Every **`.go`** file follows the same conventions — the **`operator/`** module today,
and any Go added elsewhere in the monorepo later.

| Resource | Purpose |
| --- | --- |
| [`.cursor/rules/golang-standards.mdc`](.cursor/rules/golang-standards.mdc) | Kubebuilder layout, golangci-lint, tests, generation |
| [`.cursor/rules/golang-security.mdc`](.cursor/rules/golang-security.mdc) | Secrets, HTTP/git, RBAC, subprocess |
| [`.cursor/skills/repave-golang/SKILL.md`](.cursor/skills/repave-golang/SKILL.md) | Local workflow and CI |
| [`.cursor/skills/repave-golang/reference.md`](.cursor/skills/repave-golang/reference.md) | Checklists and community links |
| [`docs/operator-standards.md`](docs/operator-standards.md) | Authoritative operator/CRD product standards |

Lint config: **`operator/.golangci.yml`**. Go version: **`operator/go.mod`**.

```bash
make operator-lint
make operator-test
```

After API or **`+kubebuilder:rbac`** changes: **`cd operator && make manifests generate`**
and commit generated **`config/crd/bases`**, **`config/rbac`**, and deepcopy files.
CI job **`operator-test`** runs when the diff includes **`operator/**`**.

CI runs these OSS tools on every push and pull request. **Docs-only** changes still trigger workflows (so required status checks complete) but jobs skip heavy work when
the diff touches only:

- `docs/**`
- `.cursor/**` (Cursor rules and skills — no runtime effect)
- `**/*.md`
- `LICENSE`
- `.github/pull_request_template.md`
- `.github/actions/ci-paths/**` (docs-only skip detection itself)
- `scripts/capture_portal_screenshots.sh`, `scripts/sync_doc_versions.py`
- Root `Makefile` (local dev entrypoints such as `make serve` for the portal
  quickstart)

Detection lives in `.github/actions/ci-paths/` (same path list). Mixed PRs (for
example `docs/` plus `engine/`) run the full gate. If you change root `Makefile`
test or quality targets, run `make quality && make test` locally even when CI skips.

The `release` workflow keeps workflow-level `paths-ignore` for docs-only merges to
`main` (no release job for markdown-only commits).

### Helm chart CI

**`chart-validate`** (helm lint + template) and **`chart-smoke`** (kind + Docker install)
run on every pull request. Unrelated diffs skip heavy steps via
`.github/actions/chart-ci-paths/`; every push to **`main`** runs both jobs in full.
Locally: `make chart-validate` and `make chart-smoke`.

When bumping a third-party GitHub Action, update both the workflow `uses:` SHA and
[`.github/action-pins.json`](.github/action-pins.json); run `python3 scripts/check-action-pins.py`.
See [`docs/supply-chain.md`](docs/supply-chain.md).

### Branch ruleset (`main`)

Repository ruleset **main branch** (see `.github/rulesets/main-branch.json`)
requires on `main` for normal contributors:

- Changes merged via pull request (no approving review required — solo maintainer)
- Status checks: `test`, `Python quality and security`, `commitlint`,
  `semantic-pull-request`, `operator-test`, `operator-e2e`, `chart-validate`, `chart-smoke`
- No force-push (`non_fast_forward`)

**Release automation bypass:** the ruleset grants **repository administrators**
(`bypass_actors`: Administrator role) so the account behind `REPAVE_RELEASE_TOKEN`
can push `chore(release): …` commits and tags to `main` after semantic-release.
Use a maintainer PAT with admin on this repo only for that secret; do not use it
for everyday feature work (use PRs like everyone else).

The **Release** and **Sync main branch ruleset** workflows apply the JSON from
this repo before publishing so bypass stays in sync with git. A failed ruleset sync
blocks release (fix the JSON or `gh` permissions before retrying).

### Operator kind e2e

**`operator-e2e`** (kind + Docker) is a required check on every pull request. PRs
that only touch docs-only paths (same list as above) or paths outside
`operator/`, `engine/`, `blueprints/`, and gate-toolchain deploy files skip the
heavy run but still report success — see `.github/actions/operator-e2e-paths/`.
Every push to **`main`** and the **nightly** schedule run the full harness so
skipped PRs do not leave `main` untested for long.

Local: `make operator-e2e` ([`docs/operator-local-dev.md`](docs/operator-local-dev.md)).

Re-apply or update the ruleset after editing the JSON:

```bash
gh api --method POST repos/opsdevcode/repave/rulesets \
  --input .github/rulesets/main-branch.json
```

To update an existing ruleset, `PUT repos/opsdevcode/repave/rulesets/{id}` with the
same payload plus changes. List IDs with `gh ruleset list --repo opsdevcode/repave`.

Classic branch protection may still restrict who can push directly to `main`; the
ruleset adds required checks and PR rules on top.

Tools on full CI runs:

| Tool | Purpose |
| --- | --- |
| [Ruff](https://docs.astral.sh/ruff/) | Linting and formatting |
| [mypy](https://mypy-lang.org/) | Static type checking |
| [Bandit](https://bandit.readthedocs.io/) | Python SAST security scan |
| [pip-audit](https://pypi.org/project/pip-audit/) | Dependency vulnerability scan (OSV) |

Configuration lives in `engine/pyproject.toml` (`repo_dir = ".."`, changelog at
`engine/CHANGELOG.md`). Release commits include changelog updates from
`semantic-release version`; the Release workflow also opens a one-off sync PR if
history and `CHANGELOG.md` diverge (run `make changelog` on `main` locally to
preview).

After each semver bump, Release runs `scripts/sync_doc_versions.py` so
`README.md`, `docs/roadmap.md` (**Current release** and path `today` line),
`docs/portal-design.md`, `docs/demo-verification.md`, and `docs/operator-ga.md`
match the new engine tag. It also syncs Helm `Chart.yaml` files and
`versions.lock` (umbrella contract matrix). Locally: `make sync-doc-versions`,
`make sync-chart-versions`, `make sync-versions-lock`
(or `python3 scripts/sync_doc_versions.py --check` /
`python3 scripts/sync_versions_lock.py --check` to verify).

Feature PRs must **not** edit `docs/roadmap.md` **Current release** — Release owns
that line (keep a blank line after it so status edits merge cleanly). Update
**In progress** / **Shipped on `main`** and section `**Status:**` lines only.

### Roadmap and docs housecleaning (pre-commit)

When shipping or closing a theme, include roadmap housecleaning in the same PR.
This is **not** chart validation — do not run `make chart-validate` unless
`deploy/k8s/chart/**` changed.

**Roadmap (`docs/roadmap.md`):**

- Refresh **In progress** and **Shipped on `main`** when status changes.
- Update the theme table and path-to-v2 tree for shipped/partial themes.
- Fix section `**Status:**` lines; remove stale `Not started`, wrong branch refs,
  and “blocked behind” wording for work already on `main`.
- Mark superseded sections with a link to the shipped replacement.

**Related docs:**

- Cross-link from operator-facing docs (`docs/durability.md`, `docs/verify.md`,
  `docs/operations/**`, `deploy/k8s/**/README.md`) when behavior or runbooks change.
- Keep “still open” / follow-up bullets consistent with the roadmap header.

**Docs-only commits** skip `make format`, `make quality`, and `make test`. Optionally
run `make sync-doc-versions --check` only if you touched version pointer lines Release
normally owns (avoid editing **Current release** in feature PRs).

## Commit messages (Conventional Commits)

This repository uses [Conventional Commits](https://www.conventionalcommits.org/)
for automated releases via
[python-semantic-release](https://python-semantic-release.readthedocs.io/).

Format:

```text
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

Common types:

- `feat:` — new feature (**minor** version bump)
- `fix:` — bug fix (**patch** version bump)
- `feat!:` or `fix!:` / `BREAKING CHANGE:` footer — **major** version bump
- `docs:`, `chore:`, `ci:`, `refactor:`, `test:`, `build:` — no release bump unless they include breaking changes

Examples:

```text
feat(engine): add ansible-role blueprint scaffold
fix(gates): skip tflint when binary is unavailable
feat!: rename blueprint input schema fields
```

Pull request titles are also validated against Conventional Commits
(`semantic-pull-request` in `.github/workflows/conventional-commits.yml`). Use the
same pattern for PR titles (for example `feat: add local docker quickstart`).
The subject after `: ` must **not** start with an uppercase letter
(for example prefer `feat(portal): add Guided/Advanced forms…` over
`feat(portal): Guided/Advanced forms…`).

## Maintainer setup

`main` is protected so only maintainers can push directly. The release workflow
uses a repository secret **`REPAVE_RELEASE_TOKEN`**: a fine-grained or classic
PAT owned by a **maintainer with the Administrator role** on this repository
(`contents: write` is not enough if branch rules block direct pushes — admin
bypass is configured in `.github/rulesets/main-branch.json`).

After merging operator or engine features, semver advances automatically when
**Release** succeeds on `main` (`feat:` → minor, `fix:` → patch). Feature PRs
should not hand-edit `engine/pyproject.toml` version. Release opens and
admin-merges a `chore/release/*` PR (Administrator ruleset bypass) because rulesets block direct pushes to `main` even for some administrator
tokens. The workflow tags the release commit after merge and creates the GitHub
Release (with wheel artifacts) via `gh release create`; it also repairs a tagged
version that has no GitHub Release yet.

**Do not break automated versioning.** The Release job must keep producing
semver tags and GitHub Releases after `feat:` / `fix:` merges to `main`.
Those tags trigger deploy pipelines (for example `repave-aws-infra` → EKS).

Release runs the **full** engine pytest suite before semantic-release. Any new
runtime needed by dry-run gates belongs in
[`.github/actions/gate-toolchain`](.github/actions/gate-toolchain) so CI and
Release stay identical — never wire it into `ci.yml` alone.

python-semantic-release 10.3+ writes GitHub Actions step outputs whenever
`GITHUB_OUTPUT` is set. Our flow uses `--no-push --no-tag` and never populates
`commit_sha`, so every `semantic-release` invocation in
`.github/workflows/release.yml` must go through the `psr()` helper
(`env -u GITHUB_OUTPUT …`). Setting `GITHUB_ACTIONS=false` alone does **not**
prevent the `commit_sha` failure.

Set or rotate **`REPAVE_RELEASE_TOKEN`**:

```bash
gh secret set REPAVE_RELEASE_TOKEN --repo opsdevcode/repave
```

Org admins may instead store the same secret at org scope for reuse across
repositories:

```bash
gh secret set REPAVE_RELEASE_TOKEN --org opsdevcode --visibility private
```

## Pull requests

- Keep changes small and focused.
- Use a Conventional Commit-style PR title.
- Wait for required checks, then merge the pull request on GitHub.
- Include tests for engine logic changes.
- Explain intent and any trade-offs in the PR description.

## Reporting issues

Use GitHub issues. For anything security-sensitive, follow
[SECURITY.md](SECURITY.md) instead of filing a public issue.
