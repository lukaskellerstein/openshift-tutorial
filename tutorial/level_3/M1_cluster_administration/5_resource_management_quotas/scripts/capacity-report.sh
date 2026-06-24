#!/usr/bin/env bash
# capacity-report.sh — Generate a cluster capacity and quota utilization report
# Usage: ./scripts/capacity-report.sh
#
# Requires: cluster-admin access, oc CLI logged in

set -euo pipefail

echo "========================================"
echo "  OpenShift Cluster Capacity Report"
echo "  Generated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "========================================"
echo

# --- Node Capacity ---
echo "--- Node Capacity ---"
oc adm top nodes 2>/dev/null || echo "(Node metrics not available — ensure metrics-server is running)"
echo

# --- Allocatable vs Requested ---
echo "--- Per-Node Allocation Summary ---"
for node in $(oc get nodes -o jsonpath='{.items[*].metadata.name}'); do
  echo "Node: ${node}"
  oc describe node "${node}" | sed -n '/Allocated resources:/,/Events:/p' | head -n 10
  echo
done

# --- ResourceQuotas Across All Namespaces ---
echo "--- ResourceQuotas (All Namespaces) ---"
oc get resourcequota --all-namespaces -o custom-columns=\
NAMESPACE:.metadata.namespace,\
NAME:.metadata.name,\
CPU_REQ_USED:.status.used.requests\\.cpu,\
CPU_REQ_HARD:.status.hard.requests\\.cpu,\
MEM_REQ_USED:.status.used.requests\\.memory,\
MEM_REQ_HARD:.status.hard.requests\\.memory,\
PODS_USED:.status.used.pods,\
PODS_HARD:.status.hard.pods \
2>/dev/null || echo "(No ResourceQuotas found)"
echo

# --- ClusterResourceQuotas ---
echo "--- ClusterResourceQuotas ---"
CRQ_LIST=$(oc get clusterresourcequota -o name 2>/dev/null)
if [ -z "${CRQ_LIST}" ]; then
  echo "(No ClusterResourceQuotas found)"
else
  for crq in ${CRQ_LIST}; do
    echo
    oc describe "${crq}" 2>/dev/null | grep -E '(Name:|Selector:|Resource|Used|Hard|Namespace)' | head -n 30
    echo "---"
  done
fi
echo

# --- PriorityClasses ---
echo "--- PriorityClasses (non-system) ---"
oc get priorityclasses -o custom-columns=\
NAME:.metadata.name,\
VALUE:.value,\
GLOBAL_DEFAULT:.globalDefault,\
PREEMPTION:.preemptionPolicy \
2>/dev/null | grep -v "^system-" || echo "(No custom PriorityClasses found)"
echo

# --- Pods Without Resource Requests ---
echo "--- Pods Without Resource Requests (potential quota issues) ---"
PODS_NO_REQ=$(oc get pods --all-namespaces -o json 2>/dev/null | \
  python3 -c "
import json, sys
data = json.load(sys.stdin)
count = 0
for pod in data.get('items', []):
    ns = pod['metadata']['namespace']
    name = pod['metadata']['name']
    for c in pod['spec'].get('containers', []):
        res = c.get('resources', {})
        if not res.get('requests'):
            print(f'  {ns}/{name} container={c[\"name\"]} — no requests')
            count += 1
            break
if count == 0:
    print('  (All pods have resource requests)')
" 2>/dev/null) || PODS_NO_REQ="  (Unable to check — python3 not available)"
echo "${PODS_NO_REQ}"
echo

echo "========================================"
echo "  Report complete."
echo "========================================"
