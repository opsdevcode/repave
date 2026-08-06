#!/usr/bin/env bash
# kind: portal (Helm + fleet registry) + operator fleetSync + drift fixture.
#
# Prerequisites: docker, kind, helm, kubectl.
#
#   make kind-co-install
#   CO_INSTALL_KEEP_CLUSTER=1 make kind-co-install   # leave cluster running
#   CO_INSTALL_SKIP_BUILD=1 make kind-co-install     # reuse local images
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CHART="${ROOT}/deploy/k8s/chart"
OPERATOR_CHART="${ROOT}/deploy/k8s/operator-chart"
OPERATOR="${ROOT}/operator"
MODULES_HOST="${OPERATOR}/testdata/modules"
FLEET_REGISTRY="${ROOT}/deploy/k8s/testdata/fleet-registry.jsonl"

CLUSTER_NAME="${KIND_CLUSTER_NAME:-repave-local}"
PORTAL_NS="${CO_INSTALL_PORTAL_NAMESPACE:-repave}"
OPERATOR_NS="${CO_INSTALL_OPERATOR_NAMESPACE:-${PORTAL_NS}}"
ENGINE_IMG="${CO_INSTALL_ENGINE_IMAGE:-repave-engine:local}"
OPERATOR_IMG="${CO_INSTALL_OPERATOR_IMAGE:-repave-operator:dev}"
TIMEOUT="${CO_INSTALL_TIMEOUT_SEC:-240}"
MANIFESTS_DIR="${CO_INSTALL_MANIFESTS_DIR:-$(mktemp -d)}"

require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$1 is required" >&2
    exit 1
  fi
}

require kind
require helm
require kubectl
require docker
require openssl

cleanup_cluster() {
  if [[ "${CO_INSTALL_KEEP_CLUSTER:-}" == "1" ]]; then
    echo "CO_INSTALL_KEEP_CLUSTER=1; cluster ${CLUSTER_NAME} left running"
    echo "  kubectl config use-context kind-${CLUSTER_NAME}"
    echo "  kubectl port-forward svc/repave 8088:8088 -n ${PORTAL_NS}"
    return 0
  fi
  kind delete cluster --name "${CLUSTER_NAME}" >/dev/null 2>&1 || true
}

if [[ "${CO_INSTALL_KEEP_CLUSTER:-}" != "1" ]]; then
  trap cleanup_cluster EXIT
fi

if [[ "${CO_INSTALL_SKIP_CLUSTER:-}" != "1" ]]; then
  echo "==> kind cluster ${CLUSTER_NAME} (module mount at /modules)"
  kind delete cluster --name "${CLUSTER_NAME}" >/dev/null 2>&1 || true
  tmp_kind_cfg="$(mktemp)"
  sed "s|hostPath: ./testdata/modules|hostPath: ${MODULES_HOST}|" \
    "${OPERATOR}/hack/kind-config.yaml" >"${tmp_kind_cfg}"
  kind create cluster --name "${CLUSTER_NAME}" --config "${tmp_kind_cfg}"
  rm -f "${tmp_kind_cfg}"
else
  kubectl config use-context "kind-${CLUSTER_NAME}"
fi

if [[ "${CO_INSTALL_SKIP_BUILD:-}" != "1" ]]; then
  echo "==> docker build ${ENGINE_IMG} (portal)"
  docker build -f "${ROOT}/deploy/local/Dockerfile" -t "${ENGINE_IMG}" "${ROOT}"
  echo "==> docker build ${OPERATOR_IMG} (slim distroless operator)"
  docker build -f "${OPERATOR}/Dockerfile" -t "${OPERATOR_IMG}" "${OPERATOR}"
fi

echo "==> kind load images"
kind load docker-image "${ENGINE_IMG}" --name "${CLUSTER_NAME}"
kind load docker-image "${OPERATOR_IMG}" --name "${CLUSTER_NAME}"

echo "==> helm portal (${PORTAL_NS}) with fleet registry"
helm upgrade --install repave "${CHART}" \
  --namespace "${PORTAL_NS}" --create-namespace \
  -f "${CHART}/values-kind.yaml" \
  --set image.repository="${ENGINE_IMG%%:*}" \
  --set image.tag="${ENGINE_IMG##*:}" \
  --set image.pullPolicy=Never \
  --set repave.output.githubOrg=example-org \
  --wait --timeout "${TIMEOUT}s"
kubectl -n "${PORTAL_NS}" rollout status deployment/repave --timeout="${TIMEOUT}s"

PORTAL_API_URL="http://repave.${PORTAL_NS}.svc.cluster.local:8088"
echo "==> operator webhook TLS + Helm install (REPAVE_API_URL=${PORTAL_API_URL})"
chmod +x "${OPERATOR}/hack/setup-webhook-certs.sh"
WEBHOOK_NAMESPACE="${OPERATOR_NS}" bash "${OPERATOR}/hack/setup-webhook-certs.sh"
CA_BUNDLE="$(base64 <"${OPERATOR}/hack/webhook-certs/ca.crt" | tr -d '\n')"
helm upgrade --install repave-operator "${OPERATOR_CHART}" \
  --namespace "${OPERATOR_NS}" --create-namespace \
  -f "${OPERATOR_CHART}/values-kind.yaml" \
  -f "${OPERATOR_CHART}/values-fleet-shared.yaml" \
  --set "image.repository=${OPERATOR_IMG%%:*}" \
  --set "image.tag=${OPERATOR_IMG##*:}" \
  --set image.pullPolicy=Never \
  --set "repave.apiUrl=${PORTAL_API_URL}" \
  --set "webhook.caBundle=${CA_BUNDLE}" \
  --wait --timeout "${TIMEOUT}s"
kubectl -n "${OPERATOR_NS}" rollout status deployment/repave-operator --timeout="${TIMEOUT}s"

echo "==> seed fleet registry in portal pod (shared PVC repave-fleet)"
portal_pod="$(kubectl get pod -n "${PORTAL_NS}" -l app.kubernetes.io/name=repave \
  -o jsonpath='{.items[0].metadata.name}')"
kubectl exec -n "${PORTAL_NS}" "${portal_pod}" -- mkdir -p /data/fleet
kubectl cp "${FLEET_REGISTRY}" "${PORTAL_NS}/${portal_pod}:/data/fleet/registry.jsonl"

echo "==> wait for operator fleet sync to create GoldenPathRepos"
deadline=$((SECONDS + TIMEOUT))
while (( SECONDS < deadline )); do
  count="$(kubectl get goldenpathrepo -l repave.dev/managed-by=repave-fleet --no-headers 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "${count}" -ge 2 ]]; then
    break
  fi
  sleep 3
done
if [[ "${count:-0}" -lt 2 ]]; then
  echo "Timed out waiting for fleet-managed GoldenPathRepos" >&2
  kubectl get goldenpathrepo -A
  exit 1
fi

echo "==> apply local drift fixture"
kubectl apply -f "${OPERATOR}/config/e2e/goldenpathrepo-drift.yaml"

echo "==> assert CRD conversion (v1alpha1 apply → v1beta1 storage)"
chmod +x "${OPERATOR}/hack/assert-crd-conversion.sh"
bash "${OPERATOR}/hack/assert-crd-conversion.sh"

echo "==> wait for e2e-drift upgrade plan"
deadline=$((SECONDS + TIMEOUT))
while (( SECONDS < deadline )); do
  planned="$(kubectl get goldenpathrepo e2e-drift \
    -o jsonpath='{.status.conditions[?(@.type=="UpgradePlanned")].status}' 2>/dev/null || true)"
  if [[ "${planned}" == "True" ]]; then
    break
  fi
  sleep 3
done
if [[ "${planned}" != "True" ]]; then
  echo "Timed out waiting for e2e-drift UpgradePlanned=True" >&2
  kubectl get goldenpathrepo -A
  exit 1
fi

echo "==> summary"
kubectl get goldenpathrepo -A
curl -sf "http://127.0.0.1:8088/health" 2>/dev/null | grep -q ok && echo "Portal /health OK (port-forward already up)" || true

echo ""
echo "OK: kind co-install complete"
echo "  kubectl port-forward svc/repave 8088:8088 -n ${PORTAL_NS}"
echo "  open http://127.0.0.1:8088/fleet  (seeded registry)"
echo "  kubectl get goldenpathrepo -A"
