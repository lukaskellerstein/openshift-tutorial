#!/usr/bin/env bash
set -euo pipefail

# ── Parse flags ──────────────────────────────────────────────────────────────
NAMESPACE=""
while getopts "n:" opt; do
  case $opt in
    n) NAMESPACE="$OPTARG" ;;
    *) echo "Usage: $0 [-n namespace]"; exit 1 ;;
  esac
done

# ── Resolve paths ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LESSON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Prerequisites ────────────────────────────────────────────────────────────
if ! command -v oc &>/dev/null; then
  echo "ERROR: 'oc' CLI not found. Install it first."
  exit 1
fi

if ! oc whoami &>/dev/null; then
  echo "ERROR: Not logged in to an OpenShift cluster. Run 'oc login' first."
  exit 1
fi

if [[ -z "$NAMESPACE" ]]; then
  NAMESPACE="$(oc project -q)"
fi

if ! oc get project "$NAMESPACE" &>/dev/null; then
  echo "ERROR: Namespace '$NAMESPACE' does not exist."
  exit 1
fi

echo "==> Using namespace: $NAMESPACE"

# ── Deploy Keycloak ──────────────────────────────────────────────────────────
echo "==> Applying Keycloak realm ConfigMap..."
oc apply -f "$LESSON_DIR/manifests/keycloak-realm-configmap.yaml" -n "$NAMESPACE"

echo "==> Applying Keycloak Deployment, Service, and Route..."
oc apply -f "$LESSON_DIR/manifests/keycloak-deployment.yaml" -n "$NAMESPACE"

echo "==> Waiting for Keycloak pod to become ready (timeout: 180s)..."
oc wait --for=condition=ready pod -l component=keycloak --timeout=180s -n "$NAMESPACE"

# ── Resolve Keycloak Route URL ───────────────────────────────────────────────
KEYCLOAK_URL="https://$(oc get route keycloak -n "$NAMESPACE" -o jsonpath='{.spec.host}')"
echo "==> Keycloak Route URL: $KEYCLOAK_URL"

# ── Apply ConfigMaps with resolved URL ───────────────────────────────────────
echo "==> Applying keycloak-auth-config ConfigMap..."
sed "s|__KEYCLOAK_URL__|${KEYCLOAK_URL}|g" "$LESSON_DIR/manifests/keycloak-auth-configmap.yaml" \
  | oc apply -f - -n "$NAMESPACE"

echo "==> Applying dashboard-keycloak-config ConfigMap..."
sed "s|__KEYCLOAK_URL__|${KEYCLOAK_URL}|g" "$LESSON_DIR/manifests/dashboard-keycloak-configmap.yaml" \
  | oc apply -f - -n "$NAMESPACE"

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "========================================"
echo "  Keycloak is ready!"
echo "========================================"
echo ""
echo "  Admin Console:  ${KEYCLOAK_URL}/admin"
echo "  Username:       admin"
echo "  Password:       admin"
echo ""
echo "  Realm:          shopinsights"
echo "  Realm Console:  ${KEYCLOAK_URL}/admin/master/console/#/shopinsights"
echo ""
echo "  Test users:"
echo "    alice / alice123  (role: editor)"
echo "    bob   / bob123    (role: viewer)"
echo "    admin / admin123  (roles: editor, viewer)"
echo ""
