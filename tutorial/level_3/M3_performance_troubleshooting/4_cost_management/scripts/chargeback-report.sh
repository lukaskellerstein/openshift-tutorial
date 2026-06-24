#!/usr/bin/env bash
#
# chargeback-report.sh — Generate a chargeback report from Prometheus metrics.
#
# Queries per-namespace CPU and memory usage over the last 24 hours,
# applies configurable cost rates, groups by team and cost-center labels,
# and outputs a formatted cost table.
#
# Prerequisites:
#   - oc CLI logged in with cluster-admin access
#   - Prometheus accessible via thanos-querier route in openshift-monitoring
#
# Usage:
#   bash scripts/chargeback-report.sh
#   CPU_RATE=0.05 MEM_RATE=0.006 bash scripts/chargeback-report.sh
#
set -euo pipefail

# Configurable cost rates (per hour)
CPU_RATE_PER_CORE_HOUR="${CPU_RATE:-0.031}"    # Default: $0.031/core-hour (AWS m5.xlarge equivalent)
MEM_RATE_PER_GB_HOUR="${MEM_RATE:-0.004}"      # Default: $0.004/GB-hour

# Time window
HOURS=24

# Get Prometheus route
PROM_ROUTE=$(oc get route thanos-querier -n openshift-monitoring -o jsonpath='{.spec.host}' 2>/dev/null || true)
if [[ -z "${PROM_ROUTE}" ]]; then
  echo "ERROR: Cannot find thanos-querier route in openshift-monitoring."
  echo "Falling back to oc adm top for basic resource usage report."
  echo ""
  echo "=== Basic Resource Usage Report ==="
  echo "Date: $(date +%Y-%m-%d)"
  echo ""
  echo "Node Resources:"
  oc adm top nodes 2>/dev/null || echo "  (cannot query node metrics)"
  echo ""
  echo "Per-Namespace Pod Resources:"
  for ns in $(oc get namespaces -l cost-center -o jsonpath='{.items[*].metadata.name}' 2>/dev/null); do
    TEAM=$(oc get namespace "$ns" -o jsonpath='{.metadata.labels.team}' 2>/dev/null || echo "unknown")
    COST_CENTER=$(oc get namespace "$ns" -o jsonpath='{.metadata.labels.cost-center}' 2>/dev/null || echo "unknown")
    echo ""
    echo "--- Namespace: $ns (Team: $TEAM, Cost Center: $COST_CENTER) ---"
    oc adm top pods -n "$ns" 2>/dev/null || echo "  (no pods or metrics unavailable)"
  done
  exit 0
fi

# Get bearer token for Prometheus queries
TOKEN=$(oc whoami -t)

# Function to query Prometheus
prom_query() {
  local query="$1"
  curl -sk \
    -H "Authorization: Bearer ${TOKEN}" \
    "https://${PROM_ROUTE}/api/v1/query" \
    --data-urlencode "query=${query}" \
    2>/dev/null
}

echo "=== Chargeback Report (Last ${HOURS} Hours) ==="
echo "Date: $(date +%Y-%m-%d)"
echo ""
echo "Cost Rates: CPU=\$${CPU_RATE_PER_CORE_HOUR}/core-hour  Memory=\$${MEM_RATE_PER_GB_HOUR}/GB-hour"
echo ""

# Query CPU usage per namespace (average cores over the last 24 hours)
CPU_RESULT=$(prom_query "sum by (namespace) (rate(container_cpu_usage_seconds_total{container!=\"POD\",container!=\"\"}[${HOURS}h]))")

# Query memory usage per namespace (average GB over the last 24 hours)
MEM_RESULT=$(prom_query "sum by (namespace) (avg_over_time(container_memory_working_set_bytes{container!=\"POD\",container!=\"\"}[${HOURS}h])) / 1073741824")

# Print header
printf "%-22s %-24s %-10s %-12s %-10s\n" "Team" "Namespace" "CPU (\$)" "Memory (\$)" "Total (\$)"
printf "%-22s %-24s %-10s %-12s %-10s\n" "----" "---------" "-------" "----------" "---------"

TOTAL_CPU_COST=0
TOTAL_MEM_COST=0

# Get all namespaces with cost-center labels
for ns in $(oc get namespaces -l cost-center -o jsonpath='{.items[*].metadata.name}' 2>/dev/null); do
  TEAM=$(oc get namespace "$ns" -o jsonpath='{.metadata.labels.team}' 2>/dev/null || echo "unknown")

  # Extract CPU usage for this namespace from the Prometheus result
  CPU_CORES=$(echo "$CPU_RESULT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for result in data.get('data', {}).get('result', []):
        if result['metric'].get('namespace') == '${ns}':
            print(result['value'][1])
            sys.exit(0)
    print('0')
except:
    print('0')
" 2>/dev/null || echo "0")

  # Extract memory usage for this namespace
  MEM_GB=$(echo "$MEM_RESULT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for result in data.get('data', {}).get('result', []):
        if result['metric'].get('namespace') == '${ns}':
            print(result['value'][1])
            sys.exit(0)
    print('0')
except:
    print('0')
" 2>/dev/null || echo "0")

  # Calculate costs (usage * rate * hours)
  CPU_COST=$(python3 -c "print(f'{float(${CPU_CORES}) * ${CPU_RATE_PER_CORE_HOUR} * ${HOURS}:.2f}')" 2>/dev/null || echo "0.00")
  MEM_COST=$(python3 -c "print(f'{float(${MEM_GB}) * ${MEM_RATE_PER_GB_HOUR} * ${HOURS}:.2f}')" 2>/dev/null || echo "0.00")
  TOTAL_COST=$(python3 -c "print(f'{float(${CPU_COST}) + float(${MEM_COST}):.2f}')" 2>/dev/null || echo "0.00")

  printf "%-22s %-24s %-10s %-12s %-10s\n" "$TEAM" "$ns" "$CPU_COST" "$MEM_COST" "$TOTAL_COST"

  TOTAL_CPU_COST=$(python3 -c "print(f'{float(${TOTAL_CPU_COST}) + float(${CPU_COST}):.2f}')" 2>/dev/null || echo "0.00")
  TOTAL_MEM_COST=$(python3 -c "print(f'{float(${TOTAL_MEM_COST}) + float(${MEM_COST}):.2f}')" 2>/dev/null || echo "0.00")
done

GRAND_TOTAL=$(python3 -c "print(f'{float(${TOTAL_CPU_COST}) + float(${TOTAL_MEM_COST}):.2f}')" 2>/dev/null || echo "0.00")

echo ""
printf "%-22s %-24s %-10s %-12s %-10s\n" "TOTAL" "" "$TOTAL_CPU_COST" "$TOTAL_MEM_COST" "$GRAND_TOTAL"
echo ""
echo "Note: Costs are estimated based on configured rates. Actual cloud"
echo "provider billing may differ due to sustained-use discounts, reserved"
echo "instances, and infrastructure overhead not captured here."
