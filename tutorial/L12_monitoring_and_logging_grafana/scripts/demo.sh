#!/usr/bin/env bash
# L12 — Demo: generate traffic and explore Grafana dashboards
set -euo pipefail

step() { echo "" && echo "=== Step $1: $2 ===" && echo ""; }

oc project shopinsights

# --- Step 1: Generate Traffic ---
step 1 "Generate traffic to all services"

echo "Sending 50 requests to Products Service /products..."
for i in $(seq 1 50); do
  oc exec deploy/dashboard-ui -n shopinsights -- \
    curl -s http://products-service:8080/products > /dev/null 2>&1 || true
done

echo "Sending 30 requests to /products/{id}..."
for i in $(seq 1 30); do
  ID=$(( (RANDOM % 12) + 1 ))
  oc exec deploy/dashboard-ui -n shopinsights -- \
    curl -s "http://products-service:8080/products/${ID}" > /dev/null 2>&1 || true
done

echo "Sending 20 requests to Orders Service /orders..."
for i in $(seq 1 20); do
  oc exec deploy/dashboard-ui -n shopinsights -- \
    curl -s http://orders-service:8080/orders > /dev/null 2>&1 || true
done

echo "Sending 10 requests to Analytics Service /analytics/summary..."
for i in $(seq 1 10); do
  oc exec deploy/dashboard-ui -n shopinsights -- \
    curl -s http://analytics-service:8080/analytics/summary > /dev/null 2>&1 || true
done

echo ""
echo "Total: ~110 requests sent across all services."

# --- Step 2: Print dashboard URLs ---
step 2 "Explore dashboards in Grafana"

GRAFANA_HOST=$(oc get route grafana-route -n shopinsights -o jsonpath='{.spec.host}' 2>/dev/null || echo "")

if [ -n "$GRAFANA_HOST" ]; then
  echo "============================================"
  echo "  Open Grafana and explore:"
  echo "============================================"
  echo ""
  echo "  Login: admin / openshift"
  echo ""
  echo "  1. Overview (CPU, memory, restarts, request rate, alerts):"
  echo "     https://${GRAFANA_HOST}/d/shopinsights-overview"
  echo ""
  echo "  2. Products Service (request rate, latency, DuckDB, errors, logs, alerts):"
  echo "     https://${GRAFANA_HOST}/d/shopinsights-products"
  echo ""
  echo "  3. Logs (all 4 services — products, orders, analytics, dashboard-ui):"
  echo "     https://${GRAFANA_HOST}/d/shopinsights-logs"
  echo ""
  echo "  4. Traces (Istio service mesh spans via Tempo):"
  echo "     https://${GRAFANA_HOST}/d/shopinsights-traces"
  echo ""
else
  echo "ERROR: Grafana route not found. Run setup.sh first."
fi

echo "=== L12 Demo Complete ==="
