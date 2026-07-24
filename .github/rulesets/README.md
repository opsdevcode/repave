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
RULESET_ID="$(gh ruleset list --repo opsdevcode/repave --json id,name \
  -q '.[] | select(.name=="main branch") | .id')"
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

Docs-only pull requests rely on workflows that **always run** but skip work via
`.github/actions/ci-paths/` so required checks still report success. GitHub does
not support path-based exceptions inside rulesets for status checks.
