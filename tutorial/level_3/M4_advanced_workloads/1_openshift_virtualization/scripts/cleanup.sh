#!/bin/bash
# cleanup.sh — Remove all resources created during the L3-M4.1 lesson
# Usage: ./scripts/cleanup.sh [--full]
#   --full  Also uninstalls the CNV operator (not just the lab resources)

set -euo pipefail

FULL_CLEANUP=false
if [ "${1:-}" = "--full" ]; then
  FULL_CLEANUP=true
fi

echo "=== Cleanup: L3-M4.1 OpenShift Virtualization ==="
echo ""

# Stop any running VMs first
echo "[1/5] Stopping running VMs in virtualization-lab..."
for VM in $(oc get vm -n virtualization-lab -o jsonpath='{.items[*].metadata.name}' 2>/dev/null); do
  echo "  Stopping VM: ${VM}"
  oc patch vm "${VM}" -n virtualization-lab --type merge -p '{"spec":{"running":false}}' 2>/dev/null || true
done

# Wait briefly for VMIs to terminate
echo "  Waiting for VMIs to terminate..."
sleep 10
oc wait vmi --all -n virtualization-lab --for=delete --timeout=120s 2>/dev/null || true

# Delete VMs, snapshots, restores
echo ""
echo "[2/5] Deleting VMs, snapshots, and restores..."
oc delete vm --all -n virtualization-lab 2>/dev/null || true
oc delete vmisnapshot --all -n virtualization-lab 2>/dev/null || true
oc delete vmirestore --all -n virtualization-lab 2>/dev/null || true
oc delete virtualmachinesnapshot --all -n virtualization-lab 2>/dev/null || true
oc delete virtualmachinerestore --all -n virtualization-lab 2>/dev/null || true

# Delete services, routes, network attachments
echo ""
echo "[3/5] Deleting networking resources..."
oc delete service,route -l tutorial-level=3,tutorial-module=M4 -n virtualization-lab 2>/dev/null || true
oc delete net-attach-def -l tutorial-level=3,tutorial-module=M4 -n virtualization-lab 2>/dev/null || true

# Delete DataVolumes and PVCs
echo ""
echo "[4/5] Deleting DataVolumes and PVCs..."
oc delete dv --all -n virtualization-lab 2>/dev/null || true
oc delete pvc --all -n virtualization-lab 2>/dev/null || true

# Delete the project
echo ""
echo "[5/5] Deleting virtualization-lab project..."
oc delete project virtualization-lab 2>/dev/null || true

# Optionally remove the CNV operator
if [ "$FULL_CLEANUP" = true ]; then
  echo ""
  echo "[FULL] Removing MigrationPolicy..."
  oc delete migrationpolicy production-migration-policy 2>/dev/null || true

  echo "[FULL] Removing HyperConverged CR..."
  oc delete hyperconverged kubevirt-hyperconverged -n openshift-cnv --timeout=300s 2>/dev/null || true

  echo "[FULL] Removing CNV Subscription..."
  oc delete subscription kubevirt-hyperconverged -n openshift-cnv 2>/dev/null || true

  echo "[FULL] Removing CSVs..."
  oc delete csv -n openshift-cnv --all 2>/dev/null || true

  echo "[FULL] Removing OperatorGroup..."
  oc delete operatorgroup kubevirt-hyperconverged-group -n openshift-cnv 2>/dev/null || true

  echo "[FULL] Removing openshift-cnv namespace..."
  oc delete namespace openshift-cnv --timeout=120s 2>/dev/null || true

  echo ""
  echo "=== Full cleanup complete (operator removed) ==="
else
  echo ""
  echo "=== Lab cleanup complete ==="
  echo "Note: The CNV operator is still installed."
  echo "To also remove the operator, run: ./scripts/cleanup.sh --full"
fi
