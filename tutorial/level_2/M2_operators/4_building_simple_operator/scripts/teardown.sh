#!/bin/bash
# teardown.sh — Remove all resources created in this lesson
#
# Usage:
#   ./teardown.sh

set -euo pipefail

PROJECT_DIR="${HOME}/webapp-operator"

echo "=== WebApp Operator Teardown ==="

# Delete WebApp CRs in the demo project
echo "--- Deleting WebApp custom resources ---"
oc delete webapp --all -n webapp-demo 2>/dev/null || true

# Undeploy the operator (CRD, RBAC, Deployment)
if [ -d "$PROJECT_DIR" ]; then
  echo "--- Undeploying operator ---"
  cd "$PROJECT_DIR"
  make undeploy 2>/dev/null || true
fi

# Clean up OLM bundle if installed
echo "--- Cleaning up OLM resources ---"
operator-sdk cleanup webapp-operator -n webapp-operator-system 2>/dev/null || true

# Delete projects
echo "--- Deleting projects ---"
oc delete project webapp-demo 2>/dev/null || true
oc delete project webapp-operator-system 2>/dev/null || true

# Remove CRD (in case make undeploy missed it)
echo "--- Removing CRD ---"
oc delete crd webapps.tutorial.openshift.io 2>/dev/null || true

# Optionally remove the local project directory
read -p "Remove local project directory ${PROJECT_DIR}? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
  rm -rf "$PROJECT_DIR"
  echo "Removed ${PROJECT_DIR}"
else
  echo "Kept ${PROJECT_DIR}"
fi

echo ""
echo "=== Teardown complete ==="
