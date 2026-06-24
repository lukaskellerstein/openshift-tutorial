#!/usr/bin/env bash
# verify-cluster.sh — Verify the PostgresCluster is healthy and accessible
#
# Usage: ./scripts/verify-cluster.sh
#
# Checks: operator status, cluster pods, services, secrets, and connectivity.

set -euo pipefail

CLUSTER_NAME="hippo"
USER_SECRET="${CLUSTER_NAME}-pguser-appuser"

echo "=== Verifying PostgresCluster '${CLUSTER_NAME}' ==="
echo ""

# 1. Check the operator is running
echo "--- Step 1: Operator pods ---"
oc get pods -n openshift-operators -l postgres-operator.crunchydata.com/control-plane=postgres-operator 2>/dev/null || \
  echo "WARNING: Could not find operator pods. Is the CrunchyData operator installed?"
echo ""

# 2. Check cluster status
echo "--- Step 2: PostgresCluster status ---"
oc get postgrescluster "${CLUSTER_NAME}" -o jsonpath='{.status.conditions[*].type}{"\t"}{.status.conditions[*].status}{"\n"}' 2>/dev/null || \
  echo "WARNING: PostgresCluster '${CLUSTER_NAME}' not found."
echo ""

# 3. Check pods
echo "--- Step 3: Cluster pods ---"
oc get pods -l "postgres-operator.crunchydata.com/cluster=${CLUSTER_NAME}" \
  -o custom-columns='NAME:.metadata.name,STATUS:.status.phase,ROLE:.metadata.labels.postgres-operator\.crunchydata\.com/role,READY:.status.conditions[?(@.type=="Ready")].status'
echo ""

# 4. Check services
echo "--- Step 4: Services ---"
oc get svc -l "postgres-operator.crunchydata.com/cluster=${CLUSTER_NAME}"
echo ""

# 5. Check user secret
echo "--- Step 5: User secret ---"
if oc get secret "${USER_SECRET}" &>/dev/null; then
  echo "Secret '${USER_SECRET}' exists with keys:"
  oc get secret "${USER_SECRET}" -o jsonpath='{range .data.*}{@}{"\n"}{end}' > /dev/null
  oc get secret "${USER_SECRET}" -o jsonpath='{.data}' | python3 -c "
import sys, json, base64
data = json.load(sys.stdin)
for k, v in sorted(data.items()):
    val = base64.b64decode(v).decode()
    if k == 'password':
        val = '********'
    print(f'  {k}: {val}')
"
else
  echo "WARNING: Secret '${USER_SECRET}' not found."
fi
echo ""

# 6. Test connectivity from within the cluster
echo "--- Step 6: Connectivity test ---"
PRIMARY_POD=$(oc get pods \
  -l "postgres-operator.crunchydata.com/cluster=${CLUSTER_NAME},postgres-operator.crunchydata.com/role=master" \
  -o name 2>/dev/null | head -1)

if [ -n "${PRIMARY_POD}" ]; then
  echo "Primary pod: ${PRIMARY_POD}"
  echo "Running SELECT 1..."
  oc exec "${PRIMARY_POD}" -- psql -U postgres -c "SELECT 1 AS connection_test;" 2>/dev/null && \
    echo "Connection test: PASSED" || \
    echo "Connection test: FAILED"
else
  echo "WARNING: No primary pod found."
fi
echo ""

echo "=== Verification complete ==="
