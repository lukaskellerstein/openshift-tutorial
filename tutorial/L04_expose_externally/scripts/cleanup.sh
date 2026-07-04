#!/usr/bin/env bash
# L04 — Cleanup: remove Routes
set -euo pipefail

echo "=== L04 Cleanup ==="
oc project shopinsights

echo "Deleting Routes..."
oc delete route -l tutorial=personalized,lesson=04 2>/dev/null || true

echo ""
echo "=== Cleanup Complete ==="
