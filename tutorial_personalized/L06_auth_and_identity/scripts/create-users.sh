#!/usr/bin/env bash
# create-users.sh — Create HTPasswd users for the ShopInsights tutorial
#
# This script:
#   1. Creates an HTPasswd file with three users (dev-user, ops-user, admin-user)
#   2. Creates a Secret in the openshift-config namespace with the HTPasswd file
#   3. Patches the OAuth cluster resource to use the HTPasswd identity provider
#
# Prerequisites:
#   - htpasswd command available (httpd-tools / apache2-utils)
#   - Logged in as kubeadmin: oc login -u kubeadmin -p <password> https://api.crc.testing:6443
#
# Usage:
#   bash scripts/create-users.sh

set -euo pipefail

HTPASSWD_FILE="/tmp/shopinsights-users"
SECRET_NAME="htpasswd-secret"
SECRET_NAMESPACE="openshift-config"
IDP_NAME="shopinsights-htpasswd"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== ShopInsights User Setup ===${NC}"
echo ""

# --- Pre-flight checks ---

# Check that htpasswd is available
if ! command -v htpasswd &> /dev/null; then
    echo -e "${RED}ERROR: htpasswd command not found.${NC}"
    echo "Install it with:"
    echo "  macOS:        brew install httpd  (or it may already be at /usr/bin/htpasswd)"
    echo "  RHEL/Fedora:  sudo dnf install httpd-tools"
    echo "  Ubuntu/Debian: sudo apt install apache2-utils"
    exit 1
fi

# Check that oc is available and we are logged in
if ! command -v oc &> /dev/null; then
    echo -e "${RED}ERROR: oc command not found. Install the OpenShift CLI.${NC}"
    exit 1
fi

CURRENT_USER=$(oc whoami 2>/dev/null || true)
if [ -z "$CURRENT_USER" ]; then
    echo -e "${RED}ERROR: Not logged in to OpenShift. Run:${NC}"
    echo "  oc login -u kubeadmin -p <password> https://api.crc.testing:6443"
    exit 1
fi

echo -e "Logged in as: ${GREEN}${CURRENT_USER}${NC}"

# Warn if not cluster-admin
if ! oc auth can-i create oauth --all-namespaces &> /dev/null; then
    echo -e "${RED}ERROR: Current user does not have cluster-admin privileges.${NC}"
    echo "Log in as kubeadmin to configure the OAuth server."
    exit 1
fi

# --- Step 1: Create HTPasswd file ---

echo ""
echo -e "${YELLOW}Step 1: Creating HTPasswd file with users...${NC}"

# Create the file with the first user (-c creates a new file)
htpasswd -c -B -b "$HTPASSWD_FILE" dev-user devpass123
htpasswd -B -b "$HTPASSWD_FILE" ops-user opspass123
htpasswd -B -b "$HTPASSWD_FILE" admin-user adminpass123

echo -e "${GREEN}Created $HTPASSWD_FILE with 3 users:${NC}"
echo "  dev-user    (password: devpass123)"
echo "  ops-user    (password: opspass123)"
echo "  admin-user  (password: adminpass123)"

# --- Step 2: Create Secret in openshift-config ---

echo ""
echo -e "${YELLOW}Step 2: Creating Secret in ${SECRET_NAMESPACE}...${NC}"

# Delete the secret if it already exists (idempotent)
oc delete secret "$SECRET_NAME" -n "$SECRET_NAMESPACE" --ignore-not-found

oc create secret generic "$SECRET_NAME" \
    --from-file=htpasswd="$HTPASSWD_FILE" \
    -n "$SECRET_NAMESPACE"

# Add labels
oc label secret "$SECRET_NAME" -n "$SECRET_NAMESPACE" \
    app=shopinsights \
    tutorial=personalized \
    lesson=06

echo -e "${GREEN}Secret '${SECRET_NAME}' created in ${SECRET_NAMESPACE}${NC}"

# --- Step 3: Patch OAuth to add HTPasswd identity provider ---

echo ""
echo -e "${YELLOW}Step 3: Configuring OAuth to use HTPasswd identity provider...${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_DIR="$(dirname "$SCRIPT_DIR")/manifests"

if [ -f "$MANIFEST_DIR/oauth-htpasswd.yaml" ]; then
    oc apply -f "$MANIFEST_DIR/oauth-htpasswd.yaml"
else
    # Fallback: apply inline if manifest is not found
    oc apply -f - <<EOF
apiVersion: config.openshift.io/v1
kind: OAuth
metadata:
  name: cluster
spec:
  identityProviders:
    - name: ${IDP_NAME}
      mappingMethod: claim
      type: HTPasswd
      htpasswd:
        fileData:
          name: ${SECRET_NAME}
EOF
fi

echo -e "${GREEN}OAuth configured with identity provider '${IDP_NAME}'${NC}"

# --- Wait for OAuth pods to restart ---

echo ""
echo -e "${YELLOW}Waiting for OAuth pods to restart (this takes 1-2 minutes)...${NC}"

# Wait for the rollout
oc rollout status deployment/oauth-openshift -n openshift-authentication --timeout=120s 2>/dev/null || \
    echo -e "${YELLOW}OAuth pods are restarting. If this times out, check manually:${NC}"

echo ""
echo -e "${GREEN}=== Setup Complete ===${NC}"
echo ""
echo "You can now log in as any of these users:"
echo "  oc login -u dev-user -p devpass123 https://api.crc.testing:6443"
echo "  oc login -u ops-user -p opspass123 https://api.crc.testing:6443"
echo "  oc login -u admin-user -p adminpass123 https://api.crc.testing:6443"
echo ""
echo "Next: Apply RBAC manifests to grant permissions:"
echo "  oc apply -f manifests/rbac-dev-team.yaml"
echo "  oc apply -f manifests/rbac-staging-view.yaml"
echo "  oc apply -f manifests/rbac-ops-team.yaml"

# --- Cleanup temp file ---

rm -f "$HTPASSWD_FILE"
echo ""
echo -e "Temporary file ${HTPASSWD_FILE} removed."
