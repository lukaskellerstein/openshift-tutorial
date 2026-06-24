#!/usr/bin/env bash
# manual-backup.sh
#
# Perform a manual etcd backup on an OpenShift cluster.
# Requires: cluster-admin privileges, oc CLI authenticated.
#
# Usage: ./manual-backup.sh [backup-directory]
#
# Default backup directory: /home/core/assets/backup
#
# This script:
#   1. Identifies a healthy control plane node
#   2. Runs cluster-backup.sh on that node via oc debug
#   3. Reports the backup location and contents

set -euo pipefail

BACKUP_DIR="${1:-/home/core/assets/backup}"

echo "============================================"
echo " OpenShift etcd Manual Backup"
echo " $(date)"
echo "============================================"
echo ""

# Verify cluster-admin access
echo "[1/4] Verifying cluster-admin access..."
if ! oc whoami > /dev/null 2>&1; then
  echo "ERROR: Not logged in. Run 'oc login' first."
  exit 1
fi

CURRENT_USER=$(oc whoami)
echo "  Logged in as: ${CURRENT_USER}"

# Identify a healthy control plane node
echo ""
echo "[2/4] Identifying a healthy control plane node..."
MASTER_NODE=$(oc get nodes -l node-role.kubernetes.io/master -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [[ -z "${MASTER_NODE}" ]]; then
  echo "ERROR: No control plane nodes found. Are you connected to a cluster?"
  exit 1
fi

MASTER_STATUS=$(oc get node "${MASTER_NODE}" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
if [[ "${MASTER_STATUS}" != "True" ]]; then
  echo "WARNING: Node ${MASTER_NODE} is not Ready. Attempting to find another..."
  MASTER_NODE=$(oc get nodes -l node-role.kubernetes.io/master -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}' | grep True | head -1 | cut -f1)
  if [[ -z "${MASTER_NODE}" ]]; then
    echo "ERROR: No Ready control plane nodes found!"
    exit 1
  fi
fi

echo "  Selected node: ${MASTER_NODE}"

# Run the backup
echo ""
echo "[3/4] Running etcd backup on ${MASTER_NODE}..."
echo "  Backup directory: ${BACKUP_DIR}"
echo "  This may take 1-3 minutes..."
echo ""

oc debug "node/${MASTER_NODE}" -- bash -c "
  chroot /host bash -c '
    mkdir -p ${BACKUP_DIR}
    /usr/local/bin/cluster-backup.sh ${BACKUP_DIR}
    echo \"\"
    echo \"Backup contents:\"
    ls -lah ${BACKUP_DIR}/
  '
"

BACKUP_EXIT=$?

# Report results
echo ""
echo "[4/4] Backup result..."
if [[ ${BACKUP_EXIT} -eq 0 ]]; then
  echo "  SUCCESS: etcd backup completed on ${MASTER_NODE}"
  echo "  Location: ${MASTER_NODE}:${BACKUP_DIR}/"
  echo ""
  echo "  To copy the backup off the node:"
  echo "    oc debug node/${MASTER_NODE} -- cat /host${BACKUP_DIR}/snapshot_*.db > snapshot.db"
  echo "    oc debug node/${MASTER_NODE} -- cat /host${BACKUP_DIR}/static_kuberesources_*.tar.gz > static_kuberesources.tar.gz"
  echo ""
  echo "  IMPORTANT: Store backups in a secure, off-cluster location."
  echo "  Recommended: encrypted S3 bucket, NFS share, or backup appliance."
else
  echo "  FAILED: etcd backup failed with exit code ${BACKUP_EXIT}"
  echo "  Check the output above for errors."
  echo "  Common issues:"
  echo "    - Insufficient disk space on the control plane node"
  echo "    - etcd is unhealthy (run etcd-health-check.sh first)"
  echo "    - Permission denied (need cluster-admin)"
  exit 1
fi
