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

**Bypass:** `main-branch.json` includes an Administrator role bypass so
semantic-release can push version commits with `REPAVE_RELEASE_TOKEN`. Re-apply
after editing bypass or rules.

**Merging pull requests:** merge via the normal GitHub **Merge pull request** (or
squash/rebase, per repo settings) once required checks pass.

**Release automation:** `chore/release/*` PRs merged with `REPAVE_RELEASE_TOKEN`
use the Administrator ruleset bypass.

Docs-only pull requests rely on workflows that **always run** but skip heavy steps
via `.github/actions/ci-paths/` so required checks still report success (fast
no-op jobs). Path list matches [CONTRIBUTING.md](../../CONTRIBUTING.md#python-quality-and-security-tooling).
GitHub does not support path-based exceptions inside rulesets for status checks.
