#!/bin/bash
# teardown.sh -- Remove all RHOAI resources created by this lesson
# Usage: ./scripts/teardown.sh [--full]
#
# Without --full: removes only the ds-project and lesson resources
# With --full: also removes RHOAI operator, GPU operator, and Serverless operator

set -euo pipefail

FULL_CLEANUP=false

for arg in "$@"; do
  case $arg in
    --full)
      FULL_CLEANUP=true
      shift
      ;;
  esac
done

echo "================================================"
echo "  OpenShift AI (RHOAI) Teardown"
echo "================================================"
echo ""

# Step 1: Remove the data science project
echo "[1/4] Removing data science project..."
oc delete namespace ds-project --wait=false 2>/dev/null || echo "  ds-project not found (already removed)"

if [ "$FULL_CLEANUP" = false ]; then
  echo ""
  echo "Project-level cleanup complete."
  echo "Run with --full to also remove operators."
  exit 0
fi

# Step 2: Remove DataScienceCluster
echo ""
echo "[2/4] Removing DataScienceCluster..."
oc delete datasciencecluster default-dsc --wait=false 2>/dev/null || echo "  DataScienceCluster not found"

echo "  Waiting for RHOAI components to terminate..."
sleep 10

# Step 3: Remove GPU Operator stack
echo ""
echo "[3/4] Removing GPU Operator stack..."
oc delete clusterpolicy gpu-cluster-policy 2>/dev/null || echo "  ClusterPolicy not found"
oc delete nodefeaturediscovery nfd-instance -n openshift-nfd 2>/dev/null || echo "  NFD instance not found"

# Remove GPU Operator subscription and CSV
GPU_CSV=$(oc get csv -n nvidia-gpu-operator 2>/dev/null | grep gpu-operator-certified | awk '{print $1}' || true)
if [ -n "$GPU_CSV" ]; then
  oc delete csv "$GPU_CSV" -n nvidia-gpu-operator 2>/dev/null || true
fi
oc delete subscription gpu-operator-certified -n nvidia-gpu-operator 2>/dev/null || true
oc delete namespace nvidia-gpu-operator --wait=false 2>/dev/null || true

# Remove NFD subscription and CSV
NFD_CSV=$(oc get csv -n openshift-nfd 2>/dev/null | grep nfd | awk '{print $1}' || true)
if [ -n "$NFD_CSV" ]; then
  oc delete csv "$NFD_CSV" -n openshift-nfd 2>/dev/null || true
fi
oc delete subscription nfd -n openshift-nfd 2>/dev/null || true
oc delete namespace openshift-nfd --wait=false 2>/dev/null || true

# Step 4: Remove RHOAI and Serverless operators
echo ""
echo "[4/4] Removing RHOAI and Serverless operators..."

# RHOAI operator
RHOAI_CSV=$(oc get csv -n redhat-ods-operator 2>/dev/null | grep rhods-operator | awk '{print $1}' || true)
if [ -n "$RHOAI_CSV" ]; then
  oc delete csv "$RHOAI_CSV" -n redhat-ods-operator 2>/dev/null || true
fi
oc delete subscription rhods-operator -n redhat-ods-operator 2>/dev/null || true
oc delete namespace redhat-ods-operator --wait=false 2>/dev/null || true
oc delete namespace redhat-ods-applications --wait=false 2>/dev/null || true
oc delete namespace redhat-ods-monitoring --wait=false 2>/dev/null || true

# Serverless operator
SERVERLESS_CSV=$(oc get csv -n openshift-serverless-operator 2>/dev/null | grep serverless-operator | awk '{print $1}' || true)
if [ -n "$SERVERLESS_CSV" ]; then
  oc delete csv "$SERVERLESS_CSV" -n openshift-serverless-operator 2>/dev/null || true
fi
oc delete subscription serverless-operator -n openshift-serverless-operator 2>/dev/null || true
oc delete namespace openshift-serverless-operator --wait=false 2>/dev/null || true

echo ""
echo "================================================"
echo "  Teardown complete!"
echo "================================================"
echo ""
echo "Note: CRDs may still remain. To remove them:"
echo "  oc get crd | grep -E 'opendatahub|kserve|datasciencecluster' | awk '{print \$1}' | xargs oc delete crd"
echo ""
echo "Some namespaces may take a few minutes to fully terminate."
echo "Check with: oc get namespaces | grep -E 'Terminating'"
