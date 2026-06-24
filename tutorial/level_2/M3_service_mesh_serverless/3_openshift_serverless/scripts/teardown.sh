#!/bin/bash
# Teardown script for L2-M3.3 — OpenShift Serverless (Knative)
# Removes all resources created during the lesson.
# Pass --keep-operator to preserve the Serverless operator for L2-M3.4.

set -euo pipefail

KEEP_OPERATOR=false
for arg in "$@"; do
  case $arg in
    --keep-operator)
      KEEP_OPERATOR=true
      ;;
  esac
done

echo "=== L2-M3.3 Teardown: OpenShift Serverless ==="
echo ""

# Step 1: Remove Knative Services and workloads
echo "--- Step 1: Removing tutorial workloads ---"
if oc get project serverless-tutorial &>/dev/null; then
  echo "Deleting all resources with tutorial labels..."
  oc delete all -l tutorial-level=2,tutorial-module=M3 -n serverless-tutorial 2>/dev/null || true

  echo "Deleting Knative Services..."
  oc delete ksvc --all -n serverless-tutorial 2>/dev/null || true

  echo "Deleting project serverless-tutorial..."
  oc delete project serverless-tutorial
  echo "Project deleted."
else
  echo "Project serverless-tutorial not found, skipping."
fi

if [[ "$KEEP_OPERATOR" == "true" ]]; then
  echo ""
  echo "--- Keeping Serverless operator installed (--keep-operator flag) ---"
  echo "The operator, Knative Serving, and Knative Eventing remain for L2-M3.4."
  echo ""
  echo "=== Teardown complete (operator preserved) ==="
  exit 0
fi

# Step 2: Remove Knative Serving and Eventing instances
echo ""
echo "--- Step 2: Removing Knative Serving and Eventing ---"
oc delete knativeserving knative-serving -n knative-serving 2>/dev/null || true
echo "Waiting for Knative Serving removal..."
sleep 10

oc delete knativeeventing knative-eventing -n knative-eventing 2>/dev/null || true
echo "Waiting for Knative Eventing removal..."
sleep 10

# Step 3: Remove the Serverless operator
echo ""
echo "--- Step 3: Removing Serverless operator ---"
oc delete subscription serverless-operator -n openshift-serverless 2>/dev/null || true
oc delete csv -n openshift-serverless -l operators.coreos.com/serverless-operator.openshift-serverless 2>/dev/null || true

echo "Removing operator namespaces..."
oc delete namespace knative-serving 2>/dev/null || true
oc delete namespace knative-eventing 2>/dev/null || true
oc delete namespace openshift-serverless 2>/dev/null || true

echo ""
echo "=== Teardown complete ==="
echo "All Serverless resources have been removed."
