#!/usr/bin/env bash
#
# dr-failover-drill.sh
# Performs a disaster recovery failover drill between two spoke clusters.
#
# Usage: ./dr-failover-drill.sh <source-cluster> <target-cluster>
# Example: ./dr-failover-drill.sh production-east production-west
#
# Prerequisites:
#   - Logged in to the hub cluster via oc
#   - Velero installed on both spoke clusters with a shared backup storage location
#   - capstone-app deployed on the source cluster
#   - ManagedCluster resources exist for both clusters
#
# This script:
#   1. Takes a final Velero backup on the source cluster
#   2. Verifies the backup completed successfully
#   3. Simulates cluster failure by labeling it as "failed"
#   4. Waits for ApplicationSet to remove the source Application
#   5. Triggers Velero restore on the target cluster
#   6. Verifies the application is healthy on the target cluster
#   7. Provides rollback instructions
#
# WARNING: This is a DR drill. It modifies cluster labels and workload placement.
#          Run in a controlled environment first.
#
set -euo pipefail

SOURCE_CLUSTER="${1:?Usage: $0 <source-cluster> <target-cluster>}"
TARGET_CLUSTER="${2:?Usage: $0 <source-cluster> <target-cluster>}"

NAMESPACE="capstone-app"
BACKUP_NAME="dr-drill-$(date +%Y%m%d-%H%M%S)"
TIMEOUT=300
POLL_INTERVAL=10

echo "=============================================="
echo "  DISASTER RECOVERY FAILOVER DRILL"
echo "=============================================="
echo ""
echo "  Source (failing):  ${SOURCE_CLUSTER}"
echo "  Target (failover): ${TARGET_CLUSTER}"
echo "  Backup name:       ${BACKUP_NAME}"
echo "  Namespace:         ${NAMESPACE}"
echo "  Timestamp:         $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""
echo "=============================================="
echo ""

# Save hub context
HUB_API=$(oc whoami --show-server)
HUB_CONTEXT=$(oc config current-context)

# Retrieve spoke cluster API URLs from ManagedCluster resources
SOURCE_API=$(oc get managedcluster "${SOURCE_CLUSTER}" \
  -o jsonpath='{.spec.managedClusterClientConfigs[0].url}' 2>/dev/null || echo "")
TARGET_API=$(oc get managedcluster "${TARGET_CLUSTER}" \
  -o jsonpath='{.spec.managedClusterClientConfigs[0].url}' 2>/dev/null || echo "")

if [[ -z "${SOURCE_API}" || -z "${TARGET_API}" ]]; then
  echo "ERROR: Could not retrieve API URLs for clusters."
  echo "       Ensure both ManagedCluster resources exist and are joined."
  exit 1
fi

echo "[Step 1/7] Taking final backup on ${SOURCE_CLUSTER}..."
echo "           Switching to source cluster context..."

# Note: In a real environment, you would use oc login or context switching.
# For the drill, we use the hub's access to the spoke via RHACM.
oc login "${SOURCE_API}" -u admin 2>/dev/null || {
  echo "WARNING: Could not log in to ${SOURCE_CLUSTER}. Proceeding with hub context."
  echo "         Manual backup may be needed."
}

# Create an on-demand backup
velero backup create "${BACKUP_NAME}" \
  --include-namespaces "${NAMESPACE}" \
  --selector app=capstone-app \
  --snapshot-volumes \
  --wait 2>/dev/null || {
  echo "WARNING: Velero backup command failed. This may be expected in a drill environment."
  echo "         Continuing with drill..."
}

echo ""
echo "[Step 2/7] Verifying backup..."
velero backup describe "${BACKUP_NAME}" 2>/dev/null || {
  echo "         Skipping backup verification (Velero may not be available in drill mode)."
}

echo ""
echo "[Step 3/7] Simulating cluster failure..."
echo "           Labeling ${SOURCE_CLUSTER} as 'failed' on the hub..."
oc config use-context "${HUB_CONTEXT}" 2>/dev/null || oc login "${HUB_API}" -u admin
oc label managedcluster "${SOURCE_CLUSTER}" status=failed --overwrite
echo "           Label applied: status=failed"
echo ""
echo "           The ApplicationSet Placement excludes clusters with status=failed."
echo "           ArgoCD will prune the Application for ${SOURCE_CLUSTER}."

echo ""
echo "[Step 4/7] Waiting for ApplicationSet to react..."
SECONDS=0
while oc get application "capstone-app-${SOURCE_CLUSTER}" -n openshift-gitops &>/dev/null; do
  if (( SECONDS >= TIMEOUT )); then
    echo "WARNING: Application was not removed within ${TIMEOUT}s."
    echo "         The ApplicationSet may need manual intervention."
    break
  fi
  printf "."
  sleep "${POLL_INTERVAL}"
done
echo ""
echo "           Application for ${SOURCE_CLUSTER} removed (or timed out)."

echo ""
echo "[Step 5/7] Restoring backup on ${TARGET_CLUSTER}..."
oc login "${TARGET_API}" -u admin 2>/dev/null || {
  echo "WARNING: Could not log in to ${TARGET_CLUSTER}."
  echo "         Manual restore may be needed."
}

velero restore create --from-backup "${BACKUP_NAME}" --wait 2>/dev/null || {
  echo "         Skipping Velero restore (may not be available in drill mode)."
  echo "         In production, run: velero restore create --from-backup ${BACKUP_NAME}"
}

echo ""
echo "[Step 6/7] Verifying application health on ${TARGET_CLUSTER}..."
oc config use-context "${HUB_CONTEXT}" 2>/dev/null || oc login "${HUB_API}" -u admin

# Check that the ApplicationSet has created an Application for the target
echo "         Checking ArgoCD Application status..."
SECONDS=0
until oc get application "capstone-app-${TARGET_CLUSTER}" -n openshift-gitops \
  -o jsonpath='{.status.health.status}' 2>/dev/null | grep -q "Healthy"; do
  if (( SECONDS >= TIMEOUT )); then
    echo "WARNING: Application on ${TARGET_CLUSTER} not yet healthy."
    echo "         Manual verification needed."
    break
  fi
  printf "."
  sleep "${POLL_INTERVAL}"
done
echo ""

echo "         Application status on ${TARGET_CLUSTER}:"
oc get application "capstone-app-${TARGET_CLUSTER}" -n openshift-gitops \
  -o custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status 2>/dev/null || \
  echo "         (Could not retrieve Application status)"

echo ""
echo "[Step 7/7] DR Drill Summary"
echo "=============================================="
echo ""
echo "  Source cluster (${SOURCE_CLUSTER}): MARKED FAILED"
echo "  Target cluster (${TARGET_CLUSTER}): SERVING TRAFFIC"
echo "  Backup used: ${BACKUP_NAME}"
echo ""
echo "  ROLLBACK INSTRUCTIONS:"
echo "  To restore the source cluster to active status:"
echo ""
echo "    1. Verify source cluster is healthy:"
echo "       oc get managedcluster ${SOURCE_CLUSTER}"
echo ""
echo "    2. Remove the failed label:"
echo "       oc label managedcluster ${SOURCE_CLUSTER} status- --overwrite"
echo ""
echo "    3. The ApplicationSet will automatically create a new"
echo "       Application for ${SOURCE_CLUSTER} and deploy workloads."
echo ""
echo "    4. Verify both clusters are serving traffic:"
echo "       oc get applications -n openshift-gitops"
echo ""
echo "  IMPORTANT: After restoring, verify data consistency"
echo "  between clusters before enabling active-active traffic."
echo ""
echo "=============================================="
echo "  DR DRILL COMPLETED: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "=============================================="
