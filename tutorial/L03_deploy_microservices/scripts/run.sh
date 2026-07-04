#!/usr/bin/env bash
# L03 — Deploy the Microservices Stack from ImageStreams
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LESSON_DIR="$(dirname "$SCRIPT_DIR")"

step() { echo "" && echo "=== Step $1: $2 ===" && echo ""; }

# --- Step 1: Switch to project ---
step 1 "Switch to shopinsights project"
oc project shopinsights

# --- Step 2: Create ConfigMap and Secret ---
step 2 "Create ConfigMap and Secret"
oc apply -f "$LESSON_DIR/manifests/configmap.yaml"
oc apply -f "$LESSON_DIR/manifests/secret.yaml"

# --- Step 3: Create PVCs ---
step 3 "Create PersistentVolumeClaims"
oc apply -f "$LESSON_DIR/manifests/pvcs.yaml"

# --- Step 4: Deploy all services ---
step 4 "Deploy Products Service"
oc apply -f "$LESSON_DIR/manifests/products-deployment.yaml"
oc apply -f "$LESSON_DIR/manifests/products-service.yaml"

step 5 "Deploy Orders Service"
oc apply -f "$LESSON_DIR/manifests/orders-deployment.yaml"
oc apply -f "$LESSON_DIR/manifests/orders-service.yaml"

step 6 "Deploy Analytics Service"
oc apply -f "$LESSON_DIR/manifests/analytics-deployment.yaml"
oc apply -f "$LESSON_DIR/manifests/analytics-service.yaml"

step 7 "Deploy Dashboard UI"
oc apply -f "$LESSON_DIR/manifests/dashboard-deployment.yaml"
oc apply -f "$LESSON_DIR/manifests/dashboard-service.yaml"

# --- Step 8: Wait for pods to be ready ---
step 8 "Waiting for pods to be ready..."
oc rollout status deploy/products-service --timeout=120s
oc rollout status deploy/orders-service --timeout=120s
oc rollout status deploy/analytics-service --timeout=120s
oc rollout status deploy/dashboard-ui --timeout=120s

# --- Step 9: Verify ---
step 9 "Verify"
echo "Pods:"
oc get pods -l app=shopinsights
echo ""
echo "Services:"
oc get svc -l app=shopinsights
echo ""
echo "Health checks:"
oc exec deploy/products-service -- curl -s http://localhost:8080/healthz 2>/dev/null || echo "  products: waiting..."
oc exec deploy/orders-service -- curl -s http://localhost:8080/healthz 2>/dev/null || echo "  orders: waiting..."
oc exec deploy/analytics-service -- curl -s http://localhost:8080/healthz 2>/dev/null || echo "  analytics: waiting..."

echo ""
echo "=== L03 Complete ==="
echo "All 4 services deployed and running."
echo "Next: cd ../L04_expose_externally && ./scripts/run.sh"
