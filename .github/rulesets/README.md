# Repository rulesets

Version-controlled definition of the **main branch** ruleset applied to
`opsdevcode/repave`.

## Apply

Requires admin on the repository:

```bash
gh api --method POST repos/opsdevcode/repave/rulesets \
  --input .github/rulesets/main-branch.json
```

If a ruleset named `main branch` already exists, update it instead:

```bash
RULESET_ID="$(gh api repos/opsdevcode/repave/rulesets --jq '.[] | select(.name=="main branch") | .id')"
gh api --method PUT "repos/opsdevcode/repave/rulesets/${RULESET_ID}" \
  --input .github/rulesets/main-branch.json
```

Inspect what applies to a branch:

```bash
gh ruleset check main --repo opsdevcode/repave
```

## Rollout (first-time merge queue)

1. Merge to `main` the PR that adds `merge_group` triggers to all required-check
   workflows (`ci.yml`, `python-quality-security.yml`, `operator.yml`,
   `conventional-commits.yml`).
2. Apply this ruleset (PUT) or merge ruleset JSON to `main` so **Sync main branch
   ruleset** updates GitHub.
3. Confirm `gh ruleset check main` lists `merge_queue` and that a test PR can enter
   the queue.

Do **not** apply the `merge_queue` rule before step 1 — the queue will wait forever
for checks that never run.

**Bypass:** `main-branch.json` includes an Administrator role bypass so
semantic-release can push version commits with `REPAVE_RELEASE_TOKEN`. Re-apply
after editing bypass or rules.

## Merge queue

The ruleset requires merges to `main` through GitHub’s **merge queue** (squash
merge, `HEADGREEN` grouping). Required checks must run on both `pull_request`
and `merge_group`; CI workflows in `.github/workflows/` include both triggers.

**After changing merge queue settings or adding required checks**, re-apply the
ruleset (see above) and confirm workflows list `merge_group`.

**Merging pull requests:** use **Merge when ready** / add to queue on GitHub.
Direct “Merge pull request” is disabled when the merge queue rule is active.

**Release automation:** `chore/release/*` PRs merged with `REPAVE_RELEASE_TOKEN`
use the Administrator ruleset bypass and do not go through the queue.

Docs-only pull requests rely on workflows that **always run** but skip work via
`.github/actions/ci-paths/` so required checks still report success. GitHub does
not support path-based exceptions inside rulesets for status checks.
