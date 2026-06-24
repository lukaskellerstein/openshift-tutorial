#!/usr/bin/env bash
# generate-load.sh — Generates HTTP traffic against the probe-demo route
# to trigger the HPA. Runs a temporary pod that sends continuous requests.
#
# Usage:
#   bash scripts/generate-load.sh          # start the load generator
#   oc delete pod load-generator           # stop the load generator

set -euo pipefail

ROUTE_URL=$(oc get route probe-demo -o jsonpath='{.spec.host}' 2>/dev/null)

if [[ -z "${ROUTE_URL}" ]]; then
  echo "ERROR: Could not find route 'probe-demo'. Is the application deployed?"
  echo "Run: oc apply -f manifests/"
  exit 1
fi

echo "Generating load against: http://${ROUTE_URL}"
echo "The load generator will run as a pod named 'load-generator'."
echo "To stop it:  oc delete pod load-generator"
echo ""

# Delete any existing load generator pod
oc delete pod load-generator --ignore-not-found 2>/dev/null

# Run a load generator pod that continuously curls the route
oc run load-generator \
  --image=registry.access.redhat.com/ubi9/ubi-minimal:latest \
  --restart=Never \
  --command -- /bin/bash -c \
  "echo 'Starting load generation against http://${ROUTE_URL}'; \
   while true; do \
     curl -s -o /dev/null http://${ROUTE_URL}; \
   done"

echo ""
echo "Load generator started. Watch the HPA with:"
echo "  oc get hpa probe-demo-hpa --watch"
