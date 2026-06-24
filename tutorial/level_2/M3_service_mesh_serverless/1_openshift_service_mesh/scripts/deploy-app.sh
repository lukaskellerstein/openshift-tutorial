#!/bin/bash
# deploy-app.sh — Deploy the sample frontend/backend application into the mesh
# Run after setup.sh has completed successfully
#
# Usage: ./scripts/deploy-app.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_DIR="${SCRIPT_DIR}/../manifests"

echo "=== Deploying sample application to mesh-demo ==="

oc project mesh-demo 2>/dev/null || true

echo "Deploying backend v1..."
oc apply -f "${MANIFEST_DIR}/backend-v1-deployment.yaml" -n mesh-demo

echo "Deploying backend v2..."
oc apply -f "${MANIFEST_DIR}/backend-v2-deployment.yaml" -n mesh-demo

echo "Deploying backend service..."
oc apply -f "${MANIFEST_DIR}/backend-service.yaml" -n mesh-demo

echo "Deploying frontend..."
oc apply -f "${MANIFEST_DIR}/frontend-deployment.yaml" -n mesh-demo

echo "Deploying frontend service..."
oc apply -f "${MANIFEST_DIR}/frontend-service.yaml" -n mesh-demo

echo "Creating frontend route..."
oc apply -f "${MANIFEST_DIR}/frontend-route.yaml" -n mesh-demo

echo ""
echo "Waiting for pods to be ready (watching for 2/2 — app + sidecar)..."

oc rollout status deployment/backend-v1 -n mesh-demo --timeout=120s
oc rollout status deployment/backend-v2 -n mesh-demo --timeout=120s
oc rollout status deployment/frontend -n mesh-demo --timeout=120s

echo ""
echo "Pod status:"
oc get pods -n mesh-demo

echo ""
echo "=== Configuring traffic management ==="

echo "Applying DestinationRule (defines v1/v2 subsets)..."
oc apply -f "${MANIFEST_DIR}/destination-rule.yaml" -n mesh-demo

echo "Applying VirtualService (routes 100% to v1)..."
oc apply -f "${MANIFEST_DIR}/virtualservice.yaml" -n mesh-demo

echo ""
echo "=== Enabling strict mTLS ==="

oc apply -f "${MANIFEST_DIR}/peer-authentication.yaml" -n mesh-demo

echo ""
echo "=== Application deployed ==="
echo ""

ROUTE_HOST=$(oc get route frontend -n mesh-demo -o jsonpath='{.spec.host}')
echo "Frontend URL: http://${ROUTE_HOST}"
echo ""
echo "Test it:"
echo "  curl -s http://${ROUTE_HOST} | python3 -m json.tool"
echo ""

# Quick smoke test
echo "Running smoke test..."
response=$(curl -s "http://${ROUTE_HOST}" 2>/dev/null || echo "")
if echo "$response" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
  echo "SUCCESS: Application is responding with valid JSON"
  echo "$response" | python3 -m json.tool
else
  echo "WARNING: Application may not be ready yet. Wait a moment and try:"
  echo "  curl -s http://${ROUTE_HOST}"
fi

echo ""
echo "=== Observability URLs ==="
echo "Kiali:   https://$(oc get route kiali -n istio-system -o jsonpath='{.spec.host}' 2>/dev/null || echo 'not-available')"
echo "Jaeger:  https://$(oc get route jaeger -n istio-system -o jsonpath='{.spec.host}' 2>/dev/null || echo 'not-available')"
echo "Grafana: https://$(oc get route grafana -n istio-system -o jsonpath='{.spec.host}' 2>/dev/null || echo 'not-available')"
