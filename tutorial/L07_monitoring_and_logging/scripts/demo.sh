#!/usr/bin/env bash
# L07 — Demo: generate traffic and verify observability via OpenShift Console
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LESSON_DIR="$(dirname "$SCRIPT_DIR")"

step() { echo "" && echo "=== Step $1: $2 ===" && echo ""; }

oc project shopinsights

# --- Step 1: Generate Traffic ---
step 1 "Generate traffic to all ShopInsights services"

echo "--- Products Service ---"
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

echo "Sending 5 requests to a non-existent product (triggers 404)..."
for i in $(seq 1 5); do
  oc exec deploy/dashboard-ui -n shopinsights -- \
    curl -s http://products-service:8080/products/999 > /dev/null 2>&1 || true
done

echo ""
echo "--- Orders Service ---"
echo "Sending 30 requests to /orders..."
for i in $(seq 1 30); do
  oc exec deploy/dashboard-ui -n shopinsights -- \
    curl -s http://orders-service:8080/orders > /dev/null 2>&1 || true
done

echo "Sending 10 requests to /orders/stats..."
for i in $(seq 1 10); do
  oc exec deploy/dashboard-ui -n shopinsights -- \
    curl -s http://orders-service:8080/orders/stats > /dev/null 2>&1 || true
done

echo ""
echo "--- Analytics Service ---"
echo "Sending 10 requests to /analytics/summary..."
for i in $(seq 1 10); do
  oc exec deploy/dashboard-ui -n shopinsights -- \
    curl -s http://analytics-service:8080/analytics/summary > /dev/null 2>&1 || true
done

echo "Sending 5 requests to /analytics/revenue..."
for i in $(seq 1 5); do
  oc exec deploy/dashboard-ui -n shopinsights -- \
    curl -s http://analytics-service:8080/analytics/revenue > /dev/null 2>&1 || true
done

echo ""
echo "Total: ~140 requests sent across all three services."

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
  echo "No Loki gateway route found — view logs via Console > Observe > Logs."
fi

# --- Step 4: Print URLs ---
step 4 "Explore the full stack"

CONSOLE_HOST=$(oc get route console -n openshift-console -o jsonpath='{.spec.host}' 2>/dev/null)
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
echo "=== L07 Demo Complete ==="
echo ""
echo "Next: L12 (custom Grafana dashboards for metrics, logs, traces, and alerts)"
