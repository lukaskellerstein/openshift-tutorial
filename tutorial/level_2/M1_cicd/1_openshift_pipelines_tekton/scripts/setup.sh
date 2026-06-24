#!/usr/bin/env bash
# Setup script for L2-M1.1 — OpenShift Pipelines (Tekton)
# Creates the project and verifies the Pipelines operator is installed
set -euo pipefail

NAMESPACE="pipelines-tutorial"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFESTS_DIR="${SCRIPT_DIR}/../manifests"

echo "=== L2-M1.1 Setup: OpenShift Pipelines (Tekton) ==="
echo ""

# Check that oc is available
if ! command -v oc &>/dev/null; then
  echo "ERROR: 'oc' CLI not found. Please install it and log in to your cluster."
  exit 1
fi

# Verify login
if ! oc whoami &>/dev/null; then
  echo "ERROR: Not logged in to OpenShift. Run 'oc login' first."
  exit 1
fi

echo "Logged in as: $(oc whoami)"
echo "Cluster: $(oc whoami --show-server)"
echo ""

# Check if the Pipelines operator is installed
echo "Checking for OpenShift Pipelines operator..."
if oc get csv -n openshift-operators 2>/dev/null | grep -q "openshift-pipelines-operator"; then
  echo "OpenShift Pipelines operator is installed."
else
  echo "OpenShift Pipelines operator is NOT installed."
  echo ""
  echo "To install it, run (as cluster-admin):"
  echo "  oc apply -f ${MANIFESTS_DIR}/subscription-pipelines-operator.yaml"
  echo ""
  echo "Or install via the Web Console:"
  echo "  1. Go to Operators > OperatorHub"
  echo "  2. Search for 'OpenShift Pipelines'"
  echo "  3. Click Install"
  echo ""
  read -rp "Would you like to install it now? (y/N) " response
  if [[ "$response" =~ ^[Yy]$ ]]; then
    echo "Installing OpenShift Pipelines operator..."
    oc apply -f "${MANIFESTS_DIR}/subscription-pipelines-operator.yaml"
    echo "Waiting for operator to be ready (this may take 2-3 minutes)..."
    sleep 30
    for i in $(seq 1 12); do
      if oc get csv -n openshift-operators 2>/dev/null | grep -q "openshift-pipelines-operator.*Succeeded"; then
        echo "Operator installed successfully!"
        break
      fi
      echo "  Still waiting... (${i}/12)"
      sleep 10
    done
  fi
fi

# Verify tkn CLI
echo ""
if command -v tkn &>/dev/null; then
  echo "tkn CLI found: $(tkn version --component client 2>/dev/null || tkn version 2>/dev/null | head -1)"
else
  echo "WARNING: 'tkn' CLI not found. It is optional but recommended."
  echo "Install it from: https://github.com/tektoncd/cli/releases"
fi

# Create the tutorial project
echo ""
echo "Creating project '${NAMESPACE}'..."
if oc get project "${NAMESPACE}" &>/dev/null; then
  echo "Project '${NAMESPACE}' already exists. Switching to it."
  oc project "${NAMESPACE}"
else
  oc new-project "${NAMESPACE}" \
    --display-name="Tekton Pipelines Tutorial" \
    --description="L2-M1.1: OpenShift Pipelines (Tekton)"
fi

echo ""
echo "=== Setup complete ==="
echo "Project: ${NAMESPACE}"
echo "You are ready to start the lesson."
