#!/usr/bin/env bash
# L02 — Cleanup: remove builds, buildconfigs, and imagestreams
set -euo pipefail

echo "=== L02 Cleanup ==="
oc project shopinsights

echo "Deleting BuildConfigs..."
oc delete buildconfig -l app=shopinsights 2>/dev/null || true

echo "Deleting Builds..."
oc delete builds --all 2>/dev/null || true

echo "Deleting ImageStreams..."
oc delete imagestream -l app=shopinsights 2>/dev/null || true

echo ""
echo "=== Cleanup Complete ==="
