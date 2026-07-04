#!/usr/bin/env bash
# L04 — Expose Services Externally: create Routes with TLS
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LESSON_DIR="$(dirname "$SCRIPT_DIR")"

step() { echo "" && echo "=== Step $1: $2 ===" && echo ""; }

oc project shopinsights

# --- Step 1: Create Routes ---
step 1 "Create Routes for all services"
oc apply -f "$LESSON_DIR/manifests/dashboard-route.yaml"
oc apply -f "$LESSON_DIR/manifests/products-route.yaml"
oc apply -f "$LESSON_DIR/manifests/orders-route.yaml"
oc apply -f "$LESSON_DIR/manifests/analytics-route.yaml"

# --- Step 2: Print URLs ---
step 2 "Service URLs"
echo "Dashboard UI:      https://$(oc get route dashboard-ui -o jsonpath='{.spec.host}')/"
echo "Products Swagger:  https://$(oc get route products-service -o jsonpath='{.spec.host}')/docs"
echo "Orders Swagger:    https://$(oc get route orders-service -o jsonpath='{.spec.host}')/docs"
echo "Analytics Swagger: https://$(oc get route analytics-service -o jsonpath='{.spec.host}')/docs"

# --- Step 3: Verify ---
step 3 "Verify Routes"
oc get routes -l app=shopinsights

echo ""
echo "Health checks via Routes:"
for svc in products-service orders-service analytics-service; do
  host=$(oc get route "$svc" -o jsonpath='{.spec.host}')
  code=$(curl -sk -o /dev/null -w "%{http_code}" "https://${host}/healthz" 2>/dev/null || echo "000")
  echo "  ${svc}: HTTP ${code}"
done

dashboard_host=$(oc get route dashboard-ui -o jsonpath='{.spec.host}')
code=$(curl -sk -o /dev/null -w "%{http_code}" "https://${dashboard_host}/" 2>/dev/null || echo "000")
echo "  dashboard-ui: HTTP ${code}"

echo ""
echo "=== L04 Complete ==="
echo "All services accessible externally via Routes."
echo "Next: cd ../L05_service_mesh && ./scripts/setup.sh"
