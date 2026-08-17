#!/usr/bin/env bash
# kind smoke: fleet shared PVC, operator fleetSync prune, snapshot CronJob, and campaign pause.
# Seeds a fleet registry, waits for fleetSync GPRs, unregisters one repo via the portal API,
# waits for GPR prune, applies an UpgradeCampaign, runs a one-off snapshot Job, verifies
# GET /platform/fleet, GET /platform/campaigns, GET /api/v2/fleet, and
# GET /api/v2/platform/campaigns,
# pauses the campaign via the portal POST, and asserts spec.paused on the CR.
# CI: .github/workflows/chart.yml (chart-smoke-fleet-snapshot job).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CHART="${ROOT}/deploy/k8s/chart"
OPERATOR_CHART="${ROOT}/deploy/k8s/operator-chart"
OPERATOR="${ROOT}/operator"
FLEET_REGISTRY="${ROOT}/deploy/k8s/testdata/fleet-registry.jsonl"
CAMPAIGN_MANIFEST="${ROOT}/deploy/k8s/testdata/upgrade-campaign-smoke.yaml"
CAMPAIGN_NAME="platform-rollout"

CLUSTER_NAME="${KIND_CLUSTER_NAME:-repave-chart-smoke-fleet-snapshot}"
NS="${CHART_SMOKE_FLEET_SNAPSHOT_NAMESPACE:-repave-fleet-snapshot-smoke}"
ENGINE_REPO="${CHART_SMOKE_FLEET_SNAPSHOT_IMAGE_REPO:-repave-engine}"
ENGINE_TAG="${CHART_SMOKE_FLEET_SNAPSHOT_IMAGE_TAG:-chart-smoke-fleet-snapshot}"
OPERATOR_REPO="${CHART_SMOKE_FLEET_SNAPSHOT_OPERATOR_REPO:-repave-operator}"
OPERATOR_TAG="${CHART_SMOKE_FLEET_SNAPSHOT_OPERATOR_TAG:-chart-smoke-fleet-snapshot}"
INSTALL_GATE_TOOLCHAIN="${CHART_SMOKE_INSTALL_GATE_TOOLCHAIN:-1}"
TIMEOUT="${CHART_SMOKE_FLEET_SNAPSHOT_TIMEOUT:-360}"
PORT="${CHART_SMOKE_FLEET_SNAPSHOT_PORT:-18091}"
SNAPSHOT_PATH="/data/fleet/operator-status.json"

require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$1 is required" >&2
    exit 1
  fi
}

require kind
require helm
require docker
require kubectl
require curl
require python3

cleanup() {
  if [[ "${CHART_SMOKE_FLEET_SNAPSHOT_KEEP_CLUSTER:-}" == "1" ]]; then
    echo "CHART_SMOKE_FLEET_SNAPSHOT_KEEP_CLUSTER=1; leaving cluster ${CLUSTER_NAME}"
    return 0
  fi
  kind delete cluster --name "${CLUSTER_NAME}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> kind cluster ${CLUSTER_NAME}"
kind delete cluster --name "${CLUSTER_NAME}" >/dev/null 2>&1 || true
kind create cluster --name "${CLUSTER_NAME}"

echo "==> docker build ${ENGINE_REPO}:${ENGINE_TAG} (gate toolchain + kubectl)"
docker build -f "${ROOT}/deploy/local/Dockerfile" \
  --build-arg "INSTALL_GATE_TOOLCHAIN=${INSTALL_GATE_TOOLCHAIN}" \
  -t "${ENGINE_REPO}:${ENGINE_TAG}" "${ROOT}"

echo "==> docker build ${OPERATOR_REPO}:${OPERATOR_TAG}"
docker build -f "${OPERATOR}/Dockerfile" -t "${OPERATOR_REPO}:${OPERATOR_TAG}" "${OPERATOR}"

echo "==> kind load images"
kind load docker-image "${ENGINE_REPO}:${ENGINE_TAG}" --name "${CLUSTER_NAME}"
kind load docker-image "${OPERATOR_REPO}:${OPERATOR_TAG}" --name "${CLUSTER_NAME}"

echo "==> helm install portal (fleet shared + snapshot CronJob)"
helm upgrade --install repave "${CHART}" \
  --namespace "${NS}" --create-namespace \
  -f "${CHART}/values-kind.yaml" \
  -f "${CHART}/values-fleet-shared.yaml" \
  --set image.repository="${ENGINE_REPO}" \
  --set image.tag="${ENGINE_TAG}" \
  --set image.pullPolicy=Never \
  --set repave.output.githubOrg=example-org \
  --set persistence.modules.enabled=false \
  --set persistence.modules.kindHostPath="" \
  --wait --timeout "${TIMEOUT}s"

kubectl -n "${NS}" rollout status deployment/repave --timeout="${TIMEOUT}s"

PORTAL_API_URL="http://repave.${NS}.svc.cluster.local:8088"
echo "==> operator webhook TLS + Helm install (REPAVE_API_URL=${PORTAL_API_URL})"
chmod +x "${OPERATOR}/hack/setup-webhook-certs.sh"
# Certs + CA SAN must match the operator release namespace (not the default
# repave-system). Bare kind has no /modules hostPath — disable the kind overlay mount.
WEBHOOK_NAMESPACE="${NS}" bash "${OPERATOR}/hack/setup-webhook-certs.sh"
CA_BUNDLE="$(base64 <"${OPERATOR}/hack/webhook-certs/ca.crt" | tr -d '\n')"
helm upgrade --install repave-operator "${OPERATOR_CHART}" \
  --namespace "${NS}" --create-namespace \
  -f "${OPERATOR_CHART}/values-kind.yaml" \
  -f "${OPERATOR_CHART}/values-fleet-shared.yaml" \
  --set "image.repository=${OPERATOR_REPO}" \
  --set "image.tag=${OPERATOR_TAG}" \
  --set image.pullPolicy=Never \
  --set "repave.apiUrl=${PORTAL_API_URL}" \
  --set "webhook.caBundle=${CA_BUNDLE}" \
  --set "fleetSync.gitopsNamespace=${NS}" \
  --set "fleetSync.intervalSeconds=15" \
  --set modules.hostPath.enabled=false \
  --wait --timeout "${TIMEOUT}s"

kubectl -n "${NS}" rollout status deployment/repave-operator --timeout="${TIMEOUT}s"

CRONJOB="repave-fleet-operator-snapshot"
PVC="repave-fleet"

echo "==> verify snapshot CronJob, RBAC, and fleet PVC"
kubectl -n "${NS}" get "cronjob/${CRONJOB}"
kubectl -n "${NS}" get "pvc/${PVC}"
kubectl -n "${NS}" get role,rolebinding -l "app.kubernetes.io/instance=repave" | grep fleet-snapshot

echo "==> seed fleet registry on shared PVC"
portal_pod="$(kubectl get pod -n "${NS}" -l app.kubernetes.io/name=repave \
  -o jsonpath='{.items[0].metadata.name}')"
kubectl exec -n "${NS}" "${portal_pod}" -- mkdir -p /data/fleet
kubectl cp "${FLEET_REGISTRY}" "${NS}/${portal_pod}:/data/fleet/registry.jsonl"

echo "==> wait for fleetSync to create GoldenPathRepos in ${NS}"
deadline=$((SECONDS + TIMEOUT))
gpr_count=0
while (( SECONDS < deadline )); do
  gpr_count="$(kubectl get goldenpathrepo -n "${NS}" -l repave.dev/managed-by=repave-fleet \
    --no-headers 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "${gpr_count}" -ge 2 ]]; then
    break
  fi
  sleep 3
done
if [[ "${gpr_count}" -lt 2 ]]; then
  echo "Timed out waiting for fleet-managed GoldenPathRepos" >&2
  kubectl get goldenpathrepo -A
  exit 1
fi

echo "==> port-forward for fleet unregister API"
kubectl -n "${NS}" port-forward svc/repave "${PORT}:8088" >/tmp/repave-fleet-snapshot-smoke-pf.log 2>&1 &
PF_PID=$!
trap 'kill "${PF_PID}" 2>/dev/null || true; cleanup' EXIT
sleep 3
curl -sf "http://127.0.0.1:${PORT}/health" | grep -q '"status":"ok"'

UNREGISTER_URL="https://github.com/acme/opa-guardrails"
PRUNED_GPR="acme-opa-guardrails"
KEPT_GPR="acme-tf-vpc"

echo "==> unregister ${UNREGISTER_URL} via API and wait for fleetSync GPR prune"
curl -sf -G -X DELETE \
  "http://127.0.0.1:${PORT}/api/v2/fleet" \
  --data-urlencode "repo_url=${UNREGISTER_URL}"
deadline=$((SECONDS + TIMEOUT))
while (( SECONDS < deadline )); do
  gpr_count="$(kubectl get goldenpathrepo -n "${NS}" -l repave.dev/managed-by=repave-fleet \
    --no-headers 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "${gpr_count}" -eq 1 ]]; then
    break
  fi
  sleep 3
done
if [[ "${gpr_count}" -ne 1 ]]; then
  echo "Timed out waiting for fleetSync to prune unregistered GoldenPathRepo" >&2
  kubectl get goldenpathrepo -n "${NS}" -A
  exit 1
fi
if kubectl -n "${NS}" get "goldenpathrepo/${PRUNED_GPR}" >/dev/null 2>&1; then
  echo "expected ${PRUNED_GPR} to be pruned after unregister" >&2
  exit 1
fi
kubectl -n "${NS}" get "goldenpathrepo/${KEPT_GPR}" >/dev/null

echo "==> apply UpgradeCampaign ${CAMPAIGN_NAME} and label kept GPR"
kubectl apply -n "${NS}" -f "${CAMPAIGN_MANIFEST}"
kubectl label "goldenpathrepo/${KEPT_GPR}" -n "${NS}" \
  "repave.dev/upgrade-campaign=${CAMPAIGN_NAME}" --overwrite
deadline=$((SECONDS + TIMEOUT))
while (( SECONDS < deadline )); do
  phase="$(kubectl get "upgradecampaign/${CAMPAIGN_NAME}" -n "${NS}" \
    -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  if [[ "${phase}" == "Active" ]]; then
    break
  fi
  sleep 3
done
phase="$(kubectl get "upgradecampaign/${CAMPAIGN_NAME}" -n "${NS}" \
  -o jsonpath='{.status.phase}' 2>/dev/null || true)"
if [[ "${phase}" != "Active" ]]; then
  echo "Timed out waiting for UpgradeCampaign ${CAMPAIGN_NAME} to become Active (phase=${phase})" >&2
  kubectl get "upgradecampaign/${CAMPAIGN_NAME}" -n "${NS}" -o yaml
  exit 1
fi

echo "==> run one-off fleet operator snapshot job from CronJob"
job_name="fleet-snapshot-smoke-$(date +%s)"
kubectl -n "${NS}" create job --from="cronjob/${CRONJOB}" "${job_name}"
kubectl -n "${NS}" wait --for=condition=complete "job/${job_name}" --timeout="${TIMEOUT}s"

echo "==> verify operator status snapshot on fleet PVC"
snapshot_json="$(kubectl exec -n "${NS}" "${portal_pod}" -- cat "${SNAPSHOT_PATH}")"
python3 -c "
import json, sys
body = json.loads(sys.argv[1])
assert body.get('version') == 2, body
repos = body.get('repos') or []
assert len(repos) >= 1, body
assert any('acme/tf-vpc' in str(row.get('repo_url', '')) for row in repos), body
assert not any('opa-guardrails' in str(row.get('repo_url', '')) for row in repos), body
campaigns = body.get('campaigns') or []
assert any(row.get('name') == sys.argv[2] for row in campaigns), body
assert any(not row.get('paused') for row in campaigns if row.get('name') == sys.argv[2]), body
" "${snapshot_json}" "${CAMPAIGN_NAME}"

echo "==> probe platform fleet page + API overlay"
fleet_html="$(curl -sf "http://127.0.0.1:${PORT}/platform/fleet")"
python3 -c "
import sys
html = sys.argv[1]
assert 'acme/tf-vpc' in html, 'expected kept repo on /platform/fleet'
assert 'opa-guardrails' not in html, 'expected unregistered repo removed from fleet page'
assert 'operator status from snapshot' in html.lower(), 'expected operator snapshot overlay'
" "${fleet_html}"
fleet_json="$(curl -sf "http://127.0.0.1:${PORT}/api/v2/fleet")"
python3 -c "
import json, sys
body = json.loads(sys.argv[1])
repos = body.get('repos') or []
assert any('acme/tf-vpc' in str(row.get('repo_url', '')) for row in repos), body
assert not any('opa-guardrails' in str(row.get('repo_url', '')) for row in repos), body
" "${fleet_json}"

echo "==> probe platform campaigns page + API snapshot"
campaigns_html="$(curl -sf "http://127.0.0.1:${PORT}/platform/campaigns")"
python3 -c "
import sys
html = sys.argv[1]
name = sys.argv[2]
assert name in html, 'expected campaign on /platform/campaigns'
assert 'Pause campaign' in html, 'expected pause action before patch'
assert 'Resume campaign' not in html, 'campaign should not appear paused yet'
" "${campaigns_html}" "${CAMPAIGN_NAME}"
campaigns_json="$(curl -sf "http://127.0.0.1:${PORT}/api/v2/platform/campaigns")"
python3 -c "
import json, sys
body = json.loads(sys.argv[1])
name = sys.argv[2]
assert body.get('operator_status_enabled') is True, body
snapshot = body.get('snapshot') or {}
campaigns = snapshot.get('campaigns') or []
assert any(row.get('name') == name for row in campaigns), body
assert any(not row.get('paused') for row in campaigns if row.get('name') == name), body
" "${campaigns_json}" "${CAMPAIGN_NAME}"

echo "==> pause ${CAMPAIGN_NAME} via platform console"
pause_status="$(curl -s -o /dev/null -w '%{http_code}' -X POST \
  "http://127.0.0.1:${PORT}/platform/campaigns/${NS}/${CAMPAIGN_NAME}/paused" \
  -d 'paused=1')"
if [[ "${pause_status}" != "303" ]]; then
  echo "expected HTTP 303 from campaign pause POST, got ${pause_status}" >&2
  exit 1
fi
deadline=$((SECONDS + TIMEOUT))
while (( SECONDS < deadline )); do
  paused="$(kubectl get "upgradecampaign/${CAMPAIGN_NAME}" -n "${NS}" \
    -o jsonpath='{.spec.paused}' 2>/dev/null || true)"
  if [[ "${paused}" == "true" ]]; then
    break
  fi
  sleep 2
done
paused="$(kubectl get "upgradecampaign/${CAMPAIGN_NAME}" -n "${NS}" \
  -o jsonpath='{.spec.paused}' 2>/dev/null || true)"
if [[ "${paused}" != "true" ]]; then
  echo "Timed out waiting for UpgradeCampaign spec.paused=true" >&2
  kubectl get "upgradecampaign/${CAMPAIGN_NAME}" -n "${NS}" -o yaml
  exit 1
fi

echo "==> resume ${CAMPAIGN_NAME} via platform console"
resume_status="$(curl -s -o /dev/null -w '%{http_code}' -X POST \
  "http://127.0.0.1:${PORT}/platform/campaigns/${NS}/${CAMPAIGN_NAME}/paused" \
  -d 'paused=0')"
if [[ "${resume_status}" != "303" ]]; then
  echo "expected HTTP 303 from campaign resume POST, got ${resume_status}" >&2
  exit 1
fi
deadline=$((SECONDS + TIMEOUT))
while (( SECONDS < deadline )); do
  paused="$(kubectl get "upgradecampaign/${CAMPAIGN_NAME}" -n "${NS}" \
    -o jsonpath='{.spec.paused}' 2>/dev/null || true)"
  if [[ "${paused}" == "false" ]]; then
    break
  fi
  sleep 2
done
paused="$(kubectl get "upgradecampaign/${CAMPAIGN_NAME}" -n "${NS}" \
  -o jsonpath='{.spec.paused}' 2>/dev/null || true)"
if [[ "${paused}" != "false" ]]; then
  echo "Timed out waiting for UpgradeCampaign spec.paused=false after resume" >&2
  kubectl get "upgradecampaign/${CAMPAIGN_NAME}" -n "${NS}" -o yaml
  exit 1
fi

echo "OK: fleet sync prune + operator snapshot + campaign pause chart smoke passed"
