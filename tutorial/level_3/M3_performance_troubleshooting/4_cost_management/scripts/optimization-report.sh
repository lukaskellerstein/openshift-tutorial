#!/usr/bin/env bash
#
# optimization-report.sh — Generate resource optimization recommendations.
#
# Compares actual CPU/memory usage against requests and limits for all
# deployments in namespaces with cost-center labels. Identifies:
#   - Over-provisioned workloads (usage < 30% of requests)
#   - Under-provisioned workloads (usage > 80% of limits)
#   - Idle workloads (near-zero usage)
#
# Prerequisites:
#   - oc CLI logged in with cluster-admin access
#   - Metrics server or Prometheus accessible
#
# Usage:
#   bash scripts/optimization-report.sh
#
set -euo pipefail

echo "=== Resource Optimization Recommendations ==="
echo "Date: $(date +%Y-%m-%d)"
echo ""
echo "Analyzing deployments in cost-labeled namespaces..."
echo ""

OVER_PROVISIONED=()
UNDER_PROVISIONED=()
IDLE_WORKLOADS=()

# Get all namespaces with cost-center labels
NAMESPACES=$(oc get namespaces -l cost-center -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)

if [[ -z "${NAMESPACES}" ]]; then
  echo "No namespaces with cost-center labels found."
  echo "Label namespaces with 'cost-center' to enable optimization analysis."
  exit 0
fi

for ns in ${NAMESPACES}; do
  # Get all deployments in this namespace
  DEPLOYMENTS=$(oc get deployments -n "$ns" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)

  for deploy in ${DEPLOYMENTS}; do
    # Get resource requests from the deployment spec
    CPU_REQUEST=$(oc get deployment "$deploy" -n "$ns" \
      -o jsonpath='{.spec.template.spec.containers[0].resources.requests.cpu}' 2>/dev/null || echo "0")
    MEM_REQUEST=$(oc get deployment "$deploy" -n "$ns" \
      -o jsonpath='{.spec.template.spec.containers[0].resources.requests.memory}' 2>/dev/null || echo "0")
    CPU_LIMIT=$(oc get deployment "$deploy" -n "$ns" \
      -o jsonpath='{.spec.template.spec.containers[0].resources.limits.cpu}' 2>/dev/null || echo "0")
    MEM_LIMIT=$(oc get deployment "$deploy" -n "$ns" \
      -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}' 2>/dev/null || echo "0")

    # Get actual usage from metrics (top pods)
    POD_METRICS=$(oc adm top pods -n "$ns" -l "app=${deploy}" --no-headers 2>/dev/null || true)

    if [[ -z "${POD_METRICS}" ]]; then
      continue
    fi

    # Parse actual CPU usage (first pod as representative)
    ACTUAL_CPU=$(echo "$POD_METRICS" | head -1 | awk '{print $2}' | sed 's/m//')
    ACTUAL_MEM=$(echo "$POD_METRICS" | head -1 | awk '{print $3}' | sed 's/Mi//')

    # Convert CPU request to millicores for comparison
    CPU_REQUEST_M=$(python3 -c "
req = '${CPU_REQUEST}'
if req.endswith('m'):
    print(int(req[:-1]))
elif req.replace('.','',1).isdigit():
    print(int(float(req) * 1000))
else:
    print(0)
" 2>/dev/null || echo "0")

    # Convert CPU limit to millicores
    CPU_LIMIT_M=$(python3 -c "
lim = '${CPU_LIMIT}'
if lim.endswith('m'):
    print(int(lim[:-1]))
elif lim.replace('.','',1).isdigit():
    print(int(float(lim) * 1000))
else:
    print(0)
" 2>/dev/null || echo "0")

    # Convert memory request to Mi
    MEM_REQUEST_MI=$(python3 -c "
req = '${MEM_REQUEST}'
if req.endswith('Mi'):
    print(int(req[:-2]))
elif req.endswith('Gi'):
    print(int(float(req[:-2]) * 1024))
elif req.endswith('Ki'):
    print(int(float(req[:-2]) / 1024))
else:
    print(0)
" 2>/dev/null || echo "0")

    # Convert memory limit to Mi
    MEM_LIMIT_MI=$(python3 -c "
lim = '${MEM_LIMIT}'
if lim.endswith('Mi'):
    print(int(lim[:-2]))
elif lim.endswith('Gi'):
    print(int(float(lim[:-2]) * 1024))
elif lim.endswith('Ki'):
    print(int(float(lim[:-2]) / 1024))
else:
    print(0)
" 2>/dev/null || echo "0")

    # Check for over-provisioned (usage < 30% of request)
    if [[ "${CPU_REQUEST_M}" -gt 0 ]] && [[ "${ACTUAL_CPU}" -gt 0 ]]; then
      CPU_UTIL=$(python3 -c "print(int(${ACTUAL_CPU} / ${CPU_REQUEST_M} * 100))" 2>/dev/null || echo "0")
      if [[ "${CPU_UTIL}" -lt 30 ]]; then
        RECOMMENDED_CPU=$((ACTUAL_CPU * 2))
        if [[ "${RECOMMENDED_CPU}" -lt 50 ]]; then
          RECOMMENDED_CPU=50
        fi
        OVER_PROVISIONED+=("  Namespace: $ns / Deployment: $deploy")
        OVER_PROVISIONED+=("    CPU: requested ${CPU_REQUEST_M}m, avg usage ${ACTUAL_CPU}m -> recommended ${RECOMMENDED_CPU}m (${CPU_UTIL}% utilization)")
      fi
    fi

    if [[ "${MEM_REQUEST_MI}" -gt 0 ]] && [[ "${ACTUAL_MEM}" -gt 0 ]]; then
      MEM_UTIL=$(python3 -c "print(int(${ACTUAL_MEM} / ${MEM_REQUEST_MI} * 100))" 2>/dev/null || echo "0")
      if [[ "${MEM_UTIL}" -lt 30 ]]; then
        RECOMMENDED_MEM=$((ACTUAL_MEM * 2))
        if [[ "${RECOMMENDED_MEM}" -lt 64 ]]; then
          RECOMMENDED_MEM=64
        fi
        OVER_PROVISIONED+=("    Memory: requested ${MEM_REQUEST_MI}Mi, avg usage ${ACTUAL_MEM}Mi -> recommended ${RECOMMENDED_MEM}Mi (${MEM_UTIL}% utilization)")
      fi
    fi

    # Check for under-provisioned (usage > 80% of limit)
    if [[ "${CPU_LIMIT_M}" -gt 0 ]] && [[ "${ACTUAL_CPU}" -gt 0 ]]; then
      CPU_LIMIT_UTIL=$(python3 -c "print(int(${ACTUAL_CPU} / ${CPU_LIMIT_M} * 100))" 2>/dev/null || echo "0")
      if [[ "${CPU_LIMIT_UTIL}" -gt 80 ]]; then
        RECOMMENDED_LIMIT=$((CPU_LIMIT_M * 3 / 2))
        UNDER_PROVISIONED+=("  Namespace: $ns / Deployment: $deploy")
        UNDER_PROVISIONED+=("    CPU: limit ${CPU_LIMIT_M}m, p99 usage ~${ACTUAL_CPU}m -> recommended limit ${RECOMMENDED_LIMIT}m (${CPU_LIMIT_UTIL}% of limit)")
      fi
    fi

    if [[ "${MEM_LIMIT_MI}" -gt 0 ]] && [[ "${ACTUAL_MEM}" -gt 0 ]]; then
      MEM_LIMIT_UTIL=$(python3 -c "print(int(${ACTUAL_MEM} / ${MEM_LIMIT_MI} * 100))" 2>/dev/null || echo "0")
      if [[ "${MEM_LIMIT_UTIL}" -gt 80 ]]; then
        RECOMMENDED_MEM_LIMIT=$((MEM_LIMIT_MI * 3 / 2))
        UNDER_PROVISIONED+=("    Memory: limit ${MEM_LIMIT_MI}Mi, p99 usage ~${ACTUAL_MEM}Mi -> recommended limit ${RECOMMENDED_MEM_LIMIT}Mi (${MEM_LIMIT_UTIL}% of limit)")
      fi
    fi

    # Check for idle workloads (< 5m CPU usage)
    if [[ "${ACTUAL_CPU}" -lt 5 ]] && [[ "${ACTUAL_MEM}" -lt 32 ]]; then
      IDLE_WORKLOADS+=("  Namespace: $ns / Deployment: $deploy")
      IDLE_WORKLOADS+=("    CPU: ${ACTUAL_CPU}m, Memory: ${ACTUAL_MEM}Mi — consider scale-to-zero or removal")
    fi
  done
done

# Print results
echo "OVER-PROVISIONED (reduce requests to save cost):"
if [[ ${#OVER_PROVISIONED[@]} -gt 0 ]]; then
  for line in "${OVER_PROVISIONED[@]}"; do
    echo "$line"
  done
else
  echo "  (none detected)"
fi

echo ""
echo "UNDER-PROVISIONED (increase limits to prevent throttling):"
if [[ ${#UNDER_PROVISIONED[@]} -gt 0 ]]; then
  for line in "${UNDER_PROVISIONED[@]}"; do
    echo "$line"
  done
else
  echo "  (none detected)"
fi

echo ""
echo "IDLE WORKLOADS (consider removal or scale-to-zero):"
if [[ ${#IDLE_WORKLOADS[@]} -gt 0 ]]; then
  for line in "${IDLE_WORKLOADS[@]}"; do
    echo "$line"
  done
else
  echo "  (none detected)"
fi

echo ""
echo "Note: Recommendations are based on current point-in-time metrics."
echo "For production decisions, analyze at least 7 days of usage data"
echo "to account for workload variability (business hours, batch jobs,"
echo "traffic spikes). Apply changes gradually: adjust by 20-30% at a"
echo "time and monitor for 48 hours before further adjustments."
