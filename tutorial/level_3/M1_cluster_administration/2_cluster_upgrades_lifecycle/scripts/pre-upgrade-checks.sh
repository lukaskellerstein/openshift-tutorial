#!/usr/bin/env bash
# =============================================================================
# Pre-Upgrade Health Check Script
# =============================================================================
# Performs comprehensive cluster health checks before an OpenShift upgrade.
# Run this script as cluster-admin before initiating any upgrade.
#
# Usage: ./pre-upgrade-checks.sh
#
# Exit codes:
#   0 - All checks passed
#   1 - One or more checks failed (do NOT proceed with upgrade)
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=0
FAIL=0
WARN=0

pass() {
  echo -e "${GREEN}[PASS]${NC} $1"
  ((PASS++))
}

fail() {
  echo -e "${RED}[FAIL]${NC} $1"
  ((FAIL++))
}

warn() {
  echo -e "${YELLOW}[WARN]${NC} $1"
  ((WARN++))
}

echo "============================================="
echo "  OpenShift Pre-Upgrade Health Checks"
echo "============================================="
echo ""
echo "Cluster: $(oc whoami --show-server 2>/dev/null || echo 'unknown')"
echo "User:    $(oc whoami 2>/dev/null || echo 'unknown')"
echo "Date:    $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

# -----------------------------------------------
# Check 1: Cluster Version Status
# -----------------------------------------------
echo "--- Cluster Version ---"
CV_AVAILABLE=$(oc get clusterversion version -o jsonpath='{.status.conditions[?(@.type=="Available")].status}' 2>/dev/null)
CV_PROGRESSING=$(oc get clusterversion version -o jsonpath='{.status.conditions[?(@.type=="Progressing")].status}' 2>/dev/null)
CV_VERSION=$(oc get clusterversion version -o jsonpath='{.status.desired.version}' 2>/dev/null)
CV_CHANNEL=$(oc get clusterversion version -o jsonpath='{.spec.channel}' 2>/dev/null)

echo "  Current version: ${CV_VERSION}"
echo "  Channel: ${CV_CHANNEL}"

if [[ "$CV_AVAILABLE" == "True" ]]; then
  pass "ClusterVersion is Available"
else
  fail "ClusterVersion is NOT Available"
fi

if [[ "$CV_PROGRESSING" == "False" ]]; then
  pass "ClusterVersion is not Progressing (no upgrade in flight)"
else
  fail "ClusterVersion is Progressing -- an upgrade may already be in progress"
fi

echo ""

# -----------------------------------------------
# Check 2: Cluster Operators
# -----------------------------------------------
echo "--- Cluster Operators ---"
DEGRADED_OPS=$(oc get clusteroperators -o json 2>/dev/null | \
  jq -r '.items[] | select(.status.conditions[] | select(.type=="Degraded" and .status=="True")) | .metadata.name')

UNAVAILABLE_OPS=$(oc get clusteroperators -o json 2>/dev/null | \
  jq -r '.items[] | select(.status.conditions[] | select(.type=="Available" and .status=="False")) | .metadata.name')

PROGRESSING_OPS=$(oc get clusteroperators -o json 2>/dev/null | \
  jq -r '.items[] | select(.status.conditions[] | select(.type=="Progressing" and .status=="True")) | .metadata.name')

if [[ -z "$DEGRADED_OPS" ]]; then
  pass "No cluster operators are Degraded"
else
  fail "Degraded cluster operators: ${DEGRADED_OPS}"
fi

if [[ -z "$UNAVAILABLE_OPS" ]]; then
  pass "All cluster operators are Available"
else
  fail "Unavailable cluster operators: ${UNAVAILABLE_OPS}"
fi

if [[ -z "$PROGRESSING_OPS" ]]; then
  pass "No cluster operators are Progressing"
else
  warn "Progressing cluster operators: ${PROGRESSING_OPS}"
fi

echo ""

# -----------------------------------------------
# Check 3: Node Health
# -----------------------------------------------
echo "--- Node Health ---"
NOT_READY_NODES=$(oc get nodes -o json 2>/dev/null | \
  jq -r '.items[] | select(.status.conditions[] | select(.type=="Ready" and .status!="True")) | .metadata.name')

if [[ -z "$NOT_READY_NODES" ]]; then
  pass "All nodes are Ready"
else
  fail "Nodes not Ready: ${NOT_READY_NODES}"
fi

TOTAL_NODES=$(oc get nodes --no-headers 2>/dev/null | wc -l | tr -d ' ')
MASTER_NODES=$(oc get nodes -l node-role.kubernetes.io/master --no-headers 2>/dev/null | wc -l | tr -d ' ')
WORKER_NODES=$(oc get nodes -l node-role.kubernetes.io/worker --no-headers 2>/dev/null | wc -l | tr -d ' ')

echo "  Total nodes: ${TOTAL_NODES} (masters: ${MASTER_NODES}, workers: ${WORKER_NODES})"

echo ""

# -----------------------------------------------
# Check 4: MachineConfigPool Status
# -----------------------------------------------
echo "--- MachineConfigPools ---"
MCP_DEGRADED=$(oc get mcp -o json 2>/dev/null | \
  jq -r '.items[] | select(.status.conditions[]? | select(.type=="Degraded" and .status=="True")) | .metadata.name')

MCP_UPDATING=$(oc get mcp -o json 2>/dev/null | \
  jq -r '.items[] | select(.status.conditions[]? | select(.type=="Updating" and .status=="True")) | .metadata.name')

MCP_PAUSED=$(oc get mcp -o json 2>/dev/null | \
  jq -r '.items[] | select(.spec.paused==true) | .metadata.name')

if [[ -z "$MCP_DEGRADED" ]]; then
  pass "No MachineConfigPools are Degraded"
else
  fail "Degraded MachineConfigPools: ${MCP_DEGRADED}"
fi

if [[ -z "$MCP_UPDATING" ]]; then
  pass "No MachineConfigPools are Updating"
else
  warn "Updating MachineConfigPools: ${MCP_UPDATING}"
fi

if [[ -z "$MCP_PAUSED" ]]; then
  pass "No MachineConfigPools are Paused"
else
  warn "Paused MachineConfigPools: ${MCP_PAUSED} (unpause before upgrade)"
fi

echo ""

# -----------------------------------------------
# Check 5: etcd Health
# -----------------------------------------------
echo "--- etcd Health ---"
ETCD_PODS=$(oc get pods -n openshift-etcd -l app=etcd --no-headers 2>/dev/null | grep -c Running || echo "0")
EXPECTED_ETCD=${MASTER_NODES}

if [[ "$ETCD_PODS" -ge "$EXPECTED_ETCD" && "$ETCD_PODS" -gt 0 ]]; then
  pass "etcd has ${ETCD_PODS} running pods (expected: ${EXPECTED_ETCD})"
else
  fail "etcd has ${ETCD_PODS} running pods (expected: ${EXPECTED_ETCD})"
fi

echo ""

# -----------------------------------------------
# Check 6: Certificate Expiration
# -----------------------------------------------
echo "--- Certificate Expiration ---"
CERTS_EXPIRING_SOON=$(oc get csr -o json 2>/dev/null | \
  jq -r '.items[] | select(.status.conditions == null) | .metadata.name' | head -5)

if [[ -z "$CERTS_EXPIRING_SOON" ]]; then
  pass "No pending CSRs found"
else
  warn "Pending CSRs detected: ${CERTS_EXPIRING_SOON}"
  echo "  Approve pending CSRs before upgrade: oc adm certificate approve <csr-name>"
fi

echo ""

# -----------------------------------------------
# Check 7: PodDisruptionBudgets
# -----------------------------------------------
echo "--- PodDisruptionBudgets ---"
PDB_COUNT=$(oc get pdb -A --no-headers 2>/dev/null | wc -l | tr -d ' ')

if [[ "$PDB_COUNT" -gt 0 ]]; then
  pass "Found ${PDB_COUNT} PodDisruptionBudgets across the cluster"
else
  warn "No PodDisruptionBudgets found -- workloads may be disrupted during node drains"
fi

# Check for PDBs that could block drains (minAvailable = replicas)
BLOCKING_PDBS=$(oc get pdb -A -o json 2>/dev/null | \
  jq -r '.items[] | select(.status.disruptionsAllowed == 0) | "\(.metadata.namespace)/\(.metadata.name)"')

if [[ -n "$BLOCKING_PDBS" ]]; then
  warn "PDBs currently blocking disruptions (0 allowed): ${BLOCKING_PDBS}"
  echo "  These may block node drains during upgrade. Review and adjust if necessary."
fi

echo ""

# -----------------------------------------------
# Check 8: Available Updates
# -----------------------------------------------
echo "--- Available Updates ---"
oc adm upgrade 2>/dev/null | head -10 || warn "Could not retrieve available updates"

echo ""

# -----------------------------------------------
# Summary
# -----------------------------------------------
echo "============================================="
echo "  Summary"
echo "============================================="
echo -e "  ${GREEN}PASS: ${PASS}${NC}"
echo -e "  ${RED}FAIL: ${FAIL}${NC}"
echo -e "  ${YELLOW}WARN: ${WARN}${NC}"
echo ""

if [[ "$FAIL" -gt 0 ]]; then
  echo -e "${RED}RESULT: Pre-upgrade checks FAILED. Fix the issues above before upgrading.${NC}"
  exit 1
else
  if [[ "$WARN" -gt 0 ]]; then
    echo -e "${YELLOW}RESULT: Pre-upgrade checks PASSED with warnings. Review warnings before proceeding.${NC}"
  else
    echo -e "${GREEN}RESULT: All pre-upgrade checks PASSED. Safe to proceed with upgrade.${NC}"
  fi
  exit 0
fi
