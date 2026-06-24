#!/usr/bin/env bash
# explore-olm.sh -- Explore the OLM and Operator ecosystem on an OpenShift cluster.
# This script runs all the exploration commands from L2-M2.1.
# Usage: ./scripts/explore-olm.sh
#
# Prerequisites:
#   - Logged in as kubeadmin (oc login -u kubeadmin ...)
#   - OpenShift cluster running (CRC or other)

set -euo pipefail

echo "========================================="
echo "  OpenShift Operator Framework Explorer"
echo "========================================="
echo ""

# --- Cluster Operators ---
echo "--- Cluster Operators ---"
echo ""
oc get clusteroperators
echo ""

TOTAL_CO=$(oc get clusteroperators --no-headers | wc -l | tr -d ' ')
HEALTHY_CO=$(oc get clusteroperators --no-headers | awk '$3=="True" && $4=="False" && $5=="False"' | wc -l | tr -d ' ')
echo "Cluster Operators: ${HEALTHY_CO}/${TOTAL_CO} healthy"
echo ""

# --- OLM Pods ---
echo "--- OLM Components ---"
echo ""
oc get pods -n openshift-operator-lifecycle-manager
echo ""

# --- CatalogSources ---
echo "--- CatalogSources (Operator Repositories) ---"
echo ""
oc get catalogsources -n openshift-marketplace
echo ""

# --- Available Operators ---
echo "--- Available Operators (PackageManifests) ---"
echo ""
TOTAL_PKG=$(oc get packagemanifests --no-headers 2>/dev/null | wc -l | tr -d ' ')
echo "Total operators available: ${TOTAL_PKG}"
echo ""

# --- Show operators by catalog source ---
echo "--- Operators by Catalog Source ---"
echo ""
for src in redhat-operators certified-operators community-operators redhat-marketplace; do
  count=$(oc get packagemanifests --no-headers -l "catalog=${src}" 2>/dev/null | wc -l | tr -d ' ')
  echo "  ${src}: ${count} operators"
done
echo ""

# --- Installed Subscriptions ---
echo "--- Installed Subscriptions ---"
echo ""
oc get subscriptions -A 2>/dev/null || echo "  No subscriptions found"
echo ""

# --- Installed CSVs ---
echo "--- Installed ClusterServiceVersions ---"
echo ""
oc get csv -A 2>/dev/null || echo "  No CSVs found"
echo ""

# --- CRD Count ---
echo "--- Custom Resource Definitions ---"
echo ""
CRD_COUNT=$(oc get crds --no-headers | wc -l | tr -d ' ')
echo "Total CRDs on cluster: ${CRD_COUNT}"
echo ""

# --- Summary ---
echo "========================================="
echo "  Summary"
echo "========================================="
echo "  Cluster Operators:    ${HEALTHY_CO}/${TOTAL_CO} healthy"
echo "  Available Operators:  ${TOTAL_PKG}"
echo "  Total CRDs:           ${CRD_COUNT}"
echo "========================================="
