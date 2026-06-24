#!/bin/bash
# Setup script for L2-M3.2 — Traffic Management & Canary Deployments
#
# Prerequisites:
#   - OpenShift cluster running (CRC or Developer Sandbox)
#   - Service Mesh operators installed (L2-M3.1)
#   - Logged in via `oc login`
#
# This script deploys the baseline canary demo application with
# 100% traffic routed to v1.

set -euo pipefail

NAMESPACE="bookinfo-mesh"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFESTS_DIR="${SCRIPT_DIR}/../manifests"

echo "=== L2-M3.2 Setup: Traffic Management & Canary Deployments ==="

# Step 1: Create project if it doesn't exist
if oc get project "${NAMESPACE}" &>/dev/null; then
  echo "[OK] Project ${NAMESPACE} already exists"
else
  echo "[...] Creating project ${NAMESPACE}"
  oc new-project "${NAMESPACE}"
fi

oc project "${NAMESPACE}"

# Step 2: Verify the project is in the ServiceMeshMemberRoll
echo "[...] Checking ServiceMeshMemberRoll"
if oc get servicemeshmemberroll default -n istio-system -o jsonpath='{.spec.members}' 2>/dev/null | grep -q "${NAMESPACE}"; then
  echo "[OK] ${NAMESPACE} is in the ServiceMeshMemberRoll"
else
  echo "[WARN] ${NAMESPACE} is not in the ServiceMeshMemberRoll."
  echo "       Add it with:"
  echo "       oc patch servicemeshmemberroll default -n istio-system \\"
  echo "         --type='json' \\"
  echo "         -p='[{\"op\": \"add\", \"path\": \"/spec/members/-\", \"value\": \"${NAMESPACE}\"}]'"
  echo ""
  echo "       Or complete L2-M3.1 first."
  exit 1
fi

# Step 3: Deploy both versions
echo "[...] Deploying canary-demo v1 and v2"
oc apply -f "${MANIFESTS_DIR}/deployment-v1.yaml" -n "${NAMESPACE}"
oc apply -f "${MANIFESTS_DIR}/deployment-v2.yaml" -n "${NAMESPACE}"
oc apply -f "${MANIFESTS_DIR}/service.yaml" -n "${NAMESPACE}"

# Step 4: Wait for pods to be ready
echo "[...] Waiting for pods to be ready (this may take a minute for sidecar injection)"
oc wait --for=condition=available deployment/canary-demo-v1 -n "${NAMESPACE}" --timeout=120s
oc wait --for=condition=available deployment/canary-demo-v2 -n "${NAMESPACE}" --timeout=120s

# Step 5: Apply DestinationRule
echo "[...] Applying DestinationRule"
oc apply -f "${MANIFESTS_DIR}/destination-rule.yaml" -n "${NAMESPACE}"

# Step 6: Apply Gateway and Route
echo "[...] Applying Gateway and Route"
oc apply -f "${MANIFESTS_DIR}/gateway.yaml" -n "${NAMESPACE}"
oc apply -f "${MANIFESTS_DIR}/route.yaml" -n "${NAMESPACE}"

# Step 7: Route 100% to v1 (baseline)
echo "[...] Applying VirtualService (100% to v1)"
oc apply -f "${MANIFESTS_DIR}/virtualservice-100-v1.yaml" -n "${NAMESPACE}"

# Step 8: Display status
echo ""
echo "=== Setup Complete ==="
echo ""
oc get pods -l app=canary-demo -n "${NAMESPACE}"
echo ""
ROUTE_URL=$(oc get route canary-demo -n "${NAMESPACE}" -o jsonpath='{.spec.host}' 2>/dev/null || echo "not-available")
echo "Route URL: http://${ROUTE_URL}"
echo "Test with: curl -s http://${ROUTE_URL}/version"
echo ""
echo "Kiali URL: https://$(oc get route kiali -n istio-system -o jsonpath='{.spec.host}' 2>/dev/null || echo 'not-available')"
echo ""
echo "All traffic is currently routed to v1. Proceed with the lesson steps."
