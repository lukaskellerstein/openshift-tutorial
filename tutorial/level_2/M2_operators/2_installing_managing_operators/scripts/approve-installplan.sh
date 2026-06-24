#!/usr/bin/env bash
# approve-installplan.sh — Approve the first pending InstallPlan in a namespace
#
# Usage: bash scripts/approve-installplan.sh <namespace>
#
# This script finds the first InstallPlan with approved=false and patches it.
# Useful for manual-approval Subscriptions.

set -euo pipefail

NAMESPACE="${1:?Usage: $0 <namespace>}"

echo "Looking for unapproved InstallPlans in namespace: ${NAMESPACE}"

# Get the name of the first unapproved InstallPlan
INSTALL_PLAN=$(oc get installplans -n "${NAMESPACE}" \
  -o jsonpath='{.items[?(@.spec.approved==false)].metadata.name}' | awk '{print $1}')

if [[ -z "${INSTALL_PLAN}" ]]; then
  echo "No unapproved InstallPlans found in ${NAMESPACE}."
  echo "Either the InstallPlan was already approved or the Subscription has not been created yet."
  exit 0
fi

echo "Found unapproved InstallPlan: ${INSTALL_PLAN}"
echo ""

# Show what the InstallPlan will install
echo "Resources to be installed:"
oc get installplan "${INSTALL_PLAN}" -n "${NAMESPACE}" \
  -o jsonpath='{range .spec.clusterServiceVersionNames[*]}  CSV: {}{"\n"}{end}'
echo ""

# Approve the InstallPlan
echo "Approving InstallPlan ${INSTALL_PLAN}..."
oc patch installplan "${INSTALL_PLAN}" \
  -n "${NAMESPACE}" \
  --type merge \
  --patch '{"spec":{"approved":true}}'

echo ""
echo "InstallPlan approved. Waiting for CSV to reach Succeeded phase..."

# Wait up to 120 seconds for the CSV to succeed
TIMEOUT=120
ELAPSED=0
while [[ ${ELAPSED} -lt ${TIMEOUT} ]]; do
  PHASE=$(oc get csv -n "${NAMESPACE}" -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "Pending")
  if [[ "${PHASE}" == "Succeeded" ]]; then
    echo "Operator installed successfully."
    oc get csv -n "${NAMESPACE}"
    exit 0
  fi
  echo "  CSV phase: ${PHASE} (waiting...)"
  sleep 5
  ELAPSED=$((ELAPSED + 5))
done

echo "Warning: CSV did not reach Succeeded phase within ${TIMEOUT} seconds."
echo "Check status with: oc get csv -n ${NAMESPACE}"
exit 1
