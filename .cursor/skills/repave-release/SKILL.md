---
name: repave-release
description: >-
  Fix or change repave Release workflow and python-semantic-release config.
  Use for Release CI failures, semver bumps on main, REPAVE_RELEASE_TOKEN,
  changelog sync, or any commit_sha / GITHUB_OUTPUT / automated versioning issue.
---

# repave Release

Automated versioning on `main` must keep working. Treat Release failures as
P0 until a tag + GitHub Release exist for the expected bump.

Read `.github/workflows/release.yml` and `engine/pyproject.toml` `[tool.semantic_release]`.

## Invariants (do not regress)

- Run PSR from **`engine/`** cwd in CI.
- **Every** PSR CLI call uses the workflow `psr()` helper:
  `env -u GITHUB_OUTPUT uv run semantic-release …`
  PSR 10.3+ requires `commit_sha` when `GITHUB_OUTPUT` is set; our custom
  `--no-push --no-tag` + `gh release create` flow never sets it.
- **`GITHUB_ACTIONS=false` is NOT a substitute** — it does not disable GHA
  output writing.
- **`upload_to_vcs_release = false`** — publish via `gh release create` in workflow.
- Version file paths are **relative to `engine/`**, not `engine/engine/`.
- Never push version commits directly to `main`; use `chore/release/*` +
  `gh pr merge --admin`.

## Debug a failed Release run

```bash
gh run view <run-id> --repo opsdevcode/repave --log-failed
```

| Error | Fix |
|-------|-----|
| `some required outputs were not set: commit_sha` | Ensure `psr()` / `env -u GITHUB_OUTPUT`; do **not** “fix” with only `GITHUB_ACTIONS=false` |
| `engine/engine/pyproject.toml` | Version paths relative to `engine/` only |
| GH013 push to main | Release PR + `--admin` merge (already in workflow) |
| No GitHub Release for tag | `publish_github_release` repair block |

## Checklist after editing release config

1. Confirm every `semantic-release` invocation still goes through `psr()`.
2. Dry-run mentally: merge `feat:` → version bump → release branch → admin merge →
   tag → GH release.
3. Confirm `pull-requests: write` on workflow.
4. Confirm operator + engine tests still run before release step.
5. After merge to `main`, watch the Release run until tag + release exist.
6. Release runs `scripts/sync_doc_versions.py` and commits every path from
   `python3 scripts/sync_doc_versions.py --list-paths` (not a hardcoded subset).

See also repo rule `.cursor/rules/repave-release.mdc` and root `CONTRIBUTING.md`.
