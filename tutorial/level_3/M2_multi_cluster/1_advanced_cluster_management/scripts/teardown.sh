#!/usr/bin/env bash
# teardown.sh — Remove all resources created in the L3-M2.1 lesson.
#
# Prerequisites:
#   - Logged in as cluster-admin on the hub cluster
#   - oc CLI available
#
# Usage:
#   ./scripts/teardown.sh [--full]
#
# Options:
#   --full    Also uninstall the ACM operator and MultiClusterHub.
#             Without this flag, only lesson-specific resources are removed
#             (policies, placements, demo app, cluster sets).
#
# This script does NOT destroy managed clusters — it only detaches them
# from the hub. The clusters continue running independently.

set -euo pipefail

FULL_UNINSTALL=false
if [[ "${1:-}" == "--full" ]]; then
  FULL_UNINSTALL=true
fi

NAMESPACE="open-cluster-management"

echo "=== L3-M2.1 Teardown Script ==="
echo ""

if ! oc whoami &>/dev/null; then
  echo "ERROR: Not logged in to an OpenShift cluster. Run 'oc login' first."
  exit 1
fi

echo "Logged in as: $(oc whoami)"
echo ""

# Remove demo application
echo "[1/5] Removing demo application..."
oc delete application demo-app -n multi-cluster-demo --ignore-not-found=true
oc delete subscription.apps.open-cluster-management.io demo-app-subscription -n multi-cluster-demo --ignore-not-found=true
oc delete channel demo-app-channel -n multi-cluster-demo --ignore-not-found=true
oc delete placement demo-app-placement -n multi-cluster-demo --ignore-not-found=true
oc delete namespace multi-cluster-demo --ignore-not-found=true
echo ""

# Remove governance policies
echo "[2/5] Removing governance policies..."
oc delete placementbinding binding-policy-resource-quota -n "${NAMESPACE}" --ignore-not-found=true
oc delete placement staging-placement -n "${NAMESPACE}" --ignore-not-found=true
oc delete policy policy-resource-quota -n "${NAMESPACE}" --ignore-not-found=true
oc delete policy policy-deny-all-networkpolicy -n "${NAMESPACE}" --ignore-not-found=true
echo ""

# Remove cluster sets
echo "[3/5] Removing cluster sets and bindings..."
oc delete managedclustersetbinding staging-clusters -n "${NAMESPACE}" --ignore-not-found=true
oc delete managedclusterset production-clusters --ignore-not-found=true
oc delete managedclusterset staging-clusters --ignore-not-found=true
echo ""

# Detach managed clusters (does NOT destroy them)
echo "[4/5] Detaching managed clusters..."
MANAGED_CLUSTERS=$(oc get managedclusters -o jsonpath='{.items[?(@.metadata.name!="local-cluster")].metadata.name}' 2>/dev/null || echo "")
if [[ -n "${MANAGED_CLUSTERS}" ]]; then
  for cluster in ${MANAGED_CLUSTERS}; do
    echo "  Detaching: ${cluster}"
    oc delete managedcluster "${cluster}" --ignore-not-found=true
  done
else
  echo "  No managed clusters to detach (excluding local-cluster)."
fi
echo ""

# Clean up by label
echo "[5/5] Cleaning up resources by tutorial labels..."
oc delete all -l tutorial-level=3,tutorial-module=M2 --all-namespaces --ignore-not-found=true 2>/dev/null || true
echo ""

if [[ "${FULL_UNINSTALL}" == true ]]; then
  echo "=== Full ACM Uninstall ==="
  echo ""
  echo "Removing MultiClusterHub..."
  oc delete multiclusterhub multiclusterhub -n "${NAMESPACE}" --ignore-not-found=true

  echo "Waiting for MultiClusterHub removal (this takes several minutes)..."
  SECONDS=0
  while oc get multiclusterhub multiclusterhub -n "${NAMESPACE}" &>/dev/null; do
    if (( SECONDS > 600 )); then
      echo "WARNING: Timed out waiting for MultiClusterHub removal."
      break
    fi
    sleep 10
  done

  echo "Removing ACM operator subscription..."
  oc delete subscription advanced-cluster-management -n "${NAMESPACE}" --ignore-not-found=true

  echo "Removing CSVs..."
  oc delete csv -n "${NAMESPACE}" -l operators.coreos.com/advanced-cluster-management.open-cluster-management --ignore-not-found=true 2>/dev/null || true

  echo "Removing namespace..."
  oc delete namespace "${NAMESPACE}" --ignore-not-found=true

  echo ""
  echo "ACM fully uninstalled."
fi

echo ""
echo "=== Teardown Complete ==="
