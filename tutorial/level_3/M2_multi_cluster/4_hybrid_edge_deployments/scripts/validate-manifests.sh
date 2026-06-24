#!/usr/bin/env bash
# validate-manifests.sh
# Validates all YAML manifests in this lesson using oc/kubectl dry-run.
# Run this before committing changes to verify manifest correctness.
#
# Usage: ./scripts/validate-manifests.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_DIR="${SCRIPT_DIR}/../manifests"

echo "=== Validating Hybrid & Edge Deployment Manifests ==="
echo ""

# Track results
PASS=0
FAIL=0
SKIP=0

validate_manifest() {
  local file="$1"
  local basename
  basename=$(basename "$file")

  # Skip files that use CRDs not available on a standard cluster
  case "$basename" in
    sno-siteconfig.yaml|edge-policy-gen-template.yaml|sno-install-config.yaml)
      echo "SKIP: ${basename} (requires RHACM/ZTP CRDs)"
      SKIP=$((SKIP + 1))
      return
      ;;
    remote-worker-machineset.yaml)
      echo "SKIP: ${basename} (requires Machine API)"
      SKIP=$((SKIP + 1))
      return
      ;;
    sno-performance-profile.yaml)
      echo "SKIP: ${basename} (requires Performance Addon Operator CRDs)"
      SKIP=$((SKIP + 1))
      return
      ;;
    remote-worker-kubelet-config.yaml)
      echo "SKIP: ${basename} (requires MCO CRDs)"
      SKIP=$((SKIP + 1))
      return
      ;;
  esac

  if oc apply --dry-run=client -f "$file" > /dev/null 2>&1; then
    echo "PASS: ${basename}"
    PASS=$((PASS + 1))
  elif kubectl apply --dry-run=client -f "$file" > /dev/null 2>&1; then
    echo "PASS: ${basename} (via kubectl)"
    PASS=$((PASS + 1))
  else
    echo "FAIL: ${basename}"
    oc apply --dry-run=client -f "$file" 2>&1 | sed 's/^/  /'
    FAIL=$((FAIL + 1))
  fi
}

for manifest in "${MANIFEST_DIR}"/*.yaml; do
  if [ -f "$manifest" ]; then
    validate_manifest "$manifest"
  fi
done

echo ""
echo "=== Results ==="
echo "Passed: ${PASS}"
echo "Failed: ${FAIL}"
echo "Skipped: ${SKIP}"
echo ""

if [ "$FAIL" -gt 0 ]; then
  echo "Some manifests failed validation. Review errors above."
  exit 1
else
  echo "All validatable manifests passed."
  exit 0
fi
