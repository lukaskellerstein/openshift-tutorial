#!/usr/bin/env bash
#
# verify-platform.sh
# Comprehensive verification of the multi-cluster platform.
#
# Usage: ./verify-platform.sh
#
# Prerequisites:
#   - Logged in to the hub cluster via oc
#   - All capstone manifests applied
#
# This script checks:
#   1. RHACM hub health
#   2. Managed cluster connectivity
#   3. Policy compliance
#   4. Observability status
#   5. ApplicationSet and Application health
#   6. Velero backup status
#   7. Alerting rule installation
#
set -euo pipefail

PASS=0
WARN=0
FAIL=0

check_pass() {
  echo "  [PASS] $1"
  ((PASS++))
}

check_warn() {
  echo "  [WARN] $1"
  ((WARN++))
}

check_fail() {
  echo "  [FAIL] $1"
  ((FAIL++))
}

echo "=============================================="
echo "  MULTI-CLUSTER PLATFORM VERIFICATION"
echo "  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "=============================================="
echo ""

# --- Section 1: RHACM Hub Health ---
echo "=== 1. RHACM Hub Health ==="

if oc get multiclusterhub -n open-cluster-management -o jsonpath='{.items[0].status.phase}' 2>/dev/null | grep -q "Running"; then
  check_pass "MultiClusterHub is Running"
else
  check_fail "MultiClusterHub is not Running"
fi

UNHEALTHY_PODS=$(oc get pods -n open-cluster-management --field-selector=status.phase!=Running,status.phase!=Succeeded --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [[ "${UNHEALTHY_PODS}" -eq 0 ]]; then
  check_pass "All RHACM pods are healthy"
else
  check_fail "${UNHEALTHY_PODS} RHACM pod(s) are not running"
fi

echo ""

# --- Section 2: Managed Clusters ---
echo "=== 2. Managed Cluster Connectivity ==="

CLUSTER_COUNT=$(oc get managedclusters --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [[ "${CLUSTER_COUNT}" -ge 3 ]]; then
  check_pass "${CLUSTER_COUNT} managed clusters registered (hub + 2 spokes)"
else
  check_warn "Only ${CLUSTER_COUNT} managed cluster(s) found (expected 3+)"
fi

for cluster in $(oc get managedclusters -o jsonpath='{.items[*].metadata.name}' 2>/dev/null); do
  available=$(oc get managedcluster "${cluster}" \
    -o jsonpath='{.status.conditions[?(@.type=="ManagedClusterConditionAvailable")].status}' 2>/dev/null)
  if [[ "${available}" == "True" ]]; then
    check_pass "Cluster '${cluster}' is Available"
  else
    check_fail "Cluster '${cluster}' is NOT Available (status: ${available:-unknown})"
  fi
done

echo ""

# --- Section 3: Policy Compliance ---
echo "=== 3. Policy Compliance ==="

TOTAL_POLICIES=$(oc get policy -A --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [[ "${TOTAL_POLICIES}" -gt 0 ]]; then
  check_pass "${TOTAL_POLICIES} policies deployed"
else
  check_fail "No policies found"
fi

NONCOMPLIANT=$(oc get policy -A -o jsonpath='{.items[?(@.status.compliant=="NonCompliant")].metadata.name}' 2>/dev/null)
if [[ -z "${NONCOMPLIANT}" ]]; then
  check_pass "All policies are Compliant"
else
  for policy in ${NONCOMPLIANT}; do
    check_warn "Policy '${policy}' is NonCompliant (may be intentional if remediationAction=inform)"
  done
fi

echo ""

# --- Section 4: Observability ---
echo "=== 4. Multi-Cluster Observability ==="

if oc get multiclusterobservability observability -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null | grep -q "True"; then
  check_pass "MultiClusterObservability is Ready"
else
  check_warn "MultiClusterObservability may not be ready yet"
fi

OBS_ADDONS=$(oc get managedclusteraddon -A --no-headers 2>/dev/null | grep observability | wc -l | tr -d ' ')
if [[ "${OBS_ADDONS}" -ge 2 ]]; then
  check_pass "Observability addon enabled on ${OBS_ADDONS} cluster(s)"
else
  check_warn "Observability addon found on only ${OBS_ADDONS} cluster(s)"
fi

GRAFANA_URL=$(oc get route grafana -n open-cluster-management-observability -o jsonpath='{.spec.host}' 2>/dev/null || echo "")
if [[ -n "${GRAFANA_URL}" ]]; then
  check_pass "Grafana accessible at: https://${GRAFANA_URL}"
else
  check_warn "Grafana route not found"
fi

echo ""

# --- Section 5: ApplicationSets and Applications ---
echo "=== 5. ApplicationSets and Applications ==="

APPSET_COUNT=$(oc get applicationsets -n openshift-gitops --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [[ "${APPSET_COUNT}" -gt 0 ]]; then
  check_pass "${APPSET_COUNT} ApplicationSet(s) deployed"
else
  check_fail "No ApplicationSets found"
fi

for app in $(oc get applications -n openshift-gitops -o jsonpath='{.items[*].metadata.name}' 2>/dev/null); do
  sync=$(oc get application "${app}" -n openshift-gitops -o jsonpath='{.status.sync.status}' 2>/dev/null)
  health=$(oc get application "${app}" -n openshift-gitops -o jsonpath='{.status.health.status}' 2>/dev/null)
  if [[ "${sync}" == "Synced" && "${health}" == "Healthy" ]]; then
    check_pass "Application '${app}': Synced & Healthy"
  else
    check_warn "Application '${app}': sync=${sync:-unknown}, health=${health:-unknown}"
  fi
done

echo ""

# --- Section 6: Velero Backups ---
echo "=== 6. Disaster Recovery (Velero) ==="

if oc get namespace velero &>/dev/null; then
  check_pass "Velero namespace exists"
else
  check_warn "Velero namespace not found (DR may not be configured)"
fi

# Note: Velero checks require being on the spoke cluster context
# This check is hub-side only via policy compliance
VELERO_POLICY=$(oc get policy policy-velero-config -n platform-policies -o jsonpath='{.status.compliant}' 2>/dev/null || echo "")
if [[ "${VELERO_POLICY}" == "Compliant" ]]; then
  check_pass "Velero configuration policy is Compliant"
elif [[ "${VELERO_POLICY}" == "NonCompliant" ]]; then
  check_warn "Velero configuration policy is NonCompliant -- check spoke cluster Velero setup"
else
  check_warn "Could not determine Velero policy compliance"
fi

echo ""

# --- Section 7: Alerting Rules ---
echo "=== 7. Alerting Rules ==="

if oc get prometheusrule capstone-platform-alerts -n open-cluster-management-observability &>/dev/null; then
  check_pass "Platform alerting rules deployed"
else
  check_warn "Platform alerting rules not found"
fi

echo ""

# --- Summary ---
echo "=============================================="
echo "  VERIFICATION SUMMARY"
echo "=============================================="
echo ""
echo "  PASS: ${PASS}"
echo "  WARN: ${WARN}"
echo "  FAIL: ${FAIL}"
echo ""

if [[ "${FAIL}" -gt 0 ]]; then
  echo "  STATUS: INCOMPLETE -- address FAIL items before proceeding"
  exit 1
elif [[ "${WARN}" -gt 0 ]]; then
  echo "  STATUS: PARTIAL -- review WARN items"
  exit 0
else
  echo "  STATUS: ALL CHECKS PASSED"
  exit 0
fi
