#!/usr/bin/env bash
# cleanup.sh — Remove all resources created by the L3-M4.3 lesson.
# Run this when you are done with the lesson to free cluster resources.
set -euo pipefail

echo "Cleaning up L3-M4.3 Stateful Workloads at Scale..."
echo ""

# Switch to the correct project
oc project stateful-workloads 2>/dev/null || {
  echo "Project 'stateful-workloads' not found. Nothing to clean up."
  exit 0
}

# Delete Kafka resources (operator will clean up child resources)
echo "Deleting Kafka resources..."
oc delete kafkatopic test-throughput --ignore-not-found
oc delete kafka kafka-production --ignore-not-found

# Delete PostgreSQL resources
echo "Deleting PostgreSQL resources..."
oc delete postgrescluster pg-restored --ignore-not-found
oc delete postgrescluster pg-production --ignore-not-found

# Wait for operators to clean up child resources
echo "Waiting for operator cleanup (15s)..."
sleep 15

# Delete the base StatefulSet
echo "Deleting Redis StatefulSet..."
oc delete statefulset redis-cluster --ignore-not-found
oc delete service redis-cluster redis-cluster-client --ignore-not-found
oc delete pdb redis-cluster-pdb --ignore-not-found

# Delete remaining PVCs (operators leave these intentionally)
echo "Deleting PVCs..."
oc delete pvc -l app=redis-cluster --ignore-not-found
oc delete pvc -l postgres-operator.crunchydata.com/cluster=pg-production --ignore-not-found
oc delete pvc -l postgres-operator.crunchydata.com/cluster=pg-restored --ignore-not-found
oc delete pvc -l strimzi.io/cluster=kafka-production --ignore-not-found

# Delete the StorageClass (if created)
echo "Deleting custom StorageClass..."
oc delete storageclass high-iops-ssd --ignore-not-found

# Delete the project
echo "Deleting project..."
oc delete project stateful-workloads --ignore-not-found

echo ""
echo "Cleanup complete."
echo ""
echo "Note: Operator subscriptions (PGO, Strimzi) are cluster-wide"
echo "and were NOT removed. To uninstall them:"
echo "  oc delete subscription crunchy-postgres-operator -n openshift-operators"
echo "  oc delete subscription strimzi-kafka-operator -n openshift-operators"
echo "  oc delete csv -n openshift-operators -l operators.coreos.com/crunchy-postgres-operator.openshift-operators="
echo "  oc delete csv -n openshift-operators -l operators.coreos.com/strimzi-kafka-operator.openshift-operators="
