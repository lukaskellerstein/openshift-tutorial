#!/bin/bash
# Setup script for L2-M1.4 — Pipelines + GitOps Together
# This script creates the project, installs prerequisites,
# and verifies that both operators are available.

set -euo pipefail

PROJECT="pipelines-gitops-demo"

echo "============================================"
echo " L2-M1.4 — Pipelines + GitOps Setup"
echo "============================================"

# 1. Check that oc is available and user is logged in
echo ""
echo "==> Checking oc CLI..."
if ! command -v oc &> /dev/null; then
  echo "ERROR: oc CLI not found. Install it first."
  exit 1
fi

oc whoami > /dev/null 2>&1 || {
  echo "ERROR: Not logged in. Run: oc login -u developer -p developer https://api.crc.testing:6443"
  exit 1
}
echo "    Logged in as: $(oc whoami)"

# 2. Verify OpenShift Pipelines operator is installed
echo ""
echo "==> Checking OpenShift Pipelines operator..."
if oc get csv -n openshift-pipelines 2>/dev/null | grep -q "openshift-pipelines-operator"; then
  echo "    OpenShift Pipelines operator is installed."
else
  echo "WARNING: OpenShift Pipelines operator may not be installed."
  echo "         Install it from OperatorHub or run:"
  echo "         oc apply -f https://raw.githubusercontent.com/tektoncd/operator/main/config/crs/kubernetes/config/all/operator_v1alpha1_config_cr.yaml"
fi

# 3. Verify OpenShift GitOps operator is installed
echo ""
echo "==> Checking OpenShift GitOps operator..."
if oc get csv -n openshift-gitops 2>/dev/null | grep -q "openshift-gitops-operator"; then
  echo "    OpenShift GitOps operator is installed."
else
  echo "WARNING: OpenShift GitOps operator may not be installed."
  echo "         Install it from OperatorHub (Operator: Red Hat OpenShift GitOps)."
fi

# 4. Create the project
echo ""
echo "==> Creating project: ${PROJECT}"
oc new-project "${PROJECT}" --display-name="CI/CD + GitOps Demo" 2>/dev/null || {
  echo "    Project ${PROJECT} already exists, switching to it."
  oc project "${PROJECT}"
}

# 5. Create the ImageStream
echo ""
echo "==> Creating ImageStream for demo-app..."
oc apply -f "$(dirname "$0")/../manifests/imagestream.yaml"

# 6. Grant ArgoCD access to the project
echo ""
echo "==> Granting ArgoCD access to the project..."
oc apply -f "$(dirname "$0")/../manifests/argocd-rbac-rolebinding.yaml"

# 7. Verify ClusterTasks are available
echo ""
echo "==> Checking for required ClusterTasks..."
if oc get clustertask git-clone &> /dev/null; then
  echo "    git-clone ClusterTask is available."
else
  echo "WARNING: git-clone ClusterTask not found."
  echo "         It should be installed by the OpenShift Pipelines operator."
fi

echo ""
echo "============================================"
echo " Setup complete!"
echo ""
echo " Next steps:"
echo "   1. Create two Git repos (source + GitOps)"
echo "   2. Configure git-credentials secret"
echo "   3. Follow the README.md for the full walkthrough"
echo "============================================"
