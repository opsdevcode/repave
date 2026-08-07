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

```bash
# GitHub — create repos in opsdevcode (PAT or use cluster GitHub App via kubectl exec)
export REPAVE_GITHUB_ORG=opsdevcode
export GITHUB_TOKEN=ghp_...    # repo + admin:org (or fine-grained equivalent)

# Local clone root for register --path (default ~/repave-modules)
export REPAVE_MODULES_ROOT=$HOME/repave-modules

# Fleet registry file (local); hosted cluster uses /data/fleet/registry.jsonl on the portal PVC
export REPAVE_FLEET_FILE=$PWD/repave-fleet/registry.jsonl
mkdir -p repave-fleet
```

**Hosted cluster:** enable fleet on the portal chart (`repave.fleet.enabled`, `persistence.fleet`)
and set `fleetOperatorSnapshot.cronJob.operatorNamespace: repave-system` when GPRs live in a
different namespace. See [repave-aws-infra](https://github.com/opsdevcode/repave-aws-infra)
`kubernetes/values/repave-prod.yaml`.

---

## One-shot seed (recommended)

From repo root:

```bash
cd engine && uv sync --extra dev
cd ..

# Preview commands
python3 scripts/seed_hosted_demo_library.py --dry-run

# Publish all repos + register fleet + render operator manifests
python3 scripts/seed_hosted_demo_library.py \
  --render-manifests \
  --manifests-dir ./fleet-manifests \
  --operator-namespace repave-system

# Apply GoldenPathRepos (portal in repave, operator in repave-system)
kubectl apply -k ./fleet-manifests
```

Or use the shell wrapper:

```bash
./scripts/seed-hosted-demo-library.sh
```

---

## Seed from inside the cluster

When `GITHUB_APP_*` is already on the portal/worker (no laptop PAT):

```bash
portal_pod=$(kubectl get pod -n repave -l app.kubernetes.io/name=repave -o jsonpath='{.items[0].metadata.name}')
kubectl cp scripts/hosted-demo-library.yaml repave/$portal_pod:/tmp/hosted-demo-library.yaml
kubectl cp scripts/seed_hosted_demo_library.py repave/$portal_pod:/tmp/seed_hosted_demo_library.py
kubectl exec -n repave "$portal_pod" -- \
  python3 /tmp/seed_hosted_demo_library.py \
  --repo-root /app \
  --modules-root /data/modules \
  --fleet-file /data/fleet/registry.jsonl \
  --engine-dir /app/engine
```

(`python3` + PyYAML must exist in the image — prefer laptop seed with `GITHUB_TOKEN` until
a corpus image ships the script.)

---

## Copy fleet registry to hosted PVC

After local `repave register`, bulk-load JSONL into the portal pod (same shape as kind co-install):

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
