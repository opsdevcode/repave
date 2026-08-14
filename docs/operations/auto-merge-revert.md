# Auto-merge kill switch and revert

Break-glass for the v3 auto-merge path. Plan/upgrade and the portal upgrade
preview report `allowed` or `review required`. When Allowed,
`apply-upgrade --open-pr` and the operator remediation publisher squash-merge
via `PUT /repos/{owner}/{repo}/pulls/{pull_number}/merge`. This runbook stops
further merges and undoes a landed pin bump.

Autonomy safety: [ADR 008](../adr/008-v3-branching-release-and-testing.md).
Decision function: `decide_auto_merge()` in
`engine/src/repave_engine/auto_merge.py` (pure; no I/O). Merge is a separate
step after the PR exists.

## When to use this

| Situation | Action |
| --- | --- |
| Unexpected `allowed` verdicts, bad pin, or fleet SLO worry | Flip the [kill switch](#1-kill-switch) first |
| Upgrade PR already squash-merged (`auto_merge.merged`) | [Revert the merge commit](#2-revert-a-merged-pull-request) |
| `apply-upgrade` committed but the PR did not merge | [Revert the apply commit](#3-revert-an-apply-commit) |
| Operator opened a remediation PR that must not land | [Close the open PR](#4-open-pr-that-must-not-land) |
| Prove the path in CI or a scratch checkout | [Local demonstration](#5-local-demonstration) |

Do not default-on `v3.enabled` or `v3.auto_merge.enabled` in hosted values.

## 1. Kill switch

`v3.auto_merge.kill_switch: true` demotes the **whole fleet** to review-required in one
config change. It wins over an otherwise eligible mechanical pin bump and prevents
the next `--open-pr` from calling GitHub merge.

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

## 2. Revert a merged pull request

`--open-pr` JSON includes `auto_merge.merged` and `auto_merge.merge_commit_sha` when
the squash merge succeeded. Revert that commit on the **base** branch (usually
`main`), not the upgrade branch.

```bash
cd /path/to/target-module
git fetch origin
git switch main
git pull --ff-only
git revert --no-edit "$MERGE_COMMIT_SHA"
git push origin main
```

`$MERGE_COMMIT_SHA` is `auto_merge.merge_commit_sha` from apply JSON, or the
squash commit GitHub shows on the merged PR. Flip the [kill switch](#1-kill-switch)
before you push so a later plan does not re-merge the same pin.

## 3. Revert an apply commit

`apply-upgrade` without a successful merge writes the pin bump onto `--git-branch`.
The JSON payload includes `commit_sha` and `git_branch`.

```bash
cd /path/to/target-module
git switch "$GIT_BRANCH"          # branch from apply-upgrade, e.g. repave/upgrade-…
git revert --no-edit "$COMMIT_SHA"
```

If that branch was pushed, push the revert commit. Close the upgrade PR if it is
still open.

If the apply never left the local clone, you can instead reset the branch to the
parent of `commit_sha` when you are sure nothing else landed on it:

```bash
git switch "$GIT_BRANCH"
git reset --hard "${COMMIT_SHA}^"
```

Prefer `git revert` when the branch may be shared.

Then re-plan. The working tree should match the pre-apply pins in `repave.yaml`.

## 4. Open PR that must not land

If merge did not run (`auto_merge.merged` false), close the PR and delete the
remote branch. Flip the [kill switch](#1-kill-switch) so a later plan does not
report `allowed` while you clean up.

```bash
gh pr close "$PR_NUMBER" --delete-branch
```

## 5. Local demonstration

Until a dedicated GitHub test organization exists, demonstrate revert on the operator
fixture (same path CI uses). From a git checkout of this repo:

```bash
cd engine
uv run pytest tests/test_upgrade_plan.py::test_apply_upgrade_commit_is_revertible -q --no-cov
uv run pytest tests/test_upgrade_plan.py::test_open_upgrade_pull_request_merges_when_auto_merge_allowed -q --no-cov
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
