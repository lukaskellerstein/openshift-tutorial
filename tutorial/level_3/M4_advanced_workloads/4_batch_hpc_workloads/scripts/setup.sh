#!/bin/bash
# Setup script for L3-M4.4 Batch & HPC Workloads
# Creates the project and applies foundational resources
set -euo pipefail

PROJECT_NAME="batch-hpc-demo"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFESTS_DIR="${SCRIPT_DIR}/../manifests"

echo "=== L3-M4.4 Batch & HPC Workloads Setup ==="
echo ""

# Create project
echo "[1/4] Creating project '${PROJECT_NAME}'..."
oc new-project "${PROJECT_NAME}" \
  --display-name="Batch & HPC Demo" \
  --description="Level 3 Module 4 Lesson 4 — Batch & HPC Workloads" \
  2>/dev/null || oc project "${PROJECT_NAME}"

# Apply RBAC
echo "[2/4] Applying RBAC resources..."
oc apply -f "${MANIFESTS_DIR}/batch-rbac.yaml"

# Apply resource quotas and limit ranges
echo "[3/4] Applying resource quotas and limit ranges..."
oc apply -f "${MANIFESTS_DIR}/resource-quota-batch.yaml"

# Apply priority classes (cluster-scoped, needs cluster-admin)
echo "[4/4] Applying priority classes..."
if oc auth can-i create priorityclasses --all-namespaces 2>/dev/null; then
  oc apply -f "${MANIFESTS_DIR}/priority-classes.yaml"
  echo "  Priority classes created."
else
  echo "  WARNING: Insufficient permissions for PriorityClasses."
  echo "  Log in as cluster-admin: oc login -u kubeadmin"
  echo "  Then run: oc apply -f ${MANIFESTS_DIR}/priority-classes.yaml"
fi

echo ""
echo "=== Setup complete ==="
echo "Project: ${PROJECT_NAME}"
echo ""
echo "To verify:"
echo "  oc get sa batch-sa"
echo "  oc get resourcequota batch-workload-quota"
echo "  oc get limitrange batch-limit-range"
echo ""
echo "Next: Run a basic Job with:"
echo "  oc apply -f ${MANIFESTS_DIR}/job-basic.yaml"
