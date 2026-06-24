#!/usr/bin/env bash
# cleanup.sh
#
# Remove all resources created by the L3-M1.4 etcd & Control Plane lesson.
# Requires: cluster-admin privileges, oc CLI authenticated.
#
# Usage: ./cleanup.sh

set -euo pipefail

echo "============================================"
echo " Cleanup: L3-M1.4 etcd & Control Plane"
echo " $(date)"
echo "============================================"
echo ""

# Remove the automated backup CronJob and related resources
echo "[1/3] Removing etcd backup CronJob and related resources..."
oc delete cronjob etcd-backup -n openshift-etcd --ignore-not-found 2>/dev/null && echo "  Deleted: CronJob/etcd-backup" || true
oc delete job -l app=etcd-backup -n openshift-etcd --ignore-not-found 2>/dev/null && echo "  Deleted: backup Jobs" || true
oc delete pvc etcd-backup-pvc -n openshift-etcd --ignore-not-found 2>/dev/null && echo "  Deleted: PVC/etcd-backup-pvc" || true
oc delete clusterrolebinding etcd-backup-crb --ignore-not-found 2>/dev/null && echo "  Deleted: ClusterRoleBinding/etcd-backup-crb" || true
oc delete serviceaccount etcd-backup-sa -n openshift-etcd --ignore-not-found 2>/dev/null && echo "  Deleted: ServiceAccount/etcd-backup-sa" || true

# Remove custom alerts
echo ""
echo "[2/3] Removing custom etcd alerts..."
oc delete prometheusrule etcd-custom-alerts -n openshift-etcd --ignore-not-found 2>/dev/null && echo "  Deleted: PrometheusRule/etcd-custom-alerts" || true

# Note about encryption
echo ""
echo "[3/3] Notes on encryption at rest..."
echo "  WARNING: etcd encryption at rest is NOT reverted by this script."
echo "  To revert encryption (if needed), run:"
echo "    oc patch apiserver cluster -p '{\"spec\":{\"encryption\":{\"type\":\"identity\"}}}' --type=merge"
echo "  This will decrypt all resources back to plaintext and takes 10-20 minutes."
echo ""

echo "============================================"
echo " Cleanup complete."
echo "============================================"
