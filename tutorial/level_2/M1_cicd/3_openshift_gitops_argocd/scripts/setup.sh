#!/bin/bash
# Setup script for L2-M1.3 — OpenShift GitOps (ArgoCD)
# Installs the OpenShift GitOps operator and waits for it to be ready
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFESTS_DIR="${SCRIPT_DIR}/../manifests"

echo "=== L2-M1.3 Setup: OpenShift GitOps (ArgoCD) ==="

# Step 1: Verify cluster access
echo ""
echo "--- Checking cluster access ---"
if ! oc whoami &>/dev/null; then
  echo "ERROR: Not logged in to OpenShift. Run: oc login -u kubeadmin <password> https://api.crc.testing:6443"
  exit 1
fi

CURRENT_USER=$(oc whoami)
echo "Logged in as: ${CURRENT_USER}"

# Installing the operator requires cluster-admin
if [[ "${CURRENT_USER}" != "kubeadmin" ]]; then
  echo "WARNING: You are not logged in as kubeadmin. Operator installation requires cluster-admin privileges."
  echo "Run: oc login -u kubeadmin -p <password> https://api.crc.testing:6443"
  exit 1
fi

# Step 2: Install the OpenShift GitOps operator
echo ""
echo "--- Installing OpenShift GitOps operator ---"
if oc get subscription openshift-gitops-operator -n openshift-operators &>/dev/null; then
  echo "OpenShift GitOps operator subscription already exists. Skipping install."
else
  oc apply -f "${MANIFESTS_DIR}/gitops-subscription.yaml"
  echo "Subscription created. Waiting for operator to install..."
fi

# Step 3: Wait for the operator CSV to succeed
echo ""
echo "--- Waiting for operator to be ready (this may take 2-3 minutes) ---"
TIMEOUT=180
ELAPSED=0
while [[ ${ELAPSED} -lt ${TIMEOUT} ]]; do
  CSV=$(oc get csv -n openshift-gitops -l operators.coreos.com/openshift-gitops-operator.openshift-operators -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "Pending")
  if [[ "${CSV}" == "Succeeded" ]]; then
    echo "Operator installed successfully."
    break
  fi
  echo "  Status: ${CSV} (${ELAPSED}s / ${TIMEOUT}s)"
  sleep 10
  ELAPSED=$((ELAPSED + 10))
done

if [[ ${ELAPSED} -ge ${TIMEOUT} ]]; then
  echo "ERROR: Timeout waiting for operator. Check: oc get csv -n openshift-gitops"
  exit 1
fi

# Step 4: Wait for ArgoCD server to be ready
echo ""
echo "--- Waiting for ArgoCD server deployment ---"
oc rollout status deployment/openshift-gitops-server -n openshift-gitops --timeout=120s

# Step 5: Create the demo namespace
echo ""
echo "--- Creating gitops-demo namespace ---"
oc apply -f "${MANIFESTS_DIR}/gitops-demo-namespace.yaml"

# Step 6: Grant ArgoCD permissions on the demo namespace
echo ""
echo "--- Granting ArgoCD permissions ---"
oc apply -f "${MANIFESTS_DIR}/argocd-rbac-rolebinding.yaml"

# Step 7: Print ArgoCD access info
echo ""
echo "=== Setup Complete ==="
echo ""
ARGOCD_ROUTE=$(oc get route openshift-gitops-server -n openshift-gitops -o jsonpath='{.spec.host}' 2>/dev/null || echo "not-found")
echo "ArgoCD Web UI: https://${ARGOCD_ROUTE}"
echo ""
echo "To get the admin password:"
echo "  oc extract secret/openshift-gitops-cluster -n openshift-gitops --to=- --keys=admin.password 2>/dev/null"
echo ""
echo "You can also log in via the OpenShift OAuth integration in the Web Console."
echo ""
