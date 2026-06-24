#!/bin/bash
# Cleanup script for L2-M4.1 — Egress & Ingress Control
# Removes all resources created during the lesson

set -e

echo "=== Cleaning up L2-M4.1 Egress & Ingress Control ==="

# Switch to the lesson project
oc project egress-demo 2>/dev/null || true

# Delete the test pod
echo "Deleting test pod..."
oc delete pod egress-test --ignore-not-found

# Delete EgressFirewall
echo "Deleting EgressFirewall..."
oc delete egressfirewall default --ignore-not-found

# Delete NetworkPolicy
echo "Deleting NetworkPolicy..."
oc delete networkpolicy restrict-egress --ignore-not-found

# Delete EgressIP (requires cluster-admin)
echo "Deleting EgressIP..."
oc delete egressip egress-demo-ip --ignore-not-found 2>/dev/null || echo "  (Skipped — requires cluster-admin)"

# Remove node label if it was added (requires cluster-admin)
echo "Removing node egress-assignable label..."
NODE=$(oc get nodes -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$NODE" ]; then
  oc label node "$NODE" k8s.ovn.org/egress-assignable- 2>/dev/null || echo "  (Skipped — requires cluster-admin or label not present)"
fi

# Remove namespace label
echo "Removing namespace egress-ip label..."
oc label namespace egress-demo egress-ip- 2>/dev/null || true

# Delete the project
echo "Deleting project..."
oc delete project egress-demo --ignore-not-found

echo ""
echo "=== Cleanup complete ==="
