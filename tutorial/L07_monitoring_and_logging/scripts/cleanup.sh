#!/usr/bin/env bash
# L07 — Cleanup: remove monitoring, logging, and Grafana components
set -euo pipefail

echo "=== L07 Cleanup ==="

# --- Grafana resources ---
echo "Removing Grafana resources..."
oc delete grafanadashboard shopinsights-products -n shopinsights 2>/dev/null || true
oc delete grafanadatasource prometheus loki -n shopinsights 2>/dev/null || true
oc delete grafana grafana -n shopinsights 2>/dev/null || true

echo "Removing Grafana RBAC..."
oc delete clusterrolebinding grafana-loki-logs-reader 2>/dev/null || true
oc delete clusterrole grafana-loki-logs-reader 2>/dev/null || true
oc adm policy remove-cluster-role-from-user cluster-monitoring-view \
  -z grafana-sa -n shopinsights 2>/dev/null || true

# --- ClusterLogForwarder ---
echo "Removing ClusterLogForwarder..."
oc delete clusterlogforwarder instance -n openshift-logging 2>/dev/null || true

echo "Removing log forwarder RBAC..."
oc adm policy remove-cluster-role-from-user collect-application-logs \
  -z cluster-logging-operator -n openshift-logging 2>/dev/null || true
oc adm policy remove-cluster-role-from-user logging-collector-logs-writer \
  -z cluster-logging-operator -n openshift-logging 2>/dev/null || true

# --- LokiStack ---
echo "Removing LokiStack..."
oc delete lokistack logging-loki -n openshift-logging 2>/dev/null || true

# --- S3 bucket cleanup ---
echo "Cleaning up S3 bucket..."
CLUSTER_ID=$(oc get infrastructure cluster -o jsonpath='{.status.infrastructureName}' 2>/dev/null || echo "")
S3_BUCKET="loki-${CLUSTER_ID}"
AWS_REGION=$(oc get infrastructure cluster -o jsonpath='{.status.platformStatus.aws.region}' 2>/dev/null || echo "")

if [ -n "$CLUSTER_ID" ] && [ -n "$AWS_REGION" ]; then
  AWS_KEY=$(oc get secret logging-loki-aws -n openshift-logging -o jsonpath='{.data.access_key_id}' 2>/dev/null | base64 -d 2>/dev/null || echo "")
  AWS_SECRET=$(oc get secret logging-loki-aws -n openshift-logging -o jsonpath='{.data.access_key_secret}' 2>/dev/null | base64 -d 2>/dev/null || echo "")
  if [ -n "$AWS_KEY" ] && [ -n "$AWS_SECRET" ]; then
    echo "Deleting S3 bucket objects and bucket: $S3_BUCKET"
    cat <<JOBEOF | oc apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: delete-loki-bucket
  namespace: openshift-logging
spec:
  ttlSecondsAfterFinished: 120
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: aws-cli
          image: amazon/aws-cli:latest
          command: ["sh", "-c"]
          args:
            - |
              aws s3 rb "s3://${S3_BUCKET}" --force --region "${AWS_REGION}" 2>/dev/null || echo "Bucket removal failed or already gone."
          env:
            - name: AWS_ACCESS_KEY_ID
              value: "${AWS_KEY}"
            - name: AWS_SECRET_ACCESS_KEY
              value: "${AWS_SECRET}"
            - name: AWS_DEFAULT_REGION
              value: "${AWS_REGION}"
JOBEOF
    echo -n "Waiting for bucket deletion..."
    for i in $(seq 1 30); do
      if oc get job delete-loki-bucket -n openshift-logging -o jsonpath='{.status.succeeded}' 2>/dev/null | grep -q 1; then
        echo " Done!"
        break
      fi
      echo -n "."
      sleep 5
    done
    oc delete job delete-loki-bucket -n openshift-logging 2>/dev/null || true
  fi
fi

echo "Removing bucket creation Job..."
oc delete job create-loki-bucket -n openshift-logging 2>/dev/null || true

# --- CredentialsRequest ---
echo "Removing CredentialsRequest..."
oc delete credentialsrequest loki-logging -n openshift-cloud-credential-operator 2>/dev/null || true
oc delete secret logging-loki-aws -n openshift-logging 2>/dev/null || true

# --- Operator Subscriptions ---
echo "Removing operator subscriptions..."
oc delete subscription grafana-operator -n openshift-operators 2>/dev/null || true
oc delete subscription cluster-logging -n openshift-logging 2>/dev/null || true
oc delete subscription loki-operator -n openshift-operators-redhat 2>/dev/null || true

# --- Operator CSVs ---
echo "Removing operator CSVs..."
oc delete csv -n openshift-operators -l operators.coreos.com/grafana-operator.openshift-operators 2>/dev/null || true
for csv in $(oc get csv -n openshift-operators --no-headers 2>/dev/null | grep -i grafana | awk '{print $1}'); do
  oc delete csv "$csv" -n openshift-operators 2>/dev/null || true
done
for csv in $(oc get csv -n openshift-logging --no-headers 2>/dev/null | grep -i cluster-logging | awk '{print $1}'); do
  oc delete csv "$csv" -n openshift-logging 2>/dev/null || true
done
for csv in $(oc get csv -n openshift-operators-redhat --no-headers 2>/dev/null | grep -i loki | awk '{print $1}'); do
  oc delete csv "$csv" -n openshift-operators-redhat 2>/dev/null || true
done

# --- Namespaces ---
echo "Removing logging namespaces..."
oc delete project openshift-logging 2>/dev/null || true
oc delete project openshift-operators-redhat 2>/dev/null || true

# --- Prometheus resources in shopinsights ---
echo "Removing ServiceMonitor and PrometheusRule..."
oc delete servicemonitor products-service-monitor -n shopinsights 2>/dev/null || true
oc delete prometheusrule products-alerting-rules -n shopinsights 2>/dev/null || true

echo ""
echo "=== L07 Cleanup Complete ==="
echo "Note: User workload monitoring was NOT disabled (other lessons may use it)."
echo "To disable: oc delete configmap cluster-monitoring-config -n openshift-monitoring"
