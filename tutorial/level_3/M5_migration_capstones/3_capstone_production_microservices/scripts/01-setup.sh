#!/bin/bash
# Setup script for the Capstone: Production-Ready Microservices lesson.
# This script creates the project, installs prerequisites, and applies
# all base manifests in the correct order.
#
# Prerequisites:
#   - OpenShift cluster running (CRC or multi-node)
#   - Logged in as kubeadmin (for operator/admin tasks)
#   - OpenShift Pipelines Operator installed
#   - OpenShift GitOps Operator installed
#   - OpenShift Service Mesh Operator installed (with Kiali, Jaeger)

set -euo pipefail

NAMESPACE="capstone-microservices"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFESTS_DIR="${SCRIPT_DIR}/../manifests"
APP_DIR="${SCRIPT_DIR}/../app"

echo "============================================"
echo "  Capstone: Production-Ready Microservices"
echo "  Setup Script"
echo "============================================"
echo ""

# Check login
echo "[1/8] Checking OpenShift login..."
if ! oc whoami &>/dev/null; then
  echo "ERROR: Not logged in to OpenShift. Run 'oc login' first."
  exit 1
fi
CURRENT_USER=$(oc whoami)
echo "  Logged in as: ${CURRENT_USER}"

# Check required operators
echo ""
echo "[2/8] Checking required operators..."
MISSING_OPERATORS=()

if ! oc get csv -n openshift-operators 2>/dev/null | grep -q "openshift-pipelines-operator"; then
  MISSING_OPERATORS+=("OpenShift Pipelines")
fi
if ! oc get csv -n openshift-gitops 2>/dev/null | grep -q "openshift-gitops-operator"; then
  MISSING_OPERATORS+=("OpenShift GitOps")
fi
if ! oc get csv -n openshift-operators 2>/dev/null | grep -q "servicemeshoperator"; then
  MISSING_OPERATORS+=("OpenShift Service Mesh")
fi

if [ ${#MISSING_OPERATORS[@]} -gt 0 ]; then
  echo "  WARNING: The following operators may not be installed:"
  for op in "${MISSING_OPERATORS[@]}"; do
    echo "    - ${op}"
  done
  echo "  Some features will not work without them."
  echo "  Continue anyway? (y/N)"
  read -r response
  if [[ ! "$response" =~ ^[yY]$ ]]; then
    echo "Aborting setup."
    exit 1
  fi
else
  echo "  All required operators found."
fi

# Enable user workload monitoring (requires kubeadmin)
echo ""
echo "[3/8] Enabling user workload monitoring..."
if [ "${CURRENT_USER}" = "kubeadmin" ] || oc auth can-i create configmaps -n openshift-monitoring &>/dev/null; then
  oc apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: cluster-monitoring-config
  namespace: openshift-monitoring
data:
  config.yaml: |
    enableUserWorkload: true
EOF
  echo "  User workload monitoring enabled."
else
  echo "  WARNING: Cannot enable user workload monitoring (need kubeadmin)."
  echo "  ServiceMonitors will not work until this is enabled."
fi

# Create the project
echo ""
echo "[4/8] Creating project ${NAMESPACE}..."
if oc get project "${NAMESPACE}" &>/dev/null; then
  echo "  Project ${NAMESPACE} already exists."
else
  oc new-project "${NAMESPACE}" \
    --display-name="Capstone: Production Microservices" \
    --description="L3-M5.3 production-ready microservices capstone"
  echo "  Project created."
fi

oc project "${NAMESPACE}"

# Apply manifests in order
echo ""
echo "[5/8] Applying RBAC, ImageStreams, and BuildConfigs..."
oc apply -f "${MANIFESTS_DIR}/01-rbac.yaml"
oc apply -f "${MANIFESTS_DIR}/02-imagestreams.yaml"
oc apply -f "${MANIFESTS_DIR}/03-buildconfigs.yaml"
echo "  Done."

# Build the container images
echo ""
echo "[6/8] Building microservice images (this may take several minutes)..."
SERVICES=("api-gateway" "order-service" "inventory-service" "payment-service")
for svc in "${SERVICES[@]}"; do
  echo "  Building ${svc}..."
  oc start-build "${svc}" \
    --from-dir="${APP_DIR}/${svc}" \
    --follow \
    --wait \
    -n "${NAMESPACE}" || echo "  WARNING: Build of ${svc} failed. Continue manually."
done
echo "  Builds complete."

# Deploy services
echo ""
echo "[7/8] Deploying services, routes, network policies, HPAs..."
oc apply -f "${MANIFESTS_DIR}/04-deployments.yaml"
oc apply -f "${MANIFESTS_DIR}/05-services.yaml"
oc apply -f "${MANIFESTS_DIR}/06-route.yaml"
oc apply -f "${MANIFESTS_DIR}/07-network-policies.yaml"
oc apply -f "${MANIFESTS_DIR}/08-hpa.yaml"
oc apply -f "${MANIFESTS_DIR}/09-monitoring.yaml"
oc apply -f "${MANIFESTS_DIR}/11-resource-quotas.yaml"
oc apply -f "${MANIFESTS_DIR}/14-pod-disruption-budgets.yaml"
echo "  Done."

# Apply service mesh and CI/CD (may fail if operators not installed)
echo ""
echo "[8/8] Applying service mesh and CI/CD manifests..."
oc apply -f "${MANIFESTS_DIR}/10-service-mesh.yaml" 2>/dev/null || \
  echo "  WARNING: Service mesh manifests failed (operator may not be installed)."
oc apply -f "${MANIFESTS_DIR}/12-tekton-pipeline.yaml" 2>/dev/null || \
  echo "  WARNING: Tekton pipeline manifests failed (operator may not be installed)."
echo "  Done."

# Wait for deployments
echo ""
echo "Waiting for deployments to roll out..."
for svc in "${SERVICES[@]}"; do
  echo "  Waiting for ${svc}..."
  oc rollout status deployment/"${svc}" -n "${NAMESPACE}" --timeout=120s || \
    echo "  WARNING: ${svc} rollout did not complete in time."
done

# Print summary
echo ""
echo "============================================"
echo "  Setup Complete"
echo "============================================"
echo ""
ROUTE_HOST=$(oc get route api-gateway -n "${NAMESPACE}" -o jsonpath='{.spec.host}' 2>/dev/null || echo "N/A")
echo "  Route URL:  https://${ROUTE_HOST}"
echo "  Namespace:  ${NAMESPACE}"
echo ""
echo "  Verify with:"
echo "    oc get pods -n ${NAMESPACE}"
echo "    curl -k https://${ROUTE_HOST}/healthz"
echo ""
echo "  View in Web Console:"
echo "    https://console-openshift-console.apps-crc.testing/topology/ns/${NAMESPACE}"
echo ""
