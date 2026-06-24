#!/bin/bash
# Cleanup script for the Capstone: Production-Ready Microservices lesson.
# Removes all resources created during the lesson.

set -euo pipefail

NAMESPACE="capstone-microservices"

echo "============================================"
echo "  Cleanup: Production-Ready Microservices"
echo "============================================"
echo ""
echo "This will delete the entire ${NAMESPACE} project and all its resources."
echo "Continue? (y/N)"
read -r response

if [[ ! "$response" =~ ^[yY]$ ]]; then
  echo "Cleanup cancelled."
  exit 0
fi

echo ""
echo "[1/3] Removing ArgoCD Application..."
oc delete application capstone-microservices -n openshift-gitops --ignore-not-found=true 2>/dev/null || true
echo "  Done."

echo ""
echo "[2/3] Removing Service Mesh membership..."
oc delete servicemeshmember default -n "${NAMESPACE}" --ignore-not-found=true 2>/dev/null || true
echo "  Done."

echo ""
echo "[3/3] Deleting project ${NAMESPACE}..."
oc delete project "${NAMESPACE}" --wait=true
echo "  Done."

echo ""
echo "============================================"
echo "  Cleanup Complete"
echo "============================================"
echo ""
echo "All resources in ${NAMESPACE} have been removed."
echo "Operators (Pipelines, GitOps, Service Mesh) are still installed."
echo ""
