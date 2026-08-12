# State store shared-deploy enablement — checklist

Turn on the authoritative Terraform/OpenTofu state store (ADR 004 Phases 1–3) in a
shared cluster. Engine support is shipped and **off by default**; this runbook is the
operator path. Phase 4 (graph-scoped parallel apply) remains **no-go** on v2/v3 and is
deferred to **v4.0.0** — see
[`docs/state-graph-phase4-review.md`](../state-graph-phase4-review.md) and
[`roadmap.md` beyond v3](../roadmap.md#beyond-v300--stategraph-and-graph-scoped-execution).

| Doc | Role |
| --- | --- |
| [`docs/state-graph.md`](../state-graph.md) | Operator guide (env vars, client, transactions) |
| [ADR 004](../adr/004-state-custody-and-the-resource-graph.md) | Design + security obligations |
| [`values-state-store.yaml`](../../deploy/k8s/chart/values-state-store.yaml) | Helm overlay |
| [`bootstrap-state-store-secrets.sh`](../../deploy/k8s/hack/bootstrap-state-store-secrets.sh) | KEK Secret bootstrap |
| [`postgres-backup-restore.md`](postgres-backup-restore.md) | Durability DR; stricter rules when store is on |

**Do not enable** until every gate below is checked. Knobs alone do not mean production-ready.

## Gates (must all pass)

| # | Gate | Owner signs |
| - | ---- | ----------- |
| 1 | Platform security review of the posture reversal (repave will hold state blobs) | |
| 2 | Named, funded owner for Terraform/OpenTofu version-skew treadmill | |
| 3 | Postgres 14+ with **continuous archiving / PITR** (not hourly-only logical dumps) | |
| 4 | Timed restore drill recorded (RPO/RTO for *state* tables, not durability defaults) | |
| 5 | KEK generated and stored **outside** the database it protects | |
| 6 | `REPAVE_API_TOKEN` (or Auth0 + bearer) ready for `repave-tf` / machine callers | |

Durability RPO ≤1h / RTO ≤4h **do not apply** to state — see
[postgres-backup-restore.md](postgres-backup-restore.md).

## Env var map (do not confuse)

| Side | Variable | Meaning |
| ---- | -------- | ------- |
| Server | `REPAVE_STATE_STORE_URL` | Postgres URL; **enables** the store |
| Server | `REPAVE_STATE_STORE_TENANT` | Default tenant |
| Server | `REPAVE_STATE_REQUIRED_GATES` | Comma-separated enforcing gates |
| Server | `REPAVE_STATE_KEK` / `REPAVE_STATE_KEK_ID` | Envelope encryption |
| Client / CI | `REPAVE_STATE_URL` | Portal base URL (not the DB URL) |
| Client / CI | `REPAVE_STATE_TOKEN` | Bearer → server `REPAVE_API_TOKEN` when auth is on |
| Unrelated | `REPAVE_DATABASE_URL` | Durability / runs / sessions — **not** the state store |

## 1. Generate and store the KEK

```bash
export REPAVE_NAMESPACE=repave
export REPAVE_SECRET_NAME=repave-secrets
export REPAVE_STATE_KEK="$(openssl rand -base64 32)"
export REPAVE_STATE_KEK_ID=default   # bump on rotation

# Persist REPAVE_STATE_KEK in your secret manager before applying to the cluster.
./deploy/k8s/hack/bootstrap-state-store-secrets.sh
```

Without `state-kek`, the chart fails to schedule the portal when the overlay is merged
(`optional: false`). Never enable the store with plaintext blobs in a shared cluster.

## 2. Helm upgrade

Prefer a dedicated Postgres database (or at least a dedicated logical DB) for state tables
when estate risk warrants isolation. Sharing the durability instance is acceptable for
early enablement if PITR covers that instance.

```bash
export REPAVE_DATABASE_URL='postgresql://...'          # durability
export REPAVE_STATE_STORE_URL='postgresql://...'       # state store (may match host)
export PORTAL_HOST='repave.example.com'

helm upgrade --install repave ./deploy/k8s/chart \
  -n "${REPAVE_NAMESPACE:-repave}" \
  -f deploy/k8s/chart/values.yaml \
  -f deploy/k8s/chart/values-decomposed-day2.yaml \
  -f deploy/k8s/chart/values-state-store.yaml \
  --set secrets.existingSecret=repave-secrets \
  --set repave.durability.databaseUrl="${REPAVE_DATABASE_URL}" \
  --set repave.stateStore.databaseUrl="${REPAVE_STATE_STORE_URL}" \
  --set repave.stateStore.defaultTenant=default
```

Optional: `--set 'repave.stateStore.requiredGates={checkov,opa}'` to make named gates
enforcing at commit time.

## 3. Verify server

| Check | Expect |
| --- | --- |
| Portal logs | No "plaintext" KEK warning; no SQLite shared-deploy warning |
| `curl -sS https://<portal-host>/api/state/v1` | JSON with `min_supported_client` / `current_client` |
| `kubectl exec` → env | `REPAVE_STATE_STORE_URL` set; `REPAVE_STATE_KEK` present (do not print) |

## 4. Client / repository rollout

1. Point a canary module at the http backend (see [`docs/state-graph.md`](../state-graph.md)).
2. Set repository Actions variable `REPAVE_STATE_URL=https://<portal-host>` so the
   generated `repave-tf` CI step activates.
3. Set `REPAVE_STATE_TOKEN` (secret) to the same value as cluster `api-token` when
   `auth.service_mode` is on.
4. Import existing state with `repave-tf state import` before cutover; keep
   `repave-tf state export` as the escape hatch.

## 5. Sign-off record

Record completion in your change ticket (not this repo unless process requires it):

- Security review: date / reviewer
- Treadmill owner: name / team / funding note
- PITR drill: date, measured RPO/RTO, restore target
- KEK location: secret-manager path (not the key material)

## Break-glass

- **Lost KEK:** encrypted blobs are unreadable. Restore from export taken *before*
  encryption, or from a backup of the KEK — not from Postgres alone.
- **Disable store:** remove `values-state-store.yaml` / set `repave.stateStore.enabled=false`
  and redeploy. Existing DB rows remain; routes unmount. Export first.
- **Wrong serial/lineage:** fix with documented import/export; do not hand-edit blobs.

## Explicit non-goals

- Graph-scoped parallel apply (Phase 4) — gated **no-go** on v2/v3; **v4.0.0** theme
  (buy preferred)
- Separate `repave-statestore` Deployment (ADR 004 decision 6) — follow-on; routes mount
  on the portal today
- Flipping chart defaults to `enabled: true`
