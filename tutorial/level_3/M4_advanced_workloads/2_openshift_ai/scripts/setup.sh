#!/bin/bash
# setup.sh -- Install RHOAI and all dependencies
# Usage: ./scripts/setup.sh [--with-gpu]
#
# This script installs:
#   1. OpenShift Serverless Operator (dependency for KServe)
#   2. RHOAI Operator
#   3. DataScienceCluster CR
#   4. (Optional) NFD + NVIDIA GPU Operator
#
# Prerequisites:
#   - Logged in as cluster-admin: oc whoami should return kubeadmin or similar
#   - Sufficient cluster resources (16+ GB RAM on worker nodes)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFESTS_DIR="${SCRIPT_DIR}/../manifests"
WITH_GPU=false

# Parse arguments
for arg in "$@"; do
  case $arg in
    --with-gpu)
      WITH_GPU=true
      shift
      ;;
  esac
done

echo "================================================"
echo "  OpenShift AI (RHOAI) Setup"
echo "================================================"
echo ""

# Verify cluster-admin access
echo "[1/6] Verifying cluster-admin access..."
if ! oc whoami &>/dev/null; then
  echo "ERROR: Not logged in to OpenShift. Run: oc login -u kubeadmin ..."
  exit 1
fi

CURRENT_USER=$(oc whoami)
echo "  Logged in as: ${CURRENT_USER}"

# Check if user has cluster-admin
if ! oc auth can-i create namespace --all-namespaces &>/dev/null; then
  echo "ERROR: Current user does not have cluster-admin privileges."
  echo "  Run: oc login -u kubeadmin -p <password> <api-url>"
  exit 1
fi

# Step 1: Create RHOAI operator namespace
echo ""
echo "[2/6] Creating namespaces and installing Serverless Operator..."
oc apply -f "${MANIFESTS_DIR}/namespace-redhat-ods-operator.yaml"
oc apply -f "${MANIFESTS_DIR}/serverless-operator-subscription.yaml"

echo "  Waiting for Serverless Operator CSV to succeed..."
for i in $(seq 1 60); do
  CSV=$(oc get csv -n openshift-serverless-operator 2>/dev/null | grep serverless-operator | awk '{print $1}' || true)
  if [ -n "$CSV" ]; then
    PHASE=$(oc get csv "$CSV" -n openshift-serverless-operator -o jsonpath='{.status.phase}' 2>/dev/null || true)
    if [ "$PHASE" = "Succeeded" ]; then
      echo "  Serverless Operator installed successfully."
      break
    fi
  fi
  if [ "$i" -eq 60 ]; then
    echo "  WARNING: Serverless Operator not ready after 5 minutes. Continuing..."
  fi
  sleep 5
done

# Step 2: Install RHOAI Operator
echo ""
echo "[3/6] Installing RHOAI Operator..."
oc apply -f "${MANIFESTS_DIR}/rhoai-operator-subscription.yaml"

echo "  Waiting for RHOAI Operator CSV to succeed..."
for i in $(seq 1 60); do
  CSV=$(oc get csv -n redhat-ods-operator 2>/dev/null | grep rhods-operator | awk '{print $1}' || true)
  if [ -n "$CSV" ]; then
    PHASE=$(oc get csv "$CSV" -n redhat-ods-operator -o jsonpath='{.status.phase}' 2>/dev/null || true)
    if [ "$PHASE" = "Succeeded" ]; then
      echo "  RHOAI Operator installed successfully."
      break
    fi
  fi
  if [ "$i" -eq 60 ]; then
    echo "  WARNING: RHOAI Operator not ready after 5 minutes. Continuing..."
  fi
  sleep 5
done

# Step 3: Create DataScienceCluster
echo ""
echo "[4/6] Creating DataScienceCluster..."
oc apply -f "${MANIFESTS_DIR}/datasciencecluster.yaml"

echo "  Waiting for DataScienceCluster to be ready..."
for i in $(seq 1 120); do
  READY=$(oc get datasciencecluster default-dsc -o jsonpath='{.status.phase}' 2>/dev/null || true)
  if [ "$READY" = "Ready" ]; then
    echo "  DataScienceCluster is ready."
    break
  fi
  if [ "$i" -eq 120 ]; then
    echo "  WARNING: DataScienceCluster not ready after 10 minutes."
    echo "  Check status: oc get datasciencecluster default-dsc -o yaml"
  fi
  sleep 5
done

# Step 4: GPU Operator (optional)
if [ "$WITH_GPU" = true ]; then
  echo ""
  echo "[5/6] Installing GPU Operator stack..."

  echo "  Installing Node Feature Discovery..."
  oc apply -f "${MANIFESTS_DIR}/nfd-operator-subscription.yaml"

  echo "  Waiting for NFD Operator..."
  for i in $(seq 1 60); do
    if oc get deployment nfd-controller-manager -n openshift-nfd &>/dev/null; then
      AVAILABLE=$(oc get deployment nfd-controller-manager -n openshift-nfd -o jsonpath='{.status.availableReplicas}' 2>/dev/null || echo "0")
      if [ "$AVAILABLE" -ge 1 ] 2>/dev/null; then
        echo "  NFD Operator ready."
        break
      fi
    fi
    if [ "$i" -eq 60 ]; then
      echo "  WARNING: NFD Operator not ready after 5 minutes."
    fi
    sleep 5
  done

  echo "  Creating NFD instance..."
  oc apply -f "${MANIFESTS_DIR}/nfd-instance.yaml"

  echo "  Installing NVIDIA GPU Operator..."
  oc apply -f "${MANIFESTS_DIR}/gpu-operator-subscription.yaml"

  echo "  Waiting for GPU Operator..."
  for i in $(seq 1 60); do
    CSV=$(oc get csv -n nvidia-gpu-operator 2>/dev/null | grep gpu-operator-certified | awk '{print $1}' || true)
    if [ -n "$CSV" ]; then
      PHASE=$(oc get csv "$CSV" -n nvidia-gpu-operator -o jsonpath='{.status.phase}' 2>/dev/null || true)
      if [ "$PHASE" = "Succeeded" ]; then
        echo "  GPU Operator installed."
        break
      fi
    fi
    if [ "$i" -eq 60 ]; then
      echo "  WARNING: GPU Operator not ready after 5 minutes."
    fi
    sleep 5
  done

  echo "  Creating ClusterPolicy..."
  oc apply -f "${MANIFESTS_DIR}/gpu-clusterpolicy.yaml"

  echo "  GPU alerts..."
  oc apply -f "${MANIFESTS_DIR}/gpu-prometheus-rules.yaml"
else
  echo ""
  echo "[5/6] Skipping GPU Operator (use --with-gpu to install)"
fi

# Step 5: Create data science project and workloads
echo ""
echo "[6/6] Creating data science project and workloads..."
oc apply -f "${MANIFESTS_DIR}/ds-project.yaml"
oc apply -f "${MANIFESTS_DIR}/notebook-pvc.yaml"
oc apply -f "${MANIFESTS_DIR}/data-connection-secret.yaml"
oc apply -f "${MANIFESTS_DIR}/workbench.yaml"
oc apply -f "${MANIFESTS_DIR}/kserve-serving-runtime.yaml"
oc apply -f "${MANIFESTS_DIR}/kserve-inference-service.yaml"
oc apply -f "${MANIFESTS_DIR}/modelmesh-serving-runtime.yaml"
oc apply -f "${MANIFESTS_DIR}/modelmesh-inference-service.yaml"
oc apply -f "${MANIFESTS_DIR}/dspa.yaml"
oc apply -f "${MANIFESTS_DIR}/rhoai-servicemonitor.yaml"

echo ""
echo "================================================"
echo "  Setup complete!"
echo "================================================"
echo ""
echo "RHOAI Dashboard:"
DASHBOARD_URL=$(oc get route rhods-dashboard -n redhat-ods-applications -o jsonpath='{.spec.host}' 2>/dev/null || echo "<pending>")
echo "  https://${DASHBOARD_URL}"
echo ""
echo "Next steps:"
echo "  1. Access the RHOAI Dashboard in your browser"
echo "  2. Navigate to Data Science Projects -> ds-project"
echo "  3. Verify the workbench is running"
echo "  4. Check model serving status"
echo ""
echo "Run the pipeline:"
echo "  oc apply -f ${MANIFESTS_DIR}/sample-pipeline-run.yaml"
