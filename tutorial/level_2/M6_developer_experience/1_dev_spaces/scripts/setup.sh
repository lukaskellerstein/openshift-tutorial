#!/usr/bin/env bash
# Setup script for L2-M6.1 — OpenShift Dev Spaces
# Creates the namespace and installs the operator

set -euo pipefail

echo "=== L2-M6.1: OpenShift Dev Spaces Setup ==="

# Check that we are logged in
if ! oc whoami &>/dev/null; then
  echo "ERROR: Not logged in to OpenShift. Run: oc login -u kubeadmin -p <password> https://api.crc.testing:6443"
  exit 1
fi

# Check that we are cluster-admin (needed for operator install)
CURRENT_USER=$(oc whoami)
echo "Logged in as: ${CURRENT_USER}"

# Create the namespace for Dev Spaces
echo ""
echo "--- Creating openshift-devspaces namespace ---"
oc create namespace openshift-devspaces --dry-run=client -o yaml | oc apply -f -

# Install the operator subscription
echo ""
echo "--- Installing Dev Spaces operator ---"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
oc apply -f "${SCRIPT_DIR}/../manifests/subscription-devspaces-operator.yaml"

# Wait for the operator to be ready
echo ""
echo "--- Waiting for operator to install (this may take 2-5 minutes) ---"
echo "Watching CSV status..."

TIMEOUT=300
ELAPSED=0
INTERVAL=10

while [ $ELAPSED -lt $TIMEOUT ]; do
  CSV_PHASE=$(oc get csv -n openshift-operators -l operators.coreos.com/devspaces.openshift-operators="" -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "Pending")

  if [ "$CSV_PHASE" = "Succeeded" ]; then
    echo "Operator installed successfully!"
    break
  fi

  echo "  Status: ${CSV_PHASE} (${ELAPSED}s elapsed)"
  sleep $INTERVAL
  ELAPSED=$((ELAPSED + INTERVAL))
done

if [ $ELAPSED -ge $TIMEOUT ]; then
  echo "WARNING: Operator installation timed out after ${TIMEOUT}s."
  echo "Check status with: oc get csv -n openshift-operators"
  echo "Continuing with CheCluster creation — it will reconcile once the operator is ready."
fi

# Apply the CheCluster CR
echo ""
echo "--- Determining which CheCluster manifest to use ---"

# Check available node resources to decide between full and minimal
NODE_MEMORY_KB=$(oc get node -o jsonpath='{.items[0].status.capacity.memory}' 2>/dev/null | sed 's/Ki//')
NODE_MEMORY_GB=$((NODE_MEMORY_KB / 1024 / 1024))

if [ "$NODE_MEMORY_GB" -lt 14 ]; then
  echo "Node has ${NODE_MEMORY_GB}Gi memory — using minimal CheCluster configuration"
  MANIFEST="checluster-minimal.yaml"
else
  echo "Node has ${NODE_MEMORY_GB}Gi memory — using full CheCluster configuration"
  MANIFEST="checluster.yaml"
fi

echo ""
echo "--- Creating CheCluster instance ---"
oc apply -f "${SCRIPT_DIR}/../manifests/${MANIFEST}"

echo ""
echo "--- Waiting for Dev Spaces components to start (this may take 5-10 minutes) ---"

TIMEOUT=600
ELAPSED=0
INTERVAL=15

while [ $ELAPSED -lt $TIMEOUT ]; do
  ACTIVE=$(oc get checluster devspaces -n openshift-devspaces -o jsonpath='{.status.chePhase}' 2>/dev/null || echo "Reconciling")

  if [ "$ACTIVE" = "Active" ]; then
    echo "Dev Spaces is active!"
    break
  fi

  echo "  Phase: ${ACTIVE} (${ELAPSED}s elapsed)"
  sleep $INTERVAL
  ELAPSED=$((ELAPSED + INTERVAL))
done

if [ $ELAPSED -ge $TIMEOUT ]; then
  echo "WARNING: Dev Spaces setup timed out after ${TIMEOUT}s."
  echo "Check status with: oc get checluster devspaces -n openshift-devspaces -o yaml"
fi

# Print the Dev Spaces URL
echo ""
echo "=== Setup Complete ==="
DEV_SPACES_URL=$(oc get checluster devspaces -n openshift-devspaces -o jsonpath='{.status.cheURL}' 2>/dev/null || echo "Not yet available")
echo "Dev Spaces Dashboard: ${DEV_SPACES_URL}"
echo ""
echo "To access Dev Spaces:"
echo "  1. Open the URL above in your browser"
echo "  2. Log in with your OpenShift credentials"
echo "  3. Create a workspace from a devfile or Git repository URL"
