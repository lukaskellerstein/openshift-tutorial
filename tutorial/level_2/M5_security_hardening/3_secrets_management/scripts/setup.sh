#!/bin/bash
# Setup script for L2-M5.3 — Secrets Management
# This script installs prerequisites and creates the lab project.

set -euo pipefail

NAMESPACE="secrets-management-lab"
SEALED_SECRETS_VERSION="v0.24.5"

echo "=== L2-M5.3 Secrets Management — Setup ==="

# Step 1: Create the project
echo "[1/4] Creating project ${NAMESPACE}..."
oc new-project "${NAMESPACE}" --display-name="Secrets Management Lab" 2>/dev/null || \
  oc project "${NAMESPACE}"

# Step 2: Install the Sealed Secrets controller
echo "[2/4] Installing Sealed Secrets controller (${SEALED_SECRETS_VERSION})..."
oc apply -f "https://github.com/bitnami-labs/sealed-secrets/releases/download/${SEALED_SECRETS_VERSION}/controller.yaml"

echo "    Waiting for Sealed Secrets controller to be ready..."
oc rollout status deployment/sealed-secrets-controller -n kube-system --timeout=120s

# Step 3: Install the External Secrets Operator via OLM
echo "[3/4] Installing External Secrets Operator..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
oc apply -f "${SCRIPT_DIR}/../manifests/eso-subscription.yaml"

echo "    Waiting for ESO operator to install (this may take 2-3 minutes)..."
timeout 180 bash -c '
  while true; do
    phase=$(oc get csv -n openshift-operators -o jsonpath="{.items[?(@.metadata.name==\"external-secrets-operator\")].status.phase}" 2>/dev/null || echo "")
    if [ "$phase" = "Succeeded" ]; then
      echo "    External Secrets Operator installed successfully."
      break
    fi
    echo "    Waiting... (current phase: ${phase:-Pending})"
    sleep 10
  done
' || echo "    WARNING: ESO install timed out. Check: oc get csv -n openshift-operators"

# Step 4: Verify installations
echo "[4/4] Verifying installations..."
echo "    Sealed Secrets controller:"
oc get pods -n kube-system -l name=sealed-secrets-controller --no-headers
echo "    External Secrets Operator:"
oc get csv -n openshift-operators --no-headers 2>/dev/null | grep external-secrets || echo "    (not yet available)"

echo ""
echo "=== Setup complete ==="
echo "Next: Follow the README.md steps to create SealedSecrets and ExternalSecrets."
