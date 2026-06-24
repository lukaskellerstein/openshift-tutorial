#!/bin/bash
# setup-observability.sh — Deploy ACM Multi-Cluster Observability
#
# Prerequisites:
#   - Logged in to the hub cluster as cluster-admin
#   - RHACM (Advanced Cluster Management) installed
#   - Object storage credentials configured
#
# Usage:
#   ./scripts/setup-observability.sh [--storage-type s3|noobaa]
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFESTS_DIR="${SCRIPT_DIR}/../manifests"
STORAGE_TYPE="${1:---storage-type}"
STORAGE_TYPE="${2:-s3}"

echo "============================================"
echo "  ACM Multi-Cluster Observability Setup"
echo "============================================"
echo ""

# --- Pre-flight checks ---
echo "[1/7] Running pre-flight checks..."

if ! oc whoami &>/dev/null; then
  echo "ERROR: Not logged in to OpenShift. Run 'oc login' first."
  exit 1
fi

CURRENT_USER=$(oc whoami)
echo "  Logged in as: ${CURRENT_USER}"

# Check for cluster-admin
if ! oc auth can-i '*' '*' --all-namespaces &>/dev/null; then
  echo "ERROR: Current user does not have cluster-admin privileges."
  echo "  Log in as kubeadmin or a user with cluster-admin role."
  exit 1
fi

# Check ACM is installed
if ! oc get multiclusterhub --all-namespaces &>/dev/null; then
  echo "ERROR: Advanced Cluster Management is not installed."
  echo "  Complete L3-M2.1 first to install RHACM."
  exit 1
fi
echo "  ACM detected: OK"

# Check managed clusters
MANAGED_COUNT=$(oc get managedclusters --no-headers 2>/dev/null | wc -l | tr -d ' ')
echo "  Managed clusters: ${MANAGED_COUNT}"
if [ "${MANAGED_COUNT}" -eq 0 ]; then
  echo "WARNING: No managed clusters found. Observability will be configured"
  echo "  but will only collect hub cluster metrics until clusters are added."
fi

echo ""

# --- Create namespace ---
echo "[2/7] Creating observability namespace..."
oc apply -f "${MANIFESTS_DIR}/observability-namespace.yaml"
echo "  Namespace created: open-cluster-management-observability"
echo ""

# --- Copy pull secret ---
echo "[3/7] Copying pull secret to observability namespace..."
DOCKER_CONFIG_JSON=$(oc extract secret/pull-secret \
  -n openshift-config --to=- 2>/dev/null)

oc create secret generic multiclusterhub-operator-pull-secret \
  -n open-cluster-management-observability \
  --from-literal=.dockerconfigjson="${DOCKER_CONFIG_JSON}" \
  --type=kubernetes.io/dockerconfigjson \
  --dry-run=client -o yaml | oc apply -f -
echo "  Pull secret configured"
echo ""

# --- Configure object storage ---
echo "[4/7] Configuring object storage secret..."
if [ "${STORAGE_TYPE}" = "noobaa" ]; then
  echo "  Using OpenShift Data Foundation (NooBaa)"
  echo "  NOTE: Ensure ODF is installed and a NooBaa instance is available."
  echo ""
  echo "  You need to manually update the secret with NooBaa credentials:"
  echo "    oc get secret noobaa-admin -n openshift-storage -o json | \\"
  echo "      jq -r '.data.AWS_ACCESS_KEY_ID | @base64d'"
  echo ""
  echo "  Edit manifests/thanos-object-storage-secret.yaml with the credentials,"
  echo "  then run: oc apply -f manifests/thanos-object-storage-secret.yaml"
else
  echo "  Using S3-compatible storage"
  echo "  Ensure you have updated manifests/thanos-object-storage-secret.yaml"
  echo "  with valid S3 credentials before continuing."
  echo ""
  read -p "  Have you configured S3 credentials? [y/N] " -n 1 -r
  echo ""
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "  Please edit manifests/thanos-object-storage-secret.yaml first."
    exit 1
  fi
fi
oc apply -f "${MANIFESTS_DIR}/thanos-object-storage-secret.yaml"
echo "  Object storage secret configured"
echo ""

# --- Deploy MultiClusterObservability CR ---
echo "[5/7] Deploying MultiClusterObservability..."
oc apply -f "${MANIFESTS_DIR}/multiclusterobservability.yaml"
echo "  MultiClusterObservability CR applied"
echo ""

# --- Wait for rollout ---
echo "[6/7] Waiting for observability components to start..."
echo "  This may take 5-10 minutes on first deployment."
echo ""

MAX_RETRIES=60
RETRY_INTERVAL=10
for i in $(seq 1 $MAX_RETRIES); do
  STATUS=$(oc get multiclusterobservability observability \
    -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "Unknown")

  if [ "${STATUS}" = "True" ]; then
    echo "  MultiClusterObservability is Ready!"
    break
  fi

  if [ "$i" -eq $MAX_RETRIES ]; then
    echo "WARNING: Timed out waiting for observability to become Ready."
    echo "  Current status: ${STATUS}"
    echo "  Check pods: oc get pods -n open-cluster-management-observability"
    echo "  Continuing with remaining setup..."
  fi

  echo "  Waiting... (${i}/${MAX_RETRIES}) Status: ${STATUS}"
  sleep $RETRY_INTERVAL
done
echo ""

# --- Apply custom metrics and dashboards ---
echo "[7/7] Applying custom metrics allowlist and dashboards..."
oc apply -f "${MANIFESTS_DIR}/custom-metrics-allowlist.yaml"
oc apply -f "${MANIFESTS_DIR}/grafana-dashboard-fleet-overview.yaml"
echo "  Custom metrics and dashboard configured"
echo ""

echo "============================================"
echo "  Setup Complete"
echo "============================================"
echo ""
echo "Access Grafana:"
GRAFANA_ROUTE=$(oc get route grafana \
  -n open-cluster-management-observability \
  -o jsonpath='{.spec.host}' 2>/dev/null || echo "<pending>")
echo "  https://${GRAFANA_ROUTE}"
echo ""
echo "Next steps:"
echo "  1. Open Grafana and explore the Fleet Overview dashboard"
echo "  2. Apply custom alerting rules:"
echo "     oc apply -f manifests/custom-alerting-rules.yaml"
echo "  3. Configure log forwarding on managed clusters:"
echo "     oc apply -f manifests/acm-observability-policy.yaml"
echo "  4. Deploy ClusterLogForwarder to managed clusters:"
echo "     oc apply -f manifests/clusterlogforwarder-hub.yaml"
echo ""
