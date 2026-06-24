#!/usr/bin/env bash
# =============================================================================
# DR Drill Script — Disaster Recovery validation for OpenShift
# =============================================================================
# This script performs an end-to-end DR drill:
#   1. Deploys a test application with persistent data
#   2. Writes a unique marker to verify data integrity
#   3. Creates a Velero backup
#   4. Deletes the test namespace (simulates disaster)
#   5. Restores from backup
#   6. Verifies application health and data integrity
#   7. Reports RTO (elapsed restore time) and backup age (RPO indicator)
#   8. Cleans up
#
# Prerequisites:
#   - cluster-admin access
#   - OADP operator installed and configured
#   - BackupStorageLocation available
#
# Usage:
#   bash scripts/dr-drill.sh
# =============================================================================

set -euo pipefail

NAMESPACE="dr-drill-$(date +%s)"
BACKUP_NAME="dr-drill-backup-$(date +%Y%m%d-%H%M%S)"
RESTORE_NAME="dr-drill-restore-$(date +%Y%m%d-%H%M%S)"
OADP_NAMESPACE="openshift-adp"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_DIR="${SCRIPT_DIR}/../manifests"
TIMEOUT=300  # 5 minutes

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $(date '+%H:%M:%S') $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $(date '+%H:%M:%S') $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $(date '+%H:%M:%S') $*"; }

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------
log_info "=== DR Drill Starting ==="
log_info "Namespace: ${NAMESPACE}"
log_info "Running preflight checks..."

if ! oc whoami &>/dev/null; then
  log_error "Not logged in to OpenShift. Run 'oc login' first."
  exit 1
fi

CURRENT_USER=$(oc whoami)
log_info "Logged in as: ${CURRENT_USER}"

if ! oc get dataprotectionapplication -n "${OADP_NAMESPACE}" &>/dev/null; then
  log_error "OADP is not installed in ${OADP_NAMESPACE}. Install OADP first."
  exit 1
fi

BSL_PHASE=$(oc get backupstoragelocations -n "${OADP_NAMESPACE}" -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "Unknown")
if [ "${BSL_PHASE}" != "Available" ]; then
  log_error "BackupStorageLocation is not Available (phase: ${BSL_PHASE}). Fix storage before running DR drill."
  exit 1
fi

log_info "Preflight checks passed."

# ---------------------------------------------------------------------------
# Step 1: Deploy test application
# ---------------------------------------------------------------------------
log_info "Step 1: Deploying test application to namespace ${NAMESPACE}..."
DEPLOY_START=$(date +%s)

oc new-project "${NAMESPACE}" --display-name="DR Drill Test" || true

# Create a simple deployment with a ConfigMap marker
cat <<EOF | oc apply -n "${NAMESPACE}" -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: dr-drill-marker
  namespace: ${NAMESPACE}
  labels:
    app: dr-drill
    tutorial-level: "3"
    tutorial-module: "M3"
data:
  DRILL_ID: "${BACKUP_NAME}"
  DRILL_TIMESTAMP: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  INTEGRITY_CHECK: "DR-DRILL-INTEGRITY-MARKER-$(date +%s)"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dr-drill-app
  namespace: ${NAMESPACE}
  labels:
    app: dr-drill
    tutorial-level: "3"
    tutorial-module: "M3"
spec:
  replicas: 1
  selector:
    matchLabels:
      app: dr-drill
  template:
    metadata:
      labels:
        app: dr-drill
    spec:
      containers:
        - name: nginx
          image: registry.access.redhat.com/ubi9/nginx-122:latest
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              cpu: 200m
              memory: 128Mi
          readinessProbe:
            httpGet:
              path: /
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: dr-drill-app
  namespace: ${NAMESPACE}
  labels:
    app: dr-drill
spec:
  selector:
    app: dr-drill
  ports:
    - port: 8080
      targetPort: 8080
---
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: dr-drill-app
  namespace: ${NAMESPACE}
  labels:
    app: dr-drill
spec:
  to:
    kind: Service
    name: dr-drill-app
  port:
    targetPort: 8080
  tls:
    termination: edge
EOF

# Wait for deployment to be ready
log_info "Waiting for deployment to be ready..."
oc rollout status deployment/dr-drill-app -n "${NAMESPACE}" --timeout="${TIMEOUT}s"

# Record the integrity marker for later verification
INTEGRITY_MARKER=$(oc get configmap dr-drill-marker -n "${NAMESPACE}" -o jsonpath='{.data.INTEGRITY_CHECK}')
log_info "Integrity marker: ${INTEGRITY_MARKER}"

DEPLOY_END=$(date +%s)
DEPLOY_TIME=$((DEPLOY_END - DEPLOY_START))
log_info "Application deployed in ${DEPLOY_TIME}s."

# ---------------------------------------------------------------------------
# Step 2: Create Velero backup
# ---------------------------------------------------------------------------
log_info "Step 2: Creating Velero backup ${BACKUP_NAME}..."
BACKUP_START=$(date +%s)

BSL_NAME=$(oc get backupstoragelocations -n "${OADP_NAMESPACE}" -o jsonpath='{.items[0].metadata.name}')

cat <<EOF | oc apply -f -
apiVersion: velero.io/v1
kind: Backup
metadata:
  name: ${BACKUP_NAME}
  namespace: ${OADP_NAMESPACE}
spec:
  includedNamespaces:
    - ${NAMESPACE}
  storageLocation: ${BSL_NAME}
  ttl: 24h
  defaultVolumesToFsBackup: true
EOF

# Wait for backup to complete
log_info "Waiting for backup to complete..."
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
  BACKUP_PHASE=$(oc get backup "${BACKUP_NAME}" -n "${OADP_NAMESPACE}" -o jsonpath='{.status.phase}' 2>/dev/null || echo "Pending")
  if [ "${BACKUP_PHASE}" = "Completed" ]; then
    break
  elif [ "${BACKUP_PHASE}" = "Failed" ] || [ "${BACKUP_PHASE}" = "PartiallyFailed" ]; then
    log_error "Backup failed with phase: ${BACKUP_PHASE}"
    oc describe backup "${BACKUP_NAME}" -n "${OADP_NAMESPACE}"
    exit 1
  fi
  sleep 5
  ELAPSED=$((ELAPSED + 5))
done

if [ "${BACKUP_PHASE}" != "Completed" ]; then
  log_error "Backup did not complete within ${TIMEOUT}s (phase: ${BACKUP_PHASE})"
  exit 1
fi

BACKUP_END=$(date +%s)
BACKUP_TIME=$((BACKUP_END - BACKUP_START))
log_info "Backup completed in ${BACKUP_TIME}s."

# ---------------------------------------------------------------------------
# Step 3: Simulate disaster — delete the namespace
# ---------------------------------------------------------------------------
log_info "Step 3: Simulating disaster — deleting namespace ${NAMESPACE}..."
oc delete project "${NAMESPACE}" --wait=true

# Verify namespace is gone
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
  if ! oc get project "${NAMESPACE}" &>/dev/null; then
    break
  fi
  sleep 5
  ELAPSED=$((ELAPSED + 5))
done

if oc get project "${NAMESPACE}" &>/dev/null; then
  log_error "Namespace ${NAMESPACE} still exists after ${TIMEOUT}s"
  exit 1
fi

log_info "Namespace deleted. Application is gone."

# ---------------------------------------------------------------------------
# Step 4: Restore from backup
# ---------------------------------------------------------------------------
log_info "Step 4: Restoring from backup ${BACKUP_NAME}..."
RESTORE_START=$(date +%s)

cat <<EOF | oc apply -f -
apiVersion: velero.io/v1
kind: Restore
metadata:
  name: ${RESTORE_NAME}
  namespace: ${OADP_NAMESPACE}
spec:
  backupName: ${BACKUP_NAME}
  includedNamespaces:
    - ${NAMESPACE}
  restorePVs: true
EOF

# Wait for restore to complete
log_info "Waiting for restore to complete..."
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
  RESTORE_PHASE=$(oc get restore "${RESTORE_NAME}" -n "${OADP_NAMESPACE}" -o jsonpath='{.status.phase}' 2>/dev/null || echo "Pending")
  if [ "${RESTORE_PHASE}" = "Completed" ]; then
    break
  elif [ "${RESTORE_PHASE}" = "Failed" ] || [ "${RESTORE_PHASE}" = "PartiallyFailed" ]; then
    log_error "Restore failed with phase: ${RESTORE_PHASE}"
    oc describe restore "${RESTORE_NAME}" -n "${OADP_NAMESPACE}"
    exit 1
  fi
  sleep 5
  ELAPSED=$((ELAPSED + 5))
done

if [ "${RESTORE_PHASE}" != "Completed" ]; then
  log_error "Restore did not complete within ${TIMEOUT}s (phase: ${RESTORE_PHASE})"
  exit 1
fi

# Wait for the deployment to be ready after restore
log_info "Waiting for application to be ready after restore..."
oc rollout status deployment/dr-drill-app -n "${NAMESPACE}" --timeout="${TIMEOUT}s"

RESTORE_END=$(date +%s)
RESTORE_TIME=$((RESTORE_END - RESTORE_START))
log_info "Restore completed in ${RESTORE_TIME}s."

# ---------------------------------------------------------------------------
# Step 5: Verify data integrity
# ---------------------------------------------------------------------------
log_info "Step 5: Verifying data integrity..."
VERIFICATION_PASSED=true

# Check ConfigMap integrity marker
RESTORED_MARKER=$(oc get configmap dr-drill-marker -n "${NAMESPACE}" -o jsonpath='{.data.INTEGRITY_CHECK}' 2>/dev/null || echo "MISSING")
if [ "${RESTORED_MARKER}" = "${INTEGRITY_MARKER}" ]; then
  log_info "ConfigMap integrity check: PASSED"
else
  log_error "ConfigMap integrity check: FAILED (expected: ${INTEGRITY_MARKER}, got: ${RESTORED_MARKER})"
  VERIFICATION_PASSED=false
fi

# Check Route exists
if oc get route dr-drill-app -n "${NAMESPACE}" &>/dev/null; then
  log_info "Route restored: PASSED"
else
  log_error "Route restored: FAILED"
  VERIFICATION_PASSED=false
fi

# Check pods are running
READY_PODS=$(oc get pods -n "${NAMESPACE}" -l app=dr-drill --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "${READY_PODS}" -ge 1 ]; then
  log_info "Pod health check: PASSED (${READY_PODS} running)"
else
  log_error "Pod health check: FAILED (${READY_PODS} running, expected >= 1)"
  VERIFICATION_PASSED=false
fi

# ---------------------------------------------------------------------------
# Step 6: Report results
# ---------------------------------------------------------------------------
TOTAL_TIME=$((RESTORE_END - BACKUP_START))

echo ""
echo "============================================================"
echo "  DR DRILL RESULTS"
echo "============================================================"
echo ""
echo "  Namespace:       ${NAMESPACE}"
echo "  Backup name:     ${BACKUP_NAME}"
echo "  Restore name:    ${RESTORE_NAME}"
echo ""
echo "  Deploy time:     ${DEPLOY_TIME}s"
echo "  Backup time:     ${BACKUP_TIME}s"
echo "  Restore time:    ${RESTORE_TIME}s  <-- This is your RTO"
echo "  Total drill:     ${TOTAL_TIME}s"
echo ""
if [ "${VERIFICATION_PASSED}" = true ]; then
  echo -e "  Data integrity:  ${GREEN}PASSED${NC}"
else
  echo -e "  Data integrity:  ${RED}FAILED${NC}"
fi
echo ""
echo "  RPO note: Your RPO equals the time between your last"
echo "  scheduled backup and the disaster event. With 4-hour"
echo "  etcd snapshots and daily Velero backups, worst-case"
echo "  RPO is ~24 hours for application data."
echo ""
echo "============================================================"

# ---------------------------------------------------------------------------
# Step 7: Cleanup
# ---------------------------------------------------------------------------
log_info "Cleaning up drill resources..."
oc delete project "${NAMESPACE}" --wait=false 2>/dev/null || true
oc delete backup "${BACKUP_NAME}" -n "${OADP_NAMESPACE}" 2>/dev/null || true
oc delete restore "${RESTORE_NAME}" -n "${OADP_NAMESPACE}" 2>/dev/null || true

log_info "=== DR Drill Complete ==="

if [ "${VERIFICATION_PASSED}" = true ]; then
  exit 0
else
  exit 1
fi
