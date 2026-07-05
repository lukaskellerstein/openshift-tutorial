#!/usr/bin/env bash
# L07 — Cleanup: remove monitoring and logging components (no Grafana — see L12)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LESSON_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== L07 Cleanup ==="

# --- Logging Console Plugin ---
echo "Removing Logging Console Plugin..."
oc delete uiplugin logging 2>/dev/null || true

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
    sed -e "s|__S3_BUCKET__|${S3_BUCKET}|g" \
        -e "s|__AWS_REGION__|${AWS_REGION}|g" \
        -e "s|__AWS_KEY__|${AWS_KEY}|g" \
        -e "s|__AWS_SECRET__|${AWS_SECRET}|g" \
        "$LESSON_DIR/manifests/job-delete-s3-bucket.yaml" | oc apply -f -
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
oc delete subscription cluster-logging -n openshift-logging 2>/dev/null || true
oc delete subscription loki-operator -n openshift-operators-redhat 2>/dev/null || true

# --- Operator CSVs ---
echo "Removing operator CSVs..."
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
