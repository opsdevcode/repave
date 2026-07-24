---
name: repave-release
description: >-
  Fix or change repave Release workflow and python-semantic-release config.
  Use for Release CI failures, semver bumps on main, REPAVE_RELEASE_TOKEN, changelog sync.
---

# repave Release

Read `.github/workflows/release.yml` and `engine/pyproject.toml` `[tool.semantic_release]`.

## Invariants

- Run PSR from **`engine/`** cwd in CI.
- **`GITHUB_ACTIONS=false`** on the release shell step (custom publish; no PSR `commit_sha` output).
- **`upload_to_vcs_release = false`** — publish via `gh release create` in workflow.
- Version file paths are **relative to `engine/`**, not `engine/engine/`.
- Never push version commits directly to `main`; use `chore/release/*` + `gh pr merge --admin`.

## Checklist after editing release config

1. Dry-run mentally: merge `feat:` → version bump → release branch → admin merge → tag → GH release.
2. Confirm `pull-requests: write` on workflow.
3. Confirm operator + engine tests still run before release step.

See also repo rule `.cursor/rules/repave-release.mdc` and root `CONTRIBUTING.md`.
