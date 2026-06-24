#!/bin/bash
# cleanup.sh — Remove all resources created in this lesson
# Pass --keep-operators to keep operators installed for the next lesson (L2-M3.2)
#
# Usage:
#   ./scripts/cleanup.sh                  # Remove everything
#   ./scripts/cleanup.sh --keep-operators  # Remove app and control plane, keep operators

set -euo pipefail

KEEP_OPERATORS=false
if [ "${1:-}" = "--keep-operators" ]; then
  KEEP_OPERATORS=true
  echo "Will keep operators installed (for use in later lessons)."
fi

echo "=== Cleaning up Service Mesh tutorial resources ==="

echo ""
echo "Removing application namespace..."
oc delete project mesh-demo --ignore-not-found=true 2>/dev/null || true

echo "Removing ServiceMeshControlPlane..."
oc delete smcp basic -n istio-system --ignore-not-found=true 2>/dev/null || true

echo "Waiting for control plane teardown..."
sleep 10

echo "Removing control plane namespace..."
oc delete project istio-system --ignore-not-found=true 2>/dev/null || true

if [ "$KEEP_OPERATORS" = false ]; then
  echo ""
  echo "Removing operators..."

  # Delete subscriptions
  oc delete subscription jaeger-product -n openshift-operators --ignore-not-found=true 2>/dev/null || true
  oc delete subscription kiali-ossm -n openshift-operators --ignore-not-found=true 2>/dev/null || true
  oc delete subscription servicemeshoperator -n openshift-operators --ignore-not-found=true 2>/dev/null || true

  # Delete CSVs
  for csv in $(oc get csv -n openshift-operators -o name 2>/dev/null | grep -E 'jaeger|kiali|servicemesh' || true); do
    echo "  Removing ${csv}..."
    oc delete "${csv}" -n openshift-operators --ignore-not-found=true 2>/dev/null || true
  done

  echo "Operators removed."
else
  echo ""
  echo "Operators kept installed. They are ready for the next lesson."
fi

echo ""
echo "=== Cleanup complete ==="
