#!/bin/bash
# Cleanup script for L2-M5.2 — Pod Security & Admission
# Removes all resources created during this lesson.
# Must be run as kubeadmin (or a user with cluster-admin privileges).

set -euo pipefail

echo "=== L2-M5.2 Cleanup: Pod Security & Admission ==="

# Check if logged in
if ! oc whoami &>/dev/null; then
  echo "ERROR: Not logged in to OpenShift. Run: oc login -u kubeadmin -p <password> https://api.crc.testing:6443"
  exit 1
fi

CURRENT_USER=$(oc whoami)
echo "Logged in as: ${CURRENT_USER}"

# Step 1: Delete Gatekeeper constraints
echo ""
echo "--- Deleting Gatekeeper constraints ---"
oc delete k8sdisallowroot disallow-root-pods --ignore-not-found=true 2>/dev/null || true
oc delete k8srequireresourcelimits require-resource-limits --ignore-not-found=true 2>/dev/null || true

# Step 2: Delete Gatekeeper constraint templates
echo ""
echo "--- Deleting Gatekeeper constraint templates ---"
oc delete constrainttemplate k8sdisallowroot --ignore-not-found=true 2>/dev/null || true
oc delete constrainttemplate k8srequireresourcelimits --ignore-not-found=true 2>/dev/null || true

# Step 3: Remove Gatekeeper installation
echo ""
echo "--- Removing OPA Gatekeeper ---"
oc delete -f https://raw.githubusercontent.com/open-policy-agent/gatekeeper/v3.16.0/deploy/gatekeeper.yaml --ignore-not-found=true 2>/dev/null || true

# Step 4: Remove custom SCC binding and SCC
echo ""
echo "--- Removing custom SCC ---"
oc adm policy remove-scc-from-user custom-network-v2 -z network-app-sa -n pod-security-demo 2>/dev/null || true
oc delete scc custom-network-v2 --ignore-not-found=true 2>/dev/null || true

# Step 5: Delete the test project
echo ""
echo "--- Deleting pod-security-demo project ---"
oc delete project pod-security-demo --ignore-not-found=true 2>/dev/null || true

echo ""
echo "=== Cleanup complete ==="
