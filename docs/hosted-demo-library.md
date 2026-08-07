# Hosted demo library seeding

Populate the **opsdevcode** GitHub org and repave fleet registry with a realistic golden-path
estate for CTO demos: Terraform modules, Ansible roles, policy packs, Helm, and GitOps —
each with `repave.yaml` lineage, gate history in **Activity**, and operator-ready
`GoldenPathRepo` manifests.

Pair with [hosted-demo.md](hosted-demo.md) (portal acts) and
[seven-minute-demo.md](seven-minute-demo.md) (click path).

---

## What gets created

| Repo | Blueprint | Demo use |
| --- | --- | --- |
| `tf-aws-vpc-demo` | terraform-module-generic | Core generate + gates |
| `tf-aws-eks-demo` | terraform-module-generic | **Operator drift** (registered at pin `0.9.0`) |
| `tf-azure-networking-demo` | terraform-module-generic | Multi-cloud breadth |
| `ansible-role-webserver` | ansible-role-generic | Ansible family |
| `ansible-role-hardening` | ansible-role-generic | Second Ansible artifact |
| `opa-policy-platform-guardrails` | opa-policy-generic | Policy pass path (Act 5 block is separate dry-run) |
| `checkov-policy-platform-baseline` | checkov-policy-generic | Checkov policy family |
| `helm-payments-api` | helm-chart-generic | Kubernetes packaging |
| `gitops-dev-payments-api` | gitops-deployment-generic | GitOps delivery layer |

Catalog source: [`scripts/hosted-demo-library.yaml`](../scripts/hosted-demo-library.yaml).

---

## Prerequisites

**Hosted repave-prod** uses a **GitHub App** (`GITHUB_APP_*` on the portal pod via
`repave-secrets`) — same auth as portal publish. No laptop PAT required. See
[github-app-auth.md](github-app-auth.md).

Enable fleet on the portal chart (`repave.fleet.enabled`, `persistence.fleet`) and set
`fleetOperatorSnapshot.cronJob.operatorNamespace: repave-system` when GPRs live in a
different namespace. See [repave-aws-infra](https://github.com/opsdevcode/repave-aws-infra)
`kubernetes/values/repave-prod.yaml`.

---

## One-shot seed on repave-prod (recommended)

From a machine with `kubectl` access to the cluster (GitHub App auth is on the portal pod):

```bash
cd /path/to/repave
chmod +x scripts/seed-hosted-demo-library-k8s.sh

SEED_DRY_RUN=1 ./scripts/seed-hosted-demo-library-k8s.sh   # preview
./scripts/seed-hosted-demo-library-k8s.sh                  # publish + register on PVC
SEED_APPLY_MANIFESTS=1 ./scripts/seed-hosted-demo-library-k8s.sh   # + apply GPRs
```

The wrapper `./scripts/seed-hosted-demo-library.sh` auto-selects the k8s path when the cluster
is reachable and `GITHUB_TOKEN` is unset.

Writes:

- published repos under `opsdevcode` (GitHub App installation)
- modules under `/data/modules` on the portal PVC
- fleet registry at `/data/fleet/registry.jsonl`
- GPR manifests copied to `./fleet-manifests` on your laptop for `kubectl apply`

---

## Local seed (dev / PAT fallback)

```bash
export REPAVE_GITHUB_ORG=opsdevcode
# GitHub App (preferred) or PAT:
export GITHUB_APP_ID=... GITHUB_APP_INSTALLATION_ID=... GITHUB_APP_PRIVATE_KEY=...
# export GITHUB_TOKEN=ghp_...   # local dev only

export REPAVE_MODULES_ROOT=$HOME/repave-modules
export REPAVE_FLEET_FILE=$PWD/repave-fleet/registry.jsonl
mkdir -p repave-fleet

cd engine && uv sync --extra dev && cd ..
python3 scripts/seed_hosted_demo_library.py --dry-run
python3 scripts/seed_hosted_demo_library.py \
  --render-manifests \
  --manifests-dir ./fleet-manifests \
  --operator-namespace repave-system
```

Or `./scripts/seed-hosted-demo-library.sh` when `GITHUB_APP_*` or `GITHUB_TOKEN` is set locally.

---

## Legacy: manual kubectl exec

Equivalent to the k8s script (portal pod, `/app` repo root, App env already injected):

```bash
portal_pod=$(kubectl get pod -n repave -l app.kubernetes.io/component=portal \
  -o jsonpath='{.items[0].metadata.name}')
kubectl cp scripts/hosted-demo-library.yaml repave/$portal_pod:/tmp/hosted-demo-library.yaml
kubectl cp scripts/seed_hosted_demo_library.py repave/$portal_pod:/tmp/seed_hosted_demo_library.py
kubectl exec -n repave "$portal_pod" -- \
  python3 /tmp/seed_hosted_demo_library.py \
  --repo-root /app \
  --modules-root /data/modules \
  --fleet-file /data/fleet/registry.jsonl \
  --engine-dir /app/engine \
  --render-manifests \
  --manifests-dir /tmp/fleet-manifests \
  --operator-namespace repave-system
```

---

## Copy fleet registry (local seed only)

When you registered on a laptop, bulk-load JSONL into the portal pod:

```bash
portal_pod=$(kubectl get pod -n repave -l app.kubernetes.io/name=repave -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n repave "$portal_pod" -- mkdir -p /data/fleet
kubectl cp repave-fleet/registry.jsonl repave/$portal_pod:/data/fleet/registry.jsonl
```

Refresh operator status for the fleet table:

```bash
cd engine && uv run repave fleet-operator-snapshot \
  --output ../repave-fleet/operator-status.json \
  --namespace repave-system
kubectl cp repave-fleet/operator-status.json repave/$portal_pod:/data/fleet/operator-status.json
```

---

## What to show in the demo

| Surface | After seeding |
| --- | --- |
| **Home / Activity** (`/activity`) | One audit row per publish (`dry_run=false`, `repository_url`, gates outcome) |
| **Fleet** (`/fleet`) | Nine governed repos with blueprint/standard pins and owner |
| **Operator** | GPRs in `repave-system`; `tf-aws-eks-demo` → **OutOfDate** when catalog > `0.9.0` |
| **GitHub org** | `opsdevcode/tf-*`, `ansible-role-*`, `opa-policy-*`, … with `repave.yaml` |

**Act 5 (OPA block):** still run live in the portal with `plan_demo=destructive_delete` — do not
publish that variant; it is dry-run only.

---

## Idempotency and teardown

- Re-running publish may fail if GitHub repos already exist — use `--skip-publish` to register only.
- `repave unregister <url>` removes fleet entries; operator fleetSync prunes GPRs on next sync
  when continuous sync is enabled.
- Delete GitHub repos manually when retiring the demo library.
