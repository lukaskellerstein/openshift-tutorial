#!/usr/bin/env bash
# L01 — Cleanup: remove dev/staging projects (keep shopinsights for other lessons)
set -euo pipefail

echo "=== L01 Cleanup ==="
echo "Deleting dev and staging projects (keeping shopinsights)..."

oc delete project shopinsights-dev 2>/dev/null || echo "shopinsights-dev not found"
oc delete project shopinsights-staging 2>/dev/null || echo "shopinsights-staging not found"

oc project shopinsights 2>/dev/null || true

echo ""
echo "=== Cleanup Complete ==="
echo "Kept: shopinsights (used by subsequent lessons)"
echo "Deleted: shopinsights-dev, shopinsights-staging"
