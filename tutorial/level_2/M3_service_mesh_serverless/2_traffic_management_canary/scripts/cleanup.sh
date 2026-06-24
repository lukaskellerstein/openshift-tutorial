#!/bin/bash
# Cleanup script for L2-M3.2 — Traffic Management & Canary Deployments
#
# Removes all resources created during this lesson.
# The project itself is preserved (delete it manually if desired).

set -euo pipefail

NAMESPACE="bookinfo-mesh"

echo "=== L2-M3.2 Cleanup: Traffic Management & Canary Deployments ==="

# Delete Istio resources (not covered by "oc delete all")
echo "[...] Deleting VirtualService, DestinationRule, and Gateway"
oc delete virtualservice canary-demo -n "${NAMESPACE}" --ignore-not-found
oc delete destinationrule canary-demo -n "${NAMESPACE}" --ignore-not-found
oc delete gateway canary-demo-gateway -n "${NAMESPACE}" --ignore-not-found

# Delete Route
echo "[...] Deleting Route"
oc delete route canary-demo -n "${NAMESPACE}" --ignore-not-found

# Delete application resources
echo "[...] Deleting Deployments, Services, and Pods"
oc delete deployment canary-demo-v1 canary-demo-v2 -n "${NAMESPACE}" --ignore-not-found
oc delete service canary-demo -n "${NAMESPACE}" --ignore-not-found

# Delete fortio load tester
echo "[...] Deleting Fortio load tester"
oc delete deployment fortio -n "${NAMESPACE}" --ignore-not-found
oc delete service fortio -n "${NAMESPACE}" --ignore-not-found

# Catch anything missed by label
echo "[...] Cleaning up by tutorial label"
oc delete all -l tutorial-level=2,tutorial-module=M3 -n "${NAMESPACE}" --ignore-not-found

echo ""
echo "=== Cleanup Complete ==="
echo ""
echo "Remaining resources in ${NAMESPACE}:"
oc get all -n "${NAMESPACE}" 2>/dev/null || echo "(none)"
echo ""
echo "To delete the project entirely: oc delete project ${NAMESPACE}"
