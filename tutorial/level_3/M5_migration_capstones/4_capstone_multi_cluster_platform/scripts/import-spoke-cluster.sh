#!/usr/bin/env bash
#
# import-spoke-cluster.sh
# Automates the process of importing a spoke cluster into the RHACM hub.
#
# Usage: ./import-spoke-cluster.sh <cluster-name> <api-url> <admin-user>
# Example: ./import-spoke-cluster.sh production-east https://api.production-east.example.com:6443 admin
#
# Prerequisites:
#   - Logged in to the hub cluster via oc
#   - ManagedCluster resource already created on the hub
#   - Access credentials for the spoke cluster
#
# This script:
#   1. Extracts import manifests from the hub
#   2. Logs in to the spoke cluster
#   3. Applies the klusterlet CRDs and import manifests
#   4. Returns to the hub context
#   5. Waits for the cluster to join
#
set -euo pipefail

CLUSTER_NAME="${1:?Usage: $0 <cluster-name> <api-url> <admin-user>}"
API_URL="${2:?Usage: $0 <cluster-name> <api-url> <admin-user>}"
ADMIN_USER="${3:?Usage: $0 <cluster-name> <api-url> <admin-user>}"

TIMEOUT=300
POLL_INTERVAL=10
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

echo "=== Importing spoke cluster: ${CLUSTER_NAME} ==="
echo "    API URL: ${API_URL}"
echo "    Admin user: ${ADMIN_USER}"
echo ""

# Save hub context
HUB_CONTEXT=$(oc config current-context)
echo "[1/6] Saved hub context: ${HUB_CONTEXT}"

# Wait for the import secret to be created by RHACM
echo "[2/6] Waiting for import secret to be generated..."
SECONDS=0
until oc get secret "${CLUSTER_NAME}-import" -n "${CLUSTER_NAME}" &>/dev/null; do
  if (( SECONDS >= TIMEOUT )); then
    echo "ERROR: Timed out waiting for import secret. Ensure ManagedCluster '${CLUSTER_NAME}' exists."
    exit 1
  fi
  sleep "${POLL_INTERVAL}"
done
echo "       Import secret found."

# Extract import manifests
echo "[3/6] Extracting import manifests..."
oc get secret "${CLUSTER_NAME}-import" -n "${CLUSTER_NAME}" \
  -o jsonpath='{.data.crds\.yaml}' | base64 -d > "${TMPDIR}/crds.yaml"
oc get secret "${CLUSTER_NAME}-import" -n "${CLUSTER_NAME}" \
  -o jsonpath='{.data.import\.yaml}' | base64 -d > "${TMPDIR}/import.yaml"
echo "       CRDs: $(wc -l < "${TMPDIR}/crds.yaml") lines"
echo "       Import: $(wc -l < "${TMPDIR}/import.yaml") lines"

# Log in to spoke cluster
echo "[4/6] Logging in to spoke cluster..."
echo "       Enter password for ${ADMIN_USER}@${API_URL}:"
oc login -u "${ADMIN_USER}" "${API_URL}"

# Apply klusterlet manifests on spoke
echo "[5/6] Applying klusterlet CRDs and import manifests on spoke..."
oc apply -f "${TMPDIR}/crds.yaml"
echo "       CRDs applied. Waiting 10s for CRD registration..."
sleep 10
oc apply -f "${TMPDIR}/import.yaml"
echo "       Import manifests applied."

# Switch back to hub context
echo "[6/6] Switching back to hub context and verifying join..."
oc config use-context "${HUB_CONTEXT}"

SECONDS=0
until oc get managedcluster "${CLUSTER_NAME}" -o jsonpath='{.status.conditions[?(@.type=="ManagedClusterJoined")].status}' 2>/dev/null | grep -q "True"; do
  if (( SECONDS >= TIMEOUT )); then
    echo "WARNING: Timed out waiting for cluster to join. It may still be initializing."
    echo "         Check status with: oc get managedcluster ${CLUSTER_NAME}"
    exit 1
  fi
  printf "."
  sleep "${POLL_INTERVAL}"
done
echo ""

echo "=== Cluster ${CLUSTER_NAME} successfully joined the hub ==="
oc get managedcluster "${CLUSTER_NAME}" \
  -o custom-columns=NAME:.metadata.name,JOINED:.status.conditions[?\(@.type==\"ManagedClusterJoined\"\)].status,AVAILABLE:.status.conditions[?\(@.type==\"ManagedClusterConditionAvailable\"\)].status
