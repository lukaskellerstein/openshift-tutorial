#!/usr/bin/env bash
# L07 — Demo: generate traffic and verify all three observability pillars
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LESSON_DIR="$(dirname "$SCRIPT_DIR")"

step() { echo "" && echo "=== Step $1: $2 ===" && echo ""; }

oc project shopinsights

# --- Step 1: Generate Traffic ---
step 1 "Generate traffic to Products Service"

echo "Sending 50 requests to /products..."
for i in $(seq 1 50); do
  oc exec deploy/dashboard-ui -n shopinsights -- \
    curl -s http://products-service:8080/products > /dev/null 2>&1 || true
done

echo "Sending 30 requests to /products/{id} (random IDs 1-12)..."
for i in $(seq 1 30); do
  ID=$(( (RANDOM % 12) + 1 ))
  oc exec deploy/dashboard-ui -n shopinsights -- \
    curl -s "http://products-service:8080/products/${ID}" > /dev/null 2>&1 || true
done

echo "Sending 10 requests to /healthz..."
for i in $(seq 1 10); do
  oc exec deploy/dashboard-ui -n shopinsights -- \
    curl -s http://products-service:8080/healthz > /dev/null 2>&1 || true
done

echo "Sending 5 requests to a non-existent product (triggers 404)..."
for i in $(seq 1 5); do
  oc exec deploy/dashboard-ui -n shopinsights -- \
    curl -s http://products-service:8080/products/999 > /dev/null 2>&1 || true
done

echo ""
echo "Total: ~95 requests sent."

# --- Step 2: Verify Prometheus Metrics ---
step 2 "Verify Prometheus metrics via Thanos Querier"

THANOS_URL="https://$(oc get route thanos-querier -n openshift-monitoring -o jsonpath='{.spec.host}' 2>/dev/null)"
TOKEN=$(oc whoami -t)

echo "Querying http_requests_total..."
curl -sk -H "Authorization: Bearer ${TOKEN}" \
  "${THANOS_URL}/api/v1/query?query=sum(http_requests_total{namespace=\"shopinsights\"})%20by%20(exported_endpoint)" \
  2>/dev/null | python3 -m json.tool 2>/dev/null | head -30 || echo "(query returned no data yet — wait 30s for scrape)"

echo ""
echo "Querying active_connections..."
curl -sk -H "Authorization: Bearer ${TOKEN}" \
  "${THANOS_URL}/api/v1/query?query=active_connections{namespace=\"shopinsights\"}" \
  2>/dev/null | python3 -m json.tool 2>/dev/null | head -15 || echo "(no data yet)"

# --- Step 3: Verify Loki Logs ---
step 3 "Verify logs in Loki"

LOKI_ROUTE=$(oc get route logging-loki-gateway-http -n openshift-logging -o jsonpath='{.spec.host}' 2>/dev/null || echo "")
if [ -n "$LOKI_ROUTE" ]; then
  echo "Querying Loki for shopinsights application logs..."
  curl -sk -H "Authorization: Bearer ${TOKEN}" \
    "https://${LOKI_ROUTE}/api/logs/v1/application/loki/api/v1/query_range?query=%7Bkubernetes_namespace_name%3D%22shopinsights%22%7D&limit=5" \
    2>/dev/null | python3 -m json.tool 2>/dev/null | head -40 || echo "(no logs yet — collector pods may need a minute)"
else
  echo "No Loki gateway route found. Checking via internal service..."
  oc exec deploy/grafana-deployment -n shopinsights -- \
    curl -sk -H "Authorization: Bearer $(oc create token grafana-sa -n shopinsights)" \
    "https://logging-loki-gateway-http.openshift-logging.svc.cluster.local:8080/api/logs/v1/application/loki/api/v1/query_range?query=%7Bkubernetes_namespace_name%3D%22shopinsights%22%7D&limit=5" \
    2>/dev/null | python3 -m json.tool 2>/dev/null | head -40 || echo "(no logs yet)"
fi

# --- Step 4: Print URLs ---
step 4 "Explore the full stack"

CONSOLE_HOST=$(oc get route console -n openshift-console -o jsonpath='{.spec.host}' 2>/dev/null)
GRAFANA_HOST=$(oc get route grafana-route -n shopinsights -o jsonpath='{.spec.host}' 2>/dev/null || echo "")
DASHBOARD_HOST=$(oc get route dashboard-ui -n shopinsights -o jsonpath='{.spec.host}' 2>/dev/null || echo "")

echo "============================================"
echo "  Open these URLs to explore:"
echo "============================================"
echo ""
echo "  1. Dashboard (generate more traffic):"
echo "     https://${DASHBOARD_HOST}"
echo ""
echo "  2. Prometheus Metrics (Console):"
echo "     https://${CONSOLE_HOST}/monitoring/query-browser"
echo "     Try: sum(rate(http_requests_total{namespace=\"shopinsights\"}[5m])) by (exported_endpoint)"
echo ""
echo "  3. Centralized Logs (Console):"
echo "     https://${CONSOLE_HOST}/monitoring/logs"
echo "     Filter by namespace: shopinsights"
echo ""
echo "  4. Alerting Rules (Console):"
echo "     https://${CONSOLE_HOST}/monitoring/alerts"
echo "     Filter by Source: User"
echo ""
if [ -n "$GRAFANA_HOST" ]; then
  echo "  5. Grafana Dashboard:"
  echo "     https://${GRAFANA_HOST}"
  echo "     Login: admin/admin (or browse anonymously)"
  echo "     Dashboard: ShopInsights - Products Service"
  echo ""
fi
echo "=== L07 Demo Complete ==="
