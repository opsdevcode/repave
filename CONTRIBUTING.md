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
- **Contracts are stable.** Changes to `schemas/blueprint.schema.json` or
  `schemas/inputs.schema.json` are breaking and require a version bump and
  discussion first.
- **Deterministic generation.** Rendering must be reproducible for the same
  inputs; avoid nondeterministic template logic.

## Development

Install [uv](https://docs.astral.sh/uv/), then from repo root:

```bash
make install
make test
```

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

CI runs these OSS tools on every push and pull request. **Docs-only** changes still
trigger workflows (so required status checks complete) but jobs skip heavy work when
the diff touches only:

- `docs/**`
- `**/*.md`
- `LICENSE`
- `.github/pull_request_template.md`

Detection lives in `.github/actions/ci-paths/` (same path list). Mixed PRs (for
example `docs/` plus `engine/`) run the full gate.

The `release` workflow keeps workflow-level `paths-ignore` for docs-only merges to
`main` (no release job for markdown-only commits).

### Branch ruleset (`main`)

Repository ruleset **main branch** (see `.github/rulesets/main-branch.json`)
requires on `main` for normal contributors:

- Changes merged via pull request (no approving review required — solo maintainer)
- Status checks: `test`, `Code quality (Ruff + mypy)`, `Security (Bandit + pip-audit)`,
  `commitlint`, `semantic-pull-request`, `operator-test`
- No force-push (`non_fast_forward`)

**Release automation bypass:** the ruleset grants **repository administrators**
(`bypass_actors`: Administrator role) so the account behind `REPAVE_RELEASE_TOKEN`
can push `chore(release): …` commits and tags to `main` after semantic-release.
Use a maintainer PAT with admin on this repo only for that secret; do not use it
for everyday feature work (use PRs like everyone else).

The **Release** and **Sync main branch ruleset** workflows apply the JSON from
this repo before publishing so bypass stays in sync with git.

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

Configuration lives in `engine/pyproject.toml`.

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

Pull request titles are also validated against Conventional Commits. Use the
same pattern for PR titles (for example `feat: add local docker quickstart`).

## Maintainer setup

`main` is protected so only maintainers can push directly. The release workflow
uses a repository secret **`REPAVE_RELEASE_TOKEN`**: a fine-grained or classic
PAT owned by a **maintainer with the Administrator role** on this repository
(`contents: write` is not enough if branch rules block direct pushes — admin
bypass is configured in `.github/rulesets/main-branch.json`).

After merging operator or engine features, semver advances automatically when
**Release** succeeds on `main` (`feat:` → minor, `fix:` → patch). Feature PRs
should not hand-edit `engine/pyproject.toml` version. If releases fail, check
Actions → **Release** and re-run the workflow after fixing ruleset/token issues.

Set or rotate it:

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
- Include tests for engine logic changes.
- Explain intent and any trade-offs in the PR description.

## Reporting issues

Use GitHub issues. For anything security-sensitive, follow
[SECURITY.md](SECURITY.md) instead of filing a public issue.
