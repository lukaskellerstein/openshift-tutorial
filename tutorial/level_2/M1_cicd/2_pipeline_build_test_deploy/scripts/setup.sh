#!/usr/bin/env bash
# Setup script for L2-M1.2 Pipeline: Build, Test, Deploy
# Creates the required projects and applies all pipeline resources
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFESTS_DIR="${SCRIPT_DIR}/../manifests"

echo "============================================="
echo " L2-M1.2 Pipeline Setup"
echo "============================================="
echo ""

# Verify prerequisites
echo "--- Checking prerequisites ---"

if ! oc whoami &>/dev/null; then
  echo "ERROR: Not logged into OpenShift. Run: oc login"
  exit 1
fi

CURRENT_USER=$(oc whoami)
echo "Logged in as: ${CURRENT_USER}"

if ! oc api-resources | grep -q "tekton.dev"; then
  echo "ERROR: OpenShift Pipelines (Tekton) is not installed."
  echo "Install it from OperatorHub or run:"
  echo "  oc apply -f https://storage.googleapis.com/tekton-releases/pipeline/latest/release.yaml"
  exit 1
fi

echo "OpenShift Pipelines: installed"
echo ""

# Step 1: Create projects
echo "--- Creating projects ---"

oc new-project cicd-pipelines --display-name="CI/CD Pipelines" \
  --description="Pipeline definitions and runs" 2>/dev/null || \
  echo "Project cicd-pipelines already exists"

oc new-project cicd-staging --display-name="Staging Environment" \
  --description="Staging deployment target" 2>/dev/null || \
  echo "Project cicd-staging already exists"

oc new-project cicd-production --display-name="Production Environment" \
  --description="Production deployment target" 2>/dev/null || \
  echo "Project cicd-production already exists"

echo ""

# Step 2: Switch to the pipelines project
echo "--- Switching to cicd-pipelines project ---"
oc project cicd-pipelines

# Step 3: Set up RBAC
echo ""
echo "--- Setting up RBAC ---"
oc apply -f "${MANIFESTS_DIR}/rbac.yaml"

# Step 4: Create the shared workspace PVC
echo ""
echo "--- Creating shared workspace PVC ---"
oc apply -f "${MANIFESTS_DIR}/workspace-pvc.yaml"

# Step 5: Create Tasks
echo ""
echo "--- Creating Tasks ---"
oc apply -f "${MANIFESTS_DIR}/task-clone.yaml"
oc apply -f "${MANIFESTS_DIR}/task-build.yaml"
oc apply -f "${MANIFESTS_DIR}/task-test.yaml"
oc apply -f "${MANIFESTS_DIR}/task-deploy.yaml"

# Step 6: Create the Pipeline
echo ""
echo "--- Creating Pipeline ---"
oc apply -f "${MANIFESTS_DIR}/pipeline.yaml"

echo ""
echo "============================================="
echo " Setup complete!"
echo "============================================="
echo ""
echo "Resources created:"
echo "  - Project: cicd-pipelines (pipeline definitions)"
echo "  - Project: cicd-staging (staging target)"
echo "  - Project: cicd-production (production target)"
echo "  - PVC: pipeline-workspace-pvc"
echo "  - Tasks: git-clone-source, build-image, run-tests, deploy-app"
echo "  - Pipeline: build-test-deploy"
echo ""
echo "To run the pipeline:"
echo "  oc create -f ${MANIFESTS_DIR}/pipelinerun.yaml"
echo ""
echo "Or use the tkn CLI:"
echo "  tkn pipeline start build-test-deploy \\"
echo "    --param git-url=https://github.com/sclorg/nodejs-ex.git \\"
echo "    --param git-revision=master \\"
echo "    --param staging-namespace=cicd-staging \\"
echo "    --param production-namespace=cicd-production \\"
echo "    --workspace name=shared-workspace,claimName=pipeline-workspace-pvc"
