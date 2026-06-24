#!/usr/bin/env bash
# Teardown script for L2-M1.2 Pipeline: Build, Test, Deploy
# Removes all resources created by the lesson
set -euo pipefail

echo "============================================="
echo " L2-M1.2 Pipeline Teardown"
echo "============================================="
echo ""

echo "This will delete the following projects and all their contents:"
echo "  - cicd-pipelines"
echo "  - cicd-staging"
echo "  - cicd-production"
echo ""

read -rp "Are you sure? (y/N): " confirm
if [[ "${confirm}" != "y" && "${confirm}" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi

echo ""
echo "--- Deleting projects ---"

oc delete project cicd-production --ignore-not-found=true
echo "Deleted: cicd-production"

oc delete project cicd-staging --ignore-not-found=true
echo "Deleted: cicd-staging"

oc delete project cicd-pipelines --ignore-not-found=true
echo "Deleted: cicd-pipelines"

echo ""
echo "============================================="
echo " Teardown complete!"
echo "============================================="
echo ""
echo "All pipeline resources, deployments, and projects have been removed."
echo "Note: Project deletion is asynchronous --- it may take a few moments"
echo "for all resources to be fully cleaned up."
