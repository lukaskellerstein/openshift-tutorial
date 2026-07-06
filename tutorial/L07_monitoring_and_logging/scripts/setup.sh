#!/usr/bin/env bash
# L07 — Monitoring & Logging Setup: Prometheus + Loki (OpenShift built-in)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LESSON_DIR="$(dirname "$SCRIPT_DIR")"

step() { echo "" && echo "=== Step $1: $2 ===" && echo ""; }

echo "NOTE: This script requires cluster-admin privileges."
echo "Make sure you are logged in with cluster-admin access."
echo ""

# --- Step 0: Prerequisites ---
step 0 "Verify prerequisites"
oc whoami || { echo "ERROR: Not logged in. Run 'oc login' first."; exit 1; }
oc auth can-i create configmap -n openshift-monitoring || {
  echo "ERROR: You need cluster-admin privileges."; exit 1
}
echo "Logged in as: $(oc whoami)"
echo "Cluster: $(oc whoami --show-server)"

AWS_REGION=$(oc get infrastructure cluster -o jsonpath='{.status.platformStatus.aws.region}' 2>/dev/null)
CLUSTER_ID=$(oc get infrastructure cluster -o jsonpath='{.status.infrastructureName}' 2>/dev/null)
if [ -z "$AWS_REGION" ]; then
  echo "ERROR: Could not detect AWS region. This script requires an AWS-based cluster."
  exit 1
fi
echo "AWS Region: $AWS_REGION"
echo "Cluster ID: $CLUSTER_ID"

# --- Step 1: Enable User Workload Monitoring ---
step 1 "Enable user workload monitoring"
oc apply -f "$LESSON_DIR/manifests/enable-user-workload-monitoring.yaml"
echo "Waiting for user-workload Prometheus pods..."
until oc get pods -n openshift-user-workload-monitoring 2>/dev/null | grep -q "Running"; do
  echo -n "."
  sleep 5
done
echo " Running!"

# --- Step 2: Create ServiceMonitors + PrometheusRule ---
step 2 "Create ServiceMonitors and PrometheusRule"
oc project shopinsights 2>/dev/null || oc new-project shopinsights

# Ensure port names are set for ServiceMonitor matching
for svc in products-service orders-service analytics-service; do
  oc get service "$svc" -n shopinsights -o jsonpath='{.spec.ports[0].name}' 2>/dev/null | grep -q http || \
    oc patch service "$svc" -n shopinsights --type=json \
      -p '[{"op":"replace","path":"/spec/ports/0/name","value":"http"}]' 2>/dev/null || true
done

oc apply -f "$LESSON_DIR/manifests/products-servicemonitor.yaml" -n shopinsights
oc apply -f "$LESSON_DIR/manifests/orders-servicemonitor.yaml" -n shopinsights
oc apply -f "$LESSON_DIR/manifests/analytics-servicemonitor.yaml" -n shopinsights
oc apply -f "$LESSON_DIR/manifests/products-prometheusrule.yaml" -n shopinsights
echo "ServiceMonitors and PrometheusRule applied."

# --- Step 3: Install Loki Operator ---
step 3 "Install the Loki Operator"
oc apply -f "$LESSON_DIR/manifests/ns-openshift-operators-redhat.yaml"
oc apply -f "$LESSON_DIR/manifests/operator-loki.yaml"

echo -n "Waiting for Loki Operator CSV..."
WAIT_COUNT=0
until oc get csv -n openshift-operators-redhat 2>/dev/null | grep -i loki | grep -q Succeeded; do
  for ip in $(oc get installplan -n openshift-operators-redhat --no-headers 2>/dev/null \
    | awk '$4=="false" {print $1}'); do
    oc patch installplan "$ip" -n openshift-operators-redhat --type merge \
      -p '{"spec":{"approved":true}}' 2>/dev/null || true
  done
  WAIT_COUNT=$((WAIT_COUNT + 1))
  if [ "$WAIT_COUNT" -gt 12 ]; then
    LATEST=$(oc get csv -n openshift-operators-redhat --no-headers 2>/dev/null \
      | grep -i loki | sort -V -k1 | tail -1 | awk '{print $1}')
    for csv in $(oc get csv -n openshift-operators-redhat --no-headers 2>/dev/null \
      | grep -i loki | grep Pending | awk '{print $1}'); do
      if [ "$csv" != "$LATEST" ]; then
        echo -n "(removing stuck $csv) "
        oc delete csv "$csv" -n openshift-operators-redhat 2>/dev/null || true
      fi
    done
  fi
  echo -n "."
  sleep 10
done
echo " Ready!"

# --- Step 4: Install Cluster Logging Operator ---
step 4 "Install the Cluster Logging Operator"
oc apply -f "$LESSON_DIR/manifests/ns-openshift-logging.yaml"
oc apply -f "$LESSON_DIR/manifests/operator-cluster-logging.yaml"

echo -n "Waiting for Cluster Logging Operator CSV..."
WAIT_COUNT=0
until oc get csv -n openshift-logging 2>/dev/null | grep -i cluster-logging | grep -q Succeeded; do
  for ip in $(oc get installplan -n openshift-logging --no-headers 2>/dev/null \
    | awk '$4=="false" {print $1}'); do
    oc patch installplan "$ip" -n openshift-logging --type merge \
      -p '{"spec":{"approved":true}}' 2>/dev/null || true
  done
  WAIT_COUNT=$((WAIT_COUNT + 1))
  if [ "$WAIT_COUNT" -gt 12 ]; then
    LATEST=$(oc get csv -n openshift-logging --no-headers 2>/dev/null \
      | grep -i cluster-logging | sort -V -k1 | tail -1 | awk '{print $1}')
    for csv in $(oc get csv -n openshift-logging --no-headers 2>/dev/null \
      | grep -i cluster-logging | grep Pending | awk '{print $1}'); do
      if [ "$csv" != "$LATEST" ]; then
        echo -n "(removing stuck $csv) "
        oc delete csv "$csv" -n openshift-logging 2>/dev/null || true
      fi
    done
  fi
  echo -n "."
  sleep 10
done
echo " Ready!"

# --- Step 5: Create S3 bucket + LokiStack ---
step 5 "Provision S3 storage and deploy LokiStack"

S3_BUCKET="loki-${CLUSTER_ID}"
echo "S3 bucket name: $S3_BUCKET"

# Try CCO first; fall back to copying existing AWS credentials if CCO can't provision
if oc get secret logging-loki-aws -n openshift-logging &>/dev/null; then
  echo "Secret logging-loki-aws already exists — skipping credential provisioning."
else
  echo "Creating CredentialsRequest for S3 access..."
  oc apply -f "$LESSON_DIR/manifests/loki-s3-credentials-request.yaml"

  echo -n "Waiting for CCO to provision credentials (30s timeout)..."
  CCO_OK=false
  for i in $(seq 1 6); do
    if oc get secret logging-loki-aws -n openshift-logging &>/dev/null; then
      echo " Created via CCO!"
      # CCO uses aws_access_key_id; Loki expects access_key_id — reformat
      AWS_KEY=$(oc get secret logging-loki-aws -n openshift-logging -o jsonpath='{.data.aws_access_key_id}' | base64 -d)
      AWS_SECRET_KEY=$(oc get secret logging-loki-aws -n openshift-logging -o jsonpath='{.data.aws_secret_access_key}' | base64 -d)
      oc create secret generic logging-loki-aws -n openshift-logging \
        --from-literal=access_key_id="$AWS_KEY" \
        --from-literal=access_key_secret="$AWS_SECRET_KEY" \
        --from-literal=bucketnames="$S3_BUCKET" \
        --from-literal=region="$AWS_REGION" \
        --from-literal=endpoint="https://s3.${AWS_REGION}.amazonaws.com" \
        --dry-run=client -o yaml | oc apply -f -
      CCO_OK=true
      break
    fi
    echo -n "."
    sleep 5
  done

  if [ "$CCO_OK" = "false" ]; then
    echo ""
    echo "CCO could not provision credentials (no root aws-creds secret)."
    echo "Falling back to existing cluster AWS credentials..."
    oc delete credentialsrequest loki-logging -n openshift-cloud-credential-operator 2>/dev/null || true

    AWS_KEY=$(oc get secret installer-cloud-credentials -n openshift-image-registry \
      -o jsonpath='{.data.aws_access_key_id}' | base64 -d)
    AWS_SECRET_KEY=$(oc get secret installer-cloud-credentials -n openshift-image-registry \
      -o jsonpath='{.data.aws_secret_access_key}' | base64 -d)

    if [ -z "$AWS_KEY" ] || [ -z "$AWS_SECRET_KEY" ]; then
      echo "ERROR: Could not find AWS credentials. Check installer-cloud-credentials in openshift-image-registry."
      exit 1
    fi

    oc create secret generic logging-loki-aws -n openshift-logging \
      --from-literal=access_key_id="$AWS_KEY" \
      --from-literal=access_key_secret="$AWS_SECRET_KEY" \
      --from-literal=bucketnames="$S3_BUCKET" \
      --from-literal=region="$AWS_REGION" \
      --from-literal=endpoint="https://s3.${AWS_REGION}.amazonaws.com" \
      --dry-run=client -o yaml | oc apply -f -
    echo "S3 secret created from cluster credentials."
  fi
fi

echo "Creating S3 bucket via a one-shot Job..."
sed -e "s|__S3_BUCKET__|${S3_BUCKET}|g" \
    -e "s|__AWS_REGION__|${AWS_REGION}|g" \
    "$LESSON_DIR/manifests/job-create-s3-bucket.yaml" | oc apply -f -

echo -n "Waiting for bucket creation Job to complete..."
until oc get job create-loki-bucket -n openshift-logging -o jsonpath='{.status.succeeded}' 2>/dev/null | grep -q 1; do
  FAILED=$(oc get job create-loki-bucket -n openshift-logging -o jsonpath='{.status.failed}' 2>/dev/null)
  if [ "$FAILED" = "1" ]; then
    echo ""
    echo "ERROR: Bucket creation Job failed. Check logs:"
    oc logs job/create-loki-bucket -n openshift-logging 2>/dev/null || true
    exit 1
  fi
  echo -n "."
  sleep 5
done
echo " Done!"
oc logs job/create-loki-bucket -n openshift-logging 2>/dev/null || true

echo "Deploying LokiStack..."
oc apply -f "$LESSON_DIR/manifests/lokistack.yaml"

echo -n "Waiting for LokiStack pods to start (this may take 3-5 minutes)..."
until oc get pods -n openshift-logging -l app.kubernetes.io/component=compactor 2>/dev/null | grep -q Running; do
  echo -n "."
  sleep 15
done
echo " LokiStack pods running!"
oc get pods -n openshift-logging -l app.kubernetes.io/instance=logging-loki --no-headers 2>/dev/null

# --- Step 6: Create ClusterLogForwarder ---
step 6 "Deploy ClusterLogForwarder"

echo "Granting cluster-logging-operator SA required RBAC..."
oc adm policy add-cluster-role-to-user collect-application-logs \
  -z cluster-logging-operator -n openshift-logging 2>/dev/null || true
oc adm policy add-cluster-role-to-user logging-collector-logs-writer \
  -z cluster-logging-operator -n openshift-logging 2>/dev/null || true

oc apply -f "$LESSON_DIR/manifests/clusterlogforwarder.yaml"

echo -n "Waiting for collector pods..."
until oc get pods -n openshift-logging -l app.kubernetes.io/component=collector 2>/dev/null | grep -q Running; do
  echo -n "."
  sleep 10
done
echo " Running!"

echo "Collector pods:"
oc get pods -n openshift-logging -l app.kubernetes.io/component=collector

# Enable the Logging Console Plugin (Observe > Logs tab)
echo ""
echo "Enabling the Logging Console Plugin..."
oc apply -f "$LESSON_DIR/manifests/uiplugin-logging.yaml"

echo -n "Waiting for logging-view-plugin to register..."
until oc get consoleplugin logging-view-plugin &>/dev/null; do
  echo -n "."
  sleep 5
done
echo " Registered!"

# --- Step 7: Print URLs ---
step 7 "Setup complete — URLs"

CONSOLE_HOST=$(oc get route console -n openshift-console -o jsonpath='{.spec.host}' 2>/dev/null)
DASHBOARD_HOST=$(oc get route dashboard-ui -n shopinsights -o jsonpath='{.spec.host}' 2>/dev/null || echo "")

echo "============================================"
echo "  L07 Observability Stack Ready!"
echo "============================================"
echo ""
echo "  Dashboard:     https://${DASHBOARD_HOST}"
echo "  Console:       https://${CONSOLE_HOST}"
echo "    Metrics:     https://${CONSOLE_HOST}/monitoring/query-browser"
echo "    Logs:        https://${CONSOLE_HOST}/monitoring/logs"
echo "    Alerts:      https://${CONSOLE_HOST}/monitoring/alerts"
echo "    Targets:     https://${CONSOLE_HOST}/monitoring/targets"
echo ""
echo "Next: ./demo.sh (generate traffic and explore)"
echo "Then: L12 (custom Grafana dashboards)"
