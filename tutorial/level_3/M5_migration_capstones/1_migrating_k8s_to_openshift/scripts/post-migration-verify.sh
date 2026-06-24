#!/usr/bin/env bash
#
# post-migration-verify.sh
# Verifies that a migration to OpenShift completed successfully.
# Run this against your OpenShift cluster AFTER migrating.
#
# Usage: ./post-migration-verify.sh <project-name>
#

set -euo pipefail

PROJECT="${1:?Usage: $0 <project-name>}"

echo "=============================================="
echo "  Post-Migration Verification"
echo "  Project: ${PROJECT}"
echo "  Date: $(date)"
echo "=============================================="
echo ""

FAILURES=0
WARNINGS=0

# ---- 1. Verify project exists ----
echo "=== 1. Project Status ==="
if oc get project "$PROJECT" &>/dev/null; then
  echo "  [PASS] Project '${PROJECT}' exists"
  oc get project "$PROJECT" -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,DISPLAY:.metadata.annotations.'openshift\.io/display-name' 2>/dev/null
else
  echo "  [FAIL] Project '${PROJECT}' not found"
  FAILURES=$((FAILURES + 1))
  echo ""
  echo "FATAL: Project does not exist. Cannot continue verification."
  exit 1
fi
echo ""

# ---- 2. Check pod status ----
echo "=== 2. Pod Status ==="
TOTAL_PODS=$(oc get pods -n "$PROJECT" --no-headers 2>/dev/null | wc -l | tr -d ' ')
RUNNING_PODS=$(oc get pods -n "$PROJECT" --no-headers --field-selector=status.phase=Running 2>/dev/null | wc -l | tr -d ' ')
FAILED_PODS=$(oc get pods -n "$PROJECT" --no-headers --field-selector=status.phase=Failed 2>/dev/null | wc -l | tr -d ' ')
PENDING_PODS=$(oc get pods -n "$PROJECT" --no-headers --field-selector=status.phase=Pending 2>/dev/null | wc -l | tr -d ' ')

echo "  Total:   ${TOTAL_PODS}"
echo "  Running: ${RUNNING_PODS}"
echo "  Pending: ${PENDING_PODS}"
echo "  Failed:  ${FAILED_PODS}"

if [ "$FAILED_PODS" -gt 0 ]; then
  echo ""
  echo "  [FAIL] Failed pods detected:"
  oc get pods -n "$PROJECT" --field-selector=status.phase=Failed 2>/dev/null
  FAILURES=$((FAILURES + 1))
fi

if [ "$PENDING_PODS" -gt 0 ]; then
  echo ""
  echo "  [WARN] Pending pods detected (may be transient):"
  oc get pods -n "$PROJECT" --field-selector=status.phase=Pending 2>/dev/null
  WARNINGS=$((WARNINGS + 1))
fi

# Check for CrashLoopBackOff
CRASHLOOP=$(oc get pods -n "$PROJECT" --no-headers 2>/dev/null | grep -c "CrashLoopBackOff" || echo "0")
if [ "$CRASHLOOP" -gt 0 ]; then
  echo ""
  echo "  [FAIL] CrashLoopBackOff pods detected (likely SCC or config issue):"
  oc get pods -n "$PROJECT" --no-headers 2>/dev/null | grep "CrashLoopBackOff"
  FAILURES=$((FAILURES + 1))
fi
echo ""

# ---- 3. Check SCC assignments ----
echo "=== 3. Security Context Constraints ==="
echo "  Pods and their assigned SCCs:"
for pod in $(oc get pods -n "$PROJECT" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null); do
  scc=$(oc get pod "$pod" -n "$PROJECT" -o jsonpath='{.metadata.annotations.openshift\.io/scc}' 2>/dev/null || echo "unknown")
  status=$(oc get pod "$pod" -n "$PROJECT" -o jsonpath='{.status.phase}' 2>/dev/null || echo "unknown")
  echo "    ${pod}: SCC=${scc}, Status=${status}"
  if [ "$scc" = "privileged" ]; then
    echo "      [WARN] Running with privileged SCC -- review if necessary"
    WARNINGS=$((WARNINGS + 1))
  fi
done
echo ""

# ---- 4. Check Routes ----
echo "=== 4. Routes ==="
ROUTE_COUNT=$(oc get routes -n "$PROJECT" --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "$ROUTE_COUNT" -gt 0 ]; then
  echo "  [PASS] ${ROUTE_COUNT} Route(s) found:"
  oc get routes -n "$PROJECT" -o custom-columns=NAME:.metadata.name,HOST:.spec.host,TLS:.spec.tls.termination,SERVICE:.spec.to.name 2>/dev/null
else
  echo "  [INFO] No Routes found (may not be needed)"
fi
echo ""

# ---- 5. Check Services ----
echo "=== 5. Services ==="
oc get svc -n "$PROJECT" -o custom-columns=NAME:.metadata.name,TYPE:.spec.type,CLUSTER-IP:.spec.clusterIP,PORTS:.spec.ports[*].port 2>/dev/null || echo "  None found"
echo ""

# ---- 6. Check PVCs ----
echo "=== 6. Persistent Volume Claims ==="
PVC_COUNT=$(oc get pvc -n "$PROJECT" --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "$PVC_COUNT" -gt 0 ]; then
  oc get pvc -n "$PROJECT" -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,STORAGECLASS:.spec.storageClassName,SIZE:.spec.resources.requests.storage 2>/dev/null
  UNBOUND=$(oc get pvc -n "$PROJECT" --no-headers 2>/dev/null | grep -cv "Bound" || echo "0")
  if [ "$UNBOUND" -gt 0 ]; then
    echo "  [FAIL] ${UNBOUND} PVC(s) not in Bound state"
    FAILURES=$((FAILURES + 1))
  fi
else
  echo "  No PVCs found"
fi
echo ""

# ---- 7. Check Events for errors ----
echo "=== 7. Recent Warning Events ==="
WARNING_EVENTS=$(oc get events -n "$PROJECT" --field-selector type=Warning --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "$WARNING_EVENTS" -gt 0 ]; then
  echo "  [WARN] ${WARNING_EVENTS} warning event(s):"
  oc get events -n "$PROJECT" --field-selector type=Warning --sort-by='.lastTimestamp' 2>/dev/null | tail -10
  WARNINGS=$((WARNINGS + 1))
else
  echo "  [PASS] No warning events"
fi
echo ""

# ---- 8. Verify Route accessibility ----
echo "=== 8. Route Accessibility ==="
for route_host in $(oc get routes -n "$PROJECT" -o jsonpath='{.items[*].spec.host}' 2>/dev/null); do
  HTTP_CODE=$(curl -sk -o /dev/null -w "%{http_code}" "https://${route_host}" 2>/dev/null || echo "000")
  if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "302" ]; then
    echo "  [PASS] https://${route_host} -> HTTP ${HTTP_CODE}"
  elif [ "$HTTP_CODE" = "000" ]; then
    echo "  [WARN] https://${route_host} -> Connection failed (DNS or network issue)"
    WARNINGS=$((WARNINGS + 1))
  else
    echo "  [WARN] https://${route_host} -> HTTP ${HTTP_CODE}"
    WARNINGS=$((WARNINGS + 1))
  fi
done
echo ""

# ---- Summary ----
echo "=============================================="
echo "  VERIFICATION SUMMARY"
echo "=============================================="
echo "  Failures: ${FAILURES}"
echo "  Warnings: ${WARNINGS}"
echo "=============================================="
echo ""

if [ "$FAILURES" -gt 0 ]; then
  echo "  RESULT: FAILED -- ${FAILURES} issue(s) need immediate attention."
  echo "  Review the failures above and consult the lesson troubleshooting section."
  exit 1
elif [ "$WARNINGS" -gt 0 ]; then
  echo "  RESULT: PASSED with ${WARNINGS} warning(s). Review warnings above."
  exit 0
else
  echo "  RESULT: PASSED -- migration verified successfully."
  exit 0
fi
