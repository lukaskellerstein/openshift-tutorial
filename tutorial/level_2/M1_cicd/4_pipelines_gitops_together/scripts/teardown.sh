#!/bin/bash
# Teardown script for L2-M1.4 — Pipelines + GitOps Together
# Removes all resources created during the lesson.

set -euo pipefail

PROJECT="pipelines-gitops-demo"

echo "============================================"
echo " L2-M1.4 — Teardown"
echo "============================================"

# 1. Delete the ArgoCD Application
echo ""
echo "==> Deleting ArgoCD Application..."
oc delete application demo-app -n openshift-gitops 2>/dev/null || echo "    (not found)"

# 2. Delete all tutorial resources in the project
echo ""
echo "==> Deleting tutorial resources..."
oc delete all -l tutorial-level=2,tutorial-module=M1 -n "${PROJECT}" 2>/dev/null || echo "    (none found)"

# 3. Delete Tekton resources
echo ""
echo "==> Deleting Tekton resources..."
oc delete pipeline ci-cd-pipeline -n "${PROJECT}" 2>/dev/null || echo "    (not found)"
oc delete task build-and-push run-tests generate-image-tag update-gitops-repo -n "${PROJECT}" 2>/dev/null || echo "    (not found)"
oc delete pipelinerun -l app=demo-app -n "${PROJECT}" 2>/dev/null || echo "    (not found)"

# 4. Delete secrets and service accounts
echo ""
echo "==> Deleting secrets and service accounts..."
oc delete secret git-credentials -n "${PROJECT}" 2>/dev/null || echo "    (not found)"
oc delete sa pipeline-gitops-sa -n "${PROJECT}" 2>/dev/null || echo "    (not found)"

# 5. Delete the RBAC rolebinding
echo ""
echo "==> Deleting RBAC resources..."
oc delete rolebinding argocd-admin -n "${PROJECT}" 2>/dev/null || echo "    (not found)"

# 6. Delete the project
echo ""
echo "==> Deleting project: ${PROJECT}"
oc delete project "${PROJECT}" 2>/dev/null || echo "    (not found)"

echo ""
echo "============================================"
echo " Teardown complete!"
echo "============================================"
