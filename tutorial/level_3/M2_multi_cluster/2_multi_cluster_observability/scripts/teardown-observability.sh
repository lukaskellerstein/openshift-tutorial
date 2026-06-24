#!/bin/bash
# teardown-observability.sh — Remove ACM Multi-Cluster Observability
#
# Removes observability components in the correct order.
# PVCs are preserved by default to prevent data loss.
#
# Usage:
#   ./scripts/teardown-observability.sh [--delete-pvcs]
#
set -euo pipefail

DELETE_PVCS=false
if [ "${1:-}" = "--delete-pvcs" ]; then
  DELETE_PVCS=true
fi

NS="open-cluster-management-observability"

echo "============================================"
echo "  ACM Observability Teardown"
echo "============================================"
echo ""

# --- Remove custom resources first ---
echo "[1/5] Removing custom alerting rules..."
oc delete -f "$(dirname "$0")/../manifests/custom-alerting-rules.yaml" \
  --ignore-not-found 2>/dev/null || true
echo ""

echo "[2/5] Removing custom metrics allowlist and dashboards..."
oc delete configmap observability-metrics-custom-allowlist \
  -n "${NS}" --ignore-not-found 2>/dev/null || true
oc delete configmap fleet-overview-dashboard \
  -n "${NS}" --ignore-not-found 2>/dev/null || true
echo ""

echo "[3/5] Removing ACM observability policy..."
oc delete -f "$(dirname "$0")/../manifests/acm-observability-policy.yaml" \
  --ignore-not-found 2>/dev/null || true
echo ""

# --- Remove the MCO CR ---
echo "[4/5] Removing MultiClusterObservability CR..."
oc delete multiclusterobservability observability --ignore-not-found
echo "  Waiting for components to terminate..."
sleep 10

# Wait for pods to terminate
TIMEOUT=120
ELAPSED=0
while [ "$(oc get pods -n "${NS}" --no-headers 2>/dev/null | wc -l | tr -d ' ')" -gt 0 ]; do
  if [ $ELAPSED -ge $TIMEOUT ]; then
    echo "  WARNING: Some pods still running after ${TIMEOUT}s"
    oc get pods -n "${NS}" --no-headers 2>/dev/null
    break
  fi
  echo "  Waiting for pods to terminate... (${ELAPSED}s)"
  sleep 10
  ELAPSED=$((ELAPSED + 10))
done
echo ""

# --- Clean up PVCs ---
if [ "${DELETE_PVCS}" = true ]; then
  echo "[5/5] Deleting PVCs (--delete-pvcs flag set)..."
  oc delete pvc --all -n "${NS}" 2>/dev/null || true
  echo "  WARNING: Metrics data has been permanently deleted."
else
  echo "[5/5] Preserving PVCs (pass --delete-pvcs to remove)"
  PVC_COUNT=$(oc get pvc -n "${NS}" --no-headers 2>/dev/null | wc -l | tr -d ' ')
  echo "  ${PVC_COUNT} PVC(s) preserved in namespace ${NS}"
fi
echo ""

# --- Remove namespace ---
echo "Removing observability namespace..."
oc delete namespace "${NS}" --ignore-not-found
echo ""

# --- Remove tutorial labels ---
echo "Cleaning up labeled resources..."
oc delete all -l tutorial-level=3,tutorial-module=M2,app=acm-observability \
  --all-namespaces --ignore-not-found 2>/dev/null || true
echo ""

echo "============================================"
echo "  Teardown Complete"
echo "============================================"
echo ""
echo "Note: Observability addons on managed clusters will be"
echo "automatically removed when the MCO CR is deleted."
echo ""
