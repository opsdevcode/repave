# Auto-merge kill switch and revert

Break-glass for the v3 auto-merge **verdict**. Plan/upgrade and the portal upgrade
preview report `allowed` or `review required`. **Apply does not merge a GitHub pull
request.** This runbook stops further `allowed` verdicts and undoes an applied
mechanical pin bump.

Autonomy safety: [ADR 008](../adr/008-v3-branching-release-and-testing.md). Decision
function: `decide_auto_merge()` in `engine/src/repave_engine/auto_merge.py`.

## When to use this

| Situation | Action |
| --- | --- |
| Unexpected `allowed` verdicts, bad pin, or fleet SLO worry | Flip the [kill switch](#1-kill-switch) first |
| `repave apply-upgrade` / `repave update --no-dry-run` already committed | [Revert the apply commit](#2-revert-an-apply-commit) |
| Operator opened a remediation PR (`--open-pr`) that must not land | [Close or leave the PR](#3-open-pr-that-must-not-land) |
| Prove the path in CI or a scratch checkout | [Local demonstration](#4-local-demonstration) |

Do not default-on `v3.enabled` or `v3.auto_merge.enabled` in hosted values.

## 1. Kill switch

`v3.auto_merge.kill_switch: true` demotes the **whole fleet** to review-required in one
config change. It wins over an otherwise eligible mechanical pin bump.

### Config file

In `repave.config.yaml` (engine repo root the portal/CLI load):

```yaml
v3:
  enabled: true
  auto_merge:
    enabled: true
    kill_switch: true
```

Reload / roll the portal so it re-reads the ConfigMap. Confirm on the next plan:

```bash
repave plan-upgrade --target-repo /path/to/module --format json
```

Expect `auto_merge.allowed` false and a reason that names `v3.auto_merge.kill_switch`.
The portal upgrade preview shows **Review required** with the same reason.

To restore mechanical verdicts later, set `kill_switch: false` (keep `v3.auto_merge.enabled`
only if you still want the opt-in). Setting `v3.auto_merge.enabled: false` also denies,
and names that key instead.

### Helm

```bash
helm upgrade repave ./deploy/k8s/chart \
  --reuse-values \
  --set repave.v3.enabled=true \
  --set repave.v3.autoMerge.killSwitch=true \
  --wait --timeout 10m
```

`repave.v3.autoMerge.enabled` requires `repave.v3.enabled` (chart fail-closed, same as
developer lab). Defaults are off. This is **not** a Helm rollback of the portal chart —
see [upgrade-and-rollback.md](upgrade-and-rollback.md) for image/chart rollback.

## 2. Revert an apply commit

`apply-upgrade` writes the rendered pin bump onto `--git-branch` and creates a commit.
The JSON payload includes `commit_sha` and `git_branch`.

```bash
cd /path/to/target-module
git switch "$GIT_BRANCH"          # branch from apply-upgrade, e.g. repave/upgrade-…
git revert --no-edit "$COMMIT_SHA"
```

If that branch was pushed, push the revert commit. Do **not** merge the original
upgrade PR (repave does not auto-merge it today).

If the apply never left the local clone, you can instead reset the branch to the
parent of `commit_sha` when you are sure nothing else landed on it:

```bash
git switch "$GIT_BRANCH"
git reset --hard "${COMMIT_SHA}^"
```

Prefer `git revert` when the branch may be shared.

Then re-plan. The working tree should match the pre-apply pins in `repave.yaml`.

## 3. Open PR that must not land

`--open-pr` / `open_upgrade_pull_request` pushes a branch and opens a GitHub PR. Close
that PR (or leave it unmerged) and delete the remote branch if you do not want the
pin bump. Flip the [kill switch](#1-kill-switch) so a later plan does not report
`allowed` while you clean up.

Repave does not merge that PR.

## 4. Local demonstration

Until a dedicated GitHub test organization exists, demonstrate revert on the operator
fixture (same path CI uses). From a git checkout of this repo:

```bash
cd engine
uv run pytest tests/test_upgrade_plan.py::test_apply_upgrade_commit_is_revertible -q --no-cov
uv run pytest tests/test_auto_merge.py::test_kill_switch_wins_over_an_otherwise_eligible_change -q --no-cov
```

Manual walkthrough (scratch module, no GitHub):

1. Copy `operator/testdata/modules/terraform-minimal` to a temp git repo and commit
   `repave.yaml`.
2. Enable `v3.enabled` and `v3.auto_merge.enabled` in the **engine**
   `repave.config.yaml` you pass as repo root (do not commit a root config).
3. `repave plan-upgrade --target-repo "$TMP" --format json` — note `auto_merge`.
4. `repave apply-upgrade --target-repo "$TMP" --git-branch repave/demo-upgrade --commit-message "demo pin bump"`.
5. `git -C "$TMP" revert --no-edit` the printed `commit_sha`.
6. Set `v3.auto_merge.kill_switch: true` and plan again — expect review required.

Record date, fixture path, and pass/fail in your change record if this is a game-day
drill. Do not treat a green unit test as a hosted fleet SLO.

## Related

- [Service operations](README.md)
- [In-cluster upgrade and rollback](upgrade-and-rollback.md) — portal/API Helm, not module pins
- [`docs/v3-development.md`](../v3-development.md)
- [`repave.config.yaml.example`](../../repave.config.yaml.example) — `v3.auto_merge` knobs
