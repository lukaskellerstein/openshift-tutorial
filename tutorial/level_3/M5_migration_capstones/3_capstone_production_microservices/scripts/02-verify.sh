#!/bin/bash
# Verification script for the Capstone: Production-Ready Microservices lesson.
# Runs a comprehensive check of all deployed components.

set -euo pipefail

NAMESPACE="capstone-microservices"
PASS=0
FAIL=0
WARN=0

check_pass() { echo "  [PASS] $1"; PASS=$((PASS+1)); }
check_fail() { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }
check_warn() { echo "  [WARN] $1"; WARN=$((WARN+1)); }

echo "============================================"
echo "  Verification: Production-Ready Microservices"
echo "============================================"
echo ""

# 1. Check project exists
echo "[1] Project"
if oc get project "${NAMESPACE}" &>/dev/null; then
  check_pass "Project ${NAMESPACE} exists"
else
  check_fail "Project ${NAMESPACE} does not exist"
fi

# 2. Check deployments
echo ""
echo "[2] Deployments"
SERVICES=("api-gateway" "order-service" "inventory-service" "payment-service")
for svc in "${SERVICES[@]}"; do
  READY=$(oc get deployment "${svc}" -n "${NAMESPACE}" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
  DESIRED=$(oc get deployment "${svc}" -n "${NAMESPACE}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "?")
  if [ "${READY}" = "${DESIRED}" ] && [ "${READY}" != "0" ]; then
    check_pass "${svc}: ${READY}/${DESIRED} replicas ready"
  else
    check_fail "${svc}: ${READY:-0}/${DESIRED} replicas ready"
  fi
done

# 3. Check services
echo ""
echo "[3] Services"
for svc in "${SERVICES[@]}"; do
  if oc get service "${svc}" -n "${NAMESPACE}" &>/dev/null; then
    check_pass "Service ${svc} exists"
  else
    check_fail "Service ${svc} missing"
  fi
done

# 4. Check route
echo ""
echo "[4] Route"
ROUTE_HOST=$(oc get route api-gateway -n "${NAMESPACE}" -o jsonpath='{.spec.host}' 2>/dev/null || echo "")
if [ -n "${ROUTE_HOST}" ]; then
  check_pass "Route api-gateway exists: ${ROUTE_HOST}"
  HTTP_CODE=$(curl -sk -o /dev/null -w "%{http_code}" "https://${ROUTE_HOST}/healthz" 2>/dev/null || echo "000")
  if [ "${HTTP_CODE}" = "200" ]; then
    check_pass "Route responds with HTTP 200"
  else
    check_warn "Route responds with HTTP ${HTTP_CODE} (may need time to propagate)"
  fi
else
  check_fail "Route api-gateway not found"
fi

# 5. Check ServiceAccounts
echo ""
echo "[5] RBAC (ServiceAccounts)"
SA_LIST=("api-gateway-sa" "order-service-sa" "inventory-service-sa" "payment-service-sa")
for sa in "${SA_LIST[@]}"; do
  if oc get sa "${sa}" -n "${NAMESPACE}" &>/dev/null; then
    check_pass "ServiceAccount ${sa} exists"
  else
    check_fail "ServiceAccount ${sa} missing"
  fi
done

# 6. Check network policies
echo ""
echo "[6] Network Policies"
NP_COUNT=$(oc get networkpolicies -n "${NAMESPACE}" --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "${NP_COUNT}" -ge 8 ]; then
  check_pass "Found ${NP_COUNT} NetworkPolicies (expected >= 8)"
else
  check_warn "Found ${NP_COUNT} NetworkPolicies (expected >= 8)"
fi

# 7. Check HPAs
echo ""
echo "[7] Horizontal Pod Autoscalers"
for svc in "${SERVICES[@]}"; do
  if oc get hpa "${svc}-hpa" -n "${NAMESPACE}" &>/dev/null; then
    check_pass "HPA ${svc}-hpa exists"
  else
    check_fail "HPA ${svc}-hpa missing"
  fi
done

# 8. Check monitoring
echo ""
echo "[8] Monitoring (ServiceMonitors)"
for svc in "${SERVICES[@]}"; do
  if oc get servicemonitor "${svc}-monitor" -n "${NAMESPACE}" &>/dev/null; then
    check_pass "ServiceMonitor ${svc}-monitor exists"
  else
    check_warn "ServiceMonitor ${svc}-monitor missing (user workload monitoring may not be enabled)"
  fi
done

# 9. Check PrometheusRules
echo ""
echo "[9] Alerting Rules"
if oc get prometheusrule capstone-microservices-alerts -n "${NAMESPACE}" &>/dev/null; then
  check_pass "PrometheusRule capstone-microservices-alerts exists"
else
  check_warn "PrometheusRule missing (user workload monitoring may not be enabled)"
fi

# 10. Check PodDisruptionBudgets
echo ""
echo "[10] PodDisruptionBudgets"
for svc in "${SERVICES[@]}"; do
  if oc get pdb "${svc}-pdb" -n "${NAMESPACE}" &>/dev/null; then
    check_pass "PDB ${svc}-pdb exists"
  else
    check_fail "PDB ${svc}-pdb missing"
  fi
done

# 11. Check service mesh
echo ""
echo "[11] Service Mesh"
if oc get servicemeshmember default -n "${NAMESPACE}" &>/dev/null; then
  check_pass "ServiceMeshMember exists"
else
  check_warn "ServiceMeshMember not found (Service Mesh operator may not be installed)"
fi
if oc get peerauthentication default-mtls -n "${NAMESPACE}" &>/dev/null; then
  check_pass "PeerAuthentication (mTLS STRICT) exists"
else
  check_warn "PeerAuthentication not found"
fi

# 12. Check Tekton pipeline
echo ""
echo "[12] Tekton Pipeline"
if oc get pipeline build-and-deploy-all -n "${NAMESPACE}" &>/dev/null; then
  check_pass "Pipeline build-and-deploy-all exists"
else
  check_warn "Pipeline not found (Pipelines operator may not be installed)"
fi

# 13. Check resource quotas
echo ""
echo "[13] Resource Quotas & Limits"
if oc get resourcequota capstone-compute-quota -n "${NAMESPACE}" &>/dev/null; then
  check_pass "ResourceQuota exists"
else
  check_fail "ResourceQuota missing"
fi
if oc get limitrange capstone-limit-range -n "${NAMESPACE}" &>/dev/null; then
  check_pass "LimitRange exists"
else
  check_fail "LimitRange missing"
fi

# Summary
echo ""
echo "============================================"
echo "  Verification Summary"
echo "============================================"
echo "  Passed:   ${PASS}"
echo "  Failed:   ${FAIL}"
echo "  Warnings: ${WARN}"
echo "============================================"
echo ""

if [ ${FAIL} -gt 0 ]; then
  echo "Some checks failed. Review the output above."
  exit 1
elif [ ${WARN} -gt 0 ]; then
  echo "All critical checks passed. Warnings indicate optional features"
  echo "that require additional operators or configuration."
  exit 0
else
  echo "All checks passed. The capstone deployment is fully operational."
  exit 0
fi
