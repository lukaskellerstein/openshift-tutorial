#!/bin/bash
# Cleanup script for L2-M3.4 Event-Driven Architecture
# Removes all resources created during the lesson

set -euo pipefail

PROJECT="event-driven-demo"

echo "=== Cleaning up L2-M3.4 Event-Driven Architecture resources ==="

# Check if project exists
if ! oc get project "$PROJECT" &>/dev/null; then
  echo "Project $PROJECT does not exist. Nothing to clean up."
  exit 0
fi

# Switch to the project
oc project "$PROJECT" 2>/dev/null || true

echo "Deleting event sources..."
oc delete pingsource heartbeat --ignore-not-found
oc delete apiserversource pod-watcher --ignore-not-found

echo "Deleting triggers..."
oc delete trigger all-events critical-only --ignore-not-found

echo "Deleting broker..."
oc delete broker default --ignore-not-found

echo "Deleting channel and subscription..."
oc delete subscription pipeline-to-display --ignore-not-found
oc delete channel processing-pipeline --ignore-not-found

echo "Deleting Knative services..."
oc delete ksvc event-display critical-logger --ignore-not-found

echo "Deleting RBAC resources..."
oc delete rolebinding event-watcher-binding --ignore-not-found
oc delete role event-watcher-role --ignore-not-found
oc delete sa event-watcher --ignore-not-found

echo "Deleting utility pods..."
oc delete pod curl-sender --ignore-not-found
oc delete pod test-event-pod --ignore-not-found

echo "Deleting project..."
oc delete project "$PROJECT"

echo "=== Cleanup complete ==="
