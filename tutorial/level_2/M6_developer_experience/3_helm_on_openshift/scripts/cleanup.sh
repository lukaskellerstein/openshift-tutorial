#!/bin/bash
# Cleanup script for L2-M6.3 — Helm on OpenShift
# Removes all resources created during this lesson

set -euo pipefail

echo "=== Cleaning up Helm on OpenShift lesson resources ==="

# Uninstall Helm releases
echo "--- Removing Helm releases ---"
helm uninstall my-web-app 2>/dev/null && echo "Removed release: my-web-app" || echo "Release my-web-app not found (skipping)"
helm uninstall nginx-test 2>/dev/null && echo "Removed release: nginx-test" || echo "Release nginx-test not found (skipping)"

# Remove custom HelmChartRepository (cluster-scoped, needs admin)
echo "--- Removing HelmChartRepository ---"
oc delete helmchartrepository bitnami 2>/dev/null && echo "Removed HelmChartRepository: bitnami" || echo "HelmChartRepository bitnami not found (skipping)"

# Remove project-scoped chart repo
echo "--- Removing ProjectHelmChartRepository ---"
oc delete projecthelmchartrepository team-charts 2>/dev/null && echo "Removed ProjectHelmChartRepository: team-charts" || echo "ProjectHelmChartRepository team-charts not found (skipping)"

# Remove any remaining labeled resources
echo "--- Removing labeled resources ---"
oc delete all -l tutorial-level=2,tutorial-module=M6 2>/dev/null || true

# Remove Helm repos from CLI
echo "--- Removing Helm CLI repos ---"
helm repo remove bitnami 2>/dev/null && echo "Removed Helm repo: bitnami" || echo "Helm repo bitnami not found (skipping)"

# Delete the project
echo "--- Deleting project ---"
oc delete project helm-demo 2>/dev/null && echo "Deleted project: helm-demo" || echo "Project helm-demo not found (skipping)"

echo ""
echo "=== Cleanup complete ==="
