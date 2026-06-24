#!/bin/bash
# validate-performance.sh — Validate performance tuning settings on an OpenShift node
#
# Usage: ./validate-performance.sh <node-name>
#
# This script checks that performance tuning components are properly configured:
#   - Node Tuning Operator status
#   - Tuned profiles applied
#   - Huge pages allocation
#   - CPU Manager state
#   - Kernel parameters
#   - NUMA topology
#   - Real-time kernel
#   - PerformanceProfile status

set -euo pipefail

NODE_NAME="${1:-}"
PASS=0
FAIL=0
WARN=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

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

header() {
  echo ""
  echo "=============================================="
  echo "  $1"
  echo "=============================================="
}

# -------------------------------------------------------
header "1. Node Tuning Operator"
# -------------------------------------------------------

NTO_STATUS=$(oc get deployment cluster-node-tuning-operator \
  -n openshift-cluster-node-tuning-operator \
  -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")

if [ "$NTO_STATUS" = "1" ]; then
  pass "Node Tuning Operator is running"
else
  fail "Node Tuning Operator is NOT running (ready replicas: $NTO_STATUS)"
fi

# -------------------------------------------------------
header "2. Custom Tuned Profiles"
# -------------------------------------------------------

TUNED_PROFILES=$(oc get tuned -n openshift-cluster-node-tuning-operator \
  --no-headers 2>/dev/null | wc -l | tr -d ' ')

if [ "$TUNED_PROFILES" -gt 2 ]; then
  pass "Custom Tuned profiles found ($TUNED_PROFILES total profiles)"
  oc get tuned -n openshift-cluster-node-tuning-operator --no-headers 2>/dev/null | \
    while read -r name rest; do
      echo "       - $name"
    done
else
  warn "Only default Tuned profiles found (no custom profiles)"
fi

# Check for db-optimized profile
if oc get tuned db-optimized -n openshift-cluster-node-tuning-operator &>/dev/null; then
  pass "db-optimized Tuned profile exists"
else
  warn "db-optimized Tuned profile not found"
fi

# -------------------------------------------------------
header "3. PerformanceProfile"
# -------------------------------------------------------

if oc get performanceprofile low-latency &>/dev/null; then
  pass "PerformanceProfile 'low-latency' exists"

  # Check conditions
  PP_AVAILABLE=$(oc get performanceprofile low-latency \
    -o jsonpath='{.status.conditions[?(@.type=="Available")].status}' 2>/dev/null)
  PP_DEGRADED=$(oc get performanceprofile low-latency \
    -o jsonpath='{.status.conditions[?(@.type=="Degraded")].status}' 2>/dev/null)

  if [ "$PP_AVAILABLE" = "True" ]; then
    pass "PerformanceProfile is Available"
  else
    fail "PerformanceProfile is NOT Available"
  fi

  if [ "$PP_DEGRADED" = "False" ]; then
    pass "PerformanceProfile is NOT Degraded"
  else
    fail "PerformanceProfile is Degraded"
    oc get performanceprofile low-latency \
      -o jsonpath='{.status.conditions[?(@.type=="Degraded")].message}' 2>/dev/null
    echo ""
  fi

  # Check RuntimeClass
  if oc get runtimeclass performance-low-latency &>/dev/null; then
    pass "RuntimeClass 'performance-low-latency' auto-generated"
  else
    fail "RuntimeClass 'performance-low-latency' NOT found"
  fi
else
  warn "PerformanceProfile 'low-latency' not found (skipping sub-checks)"
fi

# -------------------------------------------------------
header "4. MachineConfigPool"
# -------------------------------------------------------

if oc get mcp worker-perf &>/dev/null; then
  pass "MachineConfigPool 'worker-perf' exists"

  MCP_UPDATED=$(oc get mcp worker-perf -o jsonpath='{.status.conditions[?(@.type=="Updated")].status}' 2>/dev/null)
  MCP_DEGRADED=$(oc get mcp worker-perf -o jsonpath='{.status.conditions[?(@.type=="Degraded")].status}' 2>/dev/null)
  MCP_COUNT=$(oc get mcp worker-perf -o jsonpath='{.status.machineCount}' 2>/dev/null)
  MCP_READY=$(oc get mcp worker-perf -o jsonpath='{.status.readyMachineCount}' 2>/dev/null)

  echo "       Machines: $MCP_READY/$MCP_COUNT ready"

  if [ "$MCP_UPDATED" = "True" ]; then
    pass "MachineConfigPool is Updated (rollout complete)"
  else
    warn "MachineConfigPool is still Updating"
  fi

  if [ "$MCP_DEGRADED" = "False" ]; then
    pass "MachineConfigPool is NOT Degraded"
  else
    fail "MachineConfigPool is Degraded"
  fi
else
  warn "MachineConfigPool 'worker-perf' not found"
fi

# -------------------------------------------------------
# Node-specific checks (require a node name)
# -------------------------------------------------------

if [ -z "$NODE_NAME" ]; then
  echo ""
  warn "No node name provided. Skipping node-specific checks."
  echo "       Usage: $0 <node-name>"
  echo "       Example: $0 worker-0.example.com"
else
  # ---------------------------------------------------
  header "5. Huge Pages (Node: $NODE_NAME)"
  # ---------------------------------------------------

  HP_OUTPUT=$(oc debug "node/$NODE_NAME" -- chroot /host \
    cat /proc/meminfo 2>/dev/null | grep -i hugepages || echo "UNAVAILABLE")

  if echo "$HP_OUTPUT" | grep -q "HugePages_Total"; then
    HP_TOTAL=$(echo "$HP_OUTPUT" | grep "HugePages_Total" | awk '{print $2}')
    HP_FREE=$(echo "$HP_OUTPUT" | grep "HugePages_Free" | awk '{print $2}')
    if [ "$HP_TOTAL" -gt 0 ]; then
      pass "Huge pages allocated: Total=$HP_TOTAL, Free=$HP_FREE"
    else
      fail "Huge pages total is 0 (not allocated)"
    fi
  else
    fail "Could not read huge pages info from node"
  fi

  # ---------------------------------------------------
  header "6. CPU Manager (Node: $NODE_NAME)"
  # ---------------------------------------------------

  CPU_STATE=$(oc debug "node/$NODE_NAME" -- chroot /host \
    cat /var/lib/kubelet/cpu_manager_state 2>/dev/null || echo "UNAVAILABLE")

  if echo "$CPU_STATE" | grep -q '"static"'; then
    pass "CPU Manager is running with 'static' policy"
    ENTRIES=$(echo "$CPU_STATE" | python3 -c "
import sys, json
try:
    state = json.load(sys.stdin)
    entries = state.get('entries', {})
    print(f'{len(entries)} container(s) with exclusive CPUs')
except:
    print('Could not parse state')
" 2>/dev/null || echo "Could not parse state")
    echo "       $ENTRIES"
  elif echo "$CPU_STATE" | grep -q '"none"'; then
    warn "CPU Manager is running with 'none' policy (pinning disabled)"
  else
    fail "Could not determine CPU Manager policy"
  fi

  # ---------------------------------------------------
  header "7. Kernel Parameters (Node: $NODE_NAME)"
  # ---------------------------------------------------

  CMDLINE=$(oc debug "node/$NODE_NAME" -- chroot /host \
    cat /proc/cmdline 2>/dev/null || echo "UNAVAILABLE")

  # Check for key low-latency kernel args
  for PARAM in "nohz_full" "intel_pstate=disable" "tsc=reliable" "nosoftlockup"; do
    if echo "$CMDLINE" | grep -q "$PARAM"; then
      pass "Kernel parameter '$PARAM' is set"
    else
      warn "Kernel parameter '$PARAM' is NOT set"
    fi
  done

  # ---------------------------------------------------
  header "8. Real-Time Kernel (Node: $NODE_NAME)"
  # ---------------------------------------------------

  KERNEL=$(oc debug "node/$NODE_NAME" -- chroot /host \
    uname -r 2>/dev/null || echo "UNAVAILABLE")

  if echo "$KERNEL" | grep -q "\.rt"; then
    pass "Real-time kernel installed: $KERNEL"
  else
    warn "Standard kernel installed: $KERNEL (not real-time)"
  fi

  # ---------------------------------------------------
  header "9. NUMA Topology (Node: $NODE_NAME)"
  # ---------------------------------------------------

  NUMA_INFO=$(oc debug "node/$NODE_NAME" -- chroot /host \
    lscpu 2>/dev/null | grep -i "numa" || echo "UNAVAILABLE")

  if echo "$NUMA_INFO" | grep -q "NUMA node(s)"; then
    NUMA_NODES=$(echo "$NUMA_INFO" | grep "NUMA node(s)" | awk '{print $NF}')
    pass "NUMA nodes detected: $NUMA_NODES"
    echo "$NUMA_INFO" | grep "NUMA node" | while read -r line; do
      echo "       $line"
    done
  else
    warn "Could not determine NUMA topology"
  fi

  # ---------------------------------------------------
  header "10. TuneD Active Profile (Node: $NODE_NAME)"
  # ---------------------------------------------------

  TUNED_ACTIVE=$(oc debug "node/$NODE_NAME" -- chroot /host \
    tuned-adm active 2>/dev/null || echo "UNAVAILABLE")

  if echo "$TUNED_ACTIVE" | grep -q "Current active profile"; then
    pass "TuneD is active"
    echo "       $TUNED_ACTIVE"
  else
    warn "Could not determine active TuneD profile"
  fi
fi

# -------------------------------------------------------
header "Summary"
# -------------------------------------------------------

echo ""
echo -e "  ${GREEN}Passed:${NC}  $PASS"
echo -e "  ${RED}Failed:${NC}  $FAIL"
echo -e "  ${YELLOW}Warnings:${NC} $WARN"
echo ""

if [ "$FAIL" -gt 0 ]; then
  echo -e "${RED}Some checks failed. Review the output above for details.${NC}"
  exit 1
elif [ "$WARN" -gt 0 ]; then
  echo -e "${YELLOW}All critical checks passed, but there are warnings.${NC}"
  exit 0
else
  echo -e "${GREEN}All checks passed. Performance tuning is properly configured.${NC}"
  exit 0
fi
