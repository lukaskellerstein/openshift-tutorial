#!/bin/bash
# Setup script for L2-M3.3 — OpenShift Serverless (Knative)
# This script installs the OpenShift Serverless operator and Knative components.
# Run as kubeadmin.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFESTS_DIR="${SCRIPT_DIR}/../manifests"

echo "=== L2-M3.3 Setup: OpenShift Serverless ==="
echo ""

# Check login
CURRENT_USER=$(oc whoami 2>/dev/null || true)
if [[ -z "$CURRENT_USER" ]]; then
  echo "ERROR: Not logged in to OpenShift. Run: oc login -u kubeadmin -p <password> https://api.crc.testing:6443"
  exit 1
fi
echo "Logged in as: $CURRENT_USER"

# Step 1: Install the Serverless operator
echo ""
echo "--- Step 1: Installing OpenShift Serverless operator ---"
oc apply -f "${MANIFESTS_DIR}/serverless-operator-subscription.yaml"

echo "Waiting for the operator CSV to reach 'Succeeded' phase..."
ATTEMPTS=0
MAX_ATTEMPTS=60
while [[ $ATTEMPTS -lt $MAX_ATTEMPTS ]]; do
  PHASE=$(oc get csv -n openshift-serverless -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "Pending")
  if [[ "$PHASE" == "Succeeded" ]]; then
    echo "Serverless operator installed successfully."
    break
  fi
  echo "  Operator phase: $PHASE (attempt $((ATTEMPTS+1))/$MAX_ATTEMPTS)"
  sleep 10
  ATTEMPTS=$((ATTEMPTS+1))
done

if [[ $ATTEMPTS -ge $MAX_ATTEMPTS ]]; then
  echo "ERROR: Operator did not reach 'Succeeded' phase within $((MAX_ATTEMPTS * 10)) seconds."
  echo "Check: oc get csv -n openshift-serverless"
  echo "Check: oc get events -n openshift-serverless --sort-by='.lastTimestamp'"
  exit 1
fi

# Step 2: Install Knative Serving
echo ""
echo "--- Step 2: Installing Knative Serving ---"
oc apply -f "${MANIFESTS_DIR}/knative-serving.yaml"

echo "Waiting for Knative Serving to become ready..."
ATTEMPTS=0
while [[ $ATTEMPTS -lt $MAX_ATTEMPTS ]]; do
  READY=$(oc get knativeserving knative-serving -n knative-serving -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "Unknown")
  if [[ "$READY" == "True" ]]; then
    echo "Knative Serving is ready."
    break
  fi
  echo "  Knative Serving ready: $READY (attempt $((ATTEMPTS+1))/$MAX_ATTEMPTS)"
  sleep 10
  ATTEMPTS=$((ATTEMPTS+1))
done

if [[ $ATTEMPTS -ge $MAX_ATTEMPTS ]]; then
  echo "ERROR: Knative Serving did not become ready within $((MAX_ATTEMPTS * 10)) seconds."
  echo "Check: oc get knativeserving -n knative-serving -o yaml"
  exit 1
fi

# Step 3: Install Knative Eventing
echo ""
echo "--- Step 3: Installing Knative Eventing ---"
oc apply -f "${MANIFESTS_DIR}/knative-eventing.yaml"

echo "Waiting for Knative Eventing to become ready..."
ATTEMPTS=0
while [[ $ATTEMPTS -lt $MAX_ATTEMPTS ]]; do
  READY=$(oc get knativeeventing knative-eventing -n knative-eventing -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "Unknown")
  if [[ "$READY" == "True" ]]; then
    echo "Knative Eventing is ready."
    break
  fi
  echo "  Knative Eventing ready: $READY (attempt $((ATTEMPTS+1))/$MAX_ATTEMPTS)"
  sleep 10
  ATTEMPTS=$((ATTEMPTS+1))
done

if [[ $ATTEMPTS -ge $MAX_ATTEMPTS ]]; then
  echo "ERROR: Knative Eventing did not become ready within $((MAX_ATTEMPTS * 10)) seconds."
  echo "Check: oc get knativeeventing -n knative-eventing -o yaml"
  exit 1
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Log in as developer: oc login -u developer -p developer https://api.crc.testing:6443"
echo "  2. Create the tutorial project: oc new-project serverless-tutorial"
echo "  3. Follow the lesson README.md"
