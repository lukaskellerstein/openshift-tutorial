#!/usr/bin/env bash
# validate-cluster.sh — Post-installation cluster health check
#
# Validates that an OpenShift cluster is healthy after installation.
# Run this after any installation method (IPI, UPI, or agent-based).
#
# Usage:
#   ./scripts/validate-cluster.sh
#
# Prerequisites:
#   - oc CLI authenticated to the cluster (KUBECONFIG set or oc login)
#   - cluster-admin or cluster-reader permissions

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=0
FAIL=0
WARN=0

pass() {
  echo -e "  ${GREEN}PASS${NC}: $1"
  ((PASS++))
}

fail() {
  echo -e "  ${RED}FAIL${NC}: $1"
  ((FAIL++))
}

warn() {
  echo -e "  ${YELLOW}WARN${NC}: $1"
  ((WARN++))
}

echo "============================================="
echo " OpenShift Cluster Health Validation"
echo " $(date)"
echo "============================================="
echo ""

# --- 1. Authentication ---
echo "[1/8] Authentication"
if oc whoami > /dev/null 2>&1; then
  USER=$(oc whoami)
  pass "Authenticated as: ${USER}"
else
  fail "Not authenticated. Run 'oc login' or set KUBECONFIG."
  echo ""
  echo "Cannot continue without authentication."
  exit 1
fi
echo ""

# --- 2. Cluster Version ---
echo "[2/8] Cluster Version"
CV_AVAILABLE=$(oc get clusterversion version -o jsonpath='{.status.conditions[?(@.type=="Available")].status}' 2>/dev/null || echo "Unknown")
CV_PROGRESSING=$(oc get clusterversion version -o jsonpath='{.status.conditions[?(@.type=="Progressing")].status}' 2>/dev/null || echo "Unknown")
CV_VERSION=$(oc get clusterversion version -o jsonpath='{.status.desired.version}' 2>/dev/null || echo "Unknown")

echo "  Version: ${CV_VERSION}"
if [[ "${CV_AVAILABLE}" == "True" ]]; then
  pass "Cluster version available"
else
  fail "Cluster version not available (Available=${CV_AVAILABLE})"
fi

if [[ "${CV_PROGRESSING}" == "False" ]]; then
  pass "No upgrade in progress"
else
  warn "Upgrade in progress (Progressing=${CV_PROGRESSING})"
fi
echo ""

# --- 3. Cluster Operators ---
echo "[3/8] Cluster Operators"
TOTAL_CO=$(oc get co --no-headers 2>/dev/null | wc -l | tr -d ' ')
DEGRADED_CO=$(oc get co -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.conditions[?(@.type=="Degraded")].status}{"\n"}{end}' 2>/dev/null | grep -c "True" || true)
UNAVAILABLE_CO=$(oc get co -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.conditions[?(@.type=="Available")].status}{"\n"}{end}' 2>/dev/null | grep -c "False" || true)

echo "  Total operators: ${TOTAL_CO}"
if [[ "${DEGRADED_CO}" -eq 0 ]]; then
  pass "No degraded operators"
else
  fail "${DEGRADED_CO} degraded operator(s):"
  oc get co -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.conditions[?(@.type=="Degraded")].status}{"\n"}{end}' 2>/dev/null | grep "True" | while read -r name status; do
    echo "       - ${name}"
  done
fi

if [[ "${UNAVAILABLE_CO}" -eq 0 ]]; then
  pass "All operators available"
else
  fail "${UNAVAILABLE_CO} unavailable operator(s):"
  oc get co -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.conditions[?(@.type=="Available")].status}{"\n"}{end}' 2>/dev/null | grep "False" | while read -r name status; do
    echo "       - ${name}"
  done
fi
echo ""

# --- 4. Node Health ---
echo "[4/8] Node Health"
TOTAL_NODES=$(oc get nodes --no-headers 2>/dev/null | wc -l | tr -d ' ')
READY_NODES=$(oc get nodes --no-headers 2>/dev/null | grep -c " Ready" || true)
NOT_READY_NODES=$(oc get nodes --no-headers 2>/dev/null | grep -c "NotReady" || true)
MASTER_NODES=$(oc get nodes --no-headers -l node-role.kubernetes.io/master 2>/dev/null | wc -l | tr -d ' ')
WORKER_NODES=$(oc get nodes --no-headers -l node-role.kubernetes.io/worker 2>/dev/null | wc -l | tr -d ' ')

echo "  Total nodes: ${TOTAL_NODES} (masters: ${MASTER_NODES}, workers: ${WORKER_NODES})"
if [[ "${READY_NODES}" -eq "${TOTAL_NODES}" ]]; then
  pass "All ${TOTAL_NODES} nodes are Ready"
else
  fail "${NOT_READY_NODES} node(s) are NotReady"
  oc get nodes --no-headers 2>/dev/null | grep "NotReady" | while read -r line; do
    echo "       - ${line}"
  done
fi

if [[ "${MASTER_NODES}" -ge 3 ]]; then
  pass "Minimum 3 control plane nodes present"
elif [[ "${MASTER_NODES}" -eq 1 ]]; then
  warn "Single control plane node (SNO or CRC — not HA)"
else
  fail "Only ${MASTER_NODES} control plane node(s) — need 3 for HA"
fi
echo ""

# --- 5. Critical Namespaces ---
echo "[5/8] Critical System Pods"
CRITICAL_NS=(
  "openshift-etcd"
  "openshift-apiserver"
  "openshift-controller-manager"
  "openshift-ingress"
  "openshift-image-registry"
  "openshift-monitoring"
)

for ns in "${CRITICAL_NS[@]}"; do
  TOTAL_PODS=$(oc get pods -n "${ns}" --no-headers 2>/dev/null | wc -l | tr -d ' ')
  RUNNING_PODS=$(oc get pods -n "${ns}" --no-headers --field-selector=status.phase=Running 2>/dev/null | wc -l | tr -d ' ')
  NOT_RUNNING=$(( TOTAL_PODS - RUNNING_PODS ))

  if [[ "${TOTAL_PODS}" -eq 0 ]]; then
    warn "${ns}: no pods found"
  elif [[ "${NOT_RUNNING}" -eq 0 ]]; then
    pass "${ns}: all ${TOTAL_PODS} pods running"
  else
    fail "${ns}: ${NOT_RUNNING}/${TOTAL_PODS} pods not running"
  fi
done
echo ""

# --- 6. Pending CSRs ---
echo "[6/8] Certificate Signing Requests"
PENDING_CSRS=$(oc get csr --no-headers 2>/dev/null | grep -c "Pending" || true)
if [[ "${PENDING_CSRS}" -eq 0 ]]; then
  pass "No pending CSRs"
else
  warn "${PENDING_CSRS} pending CSR(s) — approve with: oc adm certificate approve <name>"
  oc get csr --no-headers 2>/dev/null | grep "Pending" | while read -r line; do
    echo "       - $(echo "${line}" | awk '{print $1}')"
  done
fi
echo ""

# --- 7. Machine Config Pools ---
echo "[7/8] Machine Config Pools"
oc get mcp --no-headers 2>/dev/null | while read -r name updated updating degraded mc count ready available age; do
  if [[ "${degraded}" == "True" ]]; then
    fail "MCP '${name}' is degraded"
  elif [[ "${updating}" == "True" ]]; then
    warn "MCP '${name}' is updating"
  else
    pass "MCP '${name}' is healthy"
  fi
done
echo ""

# --- 8. Infrastructure Info ---
echo "[8/8] Infrastructure"
PLATFORM=$(oc get infrastructure cluster -o jsonpath='{.status.platform}' 2>/dev/null || echo "Unknown")
API_URL=$(oc get infrastructure cluster -o jsonpath='{.status.apiServerURL}' 2>/dev/null || echo "Unknown")
CONSOLE_URL=$(oc get routes -n openshift-console console -o jsonpath='{.spec.host}' 2>/dev/null || echo "Unknown")

echo "  Platform:    ${PLATFORM}"
echo "  API URL:     ${API_URL}"
echo "  Console URL: https://${CONSOLE_URL}"
pass "Infrastructure info retrieved"
echo ""

# --- Summary ---
echo "============================================="
echo " Summary"
echo "============================================="
echo -e "  ${GREEN}PASS${NC}: ${PASS}"
echo -e "  ${RED}FAIL${NC}: ${FAIL}"
echo -e "  ${YELLOW}WARN${NC}: ${WARN}"
echo ""

if [[ "${FAIL}" -gt 0 ]]; then
  echo -e "${RED}Cluster has ${FAIL} failure(s). Investigate before running production workloads.${NC}"
  exit 1
elif [[ "${WARN}" -gt 0 ]]; then
  echo -e "${YELLOW}Cluster is functional with ${WARN} warning(s).${NC}"
  exit 0
else
  echo -e "${GREEN}Cluster is healthy. All checks passed.${NC}"
  exit 0
fi
