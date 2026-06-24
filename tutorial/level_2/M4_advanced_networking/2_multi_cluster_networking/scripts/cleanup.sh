#!/usr/bin/env bash
# cleanup.sh — Remove all resources created in the multi-cluster networking lesson.
#
# Usage:
#   ./scripts/cleanup.sh [--cluster-a] [--cluster-b] [--all]
#
# Options:
#   --cluster-a   Clean up resources on Cluster-A (server side)
#   --cluster-b   Clean up resources on Cluster-B (client side)
#   --all         Clean up resources on the current cluster context (default)

set -euo pipefail

echo "============================================"
echo "  Cleaning up L2-M4.2 resources"
echo "============================================"
echo ""

# Remove demo application resources
echo "Removing demo application resources..."
oc delete serviceexport demo-server -n cross-cluster-demo 2>/dev/null && echo "  Deleted ServiceExport/demo-server" || echo "  ServiceExport/demo-server not found (skipping)"
oc delete deployment demo-client -n cross-cluster-demo 2>/dev/null && echo "  Deleted Deployment/demo-client" || echo "  Deployment/demo-client not found (skipping)"
oc delete deployment demo-server -n cross-cluster-demo 2>/dev/null && echo "  Deleted Deployment/demo-server" || echo "  Deployment/demo-server not found (skipping)"
oc delete service demo-server -n cross-cluster-demo 2>/dev/null && echo "  Deleted Service/demo-server" || echo "  Service/demo-server not found (skipping)"
oc delete configmap demo-server-html -n cross-cluster-demo 2>/dev/null && echo "  Deleted ConfigMap/demo-server-html" || echo "  ConfigMap/demo-server-html not found (skipping)"

echo ""
echo "Removing demo namespace..."
oc delete namespace cross-cluster-demo 2>/dev/null && echo "  Deleted Namespace/cross-cluster-demo" || echo "  Namespace/cross-cluster-demo not found (skipping)"

echo ""
echo "Removing tutorial-labeled resources..."
oc delete all -l tutorial-level=2,tutorial-module=M4 --all-namespaces 2>/dev/null || true

echo ""
echo "NOTE: This script does NOT remove the Submariner operator or broker."
echo "      To fully remove Submariner, uninstall it via RHACM or:"
echo "        oc delete ns submariner-operator"
echo "        oc delete ns submariner-k8s-broker"
echo ""
echo "Cleanup complete."
