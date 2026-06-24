#!/usr/bin/env bash
# =============================================================================
# Post-Upgrade Validation Script
# =============================================================================
# Performs comprehensive validation after an OpenShift cluster upgrade.
# Run this script as cluster-admin after the upgrade completes.
#
# Usage: ./post-upgrade-validation.sh
#
# Exit codes:
#   0 - All checks passed
#   1 - One or more checks failed (investigate before declaring upgrade complete)
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

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
echo "  OpenShift Post-Upgrade Validation"
echo "============================================="
echo ""
echo "Cluster: $(oc whoami --show-server 2>/dev/null || echo 'unknown')"
echo "User:    $(oc whoami 2>/dev/null || echo 'unknown')"
echo "Date:    $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

# -----------------------------------------------
# Check 1: Cluster Version
# -----------------------------------------------
echo "--- Cluster Version ---"
CV_VERSION=$(oc get clusterversion version -o jsonpath='{.status.desired.version}' 2>/dev/null)
CV_AVAILABLE=$(oc get clusterversion version -o jsonpath='{.status.conditions[?(@.type=="Available")].status}' 2>/dev/null)
CV_PROGRESSING=$(oc get clusterversion version -o jsonpath='{.status.conditions[?(@.type=="Progressing")].status}' 2>/dev/null)

echo "  Cluster version: ${CV_VERSION}"

if [[ "$CV_AVAILABLE" == "True" ]]; then
  pass "ClusterVersion is Available"
else
  fail "ClusterVersion is NOT Available"
fi

if [[ "$CV_PROGRESSING" == "False" ]]; then
  pass "Upgrade is complete (not progressing)"
else
  fail "Upgrade is still in progress"
fi

echo ""

# -----------------------------------------------
# Check 2: All Cluster Operators Healthy
# -----------------------------------------------
echo "--- Cluster Operators ---"
TOTAL_OPS=$(oc get clusteroperators --no-headers 2>/dev/null | wc -l | tr -d ' ')

DEGRADED=$(oc get clusteroperators -o json 2>/dev/null | \
  jq -r '[.items[] | select(.status.conditions[] | select(.type=="Degraded" and .status=="True"))] | length')

UNAVAILABLE=$(oc get clusteroperators -o json 2>/dev/null | \
  jq -r '[.items[] | select(.status.conditions[] | select(.type=="Available" and .status=="False"))] | length')

echo "  Total cluster operators: ${TOTAL_OPS}"

if [[ "$DEGRADED" -eq 0 ]]; then
  pass "No degraded cluster operators"
else
  fail "${DEGRADED} cluster operator(s) are Degraded"
  oc get clusteroperators -o json | \
    jq -r '.items[] | select(.status.conditions[] | select(.type=="Degraded" and .status=="True")) | "    - " + .metadata.name'
fi

if [[ "$UNAVAILABLE" -eq 0 ]]; then
  pass "All cluster operators are Available"
else
  fail "${UNAVAILABLE} cluster operator(s) are Unavailable"
  oc get clusteroperators -o json | \
    jq -r '.items[] | select(.status.conditions[] | select(.type=="Available" and .status=="False")) | "    - " + .metadata.name'
fi

echo ""

# -----------------------------------------------
# Check 3: Node Status
# -----------------------------------------------
echo "--- Node Status ---"
TOTAL_NODES=$(oc get nodes --no-headers 2>/dev/null | wc -l | tr -d ' ')
READY_NODES=$(oc get nodes -o json 2>/dev/null | \
  jq -r '[.items[] | select(.status.conditions[] | select(.type=="Ready" and .status=="True"))] | length')

echo "  Total nodes: ${TOTAL_NODES}, Ready: ${READY_NODES}"

if [[ "$READY_NODES" -eq "$TOTAL_NODES" ]]; then
  pass "All ${TOTAL_NODES} nodes are Ready"
else
  fail "$((TOTAL_NODES - READY_NODES)) node(s) are NOT Ready"
  oc get nodes -o json | \
    jq -r '.items[] | select(.status.conditions[] | select(.type=="Ready" and .status!="True")) | "    - " + .metadata.name'
fi

# Check for scheduling-disabled nodes (still cordoned)
CORDONED=$(oc get nodes -o json 2>/dev/null | \
  jq -r '[.items[] | select(.spec.unschedulable==true)] | length')

if [[ "$CORDONED" -eq 0 ]]; then
  pass "No nodes are cordoned (SchedulingDisabled)"
else
  warn "${CORDONED} node(s) are still cordoned"
fi

# Verify all nodes are running the expected kubelet version
KUBELET_VERSIONS=$(oc get nodes -o json 2>/dev/null | \
  jq -r '[.items[].status.nodeInfo.kubeletVersion] | unique | .[]')
VERSION_COUNT=$(echo "$KUBELET_VERSIONS" | wc -l | tr -d ' ')

if [[ "$VERSION_COUNT" -eq 1 ]]; then
  pass "All nodes running kubelet version: ${KUBELET_VERSIONS}"
else
  warn "Multiple kubelet versions detected (upgrade may still be in progress):"
  echo "$KUBELET_VERSIONS" | while read -r v; do echo "    - $v"; done
fi

echo ""

# -----------------------------------------------
# Check 4: MachineConfigPools
# -----------------------------------------------
echo "--- MachineConfigPools ---"
MCP_NAMES=$(oc get mcp -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)

for MCP in $MCP_NAMES; do
  UPDATED=$(oc get mcp "$MCP" -o jsonpath='{.status.conditions[?(@.type=="Updated")].status}' 2>/dev/null)
  DEGRADED_MCP=$(oc get mcp "$MCP" -o jsonpath='{.status.conditions[?(@.type=="Degraded")].status}' 2>/dev/null)
  PAUSED=$(oc get mcp "$MCP" -o jsonpath='{.spec.paused}' 2>/dev/null)

  if [[ "$UPDATED" == "True" ]]; then
    pass "MCP '${MCP}' is Updated"
  else
    fail "MCP '${MCP}' is NOT Updated"
  fi

  if [[ "$DEGRADED_MCP" == "False" || -z "$DEGRADED_MCP" ]]; then
    pass "MCP '${MCP}' is not Degraded"
  else
    fail "MCP '${MCP}' is Degraded"
  fi

  if [[ "$PAUSED" == "true" ]]; then
    warn "MCP '${MCP}' is Paused -- unpause after validation"
  fi
done

echo ""

# -----------------------------------------------
# Check 5: Critical Platform Pods
# -----------------------------------------------
echo "--- Critical Platform Pods ---"
FAILED_PODS=$(oc get pods -A --no-headers 2>/dev/null | \
  grep -E "^openshift-" | \
  grep -v -E "Running|Completed|Succeeded" | \
  wc -l | tr -d ' ')

if [[ "$FAILED_PODS" -eq 0 ]]; then
  pass "All pods in openshift-* namespaces are healthy"
else
  warn "${FAILED_PODS} pod(s) in openshift-* namespaces are not Running/Completed"
  oc get pods -A --no-headers | \
    grep -E "^openshift-" | \
    grep -v -E "Running|Completed|Succeeded" | \
    head -10 | while read -r line; do echo "    $line"; done
fi

echo ""

# -----------------------------------------------
# Check 6: etcd Health
# -----------------------------------------------
echo "--- etcd Health ---"
ETCD_PODS=$(oc get pods -n openshift-etcd -l app=etcd --no-headers 2>/dev/null | grep -c Running || echo "0")
MASTER_COUNT=$(oc get nodes -l node-role.kubernetes.io/master --no-headers 2>/dev/null | wc -l | tr -d ' ')

if [[ "$ETCD_PODS" -ge "$MASTER_COUNT" && "$ETCD_PODS" -gt 0 ]]; then
  pass "etcd cluster healthy: ${ETCD_PODS} running members"
else
  fail "etcd cluster may be unhealthy: ${ETCD_PODS} running (expected: ${MASTER_COUNT})"
fi

echo ""

# -----------------------------------------------
# Check 7: API Server Responsiveness
# -----------------------------------------------
echo "--- API Server ---"
API_START=$(date +%s%N)
oc get nodes > /dev/null 2>&1
API_END=$(date +%s%N)
API_MS=$(( (API_END - API_START) / 1000000 ))

if [[ "$API_MS" -lt 5000 ]]; then
  pass "API server responded in ${API_MS}ms"
else
  warn "API server response slow: ${API_MS}ms"
fi

echo ""

# -----------------------------------------------
# Check 8: Recent Events (Errors/Warnings)
# -----------------------------------------------
echo "--- Recent Warning Events ---"
RECENT_WARNINGS=$(oc get events -A --field-selector type=Warning --sort-by=.lastTimestamp 2>/dev/null | tail -5)

if [[ -z "$RECENT_WARNINGS" ]]; then
  pass "No recent warning events"
else
  warn "Recent warning events detected:"
  echo "$RECENT_WARNINGS" | while read -r line; do echo "    $line"; done
fi

echo ""

# -----------------------------------------------
# Summary
# -----------------------------------------------
echo "============================================="
echo "  Post-Upgrade Validation Summary"
echo "============================================="
echo "  Cluster version: ${CV_VERSION}"
echo -e "  ${GREEN}PASS: ${PASS}${NC}"
echo -e "  ${RED}FAIL: ${FAIL}${NC}"
echo -e "  ${YELLOW}WARN: ${WARN}${NC}"
echo ""

if [[ "$FAIL" -gt 0 ]]; then
  echo -e "${RED}RESULT: Post-upgrade validation FAILED. Investigate failures before declaring upgrade complete.${NC}"
  exit 1
else
  if [[ "$WARN" -gt 0 ]]; then
    echo -e "${YELLOW}RESULT: Upgrade validated with warnings. Review warnings above.${NC}"
  else
    echo -e "${GREEN}RESULT: Upgrade validated successfully. All checks passed.${NC}"
  fi
  exit 0
fi
