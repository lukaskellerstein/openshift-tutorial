#!/bin/bash
# setup.sh — Install Service Mesh operators and create the control plane
# Run as cluster-admin (kubeadmin)
#
# Usage: ./scripts/setup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_DIR="${SCRIPT_DIR}/../manifests"

echo "=== Step 1: Installing Service Mesh operators ==="

echo "Installing Jaeger operator..."
oc apply -f "${MANIFEST_DIR}/operator-jaeger.yaml"

echo "Installing Kiali operator..."
oc apply -f "${MANIFEST_DIR}/operator-kiali.yaml"

echo "Installing Service Mesh operator..."
oc apply -f "${MANIFEST_DIR}/operator-servicemesh.yaml"

echo ""
echo "Waiting for operators to install (this may take 2-5 minutes)..."

# Wait for each operator CSV to reach Succeeded phase
for operator in jaeger-product kiali-ossm servicemeshoperator; do
  echo -n "  Waiting for ${operator}..."
  attempts=0
  max_attempts=60
  while [ $attempts -lt $max_attempts ]; do
    phase=$(oc get csv -n openshift-operators -o jsonpath="{.items[?(@.metadata.name=~'${operator}.*')].status.phase}" 2>/dev/null || echo "")
    if [ "$phase" = "Succeeded" ]; then
      echo " Ready"
      break
    fi
    sleep 5
    attempts=$((attempts + 1))
    echo -n "."
  done
  if [ $attempts -eq $max_attempts ]; then
    echo " TIMEOUT — check with: oc get csv -n openshift-operators"
    exit 1
  fi
done

echo ""
echo "=== Step 2: Creating control plane namespace ==="

oc new-project istio-system 2>/dev/null || oc project istio-system
echo "Using project: istio-system"

echo ""
echo "=== Step 3: Deploying ServiceMeshControlPlane ==="

oc apply -f "${MANIFEST_DIR}/smcp.yaml" -n istio-system

echo ""
echo "Waiting for control plane to be ready (this may take 3-5 minutes)..."

attempts=0
max_attempts=90
while [ $attempts -lt $max_attempts ]; do
  ready=$(oc get smcp basic -n istio-system -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "")
  if [ "$ready" = "True" ]; then
    echo "Control plane is ready!"
    break
  fi
  sleep 5
  attempts=$((attempts + 1))
  if [ $((attempts % 6)) -eq 0 ]; then
    echo "  Still waiting... ($(oc get smcp basic -n istio-system -o jsonpath='{.status.conditions[?(@.type=="Ready")].reason}' 2>/dev/null || echo 'initializing'))"
  fi
done

if [ $attempts -eq $max_attempts ]; then
  echo "TIMEOUT waiting for SMCP — check with: oc describe smcp basic -n istio-system"
  exit 1
fi

echo ""
echo "=== Step 4: Creating application namespace ==="

oc new-project mesh-demo 2>/dev/null || oc project mesh-demo
echo "Using project: mesh-demo"

echo ""
echo "=== Step 5: Enrolling namespace in the mesh ==="

oc apply -f "${MANIFEST_DIR}/smmr.yaml" -n istio-system

echo ""
echo "Verifying enrollment..."
sleep 5
oc get smmr default -n istio-system -o wide

echo ""
echo "=== Setup complete ==="
echo ""
echo "Control plane pods:"
oc get pods -n istio-system
echo ""
echo "Next: Run ./scripts/deploy-app.sh to deploy the sample application."
