# Validate github-repo → fleet → GoldenPathRepo

Ops checklist for the path that lands after a successful
[`github-repo-generic`](../github-repo-goldpath.md) apply: best-effort fleet
register, then operator fleetsync or `repave fleet-manifests` emitting a
`GoldenPathRepo` (GPR). The engine never calls Kubernetes.

Related: [Fleet registry](../fleet-registry.md), [GitHub App auth](../github-app-auth.md),
[`make chart-smoke-fleet-snapshot`](../../deploy/k8s/chart/README.md).

## What success looks like

| Signal | Expected |
| --- | --- |
| Apply message | Contains `Fleet registered: https://github.com/<org>/<repo>` (or an explicit fleet-disabled / register-failed line) |
| Registry JSONL | `event=register` for that `repo_url` with `blueprint_name=github-repo-generic` |
| Fleetsync | GPR with label `repave.dev/managed-by: repave-fleet` and matching `spec.repoURL` / `spec.desiredPins` |
| GitOps path | `repave fleet-manifests` renders the same GPR YAML under the output directory |

**Pin nuance:** auto-register stores **github-repo-generic** pins (standard
`standards/github/repo-provisioning-standard.md`). After you apply a second golden
path (Terraform, app-service, …) into the repo, re-register (or update pins) so the
GPR tracks the workload blueprint the operator should drift against.

## Tier A — no live GitHub, no cluster (fast)

Simulates the register step the pipeline performs after a successful github-repo
apply, then renders GPR manifests.

```bash
# From repo root
make validate-github-repo-fleet
# or: ./scripts/validate-github-repo-fleet.sh
```

Optional deeper unit pass:

```bash
VALIDATE_GITHUB_REPO_FLEET_UNITS=1 make validate-github-repo-fleet
```

**Success:** script exits 0; printed JSON shows `github-repo-generic@0.2.0`;
manifest YAML under the work directory has `kind: GoldenPathRepo` and
`blueprintName: github-repo-generic`.

Manual equivalent:

```bash
export REPAVE_FLEET_FILE=/tmp/repave-fleet-smoke/registry.jsonl
mkdir -p "$(dirname "$REPAVE_FLEET_FILE")"

cd engine
uv run repave register https://github.com/example-org/platform-demo \
  --repo-root .. \
  --blueprint github-repo-generic \
  --blueprint-version 0.2.0 \
  --standard-source standards/github/repo-provisioning-standard.md \
  --standard-version 1.1.0

uv run repave fleet --repo-root .. --format json
uv run repave fleet-manifests --repo-root .. \
  --output /tmp/fleet-manifests-smoke \
  --namespace repave-system \
  --kustomization --gitops-readme --prune
```

## Tier B — no live GitHub, kind cluster

Validates fleetsync create/prune, operator status snapshot, and platform campaign
actions. Uses the seeded `acme/*` registry (not github-repo-generic), which is
enough to prove register → GPR → prune without creating org repos.

```bash
make chart-smoke-fleet-snapshot

# Keep the cluster for kubectl inspection
CHART_SMOKE_FLEET_SNAPSHOT_KEEP_CLUSTER=1 make chart-smoke-fleet-snapshot
```

**Success criteria** (also asserted by the smoke script):

- ≥2 GPRs with `repave.dev/managed-by=repave-fleet` after registry seed
- After portal/API unregister of one URL, that GPR is pruned; the other remains
- Operator status snapshot `version==2` matches remaining fleet repos
- `GET /api/v2/fleet` shows the remaining repos plus operator snapshot overlay
  (`GET /platform/fleet` is a Backstage pointer)

Inspect:

```bash
kubectl get goldenpathrepo -A -l repave.dev/managed-by=repave-fleet
kubectl get goldenpathrepo -n <ns> <name> -o jsonpath='{.spec.desiredPins}{"\n"}'
```

Optional: seed a github-repo-shaped register into the shared PVC registry (same
shape as Tier A), wait one fleetsync interval, and confirm a GPR named like
`example-org-platform-demo` appears. Do not run fleetsync and `kubectl apply` of
`fleet-manifests` against the same namespace for the same URLs (double reconcile).

## Tier C — real GitHub org (optional)

Requires `GITHUB_TOKEN` or GitHub App credentials and `REPAVE_GITHUB_ORG` /
`output.github_org`. Fleet must be enabled (`fleet.enabled` + `fleet.file`, or
`REPAVE_FLEET_FILE`).

```bash
# Dry-run first (no remote create, no register)
repave create-repo --name platform-demo-smoke \
  --visibility private \
  --ruleset-profile default-pr \
  --dry-run

# Apply (creates repo, overlay, optional ruleset/teams, then best-effort register)
repave create-repo --name platform-demo-smoke \
  --visibility private \
  --ruleset-profile default-pr \
  --no-dry-run
```

Or use Portal → Catalog → Platform → `github-repo-generic` → Apply.

**Success:**

1. Apply output includes `Fleet registered: https://github.com/<org>/platform-demo-smoke`
2. `repave fleet --format json` lists that URL with `github-repo-generic` pins
3. Within one fleetsync interval (or after `repave fleet-manifests` + GitOps apply):

   ```bash
   kubectl get goldenpathrepo -A -l repave.dev/managed-by=repave-fleet \
     -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.repoURL}{"\n"}{end}'
   ```

4. Optional drift: operator phase for that GPR settles once the remote `repave.yaml`
   is readable (inventory may report OutOfDate until pins match a later golden path)

Clean up: archive/delete the smoke repo in GitHub; `repave unregister <url>` (or
portal unregister) so fleetsync prunes the GPR.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Apply says `Fleet disabled; run repave register…` | Fleet not configured or `fleet.enabled: false` | Set `fleet.enabled: true` and `fleet.file`, or `REPAVE_FLEET_FILE`; re-run apply or `repave register` |
| `Fleet register failed (provision succeeded)` | Registry path not writable | Fix PVC/permissions on the registry file; register manually |
| No GPR after register | Fleetsync off, wrong registry path, or long interval | Enable `fleetSync` / `REPAVE_FLEET_SYNC_ENABLED`; mount same file; lower `REPAVE_FLEET_SYNC_INTERVAL` in kind |
| GPR pins wrong after second golden path | Still pinned to github-repo-generic | Re-register with workload blueprint pins from the checkout `repave.yaml` (`repave register --path …`) |
| Duplicate create/update churn | Both fleetsync and GitOps apply of manifests | Use one ownership path per environment |

## Alert / day-2 hooks

There is no dedicated Prometheus alert for “register without GPR” today. Watch:

- Operator logs for fleetsync errors (`REPAVE_FLEET_SYNC_ENABLED`)
- `GET /api/v2/fleet` (or Backstage Fleet) for missing or drift-behind rows after snapshot refresh
- Apply/audit messages for `Fleet register failed`

After Helm upgrades that touch fleet shared PVC overlays, run
`make chart-smoke-fleet-snapshot` (see [upgrade-and-rollback](upgrade-and-rollback.md)).
