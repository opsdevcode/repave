# Fleet registry

The fleet registry is the list of repositories repave governs. Generation tells you what
repave *created*; the registry tells you what it is still responsible for, which is what
the operator and portal need in order to report drift across an estate.

Related: [operator overview](operator-overview.md), [roadmap](roadmap.md).

## Storage

An append-only JSONL log of `register` and `unregister` events. Current state is the fold
of those events, last write winning per repository, so re-registering a repo with new pins
updates it rather than duplicating it. This is the same shape as the
[audit sink](../repave.config.yaml.example) so the backend can move to a database later
without changing callers.

Enable it in `repave.config.yaml`:

```yaml
fleet:
  enabled: true
  file: ../repave-fleet/registry.jsonl
```

`REPAVE_FLEET_FILE` overrides the path. Relative paths resolve against the repo root. Keep
the file outside the repave repo so registry writes never dirty the working tree.

Commands fail with an explanatory error when no registry is configured, rather than
silently writing nowhere.

## CLI

Register a repository, reading its pins from a local checkout's `repave.yaml` provenance:

```bash
repave register https://github.com/acme/tf-vpc --path ~/modules/tf-vpc --owner platform
```

Successful **github-repo** apply (`github-repo-generic` / `repave create-repo`) also
best-effort registers the new repository when the fleet registry is enabled — the same
path import uses — so fleetsync / `fleet-manifests` can emit a `GoldenPathRepo`. See
[GitHub repository goldpath](github-repo-goldpath.md) and the ops checklist
[github-repo → fleet → GoldenPathRepo](operations/github-repo-fleet-validation.md)
(`make validate-github-repo-fleet`).

Provenance is the preferred source because it is exactly what the operator observes. When
you have no checkout, pass pins explicitly:

```bash
repave register https://github.com/acme/tf-vpc \
  --blueprint terraform-module-generic --blueprint-version 0.9.0
```

List and remove:

```bash
repave fleet                 # human-readable
repave fleet --format json   # scripting and CI
repave unregister https://github.com/acme/tf-vpc
```

`unregister` exits non-zero when the repository was not registered, so scripts can tell
"removed" from "was never there".

In hosted deployments, admins register and unregister through `POST`/`DELETE`
`/api/v2/fleet` (Backstage Fleet; requires `ROLE_ADMIN` when service mode is on).
`GET /platform/fleet` is a pointer page.

URL spellings collapse to one entry: `https://github.com/acme/tf-vpc.git`, the same URL
with a trailing slash, and the bare form are one repository. Register and unregister
therefore agree regardless of which form a caller uses.

## API

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/v1/fleet` | any authenticated role (`viewer` and up) |
| `POST` | `/api/v1/fleet` | `admin` |
| `DELETE` | `/api/v1/fleet?repo_url=...` | `admin` |

Roles apply in service mode only; local single-user mode has no auth. See
[service mode](auth-service-mode.md).

```bash
curl -X POST localhost:8000/api/v1/fleet \
  -H 'content-type: application/json' \
  -d '{"repo_url": "https://github.com/acme/tf-vpc", "path": "/repos/tf-vpc"}'

curl localhost:8000/api/v1/fleet
```

`GET` returns `{"count": N, "repos": [...]}`. Registration returns `201` with the stored
entry, including the normalized URL and the acting user recorded as `registered_by`.

A missing or disabled registry returns `404` rather than an empty list, so a
misconfiguration cannot be mistaken for an empty fleet.

## Portal

**Fleet** in the top navigation lists governed repositories with the blueprint and standard
each is pinned to, who registered it, and when. The page is always reachable so the nav
link never dead-ends: with no registry configured it explains the `fleet` config block, and
with an empty registry it points at `repave register`.

The page is read-only. Registration stays in the CLI and API, where the acting user is
recorded.

### Operator drift (live status)

When `fleet.operator_status_file` (or `REPAVE_FLEET_OPERATOR_STATUS_FILE`) points at a JSON
snapshot, the fleet table shows each repo's operator **phase**, message, and open remediation
PR link. Refresh the snapshot from a cluster that runs the repave operator:

```bash
repave fleet-operator-snapshot \
  --output ../repave-fleet/operator-status.json \
  --namespace repave-system
```

Run that on a schedule in CI or beside your GitOps apply job so the portal stays aligned with
`GoldenPathRepo` status without the engine calling the Kubernetes API directly.

**In-cluster (Helm):** with [`values-fleet-shared.yaml`](../deploy/k8s/chart/values-fleet-shared.yaml),
the portal chart can run a CronJob that writes the snapshot to the shared fleet PVC on a
schedule (`fleetOperatorSnapshot.cronJob`). Set `fleetOperatorSnapshot.cronJob.operatorNamespace`
when GPRs live in a different namespace than the portal release. See
[`deploy/k8s/chart/README.md`](../deploy/k8s/chart/README.md) § Fleet operator snapshot.

Validate locally:

- `make validate-github-repo-fleet` — simulate github-repo register → `fleet-manifests` (no cluster)
- `make chart-smoke-fleet-snapshot` — kind: portal + operator fleetsync + snapshot Job +
  platform campaign pause/resume via `POST /platform/campaigns/{ns}/{name}/paused`

Full checklist: [github-repo fleet validation](operations/github-repo-fleet-validation.md).

### Platform console day-2 actions

Admins with platform access (`ROLE_ADMIN` in service mode) can run day-2 actions from the
portal without shell `kubectl` hints:

| Surface | Action | Mechanism |
| --- | --- | --- |
| `POST /platform/campaigns/{ns}/{name}/paused` | Pause / resume `UpgradeCampaign` | Validates campaign in operator snapshot, then `kubectl patch upgradecampaign` (requires `kubectl` in the engine image and RBAC `patch` on `upgradecampaigns`; validated by `make chart-smoke-fleet-snapshot`). `GET /platform/campaigns` is a pointer. |
| `/platform/standards` | Confirm drift for behind repos | Submits a `fleet_drift_confirm` async run (`verify` fan-out); requires `durability.async_generation` |

Campaign phase updates still follow the fleet operator snapshot schedule — re-run snapshot or
wait for the CronJob after patching `spec.paused`.

## Operator sync

### Continuous registry sync (operator)

When `REPAVE_FLEET_SYNC_ENABLED=true`, the operator reads the same JSONL registry file
on an interval and creates, updates, or **prunes** fleet-managed `GoldenPathRepo`
objects (`repave.dev/managed-by: repave-fleet`). Unregistering a repository removes
its GPR on the next sync cycle.

Environment variables:

| Variable | Purpose |
| --- | --- |
| `REPAVE_FLEET_SYNC_ENABLED` | `true` to enable periodic sync |
| `REPAVE_FLEET_REGISTRY_PATH` / `REPAVE_FLEET_FILE` | Path to `registry.jsonl` |
| `REPAVE_FLEET_SYNC_INTERVAL` | Seconds between sync passes (default 300) |
| `REPAVE_FLEET_GITOPS_NAMESPACE` | Target namespace for GPRs (default `default`) |
| `REPAVE_FLEET_ENABLE_REMEDIATION` | Set `spec.remediation.enabled` on synced GPRs |

The operator Helm chart exposes the same settings under `fleetSync.*` — mount a shared
PVC (`values-fleet-shared.yaml` on portal + operator in the **same namespace**) or copy the
registry file into the operator pod for kind-only cross-namespace setups.

### GitOps manifests (engine)

`repave fleet-manifests` renders one `GoldenPathRepo` per registered repository so the
operator reconciles the same set the registry tracks:

```bash
repave fleet-manifests --output ./fleet-manifests --namespace repave-system \
  --kustomization --gitops-readme --prune
kubectl apply -k ./fleet-manifests
```

Flags:

| Flag | Purpose |
| --- | --- |
| `--kustomization` | Write `kustomization.yaml` for `kubectl apply -k` |
| `--gitops-readme` | Write `README.md` with apply and snapshot commands |
| `--prune` | Delete stale `*.yaml` in `--output` after render |
| `--enable-remediation` | Set `spec.remediation.enabled` on each manifest |

The plain form still works:

```bash
repave fleet-manifests --output ./fleet-manifests --namespace repave-system
kubectl apply -f ./fleet-manifests
```

The engine writes manifests rather than the operator reading the registry. That keeps the
operator free of engine storage details and needs no in-cluster engine service or token, and
it fits GitOps: commit the output directory and let Argo or Flux apply it.

Each manifest sets `spec.repoURL` (never `localPath`, since registry entries are remote) and
`spec.desiredPins` from the registered pins. Resource names come from the owner and repo
(`acme/tf-vpc` becomes `acme-tf-vpc`) so two repos with the same short name do not collide;
rendering aborts if two entries would still produce one name.

Output is deterministic, so re-running with an unchanged registry produces no diff. Entries
missing any pin are rejected before anything is written, because `desiredPins` fields are
required by the CRD — a partial apply set is worse than none. Re-register such a repo with
`--path` so pins come from its `repave.yaml`.

`operator/testdata/fleet/` holds rendered fixtures that the operator decodes strictly in
`fleet_manifest_test.go`, so a field rename on either side fails in CI rather than at apply
time. `test_fleet_manifests.py` asserts those fixtures still match the renderer.

Use **either** continuous operator sync **or** GitOps-rendered manifests — not both for
the same namespace unless you accept duplicate reconcile sources.

CI validates fleet sync create/prune and platform campaign pause/resume with
`make chart-smoke-fleet-snapshot` (shared PVC, portal API unregister, operator GPR prune,
UpgradeCampaign patch via `POST /platform/campaigns/{ns}/{name}/paused`, snapshot CronJob).
Local full stack:
`make kind-co-install` seeds [`deploy/k8s/testdata/fleet-registry.jsonl`](../deploy/k8s/testdata/fleet-registry.jsonl)
via fleetSync — see [`deploy/k8s/chart/README.md`](../deploy/k8s/chart/README.md).
