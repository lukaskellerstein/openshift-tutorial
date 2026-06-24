#!/bin/bash
# setup.sh — Scaffold, build, and deploy the WebApp operator
#
# Prerequisites:
#   - operator-sdk v1.34+ installed
#   - Go 1.21+ installed
#   - Podman installed
#   - oc logged in as kubeadmin
#   - Access to a container registry (set REGISTRY_USERNAME)
#
# Usage:
#   export REGISTRY_USERNAME=your-quay-username
#   ./setup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LESSON_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_DIR="${HOME}/webapp-operator"
REGISTRY_USERNAME="${REGISTRY_USERNAME:-}"
IMG="${IMG:-}"

# --- Validation -----------------------------------------------------------

if ! command -v operator-sdk &>/dev/null; then
  echo "ERROR: operator-sdk is not installed."
  echo "Install it: https://sdk.operatorframework.io/docs/installation/"
  exit 1
fi

if ! command -v go &>/dev/null; then
  echo "ERROR: Go is not installed."
  exit 1
fi

if ! command -v podman &>/dev/null; then
  echo "ERROR: Podman is not installed."
  exit 1
fi

if ! oc whoami &>/dev/null; then
  echo "ERROR: Not logged in to OpenShift. Run: oc login -u kubeadmin ..."
  exit 1
fi

if [ -z "$IMG" ] && [ -z "$REGISTRY_USERNAME" ]; then
  echo "ERROR: Set REGISTRY_USERNAME or IMG environment variable."
  echo "  export REGISTRY_USERNAME=your-quay-username"
  echo "  # or"
  echo "  export IMG=quay.io/your-username/webapp-operator:v0.0.1"
  exit 1
fi

if [ -z "$IMG" ]; then
  IMG="quay.io/${REGISTRY_USERNAME}/webapp-operator:v0.0.1"
fi

echo "=== WebApp Operator Setup ==="
echo "Project directory: ${PROJECT_DIR}"
echo "Operator image:    ${IMG}"
echo ""

# --- Step 1: Scaffold the project -----------------------------------------

if [ -d "$PROJECT_DIR" ]; then
  echo "WARNING: ${PROJECT_DIR} already exists. Skipping scaffold."
else
  echo "--- Step 1: Scaffolding operator project ---"
  mkdir -p "$PROJECT_DIR"
  cd "$PROJECT_DIR"

  operator-sdk init \
    --domain openshift.io \
    --repo github.com/example/webapp-operator \
    --project-name webapp-operator

  operator-sdk create api \
    --group tutorial \
    --version v1alpha1 \
    --kind WebApp \
    --resource --controller

  echo "Scaffold complete."
fi

cd "$PROJECT_DIR"

# --- Step 2: Copy source files --------------------------------------------

echo "--- Step 2: Copying source files from lesson ---"
cp "${LESSON_DIR}/app/api/v1alpha1/webapp_types.go" \
   "${PROJECT_DIR}/api/v1alpha1/webapp_types.go"

cp "${LESSON_DIR}/app/internal/controller/webapp_controller.go" \
   "${PROJECT_DIR}/internal/controller/webapp_controller.go"

echo "Source files copied."

# --- Step 3: Add OpenShift Route dependency --------------------------------

echo "--- Step 3: Adding OpenShift API dependency ---"
cd "$PROJECT_DIR"

# Add the openshift/api module for Route types
go get github.com/openshift/api@latest

# Register the Route scheme in cmd/main.go
# (This is a simplified approach — in a real project you would edit the file properly)
if ! grep -q "routev1" cmd/main.go; then
  echo ""
  echo "NOTE: You need to manually add the Route scheme to cmd/main.go."
  echo "Add these lines:"
  echo '  import routev1 "github.com/openshift/api/route/v1"'
  echo '  And in the init() or main():'
  echo '  utilruntime.Must(routev1.Install(scheme))'
fi

# --- Step 4: Generate code and manifests -----------------------------------

echo "--- Step 4: Generating code and manifests ---"
make generate
make manifests

# --- Step 5: Build the operator image --------------------------------------

echo "--- Step 5: Building operator image ---"
make docker-build IMG="$IMG" CONTAINER_TOOL=podman

echo "--- Step 6: Pushing operator image ---"
make docker-push IMG="$IMG" CONTAINER_TOOL=podman

# --- Step 7: Deploy to OpenShift -------------------------------------------

echo "--- Step 7: Deploying operator to OpenShift ---"
oc new-project webapp-operator-system 2>/dev/null || true
make deploy IMG="$IMG"

echo ""
echo "--- Waiting for operator pod to be ready ---"
oc rollout status deployment/webapp-operator-controller-manager \
  -n webapp-operator-system --timeout=120s

echo ""
echo "=== Operator deployed successfully ==="
echo ""
echo "Next: create a WebApp custom resource:"
echo "  oc new-project webapp-demo"
echo "  oc apply -f ${LESSON_DIR}/manifests/webapp-sample.yaml"
echo "  oc get webapp"
