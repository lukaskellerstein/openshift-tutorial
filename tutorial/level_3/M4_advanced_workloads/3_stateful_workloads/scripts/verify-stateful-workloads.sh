#!/usr/bin/env bash
# verify-stateful-workloads.sh — Verify all stateful workload components
# are running correctly. Run this after completing the lesson steps.
set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=0
FAIL=0

check() {
  local description="$1"
  local command="$2"
  local expected="$3"

  result=$(eval "$command" 2>/dev/null || echo "ERROR")

  if [[ "$result" == *"$expected"* ]]; then
    echo -e "  ${GREEN}PASS${NC} $description"
    ((PASS++))
  else
    echo -e "  ${RED}FAIL${NC} $description (got: $result, expected: $expected)"
    ((FAIL++))
  fi
}

echo ""
echo "========================================="
echo " Stateful Workloads Verification"
echo "========================================="
echo ""

# --- StatefulSet checks ---
echo "--- Redis StatefulSet ---"
check "Redis StatefulSet exists" \
  "oc get statefulset redis-cluster -o jsonpath='{.status.readyReplicas}'" \
  "3"

check "Redis PDB exists" \
  "oc get pdb redis-cluster-pdb -o jsonpath='{.spec.minAvailable}'" \
  "2"

check "Redis PVCs are bound" \
  "oc get pvc -l app=redis-cluster -o jsonpath='{.items[*].status.phase}'" \
  "Bound"

echo ""

# --- PostgreSQL checks ---
echo "--- PostgreSQL Cluster (PGO) ---"
check "PGO operator installed" \
  "oc get csv -n openshift-operators -o name | grep -c postgres" \
  "1"

check "PostgresCluster exists" \
  "oc get postgrescluster pg-production -o jsonpath='{.metadata.name}'" \
  "pg-production"

PG_READY=$(oc get pods -l postgres-operator.crunchydata.com/cluster=pg-production \
  -l postgres-operator.crunchydata.com/instance-set=pgha \
  --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')

if [[ "$PG_READY" -ge 2 ]]; then
  echo -e "  ${GREEN}PASS${NC} PostgreSQL instances running ($PG_READY/3)"
  ((PASS++))
else
  echo -e "  ${RED}FAIL${NC} PostgreSQL instances running ($PG_READY/3, expected >= 2)"
  ((FAIL++))
fi

check "PgBouncer proxy running" \
  "oc get pods -l postgres-operator.crunchydata.com/cluster=pg-production \
   -l postgres-operator.crunchydata.com/role=pgbouncer \
   --field-selector=status.phase=Running --no-headers | wc -l | tr -d ' '" \
  "2"

echo ""

# --- Kafka checks ---
echo "--- Kafka Cluster (Strimzi) ---"
check "Strimzi operator installed" \
  "oc get csv -n openshift-operators -o name | grep -c strimzi" \
  "1"

check "Kafka cluster ready" \
  "oc get kafka kafka-production -o jsonpath='{.status.conditions[?(@.type==\"Ready\")].status}'" \
  "True"

KAFKA_READY=$(oc get pods -l strimzi.io/cluster=kafka-production \
  -l strimzi.io/kind=Kafka \
  --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')

if [[ "$KAFKA_READY" -ge 3 ]]; then
  echo -e "  ${GREEN}PASS${NC} Kafka brokers running ($KAFKA_READY/3)"
  ((PASS++))
else
  echo -e "  ${RED}FAIL${NC} Kafka brokers running ($KAFKA_READY/3, expected 3)"
  ((FAIL++))
fi

ZK_READY=$(oc get pods -l strimzi.io/cluster=kafka-production \
  -l strimzi.io/kind=Kafka \
  -l strimzi.io/name=kafka-production-zookeeper \
  --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')

if [[ "$ZK_READY" -ge 3 ]]; then
  echo -e "  ${GREEN}PASS${NC} ZooKeeper nodes running ($ZK_READY/3)"
  ((PASS++))
else
  echo -e "  ${YELLOW}WARN${NC} ZooKeeper nodes running ($ZK_READY/3, expected 3)"
  ((FAIL++))
fi

echo ""

# --- Storage checks ---
echo "--- Storage ---"
TOTAL_PVCS=$(oc get pvc --no-headers 2>/dev/null | wc -l | tr -d ' ')
BOUND_PVCS=$(oc get pvc --field-selector=status.phase=Bound --no-headers 2>/dev/null | wc -l | tr -d ' ')

if [[ "$BOUND_PVCS" -eq "$TOTAL_PVCS" ]] && [[ "$TOTAL_PVCS" -gt 0 ]]; then
  echo -e "  ${GREEN}PASS${NC} All PVCs bound ($BOUND_PVCS/$TOTAL_PVCS)"
  ((PASS++))
else
  echo -e "  ${RED}FAIL${NC} PVC binding issue ($BOUND_PVCS bound out of $TOTAL_PVCS total)"
  ((FAIL++))
fi

echo ""
echo "========================================="
echo -e " Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}"
echo "========================================="
echo ""

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
