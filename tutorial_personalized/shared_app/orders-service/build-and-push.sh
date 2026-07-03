#!/bin/bash
set -euo pipefail

IMAGE="ghcr.io/lukaskellerstein/openshift-tutorial/shopinsights-orders:latest"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "$IMAGE — logging in to ghcr.io..."
echo "$(gh auth token)" | podman login ghcr.io -u lukaskellerstein --password-stdin

echo "Building $IMAGE..."
podman build --platform linux/amd64 -t "$IMAGE" "$SCRIPT_DIR"

echo "Pushing $IMAGE..."
podman push "$IMAGE"

echo "Done: $IMAGE"
