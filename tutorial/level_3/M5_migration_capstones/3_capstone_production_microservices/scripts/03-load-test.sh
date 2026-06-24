#!/bin/bash
# Load test script to exercise the microservices and trigger HPA scaling.
# Uses simple curl loops — no external tools required.
#
# This generates enough traffic to observe:
#   - HPA scaling up replicas
#   - Custom Prometheus metrics increasing
#   - Service mesh traffic management in action
#   - Circuit breaker behavior under load

set -euo pipefail

NAMESPACE="capstone-microservices"
ROUTE_HOST=$(oc get route api-gateway -n "${NAMESPACE}" -o jsonpath='{.spec.host}' 2>/dev/null)
BASE_URL="https://${ROUTE_HOST}"
DURATION=${1:-60}
CONCURRENCY=${2:-10}

if [ -z "${ROUTE_HOST}" ]; then
  echo "ERROR: Could not find API gateway route."
  echo "Make sure the deployment is running: oc get route -n ${NAMESPACE}"
  exit 1
fi

echo "============================================"
echo "  Load Test: Production Microservices"
echo "============================================"
echo ""
echo "  Target:      ${BASE_URL}"
echo "  Duration:    ${DURATION} seconds"
echo "  Concurrency: ${CONCURRENCY} parallel requests"
echo ""

# Function to send requests in a loop
send_requests() {
  local endpoint=$1
  local method=$2
  local data=$3
  local worker_id=$4
  local end_time=$(($(date +%s) + DURATION))
  local count=0

  while [ $(date +%s) -lt ${end_time} ]; do
    if [ "${method}" = "GET" ]; then
      curl -sk -o /dev/null -w "" "${BASE_URL}${endpoint}" 2>/dev/null || true
    else
      curl -sk -o /dev/null -w "" -X POST \
        -H "Content-Type: application/json" \
        -d "${data}" \
        "${BASE_URL}${endpoint}" 2>/dev/null || true
    fi
    count=$((count+1))
  done

  echo "  Worker ${worker_id}: sent ${count} ${method} requests to ${endpoint}"
}

echo "Starting load test..."
echo "  Press Ctrl+C to stop early."
echo ""

# Launch concurrent workers
PIDS=()

for i in $(seq 1 ${CONCURRENCY}); do
  case $((i % 4)) in
    0)
      send_requests "/api/orders" "GET" "" "${i}" &
      ;;
    1)
      send_requests "/api/inventory" "GET" "" "${i}" &
      ;;
    2)
      send_requests "/api/orders" "POST" '{"product":"widget-a","quantity":1}' "${i}" &
      ;;
    3)
      send_requests "/api/payments" "POST" '{"order_id":"test-order","amount":9.99,"method":"card"}' "${i}" &
      ;;
  esac
  PIDS+=($!)
done

# Wait for all workers to finish
for pid in "${PIDS[@]}"; do
  wait "${pid}" 2>/dev/null || true
done

echo ""
echo "Load test complete."
echo ""
echo "Check the results:"
echo "  oc get hpa -n ${NAMESPACE}          # See if replicas scaled up"
echo "  oc get pods -n ${NAMESPACE}          # See running pod count"
echo ""
echo "View metrics in the Web Console:"
echo "  Monitoring -> Metrics -> Custom Query:"
echo "    rate(api_gateway_http_requests_total[5m])"
echo "    rate(order_service_orders_created_total[5m])"
echo "    histogram_quantile(0.95, rate(payment_service_processing_duration_seconds_bucket[5m]))"
echo ""
