#!/usr/bin/env bash
# promote.sh -- Promote an application image tag across environments
#
# Usage:
#   ./promote.sh <app-name> <target-env> <image-tag> [gitops-repo-path]
#
# Examples:
#   ./promote.sh demo-app dev v1.2.3
#   ./promote.sh demo-app staging v1.2.3 /path/to/gitops-repo
#   ./promote.sh demo-app prod v1.2.3
#
# This script:
#   1. Updates the Kustomize overlay for the target environment
#   2. Creates a Git branch and commits the change
#   3. Pushes and optionally creates a PR (for staging/prod)
#
# Requirements:
#   - git CLI
#   - gh CLI (for PR creation, optional)
#   - yq (for YAML manipulation, optional -- falls back to sed)

set -euo pipefail

APP_NAME="${1:?Usage: $0 <app-name> <target-env> <image-tag> [gitops-repo-path]}"
TARGET_ENV="${2:?Usage: $0 <app-name> <target-env> <image-tag> [gitops-repo-path]}"
IMAGE_TAG="${3:?Usage: $0 <app-name> <target-env> <image-tag> [gitops-repo-path]}"
GITOPS_REPO="${4:-.}"

# Validate target environment
if [[ ! "$TARGET_ENV" =~ ^(dev|staging|prod)$ ]]; then
  echo "ERROR: target-env must be one of: dev, staging, prod"
  exit 1
fi

OVERLAY_DIR="${GITOPS_REPO}/apps/${APP_NAME}/overlays/${TARGET_ENV}"

if [[ ! -d "$OVERLAY_DIR" ]]; then
  echo "ERROR: Overlay directory not found: ${OVERLAY_DIR}"
  exit 1
fi

BRANCH_NAME="promote/${TARGET_ENV}-${APP_NAME}-${IMAGE_TAG}"

echo "=== Promoting ${APP_NAME} to ${TARGET_ENV} with tag ${IMAGE_TAG} ==="

cd "$GITOPS_REPO"

# Ensure we are on the latest main
git fetch origin
git checkout main
git pull origin main

# Create promotion branch
git checkout -b "$BRANCH_NAME"

# Update the image tag in the Kustomize overlay
KUSTOMIZATION_FILE="${OVERLAY_DIR}/kustomization.yaml"

if command -v yq &>/dev/null; then
  # Use yq for precise YAML manipulation
  yq eval -i "(.images[] | select(.name == \"*${APP_NAME}*\")).newTag = \"${IMAGE_TAG}\"" \
    "$KUSTOMIZATION_FILE"
else
  # Fallback to sed
  sed -i.bak "s/newTag: .*/newTag: ${IMAGE_TAG}/" "$KUSTOMIZATION_FILE"
  rm -f "${KUSTOMIZATION_FILE}.bak"
fi

echo "Updated ${KUSTOMIZATION_FILE}:"
grep -A2 "newTag" "$KUSTOMIZATION_FILE"

# Commit and push
git add "$KUSTOMIZATION_FILE"
git commit -m "chore(${TARGET_ENV}): promote ${APP_NAME} to ${IMAGE_TAG}"
git push origin "$BRANCH_NAME"

# For staging and prod, create a PR instead of merging directly
if [[ "$TARGET_ENV" == "dev" ]]; then
  echo "=== Dev promotion pushed. ArgoCD will auto-sync. ==="
  echo "Consider merging branch ${BRANCH_NAME} to main."
elif command -v gh &>/dev/null; then
  echo "=== Creating pull request for ${TARGET_ENV} promotion ==="
  gh pr create \
    --title "Promote ${APP_NAME} to ${IMAGE_TAG} (${TARGET_ENV})" \
    --body "## Promotion

- **Application:** ${APP_NAME}
- **Target environment:** ${TARGET_ENV}
- **Image tag:** ${IMAGE_TAG}

### Checklist
- [ ] Image \`${IMAGE_TAG}\` validated in previous environment
- [ ] No open incidents affecting this application
- [ ] Rollback plan reviewed" \
    --base main \
    --head "$BRANCH_NAME"
else
  echo "=== Branch pushed: ${BRANCH_NAME} ==="
  echo "Create a PR manually to merge into main."
  echo "(Install 'gh' CLI for automatic PR creation)"
fi

echo "=== Promotion complete ==="
