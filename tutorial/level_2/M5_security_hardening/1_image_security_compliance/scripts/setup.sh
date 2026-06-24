#!/bin/bash
# Setup script for L2-M5.1 — Image Security & Compliance
# Creates the project and deploys initial resources

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_DIR="${SCRIPT_DIR}/../manifests"

echo "=== L2-M5.1 — Image Security & Compliance Setup ==="

# Ensure we are logged in
if ! oc whoami &>/dev/null; then
  echo "ERROR: Not logged in to OpenShift. Run: oc login -u developer -p developer https://api.crc.testing:6443"
  exit 1
fi

# Create the project
echo ""
echo "--- Creating project image-security-lab ---"
oc new-project image-security-lab 2>/dev/null || oc project image-security-lab

# Deploy UBI-based application
echo ""
echo "--- Deploying UBI demo application ---"
oc apply -f "${MANIFEST_DIR}/ubi-deployment.yaml"

# Wait for rollout
echo ""
echo "--- Waiting for UBI demo rollout ---"
oc rollout status deployment/ubi-demo --timeout=120s

# Verify non-root execution
echo ""
echo "--- Verifying non-root execution ---"
oc exec deployment/ubi-demo -- id

# Deploy Docker Hub demo (expected to fail)
echo ""
echo "--- Deploying Docker Hub demo (may fail due to SCC restrictions) ---"
oc apply -f "${MANIFEST_DIR}/dockerhub-deployment.yaml"

echo ""
echo "--- Waiting 15 seconds for Docker Hub demo pods to schedule ---"
sleep 15

echo ""
echo "--- Docker Hub demo pod status ---"
oc get pods -l app=dockerhub-demo

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Inspect UBI pod: oc exec deployment/ubi-demo -- id"
echo "  2. Check Docker Hub pod logs: oc logs deployment/dockerhub-demo"
echo "  3. Apply image policy (requires cluster-admin): oc apply -f ${MANIFEST_DIR}/image-policy.yaml"
