#!/usr/bin/env bash
# L12 — Custom Monitoring Dashboards: Grafana with Prometheus, Loki, and Tempo
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LESSON_DIR="$(dirname "$SCRIPT_DIR")"

step() { echo "" && echo "=== Step $1: $2 ===" && echo ""; }

echo "NOTE: This script requires cluster-admin privileges."
echo "Prerequisites: L07 (Prometheus + Loki) and L05 (Service Mesh + Tempo) must be running."
echo ""

# --- Step 0: Verify prerequisites ---
step 0 "Verify prerequisites"
oc whoami || { echo "ERROR: Not logged in. Run 'oc login' first."; exit 1; }

echo "Checking user workload monitoring..."
oc get pods -n openshift-user-workload-monitoring --no-headers 2>/dev/null | grep -q prometheus-user-workload || {
  echo "ERROR: User workload monitoring not enabled. Run L07/scripts/setup.sh first."; exit 1
}
echo "  User workload monitoring: OK"

echo "Checking LokiStack..."
oc get lokistack logging-loki -n openshift-logging &>/dev/null || {
  echo "ERROR: LokiStack not deployed. Run L07/scripts/setup.sh first."; exit 1
}
echo "  LokiStack: OK"

echo "Checking Tempo..."
oc get tempomonolithic sample -n istio-system &>/dev/null || {
  echo "WARNING: TempoMonolithic not found. Traces dashboard will not work."
  echo "  Run L05/scripts/setup.sh to deploy the service mesh with Tempo."
  TEMPO_AVAILABLE=false
}
TEMPO_AVAILABLE=${TEMPO_AVAILABLE:-true}
echo "  Tempo: ${TEMPO_AVAILABLE}"

echo "Checking shopinsights project..."
oc project shopinsights 2>/dev/null || {
  echo "ERROR: shopinsights project not found. Deploy the app first."; exit 1
}
echo "  shopinsights: OK"

# --- Step 1: Install Grafana Operator ---
step 1 "Install the Grafana Operator (community)"
oc apply -f "$LESSON_DIR/manifests/operator-grafana.yaml"

echo -n "Waiting for Grafana Operator CSV..."
WAIT_COUNT=0
until oc get csv -n openshift-operators 2>/dev/null | grep -i grafana | grep -q Succeeded; do
  for ip in $(oc get installplan -n openshift-operators --no-headers 2>/dev/null \
    | awk '$4=="false" {print $1}'); do
    oc patch installplan "$ip" -n openshift-operators --type merge \
      -p '{"spec":{"approved":true}}' 2>/dev/null || true
  done
  WAIT_COUNT=$((WAIT_COUNT + 1))
  if [ "$WAIT_COUNT" -gt 12 ]; then
    LATEST=$(oc get csv -n openshift-operators --no-headers 2>/dev/null \
      | grep -i grafana | sort -V -k1 | tail -1 | awk '{print $1}')
    for csv in $(oc get csv -n openshift-operators --no-headers 2>/dev/null \
      | grep -i grafana | grep Pending | awk '{print $1}'); do
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

# --- Step 2: Deploy Grafana instance ---
step 2 "Deploy Grafana instance"
oc apply -f "$LESSON_DIR/manifests/grafana-instance.yaml"

echo -n "Waiting for Grafana pod..."
until oc get pods -n shopinsights -l app=grafana 2>/dev/null | grep -q Running; do
  echo -n "."
  sleep 5
done
echo " Running!"

# --- Step 3: Configure RBAC ---
step 3 "Configure Grafana ServiceAccount RBAC"

echo -n "Waiting for grafana-sa ServiceAccount..."
until oc get sa grafana-sa -n shopinsights &>/dev/null; do
  echo -n "."
  sleep 3
done
echo " Found!"

# Prometheus/Thanos access
oc adm policy add-cluster-role-to-user cluster-monitoring-view \
  -z grafana-sa -n shopinsights

# Loki logs access
oc apply -f "$LESSON_DIR/manifests/grafana-rbac-loki.yaml"

# Tempo traces access
if [ "$TEMPO_AVAILABLE" = "true" ]; then
  oc apply -f "$LESSON_DIR/manifests/grafana-rbac-tempo.yaml"
  echo "Tempo traces RBAC configured."
fi

GRAFANA_TOKEN=$(oc create token grafana-sa -n shopinsights --duration=8760h)
echo "Grafana SA token created (valid for 1 year)."

# --- Step 4: Create datasources ---
step 4 "Create Grafana datasources (Prometheus, Loki, Tempo)"

echo "Creating Prometheus datasource..."
sed "s|__GRAFANA_TOKEN__|${GRAFANA_TOKEN}|g" \
    "$LESSON_DIR/manifests/grafana-datasource-prometheus.yaml" | oc apply -f -

echo "Creating Loki datasource..."
sed "s|__GRAFANA_TOKEN__|${GRAFANA_TOKEN}|g" \
    "$LESSON_DIR/manifests/grafana-datasource-loki.yaml" | oc apply -f -

if [ "$TEMPO_AVAILABLE" = "true" ]; then
  echo "Creating Tempo datasource..."
  sed "s|__GRAFANA_TOKEN__|${GRAFANA_TOKEN}|g" \
      "$LESSON_DIR/manifests/grafana-datasource-tempo.yaml" | oc apply -f -
else
  echo "Skipping Tempo datasource (Tempo not available)."
fi

# --- Step 5: Deploy dashboards ---
step 5 "Deploy Grafana dashboards"

echo "Applying Overview dashboard..."
oc apply -f "$LESSON_DIR/manifests/grafana-dashboard-overview.yaml"

echo "Applying Products Service dashboard..."
oc apply -f "$LESSON_DIR/manifests/grafana-dashboard-products.yaml"

echo "Applying Logs dashboard..."
oc apply -f "$LESSON_DIR/manifests/grafana-dashboard-logs.yaml"

if [ "$TEMPO_AVAILABLE" = "true" ]; then
  echo "Applying Traces dashboard..."
  oc apply -f "$LESSON_DIR/manifests/grafana-dashboard-traces.yaml"
else
  echo "Skipping Traces dashboard (Tempo not available)."
fi

echo "All dashboards deployed."

# --- Step 6: Print URLs ---
step 6 "Setup complete — URLs"

GRAFANA_HOST=$(oc get route grafana-route -n shopinsights -o jsonpath='{.spec.host}' 2>/dev/null || echo "")

echo "============================================"
echo "  L12 Custom Monitoring Dashboards Ready!"
echo "============================================"
echo ""
if [ -n "$GRAFANA_HOST" ]; then
  echo "  Grafana:       https://${GRAFANA_HOST}"
  echo "    Login:       admin / openshift"
  echo ""
  echo "  Dashboards (in shopinsights folder):"
  echo "    Overview:    https://${GRAFANA_HOST}/d/shopinsights-overview"
  echo "    Products:    https://${GRAFANA_HOST}/d/shopinsights-products"
  echo "    Logs:        https://${GRAFANA_HOST}/d/shopinsights-logs"
  if [ "$TEMPO_AVAILABLE" = "true" ]; then
    echo "    Traces:      https://${GRAFANA_HOST}/d/shopinsights-traces"
  fi
fi
echo ""
echo "Next: ./demo.sh (generate traffic and explore dashboards)"
