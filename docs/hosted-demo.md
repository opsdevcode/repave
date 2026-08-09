# Hosted demo (EKS)

Live script for stakeholder demos on the **production-style** repave deployment —
`https://repave.opsdevco.de` on EKS with Auth0 login, async workers, and Postgres durability.

Pair with [Seven-minute demo (acts 1–6)](seven-minute-demo.md) for click-by-click flow and
[Demo verification](demo-verification.md) for pre-flight checks.

**Infra:** [opsdevcode/repave-aws-infra](https://github.com/opsdevcode/repave-aws-infra) owns VPC,
EKS, RDS, ingress, and Helm desired state.

---

## Before the meeting

1. Confirm portal health: `curl -fsS https://repave.opsdevco.de/health`
2. Log in with any Auth0 user allowed on the application (coarse RBAC is off until FGA).
3. Confirm `/readyz` from inside the cluster (maintainers): `kubectl exec -n repave deploy/repave -- curl -s localhost:8088/readyz`
4. Run operator smoke if demoing drift: `kubectl get goldenpathrepo -A`
5. Optional automated portal acts (local): `cd engine && uv run pytest tests/test_demo_acts.py -v`

---

## URL and auth

| Item | Value |
| --- | --- |
| Portal | https://repave.opsdevco.de |
| Login | Auth0 → redirect to `/auth/login` when unauthenticated |
| GitHub org | `opsdevcode` (publish creates repos under this org) |
| Async runs | Enabled — worker Deployment runs gates; enable **Live run console** on the form |

Unauthenticated API calls return **401** (`REPAVE_SERVICE_MODE=1`).

---

## Acts 1–6 (hosted)

Same narrative as [seven-minute-demo.md](seven-minute-demo.md); only the **start URL** and
**login** differ.

1. **Act 1 — Catalog:** open https://repave.opsdevco.de → **terraform-module-generic**.
2. **Acts 2–3 — Generate:** module `demo`, AWS, **ec2 + s3** → **Dry run preview** → confirm gates
   and **Generated files**. Optional: enable **Live run console** and watch `/runs/{id}` stream.
3. **Act 4 — Update repo:** **Update repo** → **Use terraform-minimal** (or a published demo repo) →
   **Preview upgrade**.
4. **Act 5 — OPA block:** **opa-policy-generic**, plan demo `destructive_delete` → dry-run →
   **Publish blocked**.
5. **Act 6 — Backstage:** Terraform form → **Advanced** → **Include Backstage catalog** `true`,
   **owner** `group:platform` → dry-run → **`catalog-info.yaml`** in preview.

### Real publish (optional)

On the Delivery step, disable plan-only and submit with publish enabled. Requires GitHub App
credentials on the cluster (`repave-secrets`). Published repos land under `opsdevcode/tf-*`.

---

## Operator loop (optional)

After [seeding the demo library](hosted-demo-library.md) or [demo fixtures](https://github.com/opsdevcode/repave-aws-infra/tree/main/kubernetes/demo):

```bash
kubectl get goldenpathrepo -A
kubectl describe goldenpathrepo tf-eks-demo -n repave-system
```

Expect **OutOfDate** when desired blueprint pins are ahead of `repave.yaml` in the GitHub repo,
then **UpgradePlanned** and a remediation PR when remediation is enabled.

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Redirect loop / login fails | Auth0 callback `https://repave.opsdevco.de/auth/callback`; check `repave-secrets` OIDC client secret |
| Gates all skip | Worker pods unhealthy; `kubectl logs -n repave deploy/repave-worker` |
| Generate 401 | Session expired — re-login; API needs browser session or `REPAVE_API_TOKEN` |
| Operator idle / no GPR status | Leader-election RBAC; `kubectl logs -n repave-system deploy/repave-operator` |
| Portal down after node drain | RWO PVCs pin portal+workers to one node — see demo-week notes in infra `repave-prod.yaml` |
| Container publish failed on `main` | Re-run failed jobs: `gh run rerun <run-id> --failed`. Portal-only hotfix: **Actions → Container images → Run workflow → target `portal`**. Images tag `main` and `${{ github.sha }}` on every merge. |

---

## Weekend hotfix loop (pre-CTO demo)

Merge fixes to `main` → **Container images** workflow publishes four GHCR images in **parallel**
(`repave-engine-portal` is what the portal Deployment pulls).

1. **After merge**, watch publish: `gh run list --workflow=container.yml --limit 1`
2. **If push flakes** (403 on GHCR): `gh run rerun <run-id> --failed` — the workflow retries pushes and verifies manifests.
3. **Portal-only** (fastest for UI/CSS): Actions → **Container images** → **Run workflow** → target **portal**.
4. **Roll EKS** from `repave-aws-infra` once `main` tags are green:
   ```bash
   cd repave-aws-infra
   export REPAVE_CHART_PATH=/path/to/repave/deploy/k8s/chart
   ./scripts/sync-repave.sh
   ```
5. **Smoke:** `curl -fsS https://repave.opsdevco.de/health` and one dry-run generate in the browser.

Published tags on every `main` push: `main`, commit SHA, and semver on release tags. Pin prod in
`kubernetes/releases/prod.yaml` when you want a known digest; use `main` for rapid demo iteration.

---

## Local vs hosted

| | Local Compose | Hosted EKS |
| --- | --- | --- |
| URL | http://localhost:8088 | https://repave.opsdevco.de |
| Auth | Off by default | Auth0 OIDC required |
| Gates | In portal container | External worker Deployment |
| Publish | Optional `GITHUB_TOKEN` | GitHub App via External Secrets |

Local path: [quickstart.md](quickstart.md) · `make serve` is **:8089** (engine dev only).

---

## Demo library (seed the estate)

Publish a **library** of golden-path repos into `opsdevcode` using the **GitHub App** on the
portal pod (no PAT):

```bash
cd /path/to/repave
SEED_DRY_RUN=1 ./scripts/seed-hosted-demo-library-k8s.sh
SEED_APPLY_MANIFESTS=1 ./scripts/seed-hosted-demo-library-k8s.sh
```

Full catalog and talking points: [hosted-demo-library.md](hosted-demo-library.md).

---

## Maintainer deploy (repave-prod)

After merging chart fixes in `opsdevcode/repave`, roll out from `repave-aws-infra`:

```bash
cd repave-aws-infra
export LETSENCRYPT_EMAIL=you@opsdevco.de   # sync-platform only when platform chart changed
export REPAVE_CHART_PATH=/path/to/repave/deploy/k8s/chart
export OPERATOR_CHART_PATH=/path/to/repave/deploy/k8s/operator-chart
./scripts/sync-platform.sh    # ExternalSecret repave-postgres + app secrets
./scripts/sync-repave.sh      # portal + operator (pins in kubernetes/releases/prod.yaml)
./scripts/seed-demo-fixtures.sh
```

Rotate RDS password after removing literal `REPAVE_DATABASE_URL` from live Deployments:
`./scripts/rotate-rds-password.sh`

Demo-week PVC notes: `kubernetes/values/repave-demo-week.yaml`.

---

## CTO demo script (~10 min)

Rehearse on **https://repave.opsdevco.de** (not localhost). Pre-login before the room.

| Step | Surface | Wow line |
| --- | --- | --- |
| 1 | **Home** — catalog families | “Platform owns the paved roads; builders pick a golden path.” |
| 2 | **terraform-module-generic** → Plan preview | Gates + lineage on the result — “same inputs, same artifact, receipt for auditors.” |
| 3 | **Apply** + **Live run console** | Real repo under `opsdevcode` — stage stepper through publish. |
| 4 | **Activity** (`/activity`) | Audit row for that apply — “every publish is receipted.” |
| 5 | **opa-policy-generic** → `destructive_delete` | Gate blocks publish — “policy stops the line.” |
| 6 | **Fleet** (`/fleet`) | Nine seeded repos with pins — “this is a governed estate.” |
| 7 | **Operator** (optional kubectl) | `tf-aws-eks-demo` **OutOfDate** — “fleet drift, not surprise upgrades.” |

**Apply tips:** use a fresh module name (`demo-cto-aug8`). Click **Apply** directly (radio syncs automatically on current builds).

**Operator drift (step 7):**

```bash
kubectl get goldenpathrepo -n repave-system opsdevcode-tf-aws-eks-demo
kubectl describe goldenpathrepo -n repave-system opsdevcode-tf-aws-eks-demo
```

Expect `OutOfDate` and an upgrade plan once `REPAVE_API_TOKEN` is wired (see below).

### Operator API token (upgrade planning)

Hosted portal uses Auth0 (`auth.service_mode`). The operator calls `/api/v2/upgrades/plan` with
`REPAVE_API_TOKEN` — same bearer as portal CronJobs.

```bash
cd repave-aws-infra
chmod +x scripts/ensure-api-token.sh
./scripts/ensure-api-token.sh          # adds api-token to repave-prod/app in Secrets Manager
./scripts/sync-platform.sh             # ExternalSecret → repave-secrets + repave-operator-secrets
export REPAVE_CHART_PATH=/path/to/repave/deploy/k8s/chart
export OPERATOR_CHART_PATH=/path/to/repave/deploy/k8s/operator-chart
./scripts/sync-repave.sh
```

After sync, GPR `opsdevcode-tf-aws-eks-demo` should progress past `Authentication required` on upgrade planning.
