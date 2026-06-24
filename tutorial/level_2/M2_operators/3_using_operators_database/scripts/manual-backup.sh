#!/usr/bin/env bash
# manual-backup.sh — Trigger a manual pgBackRest backup for the hippo cluster
#
# Usage: ./scripts/manual-backup.sh [full|incr|diff]
# Default: full
#
# This script annotates the PostgresCluster CR to trigger an immediate backup.
# The CrunchyData operator watches for this annotation and initiates the backup.

set -euo pipefail

BACKUP_TYPE="${1:-full}"
CLUSTER_NAME="hippo"
TIMESTAMP=$(date +%F_%H%M%S)

echo "=== Triggering ${BACKUP_TYPE} backup for cluster '${CLUSTER_NAME}' ==="
echo "Timestamp: ${TIMESTAMP}"

# Trigger the backup via annotation
oc annotate postgrescluster "${CLUSTER_NAME}" \
  postgres-operator.crunchydata.com/pgbackrest-backup="${TIMESTAMP}" \
  --overwrite

echo ""
echo "Backup triggered. Monitor progress with:"
echo "  oc describe postgrescluster ${CLUSTER_NAME} | grep -A 10 'Pgbackrest'"
echo ""
echo "Check backup jobs:"
echo "  oc get jobs -l postgres-operator.crunchydata.com/cluster=${CLUSTER_NAME}"
echo ""
echo "View pgBackRest info from within the pod:"
echo "  oc exec -it \$(oc get pods -l postgres-operator.crunchydata.com/cluster=${CLUSTER_NAME},postgres-operator.crunchydata.com/role=master -o name | head -1) -- pgbackrest info"
