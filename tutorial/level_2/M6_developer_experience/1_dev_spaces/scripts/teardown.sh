#!/usr/bin/env bash
# Teardown script for L2-M6.1 — OpenShift Dev Spaces
# Removes the CheCluster instance and optionally the operator

set -euo pipefail

echo "=== L2-M6.1: OpenShift Dev Spaces Teardown ==="

# Check that we are logged in
if ! oc whoami &>/dev/null; then
  echo "ERROR: Not logged in to OpenShift."
  exit 1
fi

# Delete all DevWorkspace instances first (workspaces must be stopped)
echo "--- Stopping and deleting all DevWorkspace instances ---"
oc get devworkspace -A --no-headers 2>/dev/null | while read -r NS NAME _REST; do
  echo "  Deleting DevWorkspace ${NAME} in namespace ${NS}"
  oc delete devworkspace "${NAME}" -n "${NS}" --wait=false 2>/dev/null || true
done

# Delete DevWorkspaceTemplates
echo ""
echo "--- Deleting DevWorkspaceTemplates ---"
oc delete devworkspacetemplate -l tutorial-level=2,tutorial-module=M6 -n openshift-devspaces 2>/dev/null || true

# Delete the CheCluster CR
echo ""
echo "--- Deleting CheCluster instance ---"
oc delete checluster devspaces -n openshift-devspaces --wait=true --timeout=120s 2>/dev/null || true

# Wait for all Dev Spaces pods to terminate
echo ""
echo "--- Waiting for Dev Spaces pods to terminate ---"
TIMEOUT=120
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
  POD_COUNT=$(oc get pods -n openshift-devspaces --no-headers 2>/dev/null | wc -l | tr -d ' ')
  if [ "$POD_COUNT" = "0" ]; then
    echo "All Dev Spaces pods terminated."
    break
  fi
  echo "  ${POD_COUNT} pods remaining (${ELAPSED}s elapsed)"
  sleep 10
  ELAPSED=$((ELAPSED + 10))
done

# Delete the namespace
echo ""
echo "--- Deleting openshift-devspaces namespace ---"
oc delete namespace openshift-devspaces --wait=false 2>/dev/null || true

# Delete user workspace namespaces
echo ""
echo "--- Cleaning up user workspace namespaces ---"
oc get namespaces -o name 2>/dev/null | grep '\-devspaces$' | while read -r NS; do
  echo "  Deleting namespace ${NS}"
  oc delete "${NS}" --wait=false 2>/dev/null || true
done

# Optionally remove the operator
echo ""
echo "--- Operator cleanup ---"
echo "The Dev Spaces operator is still installed cluster-wide."
echo "To remove it:"
echo "  1. Web Console: Operators > Installed Operators > Dev Spaces > Uninstall"
echo "  2. CLI:"
echo "     oc delete subscription devspaces -n openshift-operators"
echo '     oc delete csv $(oc get csv -n openshift-operators -o name | grep devspaces) -n openshift-operators'

echo ""
echo "=== Teardown Complete ==="
