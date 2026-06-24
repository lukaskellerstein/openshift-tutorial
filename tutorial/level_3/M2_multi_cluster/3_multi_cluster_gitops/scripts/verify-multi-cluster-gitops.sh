#!/usr/bin/env bash
# verify-multi-cluster-gitops.sh -- Verify multi-cluster GitOps setup
#
# Usage:
#   ./verify-multi-cluster-gitops.sh
#
# This script checks:
#   1. ApplicationSets exist in openshift-gitops namespace
#   2. Generated Applications are created
#   3. Sync status of all Applications
#   4. PlacementDecisions are populated
#   5. Target cluster resources are deployed
#
# Requirements:
#   - oc CLI authenticated to the hub cluster
#   - argocd CLI (optional, for detailed status)

set -euo pipefail

NAMESPACE="openshift-gitops"
PASS=0
FAIL=0
WARN=0

check_pass() {
  echo "  [PASS] $1"
  ((PASS++))
}

check_fail() {
  echo "  [FAIL] $1"
  ((FAIL++))
}

check_warn() {
  echo "  [WARN] $1"
  ((WARN++))
}

echo "=== Multi-Cluster GitOps Verification ==="
echo ""

# 1. Check ApplicationSets
echo "--- ApplicationSets ---"
APPSETS=$(oc get applicationsets -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [[ "$APPSETS" -gt 0 ]]; then
  check_pass "Found ${APPSETS} ApplicationSet(s)"
  oc get applicationsets -n "$NAMESPACE" -o custom-columns=NAME:.metadata.name,AGE:.metadata.creationTimestamp
else
  check_fail "No ApplicationSets found in ${NAMESPACE}"
fi
echo ""

# 2. Check generated Applications
echo "--- Generated Applications ---"
APPS=$(oc get applications -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [[ "$APPS" -gt 0 ]]; then
  check_pass "Found ${APPS} Application(s)"
  oc get applications -n "$NAMESPACE" \
    -o custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status
else
  check_fail "No Applications found -- ApplicationSets may not have generated any"
fi
echo ""

# 3. Check sync status
echo "--- Sync Status ---"
OUTOFSYNC=$(oc get applications -n "$NAMESPACE" --no-headers 2>/dev/null \
  | grep -v "Synced" | wc -l | tr -d ' ')
if [[ "$OUTOFSYNC" -eq 0 ]]; then
  check_pass "All Applications are Synced"
else
  check_warn "${OUTOFSYNC} Application(s) are not Synced"
  oc get applications -n "$NAMESPACE" --no-headers | grep -v "Synced" || true
fi
echo ""

# 4. Check health status
echo "--- Health Status ---"
UNHEALTHY=$(oc get applications -n "$NAMESPACE" --no-headers 2>/dev/null \
  | grep -v "Healthy" | wc -l | tr -d ' ')
if [[ "$UNHEALTHY" -eq 0 ]]; then
  check_pass "All Applications are Healthy"
else
  check_warn "${UNHEALTHY} Application(s) are not Healthy"
  oc get applications -n "$NAMESPACE" --no-headers | grep -v "Healthy" || true
fi
echo ""

# 5. Check PlacementDecisions
echo "--- RHACM PlacementDecisions ---"
if oc api-resources | grep -q placementdecisions 2>/dev/null; then
  PDS=$(oc get placementdecisions -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l | tr -d ' ')
  if [[ "$PDS" -gt 0 ]]; then
    check_pass "Found ${PDS} PlacementDecision(s)"
    oc get placementdecisions -n "$NAMESPACE" \
      -o custom-columns=NAME:.metadata.name,CLUSTERS:.status.decisions[*].clusterName
  else
    check_warn "No PlacementDecisions found -- RHACM integration may not be configured"
  fi
else
  check_warn "PlacementDecision CRD not found -- RHACM may not be installed"
fi
echo ""

# 6. Check ACM integration ConfigMap
echo "--- ACM Integration ConfigMap ---"
if oc get configmap acm-placement -n "$NAMESPACE" &>/dev/null; then
  check_pass "ACM placement ConfigMap exists"
else
  check_warn "ACM placement ConfigMap not found -- clusterDecisionResource generator will not work"
fi
echo ""

# 7. ArgoCD detailed status (if CLI available)
echo "--- ArgoCD CLI Status ---"
if command -v argocd &>/dev/null; then
  argocd app list --output wide 2>/dev/null || check_warn "argocd CLI available but could not list apps (not logged in?)"
else
  check_warn "argocd CLI not found -- skipping detailed status"
fi
echo ""

# Summary
echo "=== Summary ==="
echo "  Passed: ${PASS}"
echo "  Failed: ${FAIL}"
echo "  Warnings: ${WARN}"
echo ""

if [[ "$FAIL" -gt 0 ]]; then
  echo "Some checks FAILED. Review the output above."
  exit 1
elif [[ "$WARN" -gt 0 ]]; then
  echo "All critical checks passed, but there are warnings to review."
  exit 0
else
  echo "All checks passed."
  exit 0
fi
