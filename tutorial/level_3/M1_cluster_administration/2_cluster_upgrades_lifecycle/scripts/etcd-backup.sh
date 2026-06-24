#!/usr/bin/env bash
# =============================================================================
# etcd Backup Script
# =============================================================================
# Takes an etcd backup on the first available control plane node.
# This is a wrapper around the OpenShift cluster-backup.sh script
# that runs via `oc debug node/`.
#
# Usage: ./etcd-backup.sh [backup-label]
#
# Arguments:
#   backup-label  Optional label for the backup (default: "manual")
#
# The backup is stored on the control plane node at:
#   /home/core/etcd-backups/backup-<label>-<timestamp>/
#
# IMPORTANT: For production environments, implement a process to copy
# these backups to external storage (S3, NFS, etc.) for disaster recovery.
# =============================================================================

set -euo pipefail

LABEL="${1:-manual}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_NAME="backup-${LABEL}-${TIMESTAMP}"

echo "============================================="
echo "  etcd Backup"
echo "============================================="
echo ""

# Verify cluster-admin access
if ! oc auth can-i get nodes > /dev/null 2>&1; then
  echo "ERROR: This script requires cluster-admin privileges."
  echo "Run: oc login -u kubeadmin"
  exit 1
fi

# Find the first available master node
MASTER_NODE=$(oc get nodes -l node-role.kubernetes.io/master -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [[ -z "$MASTER_NODE" ]]; then
  echo "ERROR: Could not find a control plane node."
  exit 1
fi

echo "Target node: ${MASTER_NODE}"
echo "Backup name: ${BACKUP_NAME}"
echo "Backup path: /home/core/etcd-backups/${BACKUP_NAME}"
echo ""

# Verify etcd is healthy before backup
echo "Checking etcd health..."
ETCD_PODS=$(oc get pods -n openshift-etcd -l app=etcd --no-headers 2>/dev/null | grep -c Running || echo "0")
MASTER_COUNT=$(oc get nodes -l node-role.kubernetes.io/master --no-headers 2>/dev/null | wc -l | tr -d ' ')

if [[ "$ETCD_PODS" -lt "$MASTER_COUNT" ]]; then
  echo "WARNING: etcd has ${ETCD_PODS} running pods (expected: ${MASTER_COUNT})."
  echo "Backup may be inconsistent. Proceed anyway? (y/N)"
  read -r CONFIRM
  if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
    echo "Backup cancelled."
    exit 1
  fi
else
  echo "etcd healthy: ${ETCD_PODS} members running."
fi

echo ""
echo "Starting backup..."

# Run the backup on the master node via oc debug
oc debug "node/${MASTER_NODE}" -- chroot /host /bin/bash -c "
  mkdir -p /home/core/etcd-backups
  /usr/local/bin/cluster-backup.sh /home/core/etcd-backups/${BACKUP_NAME}
  echo ''
  echo 'Backup contents:'
  ls -lah /home/core/etcd-backups/${BACKUP_NAME}/
  echo ''
  echo 'Total backup size:'
  du -sh /home/core/etcd-backups/${BACKUP_NAME}/
"

BACKUP_EXIT=$?

echo ""
if [[ $BACKUP_EXIT -eq 0 ]]; then
  echo "============================================="
  echo "  Backup completed successfully"
  echo "============================================="
  echo ""
  echo "Backup location: ${MASTER_NODE}:/home/core/etcd-backups/${BACKUP_NAME}"
  echo ""
  echo "To restore from this backup (EMERGENCY ONLY):"
  echo "  oc debug node/${MASTER_NODE}"
  echo "  chroot /host"
  echo "  /usr/local/bin/cluster-restore.sh /home/core/etcd-backups/${BACKUP_NAME}"
  echo ""
  echo "IMPORTANT: Copy this backup to external storage for disaster recovery."
else
  echo "============================================="
  echo "  Backup FAILED"
  echo "============================================="
  echo "Check the output above for errors."
  exit 1
fi
