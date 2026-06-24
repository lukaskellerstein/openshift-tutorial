#!/bin/bash
# teardown.sh
# Cleans up all resources created in the L3-M1.3 Node Management lesson.
#
# Usage: ./scripts/teardown.sh
#
# WARNING: This will:
# - Delete the infra MachineSet (terminating infra VMs)
# - Delete custom MachineConfigs (triggering node reboots)
# - Restore default scheduling for router, registry, and monitoring
# - Remove the infra MachineConfigPool
# - Delete the autoscaler resources and test deployment

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_DIR="${SCRIPT_DIR}/../manifests"

echo "=== L3-M1.3 Node Management Cleanup ==="
echo ""
echo "WARNING: This will delete infra nodes and trigger worker node reboots."
read -p "Continue? (y/N): " -r REPLY
if [[ ! "${REPLY}" =~ ^[Yy]$ ]]; then
  echo "Aborted."
  exit 0
fi

echo ""
echo "--- Removing autoscale test resources ---"
oc delete -f "${MANIFEST_DIR}/autoscale-test-deployment.yaml" --ignore-not-found 2>/dev/null || true
oc delete -f "${MANIFEST_DIR}/machineautoscaler-worker.yaml" --ignore-not-found 2>/dev/null || true
oc delete -f "${MANIFEST_DIR}/clusterautoscaler.yaml" --ignore-not-found 2>/dev/null || true

echo ""
echo "--- Restoring default IngressController ---"
oc patch ingresscontroller default -n openshift-ingress-operator \
  --type=merge -p '{"spec": {"nodePlacement": null, "replicas": 2}}' 2>/dev/null || true

echo ""
echo "--- Restoring default image registry ---"
oc patch configs.imageregistry.operator.openshift.io/cluster \
  --type=merge -p '{"spec": {"nodeSelector": null, "tolerations": null}}' 2>/dev/null || true

echo ""
echo "--- Restoring default monitoring ---"
oc delete configmap cluster-monitoring-config -n openshift-monitoring --ignore-not-found 2>/dev/null || true

echo ""
echo "--- Removing custom MachineConfigs (will trigger reboots) ---"
oc delete machineconfig 99-infra-kernel-tuning --ignore-not-found 2>/dev/null || true
oc delete machineconfig 99-worker-custom-logrotate --ignore-not-found 2>/dev/null || true

echo ""
echo "--- Removing infra MachineConfigPool ---"
oc delete mcp infra --ignore-not-found 2>/dev/null || true

echo ""
echo "--- Removing infra MachineSet (this terminates infra VMs) ---"
CLUSTER_ID=$(oc get -o jsonpath='{.status.infrastructureName}' infrastructure cluster 2>/dev/null || echo "")
if [ -n "${CLUSTER_ID}" ]; then
  INFRA_MACHINESETS=$(oc get machinesets -n openshift-machine-api \
    -l machine.openshift.io/cluster-api-machine-role=infra \
    -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")

  if [ -n "${INFRA_MACHINESETS}" ]; then
    for ms in ${INFRA_MACHINESETS}; do
      echo "Deleting MachineSet: ${ms}"
      oc delete machineset "${ms}" -n openshift-machine-api --wait=false
    done
    echo "Infra MachineSets deletion initiated. Machines will be drained and terminated."
  else
    echo "No infra MachineSets found."
  fi
fi

echo ""
echo "--- Removing GPU MachineSet ---"
GPU_MACHINESETS=$(oc get machinesets -n openshift-machine-api \
  -l machine.openshift.io/cluster-api-machine-role=gpu \
  -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")

if [ -n "${GPU_MACHINESETS}" ]; then
  for ms in ${GPU_MACHINESETS}; do
    echo "Deleting GPU MachineSet: ${ms}"
    oc delete machineset "${ms}" -n openshift-machine-api --wait=false
  done
fi

echo ""
echo "=== Cleanup Complete ==="
echo ""
echo "Monitor node status with:"
echo "  oc get nodes -w"
echo "  oc get mcp"
echo ""
echo "Note: Worker nodes will reboot as MachineConfigs are removed."
echo "Wait for all MCPs to show UPDATED=True, DEGRADED=False before proceeding."
