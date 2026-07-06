#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${1:-shopinsights}"

echo "=== Setting up GitHub Actions deploy credentials in namespace: ${NAMESPACE} ==="
echo ""

# Create the ServiceAccount, Role, RoleBinding, and token Secret
oc apply -f manifests/deploy-sa.yaml -n "${NAMESPACE}"
oc apply -f manifests/deploy-role.yaml -n "${NAMESPACE}"
oc apply -f manifests/deploy-rolebinding.yaml -n "${NAMESPACE}"
oc apply -f manifests/deploy-sa-token.yaml -n "${NAMESPACE}"

# Wait for the token to be populated
echo ""
echo "Waiting for token to be generated..."
for i in $(seq 1 30); do
  TOKEN=$(oc get secret github-actions-deployer-token -n "${NAMESPACE}" \
    -o jsonpath='{.data.token}' 2>/dev/null | base64 -d 2>/dev/null || true)
  if [ -n "${TOKEN}" ]; then
    break
  fi
  sleep 1
done

if [ -z "${TOKEN}" ]; then
  echo "ERROR: Token was not generated within 30 seconds."
  exit 1
fi

SERVER=$(oc whoami --show-server)

echo ""
echo "========================================"
echo "  GitHub Repository Secrets to Configure"
echo "========================================"
echo ""
echo "Go to: https://github.com/<your-username>/<your-repo>/settings/secrets/actions"
echo ""
echo "Create these secrets:"
echo ""
echo "  OPENSHIFT_SERVER    = ${SERVER}"
echo "  OPENSHIFT_TOKEN     = ${TOKEN}"
echo "  OPENSHIFT_NAMESPACE = ${NAMESPACE}"
echo "  GHCR_USERNAME       = <your GitHub username>"
echo "  GHCR_TOKEN          = <your GitHub PAT with write:packages scope>"
echo ""
echo "========================================"
