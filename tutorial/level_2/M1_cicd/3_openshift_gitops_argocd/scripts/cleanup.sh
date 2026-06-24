#!/bin/bash
# Cleanup script for L2-M1.3 — OpenShift GitOps (ArgoCD)
# Removes all resources created during the lesson
set -euo pipefail

echo "=== L2-M1.3 Cleanup: OpenShift GitOps (ArgoCD) ==="

# Step 1: Delete ArgoCD Applications
echo ""
echo "--- Deleting ArgoCD Applications ---"
oc delete application sample-app-manual -n openshift-gitops --ignore-not-found
oc delete application sample-app-auto -n openshift-gitops --ignore-not-found
oc delete application app-of-apps -n openshift-gitops --ignore-not-found

# Step 2: Delete AppProject
echo ""
echo "--- Deleting ArgoCD AppProject ---"
oc delete appproject tutorial-project -n openshift-gitops --ignore-not-found

# Step 3: Delete demo namespace and its resources
echo ""
echo "--- Deleting gitops-demo namespace ---"
oc delete namespace gitops-demo --ignore-not-found

# Step 4: Delete RBAC
echo ""
echo "--- Deleting RBAC resources ---"
oc delete rolebinding argocd-admin -n gitops-demo --ignore-not-found 2>/dev/null || true

# Step 5: Optionally remove the operator (commented out — you may want to keep it)
# Uncomment if you want a full teardown:
# echo ""
# echo "--- Removing OpenShift GitOps operator ---"
# oc delete subscription openshift-gitops-operator -n openshift-operators --ignore-not-found
# CSV_NAME=$(oc get csv -n openshift-gitops -l operators.coreos.com/openshift-gitops-operator.openshift-operators -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
# if [[ -n "${CSV_NAME}" ]]; then
#   oc delete csv "${CSV_NAME}" -n openshift-gitops --ignore-not-found
# fi
# oc delete namespace openshift-gitops --ignore-not-found

echo ""
echo "--- Cleanup by labels ---"
oc delete all -l tutorial-level=2,tutorial-module=M1 -n gitops-demo --ignore-not-found 2>/dev/null || true

echo ""
echo "=== Cleanup Complete ==="
echo "Note: The OpenShift GitOps operator was NOT removed (it may be needed for L2-M1.4)."
echo "To remove the operator, uncomment the relevant section in this script."
