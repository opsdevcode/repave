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
2. Log in with an Auth0 user that has **`repave-generators`** (or **`repave-admins`**) role.
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

After [seeding demo fixtures](../repave-aws-infra/kubernetes/demo/README.md):

```bash
kubectl get goldenpathrepo -A
kubectl describe goldenpathrepo tf-eks-demo -n repave
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
