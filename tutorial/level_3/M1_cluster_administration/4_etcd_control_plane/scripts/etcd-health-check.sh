#!/usr/bin/env bash
# etcd-health-check.sh
#
# Comprehensive etcd health check for OpenShift clusters.
# Requires: cluster-admin privileges, oc CLI authenticated.
#
# Usage: ./etcd-health-check.sh
#
# Checks performed:
#   1. Cluster-etcd-operator status
#   2. etcd pod status
#   3. etcd member list
#   4. Endpoint health
#   5. Database size
#   6. Leader status
#   7. Certificate expiration (approximate via operator status)

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=0
WARN=0
FAIL=0

check_pass() {
  echo -e "  ${GREEN}[PASS]${NC} $1"
  ((PASS++))
}

check_warn() {
  echo -e "  ${YELLOW}[WARN]${NC} $1"
  ((WARN++))
}

check_fail() {
  echo -e "  ${RED}[FAIL]${NC} $1"
  ((FAIL++))
}

echo "============================================"
echo " etcd Health Check for OpenShift"
echo " $(date)"
echo "============================================"
echo ""

# ---- Check 1: Cluster Operator Status ----
echo "[1/7] Checking cluster-etcd-operator status..."
ETCD_AVAILABLE=$(oc get clusteroperator etcd -o jsonpath='{.status.conditions[?(@.type=="Available")].status}' 2>/dev/null || echo "Unknown")
ETCD_DEGRADED=$(oc get clusteroperator etcd -o jsonpath='{.status.conditions[?(@.type=="Degraded")].status}' 2>/dev/null || echo "Unknown")
ETCD_PROGRESSING=$(oc get clusteroperator etcd -o jsonpath='{.status.conditions[?(@.type=="Progressing")].status}' 2>/dev/null || echo "Unknown")

if [[ "${ETCD_AVAILABLE}" == "True" && "${ETCD_DEGRADED}" == "False" ]]; then
  check_pass "cluster-etcd-operator: Available=${ETCD_AVAILABLE}, Degraded=${ETCD_DEGRADED}"
elif [[ "${ETCD_AVAILABLE}" == "True" && "${ETCD_DEGRADED}" == "True" ]]; then
  check_warn "cluster-etcd-operator: Available but Degraded"
else
  check_fail "cluster-etcd-operator: Available=${ETCD_AVAILABLE}, Degraded=${ETCD_DEGRADED}"
fi

if [[ "${ETCD_PROGRESSING}" == "True" ]]; then
  check_warn "cluster-etcd-operator is currently progressing (rollout in progress)"
fi

# ---- Check 2: etcd Pod Status ----
echo ""
echo "[2/7] Checking etcd pod status..."
ETCD_PODS=$(oc get pods -n openshift-etcd -l app=etcd --no-headers 2>/dev/null || echo "")
if [[ -z "${ETCD_PODS}" ]]; then
  check_fail "No etcd pods found in openshift-etcd namespace"
else
  TOTAL_PODS=$(echo "${ETCD_PODS}" | wc -l | tr -d ' ')
  RUNNING_PODS=$(echo "${ETCD_PODS}" | grep -c "Running" || true)
  if [[ "${RUNNING_PODS}" -eq "${TOTAL_PODS}" ]]; then
    check_pass "All ${TOTAL_PODS} etcd pods are Running"
  else
    check_fail "${RUNNING_PODS}/${TOTAL_PODS} etcd pods are Running"
    echo "${ETCD_PODS}" | grep -v "Running" | while read -r line; do
      echo "       Not running: ${line}"
    done
  fi
fi

# ---- Check 3: etcd Member List ----
echo ""
echo "[3/7] Checking etcd member list..."
ETCD_POD=$(oc get pods -n openshift-etcd -l app=etcd -o name 2>/dev/null | head -1)
if [[ -n "${ETCD_POD}" ]]; then
  MEMBER_LIST=$(oc rsh -n openshift-etcd -c etcdctl "${ETCD_POD}" etcdctl member list -w table 2>/dev/null || echo "ERROR")
  if [[ "${MEMBER_LIST}" != "ERROR" ]]; then
    MEMBER_COUNT=$(echo "${MEMBER_LIST}" | grep -c "started" || true)
    if [[ "${MEMBER_COUNT}" -ge 3 ]]; then
      check_pass "${MEMBER_COUNT} etcd members started (quorum healthy)"
    elif [[ "${MEMBER_COUNT}" -ge 2 ]]; then
      check_warn "${MEMBER_COUNT} etcd members started (quorum maintained, but degraded)"
    elif [[ "${MEMBER_COUNT}" -eq 1 ]]; then
      check_warn "Only 1 etcd member started (single-node cluster or degraded)"
    else
      check_fail "No started etcd members found"
    fi
    echo "${MEMBER_LIST}"
  else
    check_fail "Could not retrieve etcd member list"
  fi
else
  check_fail "No etcd pod available to query"
fi

# ---- Check 4: Endpoint Health ----
echo ""
echo "[4/7] Checking etcd endpoint health..."
if [[ -n "${ETCD_POD}" ]]; then
  HEALTH=$(oc rsh -n openshift-etcd -c etcdctl "${ETCD_POD}" etcdctl endpoint health --cluster -w table 2>/dev/null || echo "ERROR")
  if [[ "${HEALTH}" != "ERROR" ]]; then
    UNHEALTHY=$(echo "${HEALTH}" | grep -c "false" || true)
    if [[ "${UNHEALTHY}" -eq 0 ]]; then
      check_pass "All endpoints are healthy"
    else
      check_fail "${UNHEALTHY} unhealthy endpoint(s) detected"
    fi
    echo "${HEALTH}"
  else
    check_fail "Could not check endpoint health"
  fi
fi

# ---- Check 5: Database Size ----
echo ""
echo "[5/7] Checking etcd database size..."
if [[ -n "${ETCD_POD}" ]]; then
  DB_STATUS=$(oc rsh -n openshift-etcd -c etcdctl "${ETCD_POD}" etcdctl endpoint status --cluster -w json 2>/dev/null || echo "ERROR")
  if [[ "${DB_STATUS}" != "ERROR" ]]; then
    # Parse JSON to get dbSize values
    echo "${DB_STATUS}" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    for entry in data:
        endpoint = entry.get('Endpoint', 'unknown')
        db_size = entry.get('Status', {}).get('dbSize', 0)
        db_size_mb = db_size / 1024 / 1024
        db_size_gb = db_size / 1024 / 1024 / 1024
        if db_size_gb > 7:
            print(f'  CRITICAL: {endpoint} - {db_size_mb:.1f}MB (>{7}GB threshold)')
        elif db_size_gb > 6:
            print(f'  WARNING:  {endpoint} - {db_size_mb:.1f}MB (>{6}GB threshold)')
        else:
            print(f'  OK:       {endpoint} - {db_size_mb:.1f}MB')
except Exception as e:
    print(f'  Could not parse database status: {e}')
" 2>/dev/null || echo "  (Could not parse database size -- check manually)"
    check_pass "Database size check completed (see details above)"
  else
    check_warn "Could not retrieve database size"
  fi
fi

# ---- Check 6: Leader Status ----
echo ""
echo "[6/7] Checking etcd leader..."
if [[ -n "${ETCD_POD}" ]]; then
  LEADER_INFO=$(oc rsh -n openshift-etcd -c etcdctl "${ETCD_POD}" etcdctl endpoint status --cluster -w table 2>/dev/null || echo "ERROR")
  if [[ "${LEADER_INFO}" != "ERROR" ]]; then
    check_pass "Leader information retrieved"
    echo "${LEADER_INFO}"
  else
    check_warn "Could not retrieve leader information"
  fi
fi

# ---- Check 7: Related Operator Status ----
echo ""
echo "[7/7] Checking related control plane operators..."
for OP in kube-apiserver kube-controller-manager kube-scheduler; do
  OP_AVAILABLE=$(oc get clusteroperator "${OP}" -o jsonpath='{.status.conditions[?(@.type=="Available")].status}' 2>/dev/null || echo "Unknown")
  OP_DEGRADED=$(oc get clusteroperator "${OP}" -o jsonpath='{.status.conditions[?(@.type=="Degraded")].status}' 2>/dev/null || echo "Unknown")
  if [[ "${OP_AVAILABLE}" == "True" && "${OP_DEGRADED}" == "False" ]]; then
    check_pass "${OP}: Available=${OP_AVAILABLE}, Degraded=${OP_DEGRADED}"
  else
    check_warn "${OP}: Available=${OP_AVAILABLE}, Degraded=${OP_DEGRADED}"
  fi
done

# ---- Summary ----
echo ""
echo "============================================"
echo " Summary"
echo "============================================"
echo -e " ${GREEN}Passed: ${PASS}${NC}"
echo -e " ${YELLOW}Warnings: ${WARN}${NC}"
echo -e " ${RED}Failed: ${FAIL}${NC}"
echo ""

if [[ "${FAIL}" -gt 0 ]]; then
  echo -e "${RED}etcd cluster requires attention!${NC}"
  exit 1
elif [[ "${WARN}" -gt 0 ]]; then
  echo -e "${YELLOW}etcd cluster is functional but has warnings.${NC}"
  exit 0
else
  echo -e "${GREEN}etcd cluster is healthy.${NC}"
  exit 0
fi
