#!/usr/bin/env bash
# L02 — Build & Image Resources: build all 4 ShopInsights services on-cluster
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LESSON_DIR="$(dirname "$SCRIPT_DIR")"

# Source .env
ENV_FILE="${LESSON_DIR}/../.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "Error: ${ENV_FILE} not found."
  echo "Run: cp tutorial/.env.example tutorial/.env  and set GITHUB_USERNAME"
  exit 1
fi
source "$ENV_FILE"

if [ "$GITHUB_USERNAME" = "your-username" ] || [ -z "$GITHUB_USERNAME" ]; then
  echo "Error: GITHUB_USERNAME is not set in ${ENV_FILE}"
  echo "Edit the file and set your GitHub username."
  exit 1
fi

apply() {
  sed "s/<your-username>/${GITHUB_USERNAME}/g" "$LESSON_DIR/$1" | oc apply -f -
}

step() { echo "" && echo "=== Step $1: $2 ===" && echo ""; }

oc project shopinsights

# --- Step 1: Create ImageStreams ---
step 1 "Create ImageStreams for all services"
oc apply -f "$LESSON_DIR/manifests/products-imagestream.yaml"
oc apply -f "$LESSON_DIR/manifests/orders-imagestream.yaml"
oc apply -f "$LESSON_DIR/manifests/analytics-imagestream.yaml"
oc apply -f "$LESSON_DIR/manifests/dashboard-imagestream.yaml"
oc get imagestreams -l app=shopinsights

# --- Step 2: Create BuildConfigs (with variable substitution) ---
step 2 "Create BuildConfigs"
apply "manifests/products-buildconfig.yaml"
apply "manifests/orders-buildconfig.yaml"
apply "manifests/analytics-buildconfig.yaml"
apply "manifests/dashboard-buildconfig.yaml"
oc get buildconfigs -l app=shopinsights

# --- Step 3: Start all builds ---
step 3 "Start builds"
oc start-build products-service
oc start-build orders-service
oc start-build analytics-service
oc start-build dashboard-ui

# --- Step 4: Wait for builds to complete ---
step 4 "Waiting for builds to complete (this takes 5-10 minutes)..."
echo "Builds started:"
oc get builds

for bc in products-service orders-service analytics-service dashboard-ui; do
  echo "Waiting for ${bc}-1..."
  while true; do
    phase=$(oc get build "${bc}-1" -o jsonpath='{.status.phase}' 2>/dev/null || echo "Unknown")
    case "$phase" in
      Complete)
        echo "  ${bc}-1: Complete"
        break
        ;;
      Failed|Error|Cancelled)
        echo "  ${bc}-1: ${phase} — check logs with: oc logs build/${bc}-1"
        exit 1
        ;;
      *)
        sleep 10
        ;;
    esac
  done
done

# --- Step 5: Verify ---
step 5 "Verify ImageStreams have tags"
oc get imagestreams -l app=shopinsights
echo ""
oc get builds

echo ""
echo "=== L02 Complete ==="
echo "All 4 images built and stored in the internal registry."
echo "Next: cd ../L03_deploy_microservices && ./scripts/run.sh"
