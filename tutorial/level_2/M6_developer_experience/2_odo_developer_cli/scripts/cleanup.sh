#!/usr/bin/env bash
# Cleanup script for L2-M6.2 — odo Developer CLI
# Removes all resources created during the lesson
set -euo pipefail

WORK_DIR="/tmp/odo-lesson"

echo "=== L2-M6.2: odo Developer CLI — Cleanup ==="

# Stop any running odo dev sessions
echo ""
echo "--- Stopping odo dev sessions ---"
if pgrep -f "odo dev" > /dev/null 2>&1; then
  pkill -f "odo dev" || true
  echo "  Stopped running odo dev processes"
else
  echo "  No odo dev sessions running"
fi

# Delete odo component if it exists
echo ""
echo "--- Deleting odo components ---"
if [ -d "$WORK_DIR" ]; then
  cd "$WORK_DIR"
  odo delete component --name odo-demo --force 2>/dev/null || true
  echo "  Deleted odo-demo component"
fi

# Delete all resources with tutorial labels
echo ""
echo "--- Deleting labeled resources ---"
oc delete all -l tutorial-level=2,tutorial-module=M6 -n odo-demo 2>/dev/null || true

# Delete the project
echo ""
echo "--- Deleting OpenShift project ---"
oc delete project odo-demo 2>/dev/null || true
echo "  Deleted project: odo-demo"

# Remove working directory
echo ""
echo "--- Removing local files ---"
if [ -d "$WORK_DIR" ]; then
  rm -rf "$WORK_DIR"
  echo "  Removed: $WORK_DIR"
else
  echo "  Working directory already removed"
fi

echo ""
echo "=== Cleanup complete ==="
