#!/bin/bash
# Teardown script for L2-M5.3 — Secrets Management
# Removes all resources created during the lesson.

set -euo pipefail

NAMESPACE="secrets-management-lab"
SEALED_SECRETS_VERSION="v0.24.5"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== L2-M5.3 Secrets Management — Teardown ==="

# Step 1: Delete lesson resources
echo "[1/4] Deleting lesson resources..."
oc delete -f "${SCRIPT_DIR}/../manifests/deployment-with-secret.yaml" --ignore-not-found -n "${NAMESPACE}"
oc delete -f "${SCRIPT_DIR}/../manifests/deployment-with-volume-secret.yaml" --ignore-not-found -n "${NAMESPACE}"
oc delete -f "${SCRIPT_DIR}/../manifests/service.yaml" --ignore-not-found -n "${NAMESPACE}"
oc delete -f "${SCRIPT_DIR}/../manifests/externalsecret-api-key.yaml" --ignore-not-found -n "${NAMESPACE}"
oc delete -f "${SCRIPT_DIR}/../manifests/secretstore-vault.yaml" --ignore-not-found -n "${NAMESPACE}"
oc delete -f "${SCRIPT_DIR}/../manifests/secretstore-aws.yaml" --ignore-not-found -n "${NAMESPACE}"
oc delete -f "${SCRIPT_DIR}/../manifests/sealedsecret-db-credentials.yaml" --ignore-not-found -n "${NAMESPACE}"

# Step 2: Delete manually created secrets
echo "[2/4] Deleting secrets..."
oc delete secret db-credentials vault-token api-credentials aws-credentials \
  -n "${NAMESPACE}" --ignore-not-found

# Step 3: Remove the Sealed Secrets controller
echo "[3/4] Removing Sealed Secrets controller..."
oc delete -f "https://github.com/bitnami-labs/sealed-secrets/releases/download/${SEALED_SECRETS_VERSION}/controller.yaml" --ignore-not-found

# Step 4: Remove the External Secrets Operator subscription (optional)
echo "[4/4] Removing External Secrets Operator subscription..."
oc delete -f "${SCRIPT_DIR}/../manifests/eso-subscription.yaml" --ignore-not-found

# Delete the project
echo "Deleting project ${NAMESPACE}..."
oc delete project "${NAMESPACE}" --ignore-not-found

echo ""
echo "=== Teardown complete ==="
