#!/bin/bash
set -euo pipefail

REGISTRY_USER="${REGISTRY_USER:-your-username}"
IMAGE="ghcr.io/${REGISTRY_USER}/openshift-tutorial/shopinsights-orders:latest"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "$IMAGE — logging in to ghcr.io..."
echo "$(gh auth token)" | podman login ghcr.io -u "${REGISTRY_USER}" --password-stdin

echo "Building $IMAGE..."
podman build --platform linux/amd64 -t "$IMAGE" "$SCRIPT_DIR"

echo "Pushing $IMAGE..."
podman push "$IMAGE"

echo "Done: $IMAGE"
