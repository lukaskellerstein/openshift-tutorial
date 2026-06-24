#!/usr/bin/env bash
# cleanup.sh
# Removes all resources created by this lesson.
#
# Usage: ./scripts/cleanup.sh [namespace]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_DIR="${SCRIPT_DIR}/../manifests"
NAMESPACE="${1:-edge-apps}"

echo "=== Cleaning Up Hybrid & Edge Deployment Resources ==="
echo ""

# Remove MicroShift application
echo "Removing MicroShift application resources from namespace ${NAMESPACE}..."
oc delete -f "${MANIFEST_DIR}/microshift-app-route.yaml" -n "${NAMESPACE}" --ignore-not-found
oc delete -f "${MANIFEST_DIR}/microshift-app-service.yaml" -n "${NAMESPACE}" --ignore-not-found
oc delete -f "${MANIFEST_DIR}/microshift-app-deployment.yaml" -n "${NAMESPACE}" --ignore-not-found

# Remove remote worker application if deployed
echo "Removing remote worker application resources..."
oc delete -f "${MANIFEST_DIR}/remote-worker-app-deployment.yaml" -n "${NAMESPACE}" --ignore-not-found 2>/dev/null || true

# Remove all resources with tutorial labels
echo "Removing any remaining resources with tutorial labels..."
oc delete all -l tutorial-level=3,tutorial-module=M2 -n "${NAMESPACE}" --ignore-not-found 2>/dev/null || true

echo ""
echo "=== Cleanup Complete ==="
echo ""
echo "Note: Cluster-level resources (MachineConfigPool, KubeletConfig,"
echo "PerformanceProfile, MachineSet) were NOT removed as they affect"
echo "cluster infrastructure. Remove them manually if needed:"
echo ""
echo "  oc delete kubeletconfig remote-worker-kubelet"
echo "  oc delete machineconfigpool remote-worker"
echo "  oc delete performanceprofile sno-edge-profile"
echo "  oc delete machineset remote-worker-branch-nyc -n openshift-machine-api"
