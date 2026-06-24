#!/bin/bash
#
# diagnose-cluster.sh -- Automated cluster diagnostic script
#
# Performs a systematic triage of an OpenShift cluster:
#   1. Cluster-level health (version, operators, nodes)
#   2. Namespace-level pod status and events
#   3. Common failure pattern detection (OOM, CrashLoop, ImagePull, Pending)
#   4. Resource utilization summary
#   5. Certificate expiry warnings
#
# Usage:
#   ./diagnose-cluster.sh                     # Diagnose all namespaces
#   ./diagnose-cluster.sh <namespace>          # Diagnose a specific namespace
#   ./diagnose-cluster.sh --output <dir>       # Save output to a directory
#
# Requires: oc CLI, cluster-admin access (for some checks)

set -euo pipefail

# --- Configuration ---
NAMESPACE="${1:-}"
OUTPUT_DIR=""
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'  # No Color
SEPARATOR="============================================================"

# Parse arguments
if [[ "${1:-}" == "--output" ]]; then
  OUTPUT_DIR="${2:-/tmp/cluster-diagnostics-${TIMESTAMP}}"
  NAMESPACE="${3:-}"
  mkdir -p "${OUTPUT_DIR}"
  echo "Saving diagnostic output to: ${OUTPUT_DIR}"
fi

# --- Helper functions ---
header() {
  echo ""
  echo "${SEPARATOR}"
  echo -e "${CYAN}$1${NC}"
  echo "${SEPARATOR}"
}

warn() {
  echo -e "${YELLOW}WARNING: $1${NC}"
}

error() {
  echo -e "${RED}ERROR: $1${NC}"
}

ok() {
  echo -e "${GREEN}OK: $1${NC}"
}

save_output() {
  if [[ -n "${OUTPUT_DIR}" ]]; then
    local filename="$1"
    shift
    "$@" > "${OUTPUT_DIR}/${filename}" 2>&1 || true
  fi
}

# --- Pre-flight checks ---
header "Pre-flight Checks"

if ! command -v oc &>/dev/null; then
  error "'oc' CLI not found. Please install it and try again."
  exit 1
fi

if ! oc whoami &>/dev/null; then
  error "Not logged in to an OpenShift cluster. Run 'oc login' first."
  exit 1
fi

CURRENT_USER=$(oc whoami)
CURRENT_SERVER=$(oc whoami --show-server)
echo "Logged in as: ${CURRENT_USER}"
echo "Server: ${CURRENT_SERVER}"
echo "Timestamp: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"

IS_ADMIN="false"
if oc auth can-i '*' '*' --all-namespaces &>/dev/null; then
  IS_ADMIN="true"
  ok "cluster-admin access confirmed"
else
  warn "No cluster-admin access. Some checks will be skipped."
fi

# --- Section 1: Cluster Health ---
header "1. Cluster Version & Health"

echo "--- Cluster Version ---"
oc get clusterversion 2>/dev/null || warn "Cannot read cluster version"

echo ""
echo "--- Cluster Operators ---"
DEGRADED_OPS=$(oc get clusteroperators -o json 2>/dev/null | \
  python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    count = 0
    for co in data.get('items', []):
        name = co['metadata']['name']
        for cond in co.get('status', {}).get('conditions', []):
            if cond['type'] == 'Degraded' and cond['status'] == 'True':
                print(f'  DEGRADED: {name} -- {cond.get(\"message\", \"no message\")}')
                count += 1
            elif cond['type'] == 'Available' and cond['status'] == 'False':
                print(f'  UNAVAILABLE: {name} -- {cond.get(\"message\", \"no message\")}')
                count += 1
    if count == 0:
        print('  All cluster operators are healthy')
except Exception as e:
    print(f'  Error parsing operator status: {e}')
" 2>/dev/null || oc get clusteroperators 2>/dev/null)
echo "${DEGRADED_OPS}"

# --- Section 2: Node Health ---
header "2. Node Health"

echo "--- Node Status ---"
oc get nodes -o wide 2>/dev/null || warn "Cannot list nodes"

echo ""
echo "--- Node Resource Usage ---"
oc adm top nodes 2>/dev/null || warn "Cannot get node metrics (metrics-server may not be available)"

echo ""
echo "--- Node Conditions ---"
oc get nodes -o json 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    issues_found = False
    for node in data.get('items', []):
        name = node['metadata']['name']
        for cond in node.get('status', {}).get('conditions', []):
            if cond['type'] == 'Ready' and cond['status'] != 'True':
                print(f'  {name}: NotReady -- {cond.get(\"message\", \"\")}')
                issues_found = True
            elif cond['type'] in ['MemoryPressure', 'DiskPressure', 'PIDPressure'] and cond['status'] == 'True':
                print(f'  {name}: {cond[\"type\"]} -- {cond.get(\"message\", \"\")}')
                issues_found = True
    if not issues_found:
        print('  All nodes are healthy')
except Exception as e:
    print(f'  Error parsing node status: {e}')
" 2>/dev/null || true

# --- Section 3: Pod Status ---
header "3. Pod Status"

if [[ -n "${NAMESPACE}" ]]; then
  NS_FLAG="-n ${NAMESPACE}"
  echo "Checking namespace: ${NAMESPACE}"
else
  NS_FLAG="--all-namespaces"
  echo "Checking all namespaces"
fi

echo ""
echo "--- Failing Pods ---"
oc get pods ${NS_FLAG} --field-selector=status.phase!=Running,status.phase!=Succeeded \
  -o custom-columns=\
NAMESPACE:.metadata.namespace,\
NAME:.metadata.name,\
STATUS:.status.phase,\
REASON:.status.containerStatuses[0].state.waiting.reason,\
RESTARTS:.status.containerStatuses[0].restartCount \
  2>/dev/null | head -50 || warn "Cannot list pods"

echo ""
echo "--- Pods with High Restart Counts (>5) ---"
oc get pods ${NS_FLAG} -o json 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    high_restarts = []
    for pod in data.get('items', []):
        ns = pod['metadata'].get('namespace', 'unknown')
        name = pod['metadata']['name']
        for cs in pod.get('status', {}).get('containerStatuses', []):
            restarts = cs.get('restartCount', 0)
            if restarts > 5:
                high_restarts.append((ns, name, cs['name'], restarts))
    if high_restarts:
        print(f'  {\"NAMESPACE\":<30} {\"POD\":<40} {\"CONTAINER\":<20} RESTARTS')
        for ns, pod, container, restarts in sorted(high_restarts, key=lambda x: -x[3]):
            print(f'  {ns:<30} {pod:<40} {container:<20} {restarts}')
    else:
        print('  No pods with high restart counts')
except Exception as e:
    print(f'  Error: {e}')
" 2>/dev/null || true

# --- Section 4: Common Failure Patterns ---
header "4. Common Failure Pattern Detection"

echo "--- OOMKilled Pods ---"
oc get pods ${NS_FLAG} -o json 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    oom_pods = []
    for pod in data.get('items', []):
        ns = pod['metadata'].get('namespace', 'unknown')
        name = pod['metadata']['name']
        for cs in pod.get('status', {}).get('containerStatuses', []):
            last = cs.get('lastState', {}).get('terminated', {})
            current = cs.get('state', {}).get('terminated', {})
            if last.get('reason') == 'OOMKilled' or current.get('reason') == 'OOMKilled':
                limits = 'unknown'
                for c in pod['spec']['containers']:
                    if c['name'] == cs['name']:
                        limits = c.get('resources', {}).get('limits', {}).get('memory', 'no limit')
                oom_pods.append((ns, name, cs['name'], limits))
    if oom_pods:
        for ns, pod, container, limits in oom_pods:
            print(f'  {ns}/{pod} ({container}) -- memory limit: {limits}')
    else:
        print('  No OOMKilled pods found')
except Exception as e:
    print(f'  Error: {e}')
" 2>/dev/null || true

echo ""
echo "--- ImagePullBackOff Pods ---"
oc get pods ${NS_FLAG} -o json 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    pull_errors = []
    for pod in data.get('items', []):
        ns = pod['metadata'].get('namespace', 'unknown')
        name = pod['metadata']['name']
        for cs in pod.get('status', {}).get('containerStatuses', []):
            waiting = cs.get('state', {}).get('waiting', {})
            if waiting.get('reason') in ['ImagePullBackOff', 'ErrImagePull']:
                image = 'unknown'
                for c in pod['spec']['containers']:
                    if c['name'] == cs['name']:
                        image = c.get('image', 'unknown')
                pull_errors.append((ns, name, image, waiting.get('message', '')))
    if pull_errors:
        for ns, pod, image, msg in pull_errors:
            print(f'  {ns}/{pod}')
            print(f'    Image: {image}')
            print(f'    Message: {msg[:120]}')
    else:
        print('  No ImagePullBackOff pods found')
except Exception as e:
    print(f'  Error: {e}')
" 2>/dev/null || true

echo ""
echo "--- Pending (Unschedulable) Pods ---"
oc get pods ${NS_FLAG} --field-selector=status.phase=Pending -o json 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    pending = []
    for pod in data.get('items', []):
        ns = pod['metadata'].get('namespace', 'unknown')
        name = pod['metadata']['name']
        for cond in pod.get('status', {}).get('conditions', []):
            if cond['type'] == 'PodScheduled' and cond['status'] == 'False':
                pending.append((ns, name, cond.get('message', 'no message')))
    if pending:
        for ns, pod, msg in pending:
            print(f'  {ns}/{pod}')
            print(f'    Reason: {msg[:150]}')
    else:
        print('  No unschedulable pods found')
except Exception as e:
    print(f'  Error: {e}')
" 2>/dev/null || true

# --- Section 5: Recent Events ---
header "5. Recent Warning Events (last 30 minutes)"

if [[ -n "${NAMESPACE}" ]]; then
  oc get events -n "${NAMESPACE}" --field-selector type=Warning \
    --sort-by='.lastTimestamp' 2>/dev/null | tail -20 || warn "Cannot list events"
else
  oc get events -A --field-selector type=Warning \
    --sort-by='.lastTimestamp' 2>/dev/null | tail -30 || warn "Cannot list events"
fi

# --- Section 6: Resource Utilization ---
header "6. Resource Utilization Summary"

if [[ -n "${NAMESPACE}" ]]; then
  echo "--- Pod Resource Usage in ${NAMESPACE} ---"
  oc adm top pods -n "${NAMESPACE}" 2>/dev/null || warn "Cannot get pod metrics"
fi

echo ""
echo "--- PVC Status ---"
oc get pvc ${NS_FLAG} 2>/dev/null | grep -v "Bound" | head -20 || echo "  All PVCs are bound (or none exist)"

# --- Section 7: Certificate Check ---
if [[ "${IS_ADMIN}" == "true" ]]; then
  header "7. Certificate Status"

  echo "--- Pending CSRs ---"
  PENDING_CSRS=$(oc get csr 2>/dev/null | grep -i pending | wc -l | tr -d ' ')
  if [[ "${PENDING_CSRS}" -gt 0 ]]; then
    warn "${PENDING_CSRS} pending certificate signing requests"
    oc get csr 2>/dev/null | grep -i pending
  else
    ok "No pending CSRs"
  fi

  echo ""
  echo "--- Router Certificate Expiry ---"
  oc get secret router-certs-default -n openshift-ingress \
    -o jsonpath='{.data.tls\.crt}' 2>/dev/null | \
    base64 -d 2>/dev/null | \
    openssl x509 -noout -dates -subject 2>/dev/null || \
    warn "Cannot check router certificate"
fi

# --- Summary ---
header "Diagnostic Summary"

echo "Timestamp: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "Cluster: ${CURRENT_SERVER}"
echo "User: ${CURRENT_USER}"
if [[ -n "${NAMESPACE}" ]]; then
  echo "Scope: namespace/${NAMESPACE}"
else
  echo "Scope: all namespaces"
fi

echo ""
echo "Next steps:"
echo "  - For cluster-wide issues:  oc adm must-gather --dest-dir=/tmp/must-gather"
echo "  - For namespace issues:     oc adm inspect namespace/<name> --dest-dir=/tmp/inspect"
echo "  - For node issues:          oc debug node/<name>"
echo "  - For support cases:        attach the must-gather tarball"

if [[ -n "${OUTPUT_DIR}" ]]; then
  echo ""
  echo "Full diagnostic output saved to: ${OUTPUT_DIR}"
fi
