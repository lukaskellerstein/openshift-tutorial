#!/bin/bash
# audit-log-analysis.sh
# Analyzes OpenShift API server audit logs for security-relevant events
#
# Usage: bash scripts/audit-log-analysis.sh
#
# Prerequisites:
#   - Logged in as kubeadmin (cluster-admin)
#   - CRC or OpenShift cluster running

set -euo pipefail

NODE=$(oc get nodes -o jsonpath='{.items[0].metadata.name}')

echo "============================================"
echo " OpenShift Audit Log Analysis"
echo " Node: ${NODE}"
echo " Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "============================================"
echo ""

# --- Section 1: Recent API activity summary ---
echo "--- 1. Recent API Activity (last 100 events) ---"
oc debug "node/${NODE}" -- chroot /host bash -c '
  tail -100 /var/log/kube-apiserver/audit.log 2>/dev/null | \
  python3 -c "
import sys, json
from collections import Counter

verbs = Counter()
users = Counter()
resources = Counter()
status_codes = Counter()

for line in sys.stdin:
    try:
        event = json.loads(line)
        verbs[event.get(\"verb\", \"unknown\")] += 1
        users[event.get(\"user\", {}).get(\"username\", \"unknown\")] += 1
        obj_ref = event.get(\"objectRef\", {})
        if obj_ref:
            resources[obj_ref.get(\"resource\", \"unknown\")] += 1
        resp = event.get(\"responseStatus\", {})
        status_codes[str(resp.get(\"code\", \"N/A\"))] += 1
    except (json.JSONDecodeError, KeyError):
        pass

print(\"  Verbs:\")
for verb, count in verbs.most_common(10):
    print(f\"    {verb}: {count}\")

print(\"  Top Users:\")
for user, count in users.most_common(5):
    print(f\"    {user}: {count}\")

print(\"  Top Resources:\")
for resource, count in resources.most_common(10):
    print(f\"    {resource}: {count}\")

print(\"  Status Codes:\")
for code, count in status_codes.most_common(5):
    print(f\"    {code}: {count}\")
" 2>/dev/null
' 2>/dev/null || echo "  (Could not access audit logs --- ensure you are cluster-admin)"
echo ""

# --- Section 2: Failed authentication attempts ---
echo "--- 2. Failed Authentication Attempts (403/401 responses) ---"
oc debug "node/${NODE}" -- chroot /host bash -c '
  tail -500 /var/log/kube-apiserver/audit.log 2>/dev/null | \
  python3 -c "
import sys, json

count = 0
for line in sys.stdin:
    try:
        event = json.loads(line)
        code = event.get(\"responseStatus\", {}).get(\"code\", 0)
        if code in (401, 403):
            user = event.get(\"user\", {}).get(\"username\", \"unknown\")
            verb = event.get(\"verb\", \"unknown\")
            resource = event.get(\"objectRef\", {}).get(\"resource\", \"unknown\")
            ts = event.get(\"requestReceivedTimestamp\", \"unknown\")
            print(f\"  {ts} | {user} | {verb} {resource} | HTTP {code}\")
            count += 1
    except (json.JSONDecodeError, KeyError):
        pass

if count == 0:
    print(\"  No failed auth attempts found in recent logs.\")
else:
    print(f\"  Total: {count} failed attempts\")
" 2>/dev/null
' 2>/dev/null || echo "  (Could not access audit logs)"
echo ""

# --- Section 3: Sensitive resource access ---
echo "--- 3. Sensitive Resource Access (secrets, configmaps, roles) ---"
oc debug "node/${NODE}" -- chroot /host bash -c '
  tail -500 /var/log/kube-apiserver/audit.log 2>/dev/null | \
  python3 -c "
import sys, json

sensitive_resources = {\"secrets\", \"clusterroles\", \"clusterrolebindings\", \"roles\", \"rolebindings\"}
count = 0
for line in sys.stdin:
    try:
        event = json.loads(line)
        resource = event.get(\"objectRef\", {}).get(\"resource\", \"\")
        verb = event.get(\"verb\", \"\")
        if resource in sensitive_resources and verb in (\"create\", \"update\", \"patch\", \"delete\"):
            user = event.get(\"user\", {}).get(\"username\", \"unknown\")
            name = event.get(\"objectRef\", {}).get(\"name\", \"N/A\")
            ns = event.get(\"objectRef\", {}).get(\"namespace\", \"cluster\")
            ts = event.get(\"requestReceivedTimestamp\", \"unknown\")
            print(f\"  {ts} | {user} | {verb} {resource}/{name} in {ns}\")
            count += 1
    except (json.JSONDecodeError, KeyError):
        pass

if count == 0:
    print(\"  No sensitive resource modifications found in recent logs.\")
else:
    print(f\"  Total: {count} sensitive resource modifications\")
" 2>/dev/null
' 2>/dev/null || echo "  (Could not access audit logs)"
echo ""

# --- Section 4: Compliance Operator scan summary ---
echo "--- 4. Current Compliance Scan Results ---"
PASS=$(oc get compliancecheckresults -n openshift-compliance --no-headers --field-selector status.result=PASS 2>/dev/null | wc -l | tr -d ' ')
FAIL=$(oc get compliancecheckresults -n openshift-compliance --no-headers --field-selector status.result=FAIL 2>/dev/null | wc -l | tr -d ' ')
MANUAL=$(oc get compliancecheckresults -n openshift-compliance --no-headers --field-selector status.result=MANUAL 2>/dev/null | wc -l | tr -d ' ')
NA=$(oc get compliancecheckresults -n openshift-compliance --no-headers --field-selector status.result=NOT-APPLICABLE 2>/dev/null | wc -l | tr -d ' ')

echo "  PASS:           ${PASS}"
echo "  FAIL:           ${FAIL}"
echo "  MANUAL REVIEW:  ${MANUAL}"
echo "  NOT APPLICABLE: ${NA}"
echo ""

if [ "${FAIL}" -gt 0 ] 2>/dev/null; then
  echo "  High-severity failures:"
  oc get compliancecheckresults -n openshift-compliance \
    --field-selector status.result=FAIL \
    -o jsonpath='{range .items[?(@.status.severity=="high")]}{.metadata.name}{"\t"}{.status.severity}{"\n"}{end}' 2>/dev/null | \
    while IFS=$'\t' read -r name severity; do
      echo "    - ${name} (${severity})"
    done
fi

echo ""
echo "============================================"
echo " Analysis complete."
echo "============================================"
