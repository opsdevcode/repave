#!/usr/bin/env bash
# Render the chart with representative values and assert core objects exist.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CHART="${ROOT}/deploy/k8s/chart"

if ! command -v helm >/dev/null 2>&1; then
  echo "helm is required (https://helm.sh/docs/intro/install/)" >&2
  exit 1
fi

helm lint "${CHART}"

rendered="$(mktemp)"
portal_rendered="$(mktemp)"
hpa_rendered="$(mktemp)"
decomposed_rendered="$(mktemp)"
job_rendered="$(mktemp)"
decomposed_smoke_rendered="$(mktemp)"
day2_rendered="$(mktemp)"
decomposed_day2_rendered="$(mktemp)"
auth0_rendered="$(mktemp)"
state_store_rendered="$(mktemp)"
digest_rendered="$(mktemp)"
multi_replica_rendered="$(mktemp)"
worker_hpa_rendered="$(mktemp)"
fleet_shared_rendered="$(mktemp)"
env_vending_rendered="$(mktemp)"
kind_rendered="$(mktemp)"
trap 'rm -f "${rendered}" "${portal_rendered}" "${hpa_rendered}" "${decomposed_rendered}" "${job_rendered}" "${decomposed_smoke_rendered}" "${day2_rendered}" "${decomposed_day2_rendered}" "${auth0_rendered}" "${state_store_rendered}" "${digest_rendered}" "${multi_replica_rendered}" "${worker_hpa_rendered}" "${fleet_shared_rendered}" "${env_vending_rendered}" "${kind_rendered}"' EXIT

helm template repave-test "${CHART}" \
  --namespace repave-test \
  --set repave.output.githubOrg=example-org \
  --set persistence.modules.enabled=false \
  --set secrets.create=true \
  --set secrets.githubToken=test-token \
  >"${rendered}"

for kind in Deployment Service ConfigMap ServiceAccount; do
  if ! grep -q "kind: ${kind}" "${rendered}"; then
    echo "missing ${kind} in helm template output" >&2
    exit 1
  fi
done

if ! grep -q 'path: /health' "${rendered}" || ! grep -q 'path: /readyz' "${rendered}"; then
  echo "probes must reference /health and /readyz" >&2
  exit 1
fi

if ! grep -q 'app.kubernetes.io/component: backstage' "${rendered}"; then
  echo "default values must render Backstage (repave.backstage.enabled default on)" >&2
  exit 1
fi
if ! grep -q 'app.kubernetes.io/component: backstage-kubernetes' "${rendered}"; then
  echo "default values must render Backstage Kubernetes RBAC" >&2
  exit 1
fi

helm template repave-kind "${CHART}" \
  --namespace repave-kind \
  --set repave.output.githubOrg=example-org \
  --set persistence.modules.enabled=false \
  -f "${CHART}/values-kind.yaml" \
  >"${kind_rendered}"
if grep -q 'app.kubernetes.io/component: backstage' "${kind_rendered}"; then
  echo "values-kind.yaml must keep Backstage off (engine-only smoke)" >&2
  exit 1
fi

if ! grep -q 'app.kubernetes.io/component: portal' "${rendered}"; then
  echo "portal Service and Deployment must include app.kubernetes.io/component: portal" >&2
  exit 1
fi

if ! grep -q 'kind: PodDisruptionBudget' "${rendered}"; then
  echo "default render must include PodDisruptionBudget" >&2
  exit 1
fi

if ! grep -q 'startupProbe:' "${rendered}"; then
  echo "deployment must define startupProbe" >&2
  exit 1
fi

if ! grep -q 'terminationGracePeriodSeconds: 120' "${rendered}"; then
  echo "deployment must set terminationGracePeriodSeconds" >&2
  exit 1
fi

helm template repave-hpa "${CHART}" \
  --namespace repave-hpa \
  --set repave.output.githubOrg=example-org \
  --set persistence.modules.enabled=false \
  --set autoscaling.enabled=true \
  --set autoscaling.minReplicas=2 \
  --set autoscaling.maxReplicas=5 \
  >"${hpa_rendered}"

if ! grep -q 'kind: HorizontalPodAutoscaler' "${hpa_rendered}"; then
  echo "autoscaling.enabled must render HorizontalPodAutoscaler" >&2
  exit 1
fi

if grep -A20 'name: repave-hpa$' "${hpa_rendered}" | grep -q '^  replicas:'; then
  echo "HPA mode must omit portal Deployment.spec.replicas" >&2
  exit 1
fi

if ! grep -q 'name: REPAVE_IMAGE_GATE_TOOLCHAIN' "${rendered}"; then
  echo "deployment must set REPAVE_IMAGE_GATE_TOOLCHAIN" >&2
  exit 1
fi


helm template repave-portal "${CHART}" \
  --namespace repave-portal \
  -f "${CHART}/values-portal.yaml" \
  --set repave.output.githubOrg=example-org \
  >"${portal_rendered}"

if ! grep -q 'repave.dev/gate-toolchain: "false"' "${portal_rendered}"; then
  echo "values-portal.yaml must render gate-toolchain: false label" >&2
  exit 1
fi

helm template repave-decomposed "${CHART}" \
  --namespace repave-decomposed \
  -f "${CHART}/values-decomposed.yaml" \
  --set repave.output.githubOrg=example-org \
  >"${decomposed_rendered}"

if ! grep -q 'name: repave-decomposed-worker' "${decomposed_rendered}"; then
  echo "values-decomposed.yaml must render worker Deployment" >&2
  exit 1
fi

if ! grep -q 'name: corpus-init' "${decomposed_rendered}"; then
  echo "values-decomposed.yaml must render corpus initContainer" >&2
  exit 1
fi

if ! grep -q 'ghcr.io/opsdevcode/repave-engine:' "${decomposed_rendered}"; then
  echo "worker Deployment must use gate-toolchain image" >&2
  exit 1
fi

if grep -q 'REPAVE_ARTIFACT_STORE_URI' "${decomposed_rendered}"; then
  echo "values-decomposed.yaml must not require REPAVE_ARTIFACT_STORE_URI (snapshots default)" >&2
  exit 1
fi

helm template repave-decomposed-job "${CHART}" \
  --namespace repave-decomposed-job \
  -f "${CHART}/values-decomposed-job.yaml" \
  --set repave.output.githubOrg=example-org \
  >"${job_rendered}"

if grep -q 'name: repave-decomposed-job-worker' "${job_rendered}"; then
  echo "values-decomposed-job.yaml must not render worker Deployment" >&2
  exit 1
fi

if ! grep -q 'kind: Role' "${job_rendered}" || ! grep -q 'run-jobs' "${job_rendered}"; then
  echo "values-decomposed-job.yaml must render run-job RBAC Role" >&2
  exit 1
fi

if ! grep -q 'REPAVE_RUN_JOBS' "${job_rendered}"; then
  echo "values-decomposed-job.yaml must set REPAVE_RUN_JOBS on portal Deployment" >&2
  exit 1
fi

helm template repave-decomposed-smoke "${CHART}" \
  --namespace repave-decomposed-smoke \
  -f "${CHART}/values-decomposed-smoke.yaml" \
  --set repave.output.githubOrg=example-org \
  >"${decomposed_smoke_rendered}"

if ! grep -q 'name: repave-decomposed-smoke-worker' "${decomposed_smoke_rendered}"; then
  echo "values-decomposed-smoke.yaml must render worker Deployment" >&2
  exit 1
fi

if ! grep -q 'repave.dev/gate-toolchain: "false"' "${decomposed_smoke_rendered}"; then
  echo "values-decomposed-smoke.yaml must render portal without gate toolchain" >&2
  exit 1
fi

if grep -q 'app.kubernetes.io/component: backstage' "${decomposed_smoke_rendered}"; then
  echo "values-decomposed-smoke.yaml must keep Backstage off (engine-only smoke)" >&2
  exit 1
fi

if ! awk '/name: repave-decomposed-smoke$/{found=1} found && /app.kubernetes.io\/component: portal/{ok=1; exit} END{exit !ok}' "${decomposed_smoke_rendered}"; then
  echo "decomposed smoke portal Deployment must use app.kubernetes.io/component: portal" >&2
  exit 1
fi

if grep -A12 'name: repave-decomposed-smoke-worker' "${decomposed_smoke_rendered}" | grep -q 'app.kubernetes.io/component: portal'; then
  echo "decomposed smoke worker Deployment must not use portal component label" >&2
  exit 1
fi

helm template repave-day2 "${CHART}" \
  --namespace repave-day2 \
  -f "${CHART}/values-day2.yaml" \
  --set repave.output.githubOrg=example-org \
  >"${day2_rendered}"

if ! grep -q 'kind: ServiceMonitor' "${day2_rendered}"; then
  echo "values-day2.yaml must render ServiceMonitor when monitoring is enabled" >&2
  exit 1
fi

if ! grep -q 'kind: PrometheusRule' "${day2_rendered}"; then
  echo "values-day2.yaml must render PrometheusRule when monitoring is enabled" >&2
  exit 1
fi

if ! grep -q 'RepaveAsyncRunFailureRateHigh' "${day2_rendered}"; then
  echo "PrometheusRule must include async run failure alert" >&2
  exit 1
fi

helm template repave-decomposed-day2 "${CHART}" \
  --namespace repave-decomposed-day2 \
  -f "${CHART}/values-decomposed-day2.yaml" \
  --set repave.output.githubOrg=example-org \
  >"${decomposed_day2_rendered}"

if ! grep -q 'name: repave-decomposed-day2-worker' "${decomposed_day2_rendered}"; then
  echo "values-decomposed-day2.yaml must render worker Deployment" >&2
  exit 1
fi

if ! grep -q 'name: corpus-init' "${decomposed_day2_rendered}"; then
  echo "values-decomposed-day2.yaml must render corpus initContainer" >&2
  exit 1
fi

if ! grep -q 'repave.dev/gate-toolchain: "false"' "${decomposed_day2_rendered}"; then
  echo "values-decomposed-day2.yaml must render portal without gate toolchain" >&2
  exit 1
fi

if ! grep -q 'kind: ServiceMonitor' "${decomposed_day2_rendered}"; then
  echo "values-decomposed-day2.yaml must render ServiceMonitor" >&2
  exit 1
fi

if ! grep -q 'kind: HorizontalPodAutoscaler' "${decomposed_day2_rendered}"; then
  echo "values-decomposed-day2.yaml must render portal and worker HPAs" >&2
  exit 1
fi

helm template repave-auth0 "${CHART}" \
  --namespace repave-auth0 \
  -f "${CHART}/values-decomposed-day2.yaml" \
  -f "${CHART}/values-auth0.yaml" \
  --set repave.output.githubOrg=example-org \
  >"${auth0_rendered}"

if ! grep -q 'service_mode: true' "${auth0_rendered}"; then
  echo "values-auth0.yaml must enable auth.service_mode" >&2
  exit 1
fi

if ! grep -q 'session_https_only: true' "${auth0_rendered}"; then
  echo "values-auth0.yaml must set session_https_only" >&2
  exit 1
fi

if ! grep -q 'REPAVE_SESSION_HTTPS_ONLY' "${auth0_rendered}"; then
  echo "values-auth0.yaml must set REPAVE_SESSION_HTTPS_ONLY on portal" >&2
  exit 1
fi

if ! grep -q -- '- openid' "${auth0_rendered}"; then
  echo "values-auth0.yaml must render OIDC scopes in ConfigMap" >&2
  exit 1
fi

if ! grep -q 'repave-admins' "${auth0_rendered}"; then
  echo "values-auth0.yaml must map Auth0 admin role groups" >&2
  exit 1
fi

# Default chart must not mount state store (off by default).
if grep -q 'REPAVE_STATE_STORE_URL' "${rendered}"; then
  echo "base values.yaml must not set REPAVE_STATE_STORE_URL" >&2
  exit 1
fi
if grep -q 'state_store:' "${rendered}"; then
  echo "base values.yaml must not render state_store config" >&2
  exit 1
fi

helm template repave-state-store "${CHART}" \
  --namespace repave-state-store \
  -f "${CHART}/values-decomposed-day2.yaml" \
  -f "${CHART}/values-state-store.yaml" \
  --set repave.output.githubOrg=example-org \
  --set secrets.existingSecret=repave-secrets \
  --set secrets.stateKek=dGVzdC1rZWstaXMtMzItYnl0ZXMtbG9uZyEh \
  >"${state_store_rendered}"

if ! grep -q 'REPAVE_STATE_STORE_URL' "${state_store_rendered}"; then
  echo "values-state-store.yaml must set REPAVE_STATE_STORE_URL on portal" >&2
  exit 1
fi
if ! grep -q 'name: REPAVE_STATE_KEK' "${state_store_rendered}"; then
  echo "values-state-store.yaml must mount REPAVE_STATE_KEK from Secret" >&2
  exit 1
fi
if ! grep -q 'key: state-kek' "${state_store_rendered}"; then
  echo "values-state-store.yaml must reference secret key state-kek" >&2
  exit 1
fi
if ! grep -q 'state_store:' "${state_store_rendered}"; then
  echo "values-state-store.yaml must render state_store in ConfigMap" >&2
  exit 1
fi
if ! grep -q 'database_url:' "${state_store_rendered}"; then
  echo "values-state-store.yaml must render state_store.database_url" >&2
  exit 1
fi

helm template repave-digest "${CHART}" \
  --namespace repave-digest \
  -f "${CHART}/values-decomposed.yaml" \
  -f "${CHART}/values-digest-pinned.yaml" \
  --set repave.output.githubOrg=example-org \
  --set image.repository=ghcr.io/example/repave-engine-portal \
  --set image.digest=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  --set workerImage.repository=ghcr.io/example/repave-engine \
  --set workerImage.digest=sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb \
  --set corpus.digest=sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc \
  >"${digest_rendered}"

if ! grep -q 'image: ghcr.io/example/repave-engine-portal@sha256:aaaaaaaa' "${digest_rendered}"; then
  echo "image.digest must render portal image as repository@digest" >&2
  exit 1
fi

if ! grep -q 'image: ghcr.io/example/repave-engine@sha256:bbbbbbbb' "${digest_rendered}"; then
  echo "workerImage.digest must render worker image as repository@digest" >&2
  exit 1
fi

if ! grep -q 'image: ghcr.io/opsdevcode/repave-corpus@sha256:cccccccc' "${digest_rendered}"; then
  echo "corpus.digest must render corpus initContainer as repository@digest" >&2
  exit 1
fi

helm template repave-multi-replica-smoke "${CHART}" \
  --namespace repave-multi-replica-smoke \
  -f "${CHART}/values-decomposed-smoke.yaml" \
  -f "${CHART}/values-multi-replica-smoke.yaml" \
  --set repave.output.githubOrg=example-org \
  >"${multi_replica_rendered}"

if ! grep -q 'replicas: 2' "${multi_replica_rendered}"; then
  echo "values-multi-replica-smoke.yaml must render portal Deployment with replicas: 2" >&2
  exit 1
fi

worker_hpa_rendered="$(mktemp)"

helm template repave-worker-hpa "${CHART}" \
  --namespace repave-worker-hpa \
  -f "${CHART}/values-decomposed.yaml" \
  --set repave.output.githubOrg=example-org \
  --set workerAutoscaling.enabled=true \
  --set workerAutoscaling.minReplicas=2 \
  --set workerAutoscaling.maxReplicas=6 \
  >"${worker_hpa_rendered}"

if ! grep -q 'kind: HorizontalPodAutoscaler' "${worker_hpa_rendered}"; then
  echo "workerAutoscaling must render worker HorizontalPodAutoscaler" >&2
  exit 1
fi

if ! grep -A2 'kind: HorizontalPodAutoscaler' "${worker_hpa_rendered}" | grep -q 'name: repave-worker-hpa-worker'; then
  echo "workerAutoscaling HPA must target repave-worker-hpa-worker Deployment" >&2
  exit 1
fi

if grep -A20 'name: repave-worker-hpa-worker' "${worker_hpa_rendered}" | grep -q '^  replicas:'; then
  echo "worker HPA mode must omit worker Deployment.spec.replicas" >&2
  exit 1
fi

fleet_shared_rendered="$(mktemp)"

helm template repave-fleet-shared "${CHART}" \
  --namespace repave \
  -f "${CHART}/values-fleet-shared.yaml" \
  --set repave.output.githubOrg=example-org \
  >"${fleet_shared_rendered}"

if ! grep -q 'kind: PersistentVolumeClaim' "${fleet_shared_rendered}"; then
  echo "values-fleet-shared.yaml must render fleet PVC" >&2
  exit 1
fi

if ! grep -q 'name: repave-fleet' "${fleet_shared_rendered}"; then
  echo "values-fleet-shared.yaml must name fleet claim repave-fleet" >&2
  exit 1
fi

if ! grep -q 'kind: CronJob' "${fleet_shared_rendered}"; then
  echo "values-fleet-shared.yaml must render fleet operator snapshot CronJob" >&2
  exit 1
fi

if ! grep -q 'fleet-operator-snapshot' "${fleet_shared_rendered}"; then
  echo "fleet snapshot CronJob must invoke repave fleet-operator-snapshot" >&2
  exit 1
fi

if ! grep -q 'operator_status_file:' "${fleet_shared_rendered}"; then
  echo "values-fleet-shared.yaml must render fleet.operator_status_file in config" >&2
  exit 1
fi

if ! grep -q 'kind: Role' "${fleet_shared_rendered}"; then
  echo "values-fleet-shared.yaml must render fleet snapshot RBAC Role" >&2
  exit 1
fi

if ! grep -q 'goldenpathrepos' "${fleet_shared_rendered}"; then
  echo "fleet snapshot RBAC must grant list/get on goldenpathrepos" >&2
  exit 1
fi

if ! grep -q 'verbs: \["get", "list", "patch"\]' "${fleet_shared_rendered}"; then
  echo "fleet snapshot RBAC must grant patch on upgradecampaigns for campaign actions" >&2
  exit 1
fi

if ! grep -q 'require_session_secret: true' "${multi_replica_rendered}"; then
  echo "values-multi-replica-smoke.yaml must require session secret for multi-replica" >&2
  exit 1
fi

env_vending_rendered="$(mktemp)"

helm template repave-env-vending "${CHART}" \
  --namespace repave-env-vending \
  -f "${CHART}/values-environment-vending.yaml" \
  --set repave.output.githubOrg=example-org \
  --set persistence.modules.enabled=false \
  >"${env_vending_rendered}"

if ! grep -q 'kind: CronJob' "${env_vending_rendered}"; then
  echo "values-environment-vending.yaml must render environment reclaim CronJob" >&2
  exit 1
fi

if ! grep -q 'kind: PersistentVolumeClaim' "${env_vending_rendered}"; then
  echo "values-environment-vending.yaml must render environments PVC" >&2
  exit 1
fi

if ! grep -q 'environment_vending:' "${env_vending_rendered}"; then
  echo "values-environment-vending.yaml must render environment_vending config block" >&2
  exit 1
fi

if ! grep -q '  - environments' "${env_vending_rendered}" || ! grep -q '  - reclaim' "${env_vending_rendered}"; then
  echo "environment reclaim CronJob must invoke repave environments reclaim" >&2
  exit 1
fi

env_vending_http_rendered="$(mktemp)"

helm template repave-env-vending-http "${CHART}" \
  --namespace repave-env-vending \
  -f "${CHART}/values-environment-vending.yaml" \
  --set repave.output.githubOrg=example-org \
  --set environmentReclaim.cronJob.invoke=http \
  --set persistence.modules.enabled=false \
  >"${env_vending_http_rendered}"

if ! grep -q '/api/v2/environments/reclaim' "${env_vending_http_rendered}"; then
  echo "environmentReclaim.cronJob.invoke=http must POST /api/v2/environments/reclaim" >&2
  exit 1
fi

if grep -q 'repave environments reclaim' "${env_vending_http_rendered}"; then
  echo "http invoke must not shell out to repave environments reclaim CLI" >&2
  exit 1
fi

if grep -q 'developer_lab:' "${rendered}"; then
  echo "default values must not enable v3.developer_lab (ADR 008)" >&2
  exit 1
fi

if ! grep -q 'service_catalog:' "${rendered}"; then
  echo "default values must enable service_catalog (Backstage sandbox 404s otherwise)" >&2
  exit 1
fi

if ! grep -q 'api-sandbox-7d' "${rendered}"; then
  echo "default values must mount bundled service-catalog fixtures" >&2
  exit 1
fi

if grep -q 'environment_vending:' "${rendered}"; then
  echo "default values must not enable environment_vending (empty include must be falsy)" >&2
  exit 1
fi

lab_rendered="$(mktemp)"

helm template repave-developer-lab "${CHART}" \
  --namespace repave-lab \
  --set repave.output.githubOrg=example-org \
  --set persistence.modules.enabled=false \
  --set repave.serviceCatalog.enabled=false \
  --set repave.v3.enabled=true \
  --set repave.v3.developerLab.enabled=true \
  >"${lab_rendered}"

if ! grep -q 'developer_lab:' "${lab_rendered}"; then
  echo "v3.developerLab.enabled must render v3.developer_lab in the ConfigMap" >&2
  exit 1
fi

if grep -q 'environment_vending:' "${lab_rendered}"; then
  echo "developer lab flags must not enable environment_vending" >&2
  exit 1
fi

if grep -q 'service_catalog:' "${lab_rendered}"; then
  echo "developer lab flags must not invent a service_catalog block; mount catalog YAML separately" >&2
  exit 1
fi

catalog_rendered="$(mktemp)"

helm template repave-service-catalog "${CHART}" \
  --namespace repave-catalog \
  --set repave.output.githubOrg=example-org \
  --set persistence.modules.enabled=false \
  --set repave.serviceCatalog.enabled=true \
  --set repave.serviceCatalog.bundleExamples=false \
  >"${catalog_rendered}"

if ! grep -q 'service_catalog:' "${catalog_rendered}"; then
  echo "serviceCatalog.enabled must render service_catalog in the ConfigMap" >&2
  exit 1
fi

if grep -q 'app.kubernetes.io/component: service-catalog' "${catalog_rendered}"; then
  echo "serviceCatalog.enabled alone must not mount bundled catalog fixtures" >&2
  exit 1
fi

for catalog_file in maturity-rubric.yaml workload-profiles.yaml deployment-sets.yaml; do
  if ! cmp -s \
    "${CHART}/files/service-catalog/${catalog_file}" \
    "${ROOT}/examples/platform-dev/config/${catalog_file}"; then
    echo "chart files/service-catalog/${catalog_file} must match examples/platform-dev/config/${catalog_file}" >&2
    exit 1
  fi
done
if ! cmp -s \
  "${CHART}/files/service-catalog/initiatives.jsonl" \
  "${ROOT}/examples/platform-dev/fixtures/platform-metrics/initiatives.jsonl"; then
  echo "chart files/service-catalog/initiatives.jsonl must match examples/platform-dev fixtures" >&2
  exit 1
fi

if helm template repave-lab-without-v3 "${CHART}" \
  --namespace repave-lab \
  --set repave.output.githubOrg=example-org \
  --set persistence.modules.enabled=false \
  --set repave.v3.developerLab.enabled=true \
  >/dev/null 2>&1; then
  echo "developerLab.enabled without v3.enabled must fail (ADR 008)" >&2
  exit 1
fi

if helm template repave-auto-merge-without-v3 "${CHART}" \
  --namespace repave-lab \
  --set repave.output.githubOrg=example-org \
  --set persistence.modules.enabled=false \
  --set repave.v3.autoMerge.enabled=true \
  >/dev/null 2>&1; then
  echo "autoMerge.enabled without v3.enabled must fail (ADR 008)" >&2
  exit 1
fi

kill_rendered="$(mktemp)"

helm template repave-auto-merge-kill "${CHART}" \
  --namespace repave-lab \
  --set repave.output.githubOrg=example-org \
  --set persistence.modules.enabled=false \
  --set repave.v3.enabled=true \
  --set repave.v3.autoMerge.killSwitch=true \
  >"${kill_rendered}"

if ! grep -q 'kill_switch: true' "${kill_rendered}"; then
  echo "v3.autoMerge.killSwitch must render v3.auto_merge.kill_switch in the ConfigMap" >&2
  exit 1
fi

bs_rendered="$(mktemp)"
helm template repave-backstage "${CHART}" \
  --namespace repave-backstage \
  --set repave.output.githubOrg=example-org \
  --set persistence.modules.enabled=false \
  --set repave.backstage.enabled=true \
  >"${bs_rendered}"

if ! grep -q 'app.kubernetes.io/component: backstage' "${bs_rendered}"; then
  echo "repave.backstage.enabled must render a Backstage Deployment/Service" >&2
  rm -f "${bs_rendered}"
  exit 1
fi
if ! grep -q 'REPAVE_API_BASE_URL' "${bs_rendered}"; then
  echo "Backstage Deployment must set REPAVE_API_BASE_URL" >&2
  rm -f "${bs_rendered}"
  exit 1
fi
if ! grep -q 'REPAVE_API_TOKEN' "${bs_rendered}"; then
  echo "Backstage Deployment must set REPAVE_API_TOKEN (empty is fine)" >&2
  rm -f "${bs_rendered}"
  exit 1
fi
if ! grep -q 'initialDelaySeconds: 60' "${bs_rendered}"; then
  echo "Backstage liveness initialDelaySeconds must be 60 for first boot" >&2
  rm -f "${bs_rendered}"
  exit 1
fi
if ! grep -q 'app.kubernetes.io/component: backstage-kubernetes' "${bs_rendered}"; then
  echo "Backstage Kubernetes RBAC must render when backstage is enabled" >&2
  rm -f "${bs_rendered}"
  exit 1
fi
rm -f "${bs_rendered}"

bs_overlay="$(mktemp)"
helm template repave-backstage-overlay "${CHART}" \
  --namespace repave-backstage \
  --set repave.output.githubOrg=example-org \
  --set persistence.modules.enabled=false \
  -f "${CHART}/values-backstage.yaml" \
  --set ingress.enabled=true \
  --set repave.backstage.ingress.enabled=true \
  >"${bs_overlay}"

if ! grep -q 'html: true' "${bs_overlay}"; then
  echo "values-backstage.yaml must keep portal.html=true in the ConfigMap" >&2
  rm -f "${bs_overlay}"
  exit 1
fi
if grep -q 'html: false' "${bs_overlay}"; then
  echo "values-backstage.yaml must not disable the HTML workbench" >&2
  rm -f "${bs_overlay}"
  exit 1
fi
if ! grep -q 'path: /api' "${bs_overlay}"; then
  echo "values-backstage.yaml must send /api to the engine Ingress" >&2
  rm -f "${bs_overlay}"
  exit 1
fi
if ! grep -q 'path: /idp' "${bs_overlay}"; then
  echo "values-backstage.yaml must send /idp to the Backstage Ingress" >&2
  rm -f "${bs_overlay}"
  exit 1
fi
if ! grep -q 'backstage_url: "/idp"' "${bs_overlay}"; then
  echo "values-backstage.yaml must set portal.backstage_url=/idp for catalog handoff" >&2
  rm -f "${bs_overlay}"
  exit 1
fi
if ! grep -q 'name: APP_BASE_URL' "${bs_overlay}"; then
  echo "values-backstage.yaml must set APP_BASE_URL so Catalog is same-host /idp" >&2
  rm -f "${bs_overlay}"
  exit 1
fi
if ! grep -q 'https://repave.example.com/idp' "${bs_overlay}"; then
  echo "values-backstage.yaml must wire app.baseUrl to https://<host>/idp (no iframe)" >&2
  rm -f "${bs_overlay}"
  exit 1
fi
if ! grep -q 'app.kubernetes.io/component: backstage' "${bs_overlay}"; then
  echo "values-backstage.yaml must render a Backstage Ingress/Deployment" >&2
  rm -f "${bs_overlay}"
  exit 1
fi
if ! grep -q 'service_catalog:' "${bs_overlay}"; then
  echo "values-backstage.yaml must enable service_catalog (sandbox vend 404s otherwise)" >&2
  rm -f "${bs_overlay}"
  exit 1
fi
if ! grep -q 'api-sandbox-7d' "${bs_overlay}"; then
  echo "values-backstage.yaml must mount bundled deployment-sets fixtures" >&2
  rm -f "${bs_overlay}"
  exit 1
fi
rm -f "${bs_overlay}"

echo "helm lint and template checks passed"
