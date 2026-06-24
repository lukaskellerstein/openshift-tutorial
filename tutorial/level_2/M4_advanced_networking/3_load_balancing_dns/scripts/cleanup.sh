#!/bin/bash
# Cleanup script for L2-M4.3 — Load Balancing & DNS
# Removes all resources created during the lesson

set -euo pipefail

echo "=== Cleaning up L2-M4.3 Load Balancing & DNS resources ==="

# Remove demo project
echo "Removing demo project..."
oc delete project l2-m4-lb-demo --ignore-not-found=true

# Remove MetalLB configuration
echo "Removing MetalLB configuration..."
oc delete l2advertisement demo-l2adv -n metallb-system --ignore-not-found=true
oc delete bgpadvertisement demo-bgp-adv -n metallb-system --ignore-not-found=true
oc delete bgppeer upstream-router -n metallb-system --ignore-not-found=true
oc delete ipaddresspool demo-pool -n metallb-system --ignore-not-found=true

# Remove MetalLB instance
echo "Removing MetalLB instance..."
oc delete metallb metallb -n metallb-system --ignore-not-found=true

# Remove External DNS resources
echo "Removing External DNS resources..."
oc delete externaldns demo-dns -n external-dns-operator --ignore-not-found=true
oc delete externaldns demo-dns-services -n external-dns-operator --ignore-not-found=true
oc delete secret aws-dns-credentials -n external-dns-operator --ignore-not-found=true
oc delete secret azure-dns-credentials -n external-dns-operator --ignore-not-found=true

# Remove operators (optional — uncomment to fully remove)
# echo "Removing MetalLB operator..."
# oc delete subscription metallb-operator -n metallb-system --ignore-not-found=true
# oc delete csv -n metallb-system -l operators.coreos.com/metallb-operator.metallb-system --ignore-not-found=true
# oc delete namespace metallb-system --ignore-not-found=true

# echo "Removing External DNS operator..."
# oc delete subscription external-dns-operator -n external-dns-operator --ignore-not-found=true
# oc delete csv -n external-dns-operator -l operators.coreos.com/external-dns-operator.external-dns-operator --ignore-not-found=true
# oc delete namespace external-dns-operator --ignore-not-found=true

echo "=== Cleanup complete ==="
