#!/usr/bin/env bash
# L03 — Cleanup: remove deployments, services, configmaps, secrets, PVCs
set -euo pipefail

echo "=== L03 Cleanup ==="
oc project shopinsights

echo "Deleting lesson resources..."
oc delete all -l tutorial=personalized,lesson=03 2>/dev/null || true
oc delete configmap shopinsights-config 2>/dev/null || true
oc delete secret shopinsights-secrets 2>/dev/null || true
oc delete pvc -l tutorial=personalized,lesson=03 2>/dev/null || true

echo ""
echo "=== Cleanup Complete ==="
