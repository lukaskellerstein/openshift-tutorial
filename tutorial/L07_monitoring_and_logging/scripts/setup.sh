#!/usr/bin/env bash
# L07 — Monitoring & Logging Setup: Prometheus + Loki + Grafana
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

# --- Step 2: Build and deploy instrumented Products Service ---
step 2 "Build instrumented Products Service (binary build)"
oc project shopinsights 2>/dev/null || oc new-project shopinsights

BUILD_DIR=$(mktemp -d)
trap "rm -rf $BUILD_DIR" EXIT

cp "$LESSON_DIR/app/products_service_with_metrics.py" "$BUILD_DIR/app.py"

cat > "$BUILD_DIR/pyproject.toml" <<'PYPROJECT'
[project]
name = "products-service"
version = "1.0.0"
description = "ShopInsights Products Service — FastAPI + DuckDB"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn>=0.30.6",
    "duckdb>=1.1.0",
    "pydantic>=2.9.0",
    "pyarrow>=17.0.0",
    "prometheus_client>=0.21.0",
]
PYPROJECT

cat > "$BUILD_DIR/Dockerfile" <<'DOCKERFILE'
FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN useradd -m -u 1001 appuser
WORKDIR /app
COPY pyproject.toml ./
RUN uv lock && uv sync --frozen --no-dev --no-install-project
COPY app.py .
RUN mkdir -p /data && chown appuser:appuser /data
ENV UV_CACHE_DIR=/tmp/uv-cache
USER 1001
EXPOSE 8080
CMD ["uv", "run", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
DOCKERFILE

# Remove contextDir from BuildConfig if present (binary builds can't use contextDir)
oc get bc products-service -n shopinsights -o jsonpath='{.spec.source.contextDir}' 2>/dev/null && \
  oc patch bc products-service -n shopinsights --type=json \
    -p '[{"op": "remove", "path": "/spec/source/contextDir"}]' 2>/dev/null || true

echo "Starting binary build..."
oc start-build products-service --from-dir="$BUILD_DIR" --follow -n shopinsights

echo "Waiting for rollout..."
oc rollout status deployment/products-service -n shopinsights --timeout=120s

# Ensure port name is set for ServiceMonitor matching
oc get service products-service -n shopinsights -o jsonpath='{.spec.ports[0].name}' 2>/dev/null | grep -q http || \
  oc patch service products-service -n shopinsights --type=json \
    -p '[{"op":"replace","path":"/spec/ports/0/name","value":"http"}]'

echo "Products Service deployed."

# --- Step 3: Create ServiceMonitor + PrometheusRule ---
step 3 "Create ServiceMonitor and PrometheusRule"
oc apply -f "$LESSON_DIR/manifests/products-servicemonitor.yaml" -n shopinsights
oc apply -f "$LESSON_DIR/manifests/products-prometheusrule.yaml" -n shopinsights
echo "ServiceMonitor and PrometheusRule applied."

# --- Step 4: Install Loki Operator ---
step 4 "Install the Loki Operator"
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

# --- Step 5: Install Cluster Logging Operator ---
step 5 "Install the Cluster Logging Operator"
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

# --- Step 6: Create S3 bucket + LokiStack ---
step 6 "Provision S3 storage and deploy LokiStack"

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
cat <<JOBEOF | oc apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: create-loki-bucket
  namespace: openshift-logging
spec:
  ttlSecondsAfterFinished: 300
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: aws-cli
          image: amazon/aws-cli:latest
          command: ["sh", "-c"]
          args:
            - |
              aws s3api create-bucket \
                --bucket "\${S3_BUCKET}" \
                --region "\${AWS_REGION}" \
                --create-bucket-configuration LocationConstraint="\${AWS_REGION}" \
              2>/dev/null || echo "Bucket may already exist — continuing."
              echo "Bucket \${S3_BUCKET} ready."
          env:
            - name: AWS_ACCESS_KEY_ID
              valueFrom:
                secretKeyRef:
                  name: logging-loki-aws
                  key: access_key_id
            - name: AWS_SECRET_ACCESS_KEY
              valueFrom:
                secretKeyRef:
                  name: logging-loki-aws
                  key: access_key_secret
            - name: AWS_DEFAULT_REGION
              value: "$AWS_REGION"
            - name: S3_BUCKET
              value: "$S3_BUCKET"
            - name: AWS_REGION
              value: "$AWS_REGION"
JOBEOF

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

# --- Step 7: Create ClusterLogForwarder ---
step 7 "Deploy ClusterLogForwarder"

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

# --- Step 8: Install Grafana Operator ---
step 8 "Install the Grafana Operator (community)"
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

# --- Step 9: Create Grafana RBAC ---
step 9 "Configure Grafana ServiceAccount RBAC"

echo "Waiting for Grafana operator to create grafana-sa..."
until oc get sa grafana-sa -n shopinsights &>/dev/null; do
  echo -n "."
  sleep 3
done
echo " Found!"

oc adm policy add-cluster-role-to-user cluster-monitoring-view \
  -z grafana-sa -n shopinsights

cat <<'RBAC' | oc apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: grafana-loki-logs-reader
rules:
  - apiGroups: ["loki.grafana.com"]
    resources: ["application"]
    resourceNames: ["logs"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: grafana-loki-logs-reader
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: grafana-loki-logs-reader
subjects:
  - kind: ServiceAccount
    name: grafana-sa
    namespace: shopinsights
RBAC

GRAFANA_TOKEN=$(oc create token grafana-sa -n shopinsights --duration=8760h)
echo "Grafana SA token created (valid for 1 year)."

# --- Step 10: Deploy Grafana instance + datasources + dashboard ---
step 10 "Deploy Grafana instance, datasources, and dashboard"

oc apply -f "$LESSON_DIR/manifests/grafana-instance.yaml"

echo -n "Waiting for Grafana pod..."
until oc get pods -n shopinsights -l app=grafana 2>/dev/null | grep -q Running; do
  echo -n "."
  sleep 5
done
echo " Running!"

THANOS_URL="https://thanos-querier.openshift-monitoring.svc.cluster.local:9091"
LOKI_URL="https://logging-loki-gateway-http.openshift-logging.svc.cluster.local:8080/api/logs/v1/application"

echo "Creating Prometheus datasource..."
cat <<DSEOF | oc apply -f -
apiVersion: grafana.integreatly.org/v1beta1
kind: GrafanaDatasource
metadata:
  name: prometheus
  namespace: shopinsights
spec:
  instanceSelector:
    matchLabels:
      dashboards: grafana
  datasource:
    name: Prometheus
    type: prometheus
    access: proxy
    url: ${THANOS_URL}
    isDefault: true
    jsonData:
      httpHeaderName1: Authorization
      timeInterval: "15s"
      tlsSkipVerify: true
    secureJsonData:
      httpHeaderValue1: "Bearer ${GRAFANA_TOKEN}"
DSEOF

echo "Creating Loki datasource..."
cat <<DSEOF | oc apply -f -
apiVersion: grafana.integreatly.org/v1beta1
kind: GrafanaDatasource
metadata:
  name: loki
  namespace: shopinsights
spec:
  instanceSelector:
    matchLabels:
      dashboards: grafana
  datasource:
    name: Loki
    type: loki
    access: proxy
    url: ${LOKI_URL}
    jsonData:
      httpHeaderName1: Authorization
      tlsSkipVerify: true
    secureJsonData:
      httpHeaderValue1: "Bearer ${GRAFANA_TOKEN}"
DSEOF

echo "Creating Grafana dashboard..."
oc apply -f "$LESSON_DIR/manifests/grafana-dashboard.yaml"

echo "Grafana resources deployed."

# --- Step 11: Print URLs ---
step 11 "Setup complete — URLs"

CONSOLE_HOST=$(oc get route console -n openshift-console -o jsonpath='{.spec.host}' 2>/dev/null)
GRAFANA_HOST=$(oc get route grafana-route -n shopinsights -o jsonpath='{.spec.host}' 2>/dev/null || echo "")
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
if [ -n "$GRAFANA_HOST" ]; then
  echo "  Grafana:       https://${GRAFANA_HOST}"
  echo "    (admin/admin or anonymous viewer)"
fi
echo ""
echo "Next: ./demo.sh (generate traffic and explore)"
