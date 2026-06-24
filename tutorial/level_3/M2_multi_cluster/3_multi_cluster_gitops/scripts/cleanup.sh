#!/usr/bin/env bash
# cleanup.sh -- Remove all resources created by the multi-cluster GitOps lesson
#
# Usage:
#   ./cleanup.sh
#
# This script removes:
#   - ApplicationSets from the hub cluster
#   - Placement resources
#   - ACM integration ConfigMap
#   - Namespaces on target clusters (if accessible)
#
# Requirements:
#   - oc CLI authenticated to the hub cluster

set -euo pipefail

NAMESPACE="openshift-gitops"

echo "=== Cleaning up Multi-Cluster GitOps resources ==="
echo ""

# Remove ApplicationSets (this cascades to delete generated Applications)
echo "--- Removing ApplicationSets ---"
for appset in demo-app demo-app-cluster-gen demo-app-placement platform-apps; do
  if oc get applicationset "$appset" -n "$NAMESPACE" &>/dev/null; then
    oc delete applicationset "$appset" -n "$NAMESPACE"
    echo "  Deleted ApplicationSet: ${appset}"
  else
    echo "  ApplicationSet not found (skipping): ${appset}"
  fi
done
echo ""

# Remove Placement resources
echo "--- Removing Placement resources ---"
if oc get placement prod-clusters -n "$NAMESPACE" &>/dev/null; then
  oc delete placement prod-clusters -n "$NAMESPACE"
  echo "  Deleted Placement: prod-clusters"
else
  echo "  Placement not found (skipping): prod-clusters"
fi
echo ""

# Remove ConfigMap
echo "--- Removing ACM integration ConfigMap ---"
if oc get configmap acm-placement -n "$NAMESPACE" &>/dev/null; then
  oc delete configmap acm-placement -n "$NAMESPACE"
  echo "  Deleted ConfigMap: acm-placement"
else
  echo "  ConfigMap not found (skipping): acm-placement"
fi
echo ""

# Clean up target cluster namespaces
echo "--- Cleaning up target cluster namespaces ---"
echo "  Attempting to clean namespaces on target clusters..."
echo "  (This requires contexts for each cluster to be configured)"
for ctx in dev-cluster staging-cluster prod-cluster-east prod-cluster-west; do
  if oc config get-contexts "$ctx" &>/dev/null 2>&1; then
    for ns in demo-dev demo-staging demo-prod; do
      if oc --context "$ctx" get namespace "$ns" &>/dev/null 2>&1; then
        oc --context "$ctx" delete namespace "$ns" --ignore-not-found
        echo "  Deleted namespace ${ns} on ${ctx}"
      fi
    done
  else
    echo "  Context ${ctx} not found -- skipping (clean up manually if needed)"
  fi
done
echo ""

# Verify cleanup
echo "--- Verifying cleanup ---"
REMAINING_APPSETS=$(oc get applicationsets -n "$NAMESPACE" -l tutorial-module=M2 --no-headers 2>/dev/null | wc -l | tr -d ' ')
REMAINING_APPS=$(oc get applications -n "$NAMESPACE" -l tutorial-module=M2 --no-headers 2>/dev/null | wc -l | tr -d ' ')

if [[ "$REMAINING_APPSETS" -eq 0 ]] && [[ "$REMAINING_APPS" -eq 0 ]]; then
  echo "  All tutorial resources cleaned up successfully."
else
  echo "  WARNING: ${REMAINING_APPSETS} ApplicationSet(s) and ${REMAINING_APPS} Application(s) remain."
  echo "  These may need manual cleanup."
fi

echo ""
echo "=== Cleanup complete ==="
