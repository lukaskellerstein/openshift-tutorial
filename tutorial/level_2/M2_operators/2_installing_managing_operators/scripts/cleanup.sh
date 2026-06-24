#!/usr/bin/env bash
# cleanup.sh — Remove all resources created by L2-M2.2
#
# Usage: bash scripts/cleanup.sh

set -euo pipefail

echo "=== Cleaning up L2-M2.2 — Installing & Managing Operators ==="
echo ""

# Remove manual-approval namespace and its resources
echo "Removing manual-approval demo (etcd-demo)..."
if oc get namespace etcd-demo &>/dev/null; then
  oc delete subscription etcd -n etcd-demo --ignore-not-found
  oc delete csv --all -n etcd-demo --ignore-not-found
  oc delete operatorgroup etcd-demo-og -n etcd-demo --ignore-not-found
  oc delete project etcd-demo
  echo "  etcd-demo namespace deleted."
else
  echo "  etcd-demo namespace not found, skipping."
fi
echo ""

# Remove automatic-approval namespace and its resources
echo "Removing automatic-approval demo (etcd-auto-demo)..."
if oc get namespace etcd-auto-demo &>/dev/null; then
  oc delete subscription etcd -n etcd-auto-demo --ignore-not-found
  oc delete csv --all -n etcd-auto-demo --ignore-not-found
  oc delete operatorgroup etcd-auto-demo-og -n etcd-auto-demo --ignore-not-found
  oc delete project etcd-auto-demo
  echo "  etcd-auto-demo namespace deleted."
else
  echo "  etcd-auto-demo namespace not found, skipping."
fi
echo ""

# Clean up cluster-scoped CRDs (only if no other installations use them)
echo "Cleaning up etcd CRDs (if not used elsewhere)..."
for crd in etcdclusters.etcd.database.coreos.com etcdbackups.etcd.database.coreos.com etcdrestores.etcd.database.coreos.com; do
  if oc get crd "${crd}" &>/dev/null; then
    # Check if any CSV still references this CRD
    REFS=$(oc get csv --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}{"\n"}{end}' 2>/dev/null | wc -l)
    if [[ ${REFS} -le 0 ]]; then
      oc delete crd "${crd}" --ignore-not-found
      echo "  Deleted CRD: ${crd}"
    else
      echo "  Skipping CRD ${crd} (may still be in use)."
    fi
  fi
done

echo ""
echo "=== Cleanup complete ==="
