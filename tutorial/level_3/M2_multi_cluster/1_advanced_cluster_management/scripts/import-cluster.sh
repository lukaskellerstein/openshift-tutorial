#!/usr/bin/env bash
# import-cluster.sh — Import an existing cluster into ACM as a managed cluster.
#
# Prerequisites:
#   - ACM is installed and MultiClusterHub is Running on the hub cluster
#   - You have cluster-admin access to both the hub and the target cluster
#   - oc CLI available
#
# Usage:
#   ./scripts/import-cluster.sh <cluster-name> <hub-api-url> <spoke-api-url>
#
# Example:
#   ./scripts/import-cluster.sh spoke-cluster-1 \
#     https://api.hub.example.com:6443 \
#     https://api.spoke.example.com:6443
#
# This script:
#   1. Logs in to the hub cluster
#   2. Creates the ManagedCluster and KlusterletAddonConfig
#   3. Extracts the import manifests
#   4. Logs in to the spoke cluster
#   5. Applies the import manifests
#   6. Returns to the hub and verifies the import

set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <cluster-name> <hub-api-url> <spoke-api-url>"
  echo ""
  echo "Example:"
  echo "  $0 spoke-cluster-1 https://api.hub.example.com:6443 https://api.spoke.example.com:6443"
  exit 1
fi

CLUSTER_NAME="$1"
HUB_API="$2"
SPOKE_API="$3"
MANIFESTS_DIR="$(cd "$(dirname "$0")/../manifests" && pwd)"
TIMEOUT=300  # 5 minutes

echo "=== Cluster Import Script ==="
echo "Cluster name: ${CLUSTER_NAME}"
echo "Hub API:      ${HUB_API}"
echo "Spoke API:    ${SPOKE_API}"
echo ""

# Step 1: Ensure we are on the hub cluster
echo "[1/6] Connecting to hub cluster..."
echo "Please enter hub cluster credentials when prompted."
oc login "${HUB_API}"
echo ""

# Step 2: Create ManagedCluster resource
echo "[2/6] Creating ManagedCluster '${CLUSTER_NAME}' on hub..."
cat <<EOF | oc apply -f -
apiVersion: cluster.open-cluster-management.io/v1
kind: ManagedCluster
metadata:
  name: ${CLUSTER_NAME}
  labels:
    app: acm
    tutorial-level: "3"
    tutorial-module: "M2"
    cloud: auto-detect
    vendor: auto-detect
    environment: staging
spec:
  hubAcceptsClient: true
  leaseDurationSeconds: 60
EOF
echo ""

# Step 3: Create KlusterletAddonConfig
echo "[3/6] Creating KlusterletAddonConfig..."
cat <<EOF | oc apply -f -
apiVersion: agent.open-cluster-management.io/v1
kind: KlusterletAddonConfig
metadata:
  name: ${CLUSTER_NAME}
  namespace: ${CLUSTER_NAME}
spec:
  clusterName: ${CLUSTER_NAME}
  clusterNamespace: ${CLUSTER_NAME}
  applicationManager:
    enabled: true
  certPolicyController:
    enabled: true
  iamPolicyController:
    enabled: true
  policyController:
    enabled: true
  searchCollector:
    enabled: true
EOF
echo ""

# Step 4: Extract import manifests
echo "[4/6] Extracting import manifests..."
SECONDS=0
while true; do
  if oc get secret -n "${CLUSTER_NAME}" "${CLUSTER_NAME}-import" &>/dev/null; then
    break
  fi
  if (( SECONDS > 60 )); then
    echo "ERROR: Timed out waiting for import secret to be created."
    exit 1
  fi
  echo "  Waiting for import secret..."
  sleep 5
done

TMPDIR=$(mktemp -d)
oc get secret -n "${CLUSTER_NAME}" "${CLUSTER_NAME}-import" \
  -o jsonpath='{.data.crds\.yaml}' | base64 -d > "${TMPDIR}/klusterlet-crds.yaml"
oc get secret -n "${CLUSTER_NAME}" "${CLUSTER_NAME}-import" \
  -o jsonpath='{.data.import\.yaml}' | base64 -d > "${TMPDIR}/klusterlet-import.yaml"
echo "  Import manifests saved to ${TMPDIR}/"
echo ""

# Step 5: Apply import manifests on the spoke cluster
echo "[5/6] Connecting to spoke cluster and applying import manifests..."
echo "Please enter spoke cluster credentials when prompted."
oc login "${SPOKE_API}"
oc apply -f "${TMPDIR}/klusterlet-crds.yaml"
oc apply -f "${TMPDIR}/klusterlet-import.yaml"
echo ""

# Step 6: Return to hub and verify
echo "[6/6] Returning to hub cluster and verifying import..."
oc login "${HUB_API}"

echo "Waiting for managed cluster to become available (timeout: ${TIMEOUT}s)..."
SECONDS=0
while true; do
  AVAILABLE=$(oc get managedcluster "${CLUSTER_NAME}" \
    -o jsonpath='{.status.conditions[?(@.type=="ManagedClusterConditionAvailable")].status}' 2>/dev/null || echo "")
  if [[ "${AVAILABLE}" == "True" ]]; then
    echo ""
    echo "Cluster '${CLUSTER_NAME}' imported successfully and is available."
    break
  fi
  if (( SECONDS > TIMEOUT )); then
    echo ""
    echo "WARNING: Timed out waiting for cluster to become available."
    echo "The import may still be in progress. Check with:"
    echo "  oc get managedcluster ${CLUSTER_NAME}"
    break
  fi
  echo "  Waiting... (${SECONDS}s elapsed, available: ${AVAILABLE:-unknown})"
  sleep 10
done

# Cleanup temp files
rm -rf "${TMPDIR}"

echo ""
echo "=== Import Complete ==="
oc get managedclusters
