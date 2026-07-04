#!/usr/bin/env bash
# L01 — Projects: create shopinsights + dev/staging projects with quotas
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LESSON_DIR="$(dirname "$SCRIPT_DIR")"

step() { echo "" && echo "=== Step $1: $2 ===" && echo ""; }

# --- Step 1: Create the main ShopInsights project ---
step 1 "Create the main ShopInsights project"
oc new-project shopinsights \
  --display-name="ShopInsights" \
  --description="Main project for the ShopInsights tutorial microservices" 2>/dev/null \
  || oc project shopinsights
echo "Active project: $(oc project -q)"

# --- Step 2: Create the Dev project ---
step 2 "Create the Dev project"
oc new-project shopinsights-dev \
  --display-name="ShopInsights Dev" \
  --description="Development environment for ShopInsights microservices" 2>/dev/null \
  || echo "shopinsights-dev already exists"

# --- Step 3: Create the Staging project ---
step 3 "Create the Staging project"
oc new-project shopinsights-staging \
  --display-name="ShopInsights Staging" \
  --description="Staging environment for ShopInsights — resource-constrained to mirror production limits" 2>/dev/null \
  || echo "shopinsights-staging already exists"

# --- Step 4: Apply ResourceQuota to Staging ---
step 4 "Apply ResourceQuota to Staging"
if oc apply -f "$LESSON_DIR/manifests/resource-quota.yaml" 2>/dev/null; then
  oc describe quota staging-quota -n shopinsights-staging
else
  echo "SKIPPED: ResourceQuota requires cluster-admin privileges."
  echo "  Run: oc login -u kubeadmin -p <password> https://api.crc.testing:6443"
  echo "  Then re-run this script, or apply manually:"
  echo "    oc apply -f manifests/resource-quota.yaml"
fi

# --- Step 5: Apply LimitRange to Staging ---
step 5 "Apply LimitRange to Staging"
if oc apply -f "$LESSON_DIR/manifests/limit-range.yaml" 2>/dev/null; then
  oc describe limitrange staging-limits -n shopinsights-staging
else
  echo "SKIPPED: LimitRange requires cluster-admin privileges."
  echo "  Same fix as Step 4 — log in as kubeadmin first."
fi

# --- Step 6: Switch back to main project ---
step 6 "Switch back to shopinsights"
oc project shopinsights

echo ""
echo "=== L01 Complete ==="
echo "Projects created: shopinsights, shopinsights-dev, shopinsights-staging"
echo "Next: cd ../L02_builds_and_images && ./scripts/run.sh"
