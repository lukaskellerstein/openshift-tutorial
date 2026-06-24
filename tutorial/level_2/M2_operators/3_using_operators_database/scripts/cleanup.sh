#!/usr/bin/env bash
# cleanup.sh — Remove all resources created in this lesson
#
# Usage: ./scripts/cleanup.sh
#
# Removes: PostgresClusters, test app, manual K8s StatefulSet resources, and the project.

set -euo pipefail

PROJECT="postgres-operator-demo"

echo "=== Cleaning up lesson resources ==="
echo ""

# 1. Delete the restored cluster (if it exists)
echo "--- Deleting restored PostgresCluster ---"
oc delete postgrescluster hippo-restored --ignore-not-found 2>/dev/null || true
echo ""

# 2. Delete the test application
echo "--- Deleting test application ---"
oc delete deployment pg-test-app --ignore-not-found 2>/dev/null || true
echo ""

# 3. Delete the primary PostgresCluster
echo "--- Deleting primary PostgresCluster ---"
oc delete postgrescluster hippo --ignore-not-found 2>/dev/null || true
echo ""

# 4. Delete manual K8s StatefulSet resources
echo "--- Deleting manual K8s StatefulSet resources ---"
oc delete statefulset postgres --ignore-not-found 2>/dev/null || true
oc delete service postgres --ignore-not-found 2>/dev/null || true
oc delete secret postgres-credentials --ignore-not-found 2>/dev/null || true
oc delete pvc -l app=postgres --ignore-not-found 2>/dev/null || true
echo ""

# 5. Wait for PVCs to be released
echo "--- Waiting for PVCs to be released ---"
oc delete pvc -l "postgres-operator.crunchydata.com/cluster=hippo" --ignore-not-found 2>/dev/null || true
oc delete pvc -l "postgres-operator.crunchydata.com/cluster=hippo-restored" --ignore-not-found 2>/dev/null || true
echo ""

# 6. Delete the project
echo "--- Deleting project ---"
oc delete project "${PROJECT}" --ignore-not-found 2>/dev/null || true
echo ""

echo "=== Cleanup complete ==="
echo ""
echo "Note: The CrunchyData operator itself remains installed cluster-wide."
echo "To remove it, delete the Subscription and CSV:"
echo "  oc delete subscription crunchy-postgres-operator -n openshift-operators"
echo "  oc delete csv -n openshift-operators -l operators.coreos.com/crunchy-postgres-operator.openshift-operators"
