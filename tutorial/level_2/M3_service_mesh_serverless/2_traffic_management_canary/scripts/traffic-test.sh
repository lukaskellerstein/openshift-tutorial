#!/bin/bash
# Traffic test script for L2-M3.2 — Traffic Management & Canary Deployments
#
# Sends a configurable number of requests and reports the distribution
# between v1 and v2. Useful for verifying traffic split percentages.
#
# Usage:
#   ./traffic-test.sh              # 100 requests (default)
#   ./traffic-test.sh 500          # 500 requests

set -euo pipefail

NAMESPACE="bookinfo-mesh"
NUM_REQUESTS="${1:-100}"

ROUTE_URL=$(oc get route canary-demo -n "${NAMESPACE}" -o jsonpath='{.spec.host}' 2>/dev/null)
if [[ -z "${ROUTE_URL}" ]]; then
  echo "ERROR: Could not find route 'canary-demo' in namespace '${NAMESPACE}'"
  echo "Run the setup script first: ./setup.sh"
  exit 1
fi

echo "=== Traffic Distribution Test ==="
echo "Endpoint: http://${ROUTE_URL}/version"
echo "Requests: ${NUM_REQUESTS}"
echo ""

V1_COUNT=0
V2_COUNT=0
ERROR_COUNT=0

for i in $(seq 1 "${NUM_REQUESTS}"); do
  RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "http://${ROUTE_URL}/version" 2>/dev/null || echo "000")

  if [[ "${RESPONSE}" == "200" ]]; then
    VERSION=$(curl -s "http://${ROUTE_URL}/version" 2>/dev/null)
    if echo "${VERSION}" | grep -q '"v1"'; then
      V1_COUNT=$((V1_COUNT + 1))
    elif echo "${VERSION}" | grep -q '"v2"'; then
      V2_COUNT=$((V2_COUNT + 1))
    fi
  else
    ERROR_COUNT=$((ERROR_COUNT + 1))
  fi

  # Progress indicator
  if (( i % 10 == 0 )); then
    printf "\r  Progress: %d/%d" "${i}" "${NUM_REQUESTS}"
  fi
done

echo ""
echo ""
echo "=== Results ==="
TOTAL=$((V1_COUNT + V2_COUNT))
if [[ ${TOTAL} -gt 0 ]]; then
  V1_PCT=$(( (V1_COUNT * 100) / TOTAL ))
  V2_PCT=$(( (V2_COUNT * 100) / TOTAL ))
  echo "  v1: ${V1_COUNT} requests (${V1_PCT}%)"
  echo "  v2: ${V2_COUNT} requests (${V2_PCT}%)"
else
  echo "  No successful responses received."
fi

if [[ ${ERROR_COUNT} -gt 0 ]]; then
  echo "  Errors: ${ERROR_COUNT} requests"
fi
echo ""
