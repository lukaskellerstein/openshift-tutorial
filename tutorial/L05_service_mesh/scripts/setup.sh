#!/usr/bin/env bash
# L05 — Service Mesh Setup: install operators, Istio ambient mode, waypoint proxy
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LESSON_DIR="$(dirname "$SCRIPT_DIR")"

step() { echo "" && echo "=== Step $1: $2 ===" && echo ""; }

echo "NOTE: This script requires cluster-admin privileges."
echo "Make sure you are logged in with cluster-admin access."
echo ""

# --- Step 0: Enable OVN-Kubernetes local gateway mode ---
step 0 "Enable OVN-Kubernetes local gateway mode (routingViaHost)"
CURRENT_RVH=$(oc get network.operator.openshift.io cluster -o jsonpath='{.spec.defaultNetwork.ovnKubernetesConfig.gatewayConfig.routingViaHost}' 2>/dev/null)
if [ "$CURRENT_RVH" = "true" ]; then
  echo "routingViaHost already enabled — skipping."
else
  echo "Setting routingViaHost=true (required for ambient mode health probes on OVN-Kubernetes)..."
  oc patch network.operator.openshift.io cluster --type merge \
    -p '{"spec":{"defaultNetwork":{"ovnKubernetesConfig":{"gatewayConfig":{"routingViaHost":true}}}}}'
  echo "Waiting for OVN-Kubernetes rollout..."
  sleep 60
  oc get co network 2>/dev/null | tail -1
fi

# --- Step 1: Install the Service Mesh Operator ---
step 1 "Install the Service Mesh Operator (Sail)"
oc apply -f "$LESSON_DIR/manifests/operator-sail.yaml"

# --- Step 2: Install the Kiali Operator ---
step 2 "Install the Kiali Operator"
oc apply -f "$LESSON_DIR/manifests/operator-kiali.yaml"

# --- Step 3: Install the Tempo Operator ---
step 3 "Install the Tempo Operator"
oc apply -f "$LESSON_DIR/manifests/operator-tempo.yaml"

# --- Step 3b: Install the Cluster Observability Operator ---
step "3b" "Install the Cluster Observability Operator (Console tracing plugin)"
oc apply -f "$LESSON_DIR/manifests/operator-coo.yaml"

# --- Step 3c: Install the OpenTelemetry Operator ---
step "3c" "Install the OpenTelemetry Operator"
oc apply -f "$LESSON_DIR/manifests/operator-otel.yaml"

# --- Wait for all operator CSVs ---
step "1-3" "Waiting for operator CSVs to reach Succeeded..."
echo "This may take 2-5 minutes."

for op in servicemesh kiali tempo observability opentelemetry; do
  echo -n "Waiting for ${op} operator CSV..."
  WAIT_COUNT=0
  until oc get csv -n openshift-operators 2>/dev/null | grep -i "$op" | grep -q Succeeded; do
    # Auto-approve any pending InstallPlans (some clusters use Manual approval)
    for ip in $(oc get installplan -n openshift-operators --no-headers 2>/dev/null \
      | awk '$4=="false" {print $1}'); do
      oc patch installplan "$ip" -n openshift-operators --type merge \
        -p '{"spec":{"approved":true}}' 2>/dev/null || true
    done
    # After 2 minutes, remove intermediate Pending CSVs that block the upgrade chain
    # (keep the latest version, only delete older stuck intermediates)
    WAIT_COUNT=$((WAIT_COUNT + 1))
    if [ "$WAIT_COUNT" -gt 12 ]; then
      LATEST=$(oc get csv -n openshift-operators --no-headers 2>/dev/null \
        | grep -i "$op" | sort -V -k1 | tail -1 | awk '{print $1}')
      for csv in $(oc get csv -n openshift-operators --no-headers 2>/dev/null \
        | grep -i "$op" | grep Pending | awk '{print $1}'); do
        if [ "$csv" != "$LATEST" ]; then
          echo -n "(removing stuck $csv) "
          oc delete csv "$csv" -n openshift-operators 2>/dev/null || true
        fi
      done
    fi
    echo -n "."
    sleep 10
  done
  echo " Ready!"
done

echo ""
oc get csv -n openshift-operators

# --- Step 4: Create Istio Control Plane, CNI, and ZTunnel ---
step 4 "Create Istio control plane, CNI, and ZTunnel"
oc new-project istio-system 2>/dev/null || oc project istio-system
oc new-project istio-cni 2>/dev/null || true
oc new-project ztunnel 2>/dev/null || true

oc apply -f "$LESSON_DIR/manifests/istio.yaml"
oc apply -f "$LESSON_DIR/manifests/istiocni.yaml"
oc apply -f "$LESSON_DIR/manifests/ztunnel.yaml"

echo "Waiting for all components to become Healthy..."
for component in istio istiocni ztunnel; do
  echo -n "  ${component}..."
  until oc get "$component" default 2>/dev/null | grep -q Healthy; do
    echo -n "."
    sleep 10
  done
  echo " Healthy!"
done

echo ""
oc get istio,istiocni,ztunnel -A 2>/dev/null
echo ""
echo "Istiod pods:"
oc get pods -n istio-system

# --- Step 5: Deploy Observability (Kiali + Tempo) ---
step 5 "Deploy Kiali and Tempo instances"

echo "Creating Kiali instance..."
oc apply -f "$LESSON_DIR/manifests/kiali.yaml"

echo "Creating TempoMonolithic instance..."
oc apply -f "$LESSON_DIR/manifests/tempo.yaml"

echo "Creating Telemetry resource (100% trace sampling)..."
oc apply -f "$LESSON_DIR/manifests/telemetry-tracing.yaml"

echo "Granting Kiali SA cluster-monitoring-view for Prometheus access..."
oc adm policy add-cluster-role-to-user cluster-monitoring-view \
  -z kiali-service-account -n istio-system 2>/dev/null || true

echo "Waiting for Kiali pod..."
until oc get pods -n istio-system -l app.kubernetes.io/name=kiali 2>/dev/null | grep -q "1/1"; do
  echo -n "."
  sleep 5
done
echo " Ready!"

echo "Waiting for Tempo pod..."
until oc get pods -n istio-system -l app.kubernetes.io/name=tempo 2>/dev/null | grep -q Running; do
  echo -n "."
  sleep 5
done
echo " Ready!"

echo "Creating OTel collector ServiceAccount..."
oc create serviceaccount otel-collector -n istio-system 2>/dev/null || true

echo "Creating RBAC for OTel collector to write traces to 'dev' tenant..."
oc apply -f "$LESSON_DIR/manifests/rbac-tempo-write.yaml"

echo "Creating RBAC for authenticated users to read traces..."
oc apply -f "$LESSON_DIR/manifests/rbac-tempo-read.yaml"

echo "Creating OpenTelemetry Collector..."
oc apply -f "$LESSON_DIR/manifests/otel-collector.yaml"

echo "Waiting for OTel collector pod..."
until oc get pods -n istio-system -l app.kubernetes.io/name=otel-collector-collector 2>/dev/null | grep -q "1/1"; do
  echo -n "."
  sleep 5
done
echo " Ready!"

echo "Creating distributed tracing UI plugin..."
oc apply -f "$LESSON_DIR/manifests/uiplugin-tracing.yaml"

# Grant ztunnel SA permission to impersonate service accounts (needed for SPIFFE cert fetching)
echo ""
echo "Granting ztunnel impersonation RBAC..."
oc apply -f "$LESSON_DIR/manifests/rbac-ztunnel-impersonation.yaml"

# --- Step 7: Enroll the ShopInsights Namespace ---
step 7 "Enroll shopinsights namespace in ambient mesh"
oc label namespace shopinsights istio.io/dataplane-mode=ambient --overwrite

echo "Namespace labels:"
oc get namespace shopinsights --show-labels | grep dataplane

echo ""
echo "Restarting application pods so istio-cni can configure ztunnel traffic interception..."
oc rollout restart deployment/dashboard-ui deployment/analytics-service \
  deployment/products-service deployment/orders-service -n shopinsights
oc rollout status deployment/dashboard-ui deployment/analytics-service \
  deployment/products-service deployment/orders-service -n shopinsights --timeout=120s

echo ""
echo "Pods (should be 1/1 — no sidecars):"
oc get pods -n shopinsights

# --- Step 8: Verify mTLS ---
step 8 "Verify mTLS (automatic in ambient mode)"
echo "Testing inter-service communication (mTLS transparent to app):"
oc exec deploy/dashboard-ui -n shopinsights -- \
  curl -s http://products-service:8080/healthz 2>/dev/null || echo "(service not responding — check pods)"
echo "mTLS is enabled by default in ambient mode (PERMISSIVE). No PeerAuthentication needed."

# --- Step 9: Deploy Waypoint Proxy ---
step 9 "Deploy waypoint proxy and label services"
oc apply -f "$LESSON_DIR/manifests/waypoint.yaml"

echo "Waiting for waypoint pod..."
until oc get pods -n shopinsights -l gateway.networking.k8s.io/gateway-name=waypoint 2>/dev/null | grep -q Running; do
  echo -n "."
  sleep 5
done
echo " Running!"

oc label service analytics-service -n shopinsights istio.io/use-waypoint=waypoint --overwrite
oc label service orders-service -n shopinsights istio.io/use-waypoint=waypoint --overwrite
oc label service products-service -n shopinsights istio.io/use-waypoint=waypoint --overwrite

echo ""
echo "Waypoint pod:"
oc get pods -n shopinsights -l gateway.networking.k8s.io/gateway-name=waypoint

echo ""
echo "Services with waypoint label:"
oc get service -n shopinsights -L istio.io/use-waypoint

echo ""
echo "=== L05 Setup Complete ==="
echo "Ambient mesh is active with mTLS + waypoint proxy."
echo "Next: ./demo.sh (canary deployment, circuit breaker, observability)"
