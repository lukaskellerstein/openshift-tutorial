#!/bin/bash
# Cleanup script for L2-M5.1 — Image Security & Compliance
# Removes all resources created during the lesson

set -euo pipefail

echo "=== L2-M5.1 — Image Security & Compliance Cleanup ==="

# Ensure we are logged in
if ! oc whoami &>/dev/null; then
  echo "ERROR: Not logged in to OpenShift. Run: oc login"
  exit 1
fi

# Delete the project (as developer)
echo ""
echo "--- Deleting project image-security-lab ---"
oc delete project image-security-lab --ignore-not-found=true

# Revert cluster-wide changes (requires cluster-admin)
CURRENT_USER=$(oc whoami)
echo ""
echo "--- Checking for cluster-wide changes to revert ---"

# Try to switch to kubeadmin for cluster-wide cleanup
if oc login -u kubeadmin https://api.crc.testing:6443 &>/dev/null; then
  echo "Logged in as kubeadmin for cluster-wide cleanup"

  # Remove registry restrictions
  echo ""
  echo "--- Removing registry restrictions from cluster image policy ---"
  oc patch image.config.openshift.io/cluster --type=json \
    -p='[{"op": "remove", "path": "/spec/registrySources"}]' 2>/dev/null || \
    echo "No registrySources to remove (already clean)"

  # Remove MachineConfig if applied
  echo ""
  echo "--- Removing signature verification MachineConfig ---"
  oc delete machineconfig 50-image-signature-policy --ignore-not-found=true

  # Remove ImageTagMirrorSet if applied
  echo ""
  echo "--- Removing ImageTagMirrorSet ---"
  oc delete imagetagmirrorset docker-hub-mirror --ignore-not-found=true

  # Switch back to developer
  echo ""
  echo "--- Switching back to developer user ---"
  oc login -u developer -p developer https://api.crc.testing:6443
else
  echo "WARNING: Could not log in as kubeadmin."
  echo "If you applied cluster-wide changes (image policy, MachineConfig, ImageTagMirrorSet),"
  echo "you must revert them manually as cluster-admin."
fi

echo ""
echo "=== Cleanup complete ==="
