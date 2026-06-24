#!/usr/bin/env bash
# Teardown script for L2-M1.1 — OpenShift Pipelines (Tekton)
# Removes all resources created during the lesson
set -euo pipefail

NAMESPACE="pipelines-tutorial"

echo "=== L2-M1.1 Teardown: OpenShift Pipelines (Tekton) ==="
echo ""

# Check that oc is available and logged in
if ! oc whoami &>/dev/null; then
  echo "ERROR: Not logged in to OpenShift. Run 'oc login' first."
  exit 1
fi

echo "Cleaning up resources in project '${NAMESPACE}'..."
echo ""

# Delete all tutorial resources by label
echo "Deleting Tekton resources..."
oc delete pipelinerun -l tutorial-level=2,tutorial-module=M1 -n "${NAMESPACE}" --ignore-not-found 2>/dev/null || true
oc delete taskrun -l tutorial-level=2,tutorial-module=M1 -n "${NAMESPACE}" --ignore-not-found 2>/dev/null || true
oc delete pipeline -l tutorial-level=2,tutorial-module=M1 -n "${NAMESPACE}" --ignore-not-found 2>/dev/null || true
oc delete task -l tutorial-level=2,tutorial-module=M1 -n "${NAMESPACE}" --ignore-not-found 2>/dev/null || true

echo "Deleting Trigger resources..."
oc delete eventlistener -l tutorial-level=2,tutorial-module=M1 -n "${NAMESPACE}" --ignore-not-found 2>/dev/null || true
oc delete triggertemplate -l tutorial-level=2,tutorial-module=M1 -n "${NAMESPACE}" --ignore-not-found 2>/dev/null || true
oc delete triggerbinding -l tutorial-level=2,tutorial-module=M1 -n "${NAMESPACE}" --ignore-not-found 2>/dev/null || true

echo "Deleting Routes..."
oc delete route -l tutorial-level=2,tutorial-module=M1 -n "${NAMESPACE}" --ignore-not-found 2>/dev/null || true

echo "Cleaning up PVCs from PipelineRuns..."
oc delete pvc -l tekton.dev/pipeline=clone-and-build -n "${NAMESPACE}" --ignore-not-found 2>/dev/null || true

echo ""
echo "Deleting project '${NAMESPACE}'..."
oc delete project "${NAMESPACE}" --ignore-not-found 2>/dev/null || true

echo ""
echo "=== Teardown complete ==="
echo "Note: The OpenShift Pipelines operator is still installed cluster-wide."
echo "To uninstall it, use the Web Console: Operators > Installed Operators > Uninstall."
