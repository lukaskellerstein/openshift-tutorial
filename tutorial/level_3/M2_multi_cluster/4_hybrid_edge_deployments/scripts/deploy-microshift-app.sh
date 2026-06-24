#!/usr/bin/env bash
# deploy-microshift-app.sh
# Deploys the edge data collector application to a MicroShift or OpenShift cluster.
# This script can be used on any cluster with oc/kubectl access.
#
# Usage: ./scripts/deploy-microshift-app.sh [namespace]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_DIR="${SCRIPT_DIR}/../manifests"
NAMESPACE="${1:-edge-apps}"

echo "=== Deploying Edge Data Collector Application ==="
echo "Namespace: ${NAMESPACE}"
echo ""

# Create namespace if it does not exist
if ! oc get namespace "${NAMESPACE}" > /dev/null 2>&1; then
  echo "Creating namespace ${NAMESPACE}..."
  oc create namespace "${NAMESPACE}" || oc new-project "${NAMESPACE}"
fi

# Deploy application components
echo "Deploying application..."
oc apply -n "${NAMESPACE}" -f "${MANIFEST_DIR}/microshift-app-deployment.yaml"
oc apply -n "${NAMESPACE}" -f "${MANIFEST_DIR}/microshift-app-service.yaml"
oc apply -n "${NAMESPACE}" -f "${MANIFEST_DIR}/microshift-app-route.yaml"

echo ""
echo "Waiting for deployment to be ready..."
oc rollout status deployment/edge-data-collector -n "${NAMESPACE}" --timeout=120s

echo ""
echo "=== Deployment Status ==="
oc get pods -n "${NAMESPACE}" -l app=edge-data-collector
echo ""
oc get svc -n "${NAMESPACE}" -l app=edge-data-collector
echo ""
oc get routes -n "${NAMESPACE}" -l app=edge-data-collector

# Get the route URL
ROUTE_HOST=$(oc get route edge-data-collector -n "${NAMESPACE}" -o jsonpath='{.spec.host}' 2>/dev/null || echo "")
if [ -n "${ROUTE_HOST}" ]; then
  echo ""
  echo "Application URL: https://${ROUTE_HOST}"
fi

echo ""
echo "=== Deployment Complete ==="
echo "To view logs: oc logs -f deployment/edge-data-collector -n ${NAMESPACE}"
echo "To clean up:  oc delete -f ${MANIFEST_DIR}/microshift-app-deployment.yaml \\"
echo "              -f ${MANIFEST_DIR}/microshift-app-service.yaml \\"
echo "              -f ${MANIFEST_DIR}/microshift-app-route.yaml -n ${NAMESPACE}"
