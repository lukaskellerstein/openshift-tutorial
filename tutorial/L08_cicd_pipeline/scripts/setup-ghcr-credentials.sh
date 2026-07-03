#!/usr/bin/env bash
# Setup script for GitHub Container Registry credentials
# Creates a dockerconfigjson secret and links it to the pipeline ServiceAccount
#
# Usage:
#   chmod +x scripts/setup-ghcr-credentials.sh
#   ./scripts/setup-ghcr-credentials.sh

set -euo pipefail

NAMESPACE="${NAMESPACE:-shopinsights}"
SECRET_NAME="ghcr-credentials"
SA_NAME="shopinsights-pipeline"

echo "=== GHCR Credentials Setup ==="
echo "Namespace: ${NAMESPACE}"
echo ""

# Prompt for GitHub username
read -rp "GitHub username: " GITHUB_USER
if [ -z "${GITHUB_USER}" ]; then
  echo "Error: GitHub username cannot be empty"
  exit 1
fi

# Prompt for Personal Access Token (PAT)
echo "Enter a GitHub PAT with 'write:packages' scope."
echo "Create one at: https://github.com/settings/tokens/new?scopes=write:packages"
read -rsp "GitHub PAT: " GITHUB_PAT
echo ""

if [ -z "${GITHUB_PAT}" ]; then
  echo "Error: GitHub PAT cannot be empty"
  exit 1
fi

# Check if logged into OpenShift
if ! oc whoami &>/dev/null; then
  echo "Error: Not logged into OpenShift. Run 'oc login' first."
  exit 1
fi

# Switch to the target namespace
echo ""
echo "Switching to project ${NAMESPACE}..."
oc project "${NAMESPACE}" 2>/dev/null || {
  echo "Error: Project '${NAMESPACE}' does not exist. Create it with: oc new-project ${NAMESPACE}"
  exit 1
}

# Delete existing secret if it exists
if oc get secret "${SECRET_NAME}" -n "${NAMESPACE}" &>/dev/null; then
  echo "Deleting existing secret '${SECRET_NAME}'..."
  oc delete secret "${SECRET_NAME}" -n "${NAMESPACE}"
fi

# Create the dockerconfigjson secret
echo "Creating secret '${SECRET_NAME}'..."
oc create secret docker-registry "${SECRET_NAME}" \
  --docker-server=ghcr.io \
  --docker-username="${GITHUB_USER}" \
  --docker-password="${GITHUB_PAT}" \
  -n "${NAMESPACE}"

# Add labels for cleanup
oc label secret "${SECRET_NAME}" \
  app=shopinsights \
  tutorial=personalized \
  lesson=08 \
  -n "${NAMESPACE}"

# Annotate for Tekton — tells Tekton this secret is for ghcr.io
oc annotate secret "${SECRET_NAME}" \
  "tekton.dev/docker-0=https://ghcr.io" \
  -n "${NAMESPACE}"

# Create the ServiceAccount if it does not exist
if ! oc get sa "${SA_NAME}" -n "${NAMESPACE}" &>/dev/null; then
  echo "Creating ServiceAccount '${SA_NAME}'..."
  oc apply -f manifests/pipeline-sa.yaml -n "${NAMESPACE}"
fi

# Link the secret to the ServiceAccount
echo "Linking secret to ServiceAccount '${SA_NAME}'..."
oc secrets link "${SA_NAME}" "${SECRET_NAME}" -n "${NAMESPACE}"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Verify with:"
echo "  oc get secret ${SECRET_NAME} -n ${NAMESPACE}"
echo "  oc get sa ${SA_NAME} -n ${NAMESPACE} -o yaml | grep -A5 secrets"
echo ""
echo "Test GHCR access:"
echo "  oc create -f manifests/pipelinerun.yaml"
