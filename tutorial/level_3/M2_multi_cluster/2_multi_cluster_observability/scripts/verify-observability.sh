#!/bin/bash
# verify-observability.sh — Verify ACM Multi-Cluster Observability health
#
# Checks all observability components and reports status.
# Useful for troubleshooting and post-deployment validation.
#
set -euo pipefail

echo "============================================"
echo "  ACM Observability Health Check"
echo "============================================"
echo ""

PASS=0
WARN=0
FAIL=0

check_pass() { echo "  [PASS] $1"; ((PASS++)); }
check_warn() { echo "  [WARN] $1"; ((WARN++)); }
check_fail() { echo "  [FAIL] $1"; ((FAIL++)); }

# --- 1. MultiClusterObservability CR ---
echo "[1] MultiClusterObservability CR Status"
MCO_STATUS=$(oc get multiclusterobservability observability \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "NotFound")
if [ "${MCO_STATUS}" = "True" ]; then
  check_pass "MultiClusterObservability is Ready"
elif [ "${MCO_STATUS}" = "NotFound" ]; then
  check_fail "MultiClusterObservability CR not found"
else
  check_warn "MultiClusterObservability status: ${MCO_STATUS}"
fi
echo ""

# --- 2. Thanos Components ---
echo "[2] Thanos Component Pods"
NS="open-cluster-management-observability"

for component in "thanos-receive" "thanos-store" "thanos-query" "thanos-query-frontend" "thanos-compact" "thanos-rule"; do
  READY=$(oc get pods -n "${NS}" -l "app.kubernetes.io/name=${component}" \
    --no-headers 2>/dev/null | grep -c "Running" || echo 0)
  TOTAL=$(oc get pods -n "${NS}" -l "app.kubernetes.io/name=${component}" \
    --no-headers 2>/dev/null | wc -l | tr -d ' ')

  if [ "${TOTAL}" -eq 0 ]; then
    check_fail "${component}: no pods found"
  elif [ "${READY}" -eq "${TOTAL}" ]; then
    check_pass "${component}: ${READY}/${TOTAL} running"
  else
    check_warn "${component}: ${READY}/${TOTAL} running"
  fi
done
echo ""

# --- 3. Grafana ---
echo "[3] Grafana"
GRAFANA_READY=$(oc get pods -n "${NS}" -l app=multicluster-observability-grafana \
  --no-headers 2>/dev/null | grep -c "Running" || echo 0)
if [ "${GRAFANA_READY}" -gt 0 ]; then
  check_pass "Grafana: ${GRAFANA_READY} pod(s) running"
  GRAFANA_ROUTE=$(oc get route grafana -n "${NS}" \
    -o jsonpath='{.spec.host}' 2>/dev/null || echo "")
  if [ -n "${GRAFANA_ROUTE}" ]; then
    check_pass "Grafana route: https://${GRAFANA_ROUTE}"
  else
    check_warn "Grafana route not found"
  fi
else
  check_fail "Grafana: no running pods"
fi
echo ""

# --- 4. AlertManager ---
echo "[4] AlertManager"
AM_READY=$(oc get pods -n "${NS}" -l app=multicluster-observability-alertmanager \
  --no-headers 2>/dev/null | grep -c "Running" || echo 0)
if [ "${AM_READY}" -gt 0 ]; then
  check_pass "AlertManager: ${AM_READY} pod(s) running"
else
  check_warn "AlertManager: no running pods (may still be starting)"
fi
echo ""

# --- 5. Observability Addon on Managed Clusters ---
echo "[5] Observability Addon Status on Managed Clusters"
CLUSTERS=$(oc get managedclusters --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null)
if [ -z "${CLUSTERS}" ]; then
  check_warn "No managed clusters found"
else
  while IFS= read -r cluster; do
    ADDON_STATUS=$(oc get managedclusteraddon observability-controller \
      -n "${cluster}" \
      -o jsonpath='{.status.conditions[?(@.type=="Available")].status}' 2>/dev/null || echo "NotFound")
    if [ "${ADDON_STATUS}" = "True" ]; then
      check_pass "Cluster '${cluster}': addon available"
    elif [ "${ADDON_STATUS}" = "NotFound" ]; then
      check_fail "Cluster '${cluster}': addon not found"
    else
      check_warn "Cluster '${cluster}': addon status ${ADDON_STATUS}"
    fi
  done <<< "${CLUSTERS}"
fi
echo ""

# --- 6. Object Storage Connectivity ---
echo "[6] Object Storage"
SECRET_EXISTS=$(oc get secret thanos-object-storage -n "${NS}" \
  --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "${SECRET_EXISTS}" -gt 0 ]; then
  check_pass "Thanos object storage secret exists"
else
  check_fail "Thanos object storage secret missing"
fi

# Check for compact errors (indicates storage issues)
COMPACT_ERRORS=$(oc logs -n "${NS}" -l "app.kubernetes.io/name=thanos-compact" \
  --tail=50 2>/dev/null | grep -ci "error" || echo 0)
if [ "${COMPACT_ERRORS}" -gt 5 ]; then
  check_warn "Thanos Compact has ${COMPACT_ERRORS} recent errors in logs"
else
  check_pass "Thanos Compact logs look healthy"
fi
echo ""

# --- 7. PVC Status ---
echo "[7] Persistent Volume Claims"
PVC_ISSUES=$(oc get pvc -n "${NS}" --no-headers 2>/dev/null | grep -v "Bound" | wc -l | tr -d ' ')
PVC_TOTAL=$(oc get pvc -n "${NS}" --no-headers 2>/dev/null | wc -l | tr -d ' ')
PVC_BOUND=$((PVC_TOTAL - PVC_ISSUES))

if [ "${PVC_TOTAL}" -eq 0 ]; then
  check_warn "No PVCs found in observability namespace"
elif [ "${PVC_ISSUES}" -eq 0 ]; then
  check_pass "All ${PVC_TOTAL} PVCs are Bound"
else
  check_warn "${PVC_BOUND}/${PVC_TOTAL} PVCs are Bound (${PVC_ISSUES} not bound)"
  oc get pvc -n "${NS}" --no-headers | grep -v "Bound"
fi
echo ""

# --- Summary ---
echo "============================================"
echo "  Summary"
echo "============================================"
echo "  Passed: ${PASS}"
echo "  Warnings: ${WARN}"
echo "  Failed: ${FAIL}"
echo ""

if [ "${FAIL}" -gt 0 ]; then
  echo "  Status: UNHEALTHY - ${FAIL} check(s) failed"
  echo ""
  echo "  Troubleshooting:"
  echo "    oc get pods -n ${NS}"
  echo "    oc describe multiclusterobservability observability"
  echo "    oc logs -n ${NS} -l app.kubernetes.io/name=thanos-receive --tail=100"
  exit 1
elif [ "${WARN}" -gt 0 ]; then
  echo "  Status: DEGRADED - ${WARN} warning(s)"
  exit 0
else
  echo "  Status: HEALTHY"
  exit 0
fi
