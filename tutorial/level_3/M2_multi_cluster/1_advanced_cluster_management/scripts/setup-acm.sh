#!/usr/bin/env bash
# setup-acm.sh — Install ACM operator and create MultiClusterHub on the hub cluster.
#
# Prerequisites:
#   - Logged in as cluster-admin on the hub cluster
#   - oc CLI available
#
# Usage:
#   ./scripts/setup-acm.sh
#
# This script:
#   1. Creates the open-cluster-management namespace
#   2. Creates the OperatorGroup
#   3. Applies the ACM operator Subscription
#   4. Waits for the operator CSV to reach Succeeded phase
#   5. Creates the MultiClusterHub CR
#   6. Waits for the hub to reach Running phase

set -euo pipefail

NAMESPACE="open-cluster-management"
MANIFESTS_DIR="$(cd "$(dirname "$0")/../manifests" && pwd)"
TIMEOUT=600  # 10 minutes

echo "=== ACM Setup Script ==="
echo ""

# Check we are logged in as cluster-admin
if ! oc whoami &>/dev/null; then
  echo "ERROR: Not logged in to an OpenShift cluster. Run 'oc login' first."
  exit 1
fi

CURRENT_USER=$(oc whoami)
echo "Logged in as: ${CURRENT_USER}"
echo ""

# Step 1: Create namespace
echo "[1/5] Creating namespace ${NAMESPACE}..."
oc create namespace "${NAMESPACE}" --dry-run=client -o yaml | oc apply -f -
echo ""

# Step 2: Create OperatorGroup
echo "[2/5] Creating OperatorGroup..."
cat <<EOF | oc apply -f -
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: open-cluster-management
  namespace: ${NAMESPACE}
spec:
  targetNamespaces:
    - ${NAMESPACE}
EOF
echo ""

# Step 3: Apply the operator subscription
echo "[3/5] Applying ACM operator Subscription..."
oc apply -f "${MANIFESTS_DIR}/acm-operator-subscription.yaml"
echo ""

# Step 4: Wait for the CSV to succeed
echo "[4/5] Waiting for ACM operator to install (timeout: ${TIMEOUT}s)..."
SECONDS=0
while true; do
  CSV_PHASE=$(oc get csv -n "${NAMESPACE}" -o jsonpath='{.items[?(@.spec.displayName=="Advanced Cluster Management for Kubernetes")].status.phase}' 2>/dev/null || echo "")
  if [[ "${CSV_PHASE}" == "Succeeded" ]]; then
    echo "  ACM operator installed successfully."
    break
  fi
  if (( SECONDS > TIMEOUT )); then
    echo "ERROR: Timed out waiting for ACM operator to install."
    echo "  Current CSV phase: ${CSV_PHASE:-not found}"
    echo "  Check: oc get csv -n ${NAMESPACE}"
    exit 1
  fi
  echo "  Waiting... (${SECONDS}s elapsed, CSV phase: ${CSV_PHASE:-pending})"
  sleep 15
done
echo ""

# Step 5: Create MultiClusterHub
echo "[5/5] Creating MultiClusterHub..."
oc apply -f "${MANIFESTS_DIR}/multiclusterhub.yaml"
echo ""

echo "MultiClusterHub is deploying. This takes 10-15 minutes."
echo "Monitor progress with:"
echo "  oc get multiclusterhub -n ${NAMESPACE} -w"
echo "  oc get pods -n ${NAMESPACE} --watch"
echo ""
echo "Wait for status.phase to reach 'Running' before proceeding."
