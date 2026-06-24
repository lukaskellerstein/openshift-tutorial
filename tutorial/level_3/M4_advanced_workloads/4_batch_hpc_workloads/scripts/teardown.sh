#!/bin/bash
# Teardown script for L3-M4.4 Batch & HPC Workloads
# Removes all resources created during this lesson
set -euo pipefail

PROJECT_NAME="batch-hpc-demo"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFESTS_DIR="${SCRIPT_DIR}/../manifests"

echo "=== L3-M4.4 Batch & HPC Workloads Teardown ==="
echo ""

# Delete Kueue resources (namespace-scoped first, then cluster-scoped)
echo "[1/5] Deleting Kueue resources (if present)..."
oc delete -f "${MANIFESTS_DIR}/kueue-job.yaml" --ignore-not-found 2>/dev/null || true
oc delete -f "${MANIFESTS_DIR}/kueue-resources.yaml" --ignore-not-found 2>/dev/null || true

# Delete MPI jobs
echo "[2/5] Deleting MPI jobs (if present)..."
oc delete -f "${MANIFESTS_DIR}/mpi-job.yaml" --ignore-not-found 2>/dev/null || true

# Delete GPU jobs
echo "[3/5] Deleting GPU jobs (if present)..."
oc delete -f "${MANIFESTS_DIR}/gpu-job.yaml" --ignore-not-found 2>/dev/null || true

# Delete all batch resources by label
echo "[4/5] Deleting all labeled resources..."
oc delete all,sa,role,rolebinding,resourcequota,limitrange \
  -l tutorial-level=3,tutorial-module=M4 \
  --ignore-not-found 2>/dev/null || true

# Delete priority classes (cluster-scoped)
echo "[5/5] Deleting priority classes..."
if oc auth can-i delete priorityclasses --all-namespaces 2>/dev/null; then
  oc delete -f "${MANIFESTS_DIR}/priority-classes.yaml" --ignore-not-found 2>/dev/null || true
else
  echo "  WARNING: Insufficient permissions. Log in as cluster-admin to delete PriorityClasses."
fi

# Delete project
echo ""
read -p "Delete project '${PROJECT_NAME}'? (y/N) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
  oc delete project "${PROJECT_NAME}" --ignore-not-found
  echo "Project deleted."
else
  echo "Project retained."
fi

echo ""
echo "=== Teardown complete ==="
