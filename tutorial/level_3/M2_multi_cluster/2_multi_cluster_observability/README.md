# L3-M2.2 — Multi-Cluster Observability

**Level:** Expert
**Duration:** 45 min

## Overview

In a single Kubernetes cluster, you install Prometheus and Grafana, set up some dashboards, and call it a day. But when you manage a fleet of 5, 50, or 500 clusters, the fundamental question changes from "how is my cluster doing?" to "which of my clusters needs attention right now?" This lesson teaches you how to deploy RHACM's Multi-Cluster Observability, which uses Thanos to aggregate metrics from every managed cluster into a single pane of glass on the hub. You will also configure centralized log forwarding and build Grafana dashboards that give fleet-wide visibility.

## Prerequisites

- Completed: L3-M2.1 (Advanced Cluster Management) -- RHACM hub cluster with at least one managed cluster
- OpenShift cluster running (hub cluster with RHACM installed)
- At least one managed cluster registered with ACM
- S3-compatible object storage (AWS S3, MinIO, or OpenShift Data Foundation/NooBaa)
- `cluster-admin` access on the hub cluster
- Familiarity with Prometheus, Grafana, and PromQL (L1-M6.1, L1-M6.2)
- Understanding of OpenShift Logging (L1-M6.3)

## K8s Context

In vanilla Kubernetes, observability across multiple clusters is a build-it-yourself problem. You typically deploy Prometheus on each cluster, then choose an aggregation strategy:

- **Federation**: A central Prometheus scrapes `/federate` endpoints on each cluster's Prometheus. Works for small fleets but does not scale -- the central instance becomes a bottleneck and single point of failure.
- **Thanos / Cortex / Mimir**: You deploy a sidecar or remote-write receiver on each cluster, push metrics to a shared object store, and run a query layer on top. This is the production-grade approach, but you are responsible for every piece: deploying sidecars, managing object storage, configuring query routing, setting up compaction, and building dashboards.
- **Logging**: Similarly, you configure Fluentd/Vector on each cluster to forward logs to a central Elasticsearch, Loki, or Splunk instance. Again, entirely your responsibility.

The result is weeks of engineering work just to get a multi-cluster observability stack running, and ongoing maintenance to keep it healthy.

## Concepts

### ACM Observability Architecture

RHACM's Multi-Cluster Observability automates the entire Thanos-based metrics pipeline. When you create a `MultiClusterObservability` custom resource on the hub, ACM automatically:

1. Deploys a full Thanos stack on the hub (Receive, Store, Query, QueryFrontend, Compact, Rule)
2. Installs a `metrics-collector` addon on every managed cluster
3. Configures the collectors to push metrics to Thanos Receive on the hub
4. Provisions Grafana with pre-built dashboards for fleet-wide visibility
5. Sets up AlertManager for cross-cluster alerting

```
+-------------------------------------------------------------------+
|                        Hub Cluster                                 |
|                                                                    |
|  +---------------------+    +----------------------------------+  |
|  |   ACM Console       |    |   Observability Stack            |  |
|  |   (Fleet View)      |    |                                  |  |
|  +---------------------+    |  +----------+   +-------------+  |  |
|                              |  | Grafana  |   | AlertManager|  |  |
|                              |  +----+-----+   +------+------+  |  |
|                              |       |                |          |  |
|                              |  +----v--------------+ |          |  |
|                              |  | Thanos Query      | |          |  |
|                              |  | (+ QueryFrontend) | |          |  |
|                              |  +----+--------------+ |          |  |
|                              |       |                |          |  |
|                              |  +----v-----+  +------v------+  |  |
|                              |  | Thanos   |  | Thanos Rule |  |  |
|                              |  | Store    |  +-------------+  |  |
|                              |  +----+-----+                    |  |
|                              |       |                          |  |
|                              |  +----v---------+               |  |
|                              |  | Thanos       |               |  |
|                              |  | Compact      |               |  |
|                              |  +----+---------+               |  |
|                              |       |                          |  |
|                              |  +----v---------+               |  |
|                              |  | Object Store |               |  |
|                              |  | (S3/NooBaa)  |               |  |
|                              |  +--------------+               |  |
|                              +----------------------------------+  |
+------^-----------------------^-----------------------^-------------+
       |                       |                       |
  metrics-collector       metrics-collector       metrics-collector
       |                       |                       |
+------+------+    +-----------+-------+   +-----------+-------+
| Managed     |    | Managed           |   | Managed           |
| Cluster 1   |    | Cluster 2         |   | Cluster N         |
|             |    |                   |   |                   |
| Prometheus  |    | Prometheus        |   | Prometheus        |
| (local)     |    | (local)           |   | (local)           |
+-------------+    +-------------------+   +-------------------+
```

### Thanos Components Explained

Each Thanos component serves a specific role in the pipeline:

| Component | Role | Scaling Notes |
|-----------|------|---------------|
| **Receive** | Ingests metrics from managed cluster collectors via remote-write | Scale horizontally for more clusters; each replica handles a shard |
| **Store** | Serves historical data from object storage | Scale horizontally; uses a time-based sharding strategy |
| **Query** | Fanout query engine -- queries Receive (recent) and Store (historical) | Scale for query concurrency; add replicas behind QueryFrontend |
| **QueryFrontend** | Caches and splits queries for performance | 2 replicas typical; caches query results |
| **Compact** | Downsamples old data (5m, 1h) and garbage-collects deleted blocks | Single instance; CPU/memory intensive during compaction windows |
| **Rule** | Evaluates recording and alerting rules against aggregated data | Scale for rule volume; sends alerts to AlertManager |

### Metrics Collection Flow

The `metrics-collector` addon deployed on each managed cluster works as follows:

1. Reads a predefined allowlist of metrics from the local Prometheus
2. Adds a `cluster` label to every metric (identifying the source cluster)
3. Pushes metrics to Thanos Receive on the hub via remote-write over mTLS
4. Collects at a configurable interval (default: 300 seconds / 5 minutes)

Only allowlisted metrics are forwarded. This is intentional -- forwarding all metrics from dozens of clusters would overwhelm storage. You can extend the allowlist with a ConfigMap.

### Multi-Cluster Logging Architecture

While ACM Observability handles metrics natively, log aggregation uses OpenShift Logging's `ClusterLogForwarder` CR on each managed cluster to ship logs to a centralized store:

```
+------------------+     +------------------+     +------------------+
| Managed Cluster 1|     | Managed Cluster 2|     | Managed Cluster N|
|                  |     |                  |     |                  |
| Vector/Fluentd   |     | Vector/Fluentd   |     | Vector/Fluentd   |
| ClusterLog       |     | ClusterLog       |     | ClusterLog       |
| Forwarder        |     | Forwarder        |     | Forwarder        |
+--------+---------+     +--------+---------+     +--------+---------+
         |                        |                        |
         +------------------------+------------------------+
                                  |
                    +-------------v--------------+
                    |   Central Log Store         |
                    |   (Loki / Elasticsearch)    |
                    |   on Hub or Dedicated       |
                    |   Infrastructure            |
                    +-----------------------------+
```

ACM policies can automate the deployment of the Logging operator and `ClusterLogForwarder` configuration across all managed clusters.

### Retention and Downsampling

Thanos Compact automatically downsamples metrics over time:

| Resolution | Retention (default) | Use Case |
|-----------|-------------------|----------|
| Raw (original) | 30 days | Recent debugging, precise values |
| 5-minute | 180 days | Trend analysis, capacity planning |
| 1-hour | 365 days | Long-term trending, year-over-year |

This means a query for "last 7 days" returns raw data, while "last 6 months" transparently returns 5-minute aggregates. The user does not need to know which resolution is being served.

## Step-by-Step

### Step 1: Create the Observability Namespace

The ACM Observability components run in a dedicated namespace that must be named exactly `open-cluster-management-observability`.

```bash
oc apply -f manifests/observability-namespace.yaml
```

```yaml
# manifests/observability-namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: open-cluster-management-observability
  labels:
    app: acm-observability
    tutorial-level: "3"
    tutorial-module: "M2"
```

### Step 2: Copy the Image Pull Secret

The observability components need to pull images from the Red Hat registry. Copy the cluster's existing pull secret into the new namespace:

```bash
# Extract the existing pull secret
DOCKER_CONFIG_JSON=$(oc extract secret/pull-secret \
  -n openshift-config --to=-)

# Create it in the observability namespace
oc create secret generic multiclusterhub-operator-pull-secret \
  -n open-cluster-management-observability \
  --from-literal=.dockerconfigjson="${DOCKER_CONFIG_JSON}" \
  --type=kubernetes.io/dockerconfigjson
```

### Step 3: Configure Object Storage for Thanos

Thanos requires S3-compatible object storage for long-term metrics retention. This is the backing store for all aggregated metrics across your fleet.

**Option A: AWS S3** -- Edit `manifests/thanos-object-storage-secret.yaml` and replace the placeholder credentials:

```bash
# Edit the secret with your actual S3 credentials
vi manifests/thanos-object-storage-secret.yaml

# Apply
oc apply -f manifests/thanos-object-storage-secret.yaml
```

**Option B: OpenShift Data Foundation (NooBaa)** -- If you are running ODF, extract credentials from the NooBaa operator:

```bash
# Get NooBaa S3 endpoint and credentials
NOOBAA_ENDPOINT=$(oc get route s3 -n openshift-storage \
  -o jsonpath='{.spec.host}')
ACCESS_KEY=$(oc get secret noobaa-admin -n openshift-storage \
  -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 -d)
SECRET_KEY=$(oc get secret noobaa-admin -n openshift-storage \
  -o jsonpath='{.data.AWS_SECRET_ACCESS_KEY}' | base64 -d)

# Create the Thanos storage secret
cat <<EOF | oc apply -f -
apiVersion: v1
kind: Secret
metadata:
  name: thanos-object-storage
  namespace: open-cluster-management-observability
type: Opaque
stringData:
  thanos.yaml: |
    type: s3
    config:
      bucket: first.bucket
      endpoint: ${NOOBAA_ENDPOINT}
      insecure: true
      access_key: ${ACCESS_KEY}
      secret_key: ${SECRET_KEY}
EOF
```

**Why object storage?** Prometheus stores metrics locally on disk with limited retention. Thanos offloads historical blocks to object storage, enabling practically unlimited retention with tiered downsampling. Without it, you would need enormous local disks on the hub cluster.

### Step 4: Deploy the MultiClusterObservability CR

This is the central resource that orchestrates the entire observability stack:

```bash
oc apply -f manifests/multiclusterobservability.yaml
```

Key configuration sections in the CR:

```yaml
# manifests/multiclusterobservability.yaml (key excerpts)
spec:
  # Addon deployed to each managed cluster
  observabilityAddonSpec:
    enableMetrics: true
    interval: 300                # Collection interval in seconds
    resources:
      requests:
        cpu: 200m
        memory: 256Mi
      limits:
        cpu: 500m
        memory: 1Gi

  # Object storage reference
  storageConfig:
    metricObjectStorage:
      name: thanos-object-storage
      key: thanos.yaml
    compactStorageSize: 100Gi    # Local working space for Thanos Compact
    receiveStorageSize: 100Gi    # Write-ahead log for Thanos Receive
    ruleStorageSize: 20Gi        # Rule evaluation state
    storeStorageSize: 100Gi      # Block cache for Thanos Store

  # How long to keep data at each resolution
  retentionConfig:
    retentionResolutionRaw: 30d
    retentionResolution5m: 180d
    retentionResolution1h: 365d
```

Watch the deployment progress:

```bash
# Watch the MCO status
oc get multiclusterobservability observability -w

# Watch pods come up (expect 15-20 pods)
oc get pods -n open-cluster-management-observability -w
```

This deployment typically takes 5-10 minutes. ACM will automatically deploy the `metrics-collector` addon to every managed cluster.

### Step 5: Verify Addon Deployment on Managed Clusters

Once the MCO is ready, verify that the metrics-collector addon has been deployed to each managed cluster:

```bash
# Check addon status on all managed clusters
oc get managedclusteraddon observability-controller -A

# Expected output:
# NAMESPACE         NAME                       AVAILABLE   DEGRADED   STATUS
# cluster-east      observability-controller   True                   
# cluster-west      observability-controller   True                   
# local-cluster     observability-controller   True                   
```

If an addon shows as Degraded, inspect it:

```bash
oc describe managedclusteraddon observability-controller -n <cluster-name>
```

### Step 6: Add Custom Metrics to the Allowlist

By default, ACM collects a predefined set of platform metrics (node, kubelet, API server, etcd). To monitor your application metrics across the fleet, add them to the allowlist:

```bash
oc apply -f manifests/custom-metrics-allowlist.yaml
```

```yaml
# manifests/custom-metrics-allowlist.yaml (excerpt)
data:
  metrics_list.yaml: |
    names:
      - http_requests_total
      - http_request_duration_seconds_bucket
      - container_cpu_usage_seconds_total
      - container_memory_working_set_bytes
    matches:
      - __name__="apiserver_request_total",job="apiserver"
```

The `names` field adds specific metric names. The `matches` field uses label matchers for more precise selection. After applying, the metrics-collector on each cluster will begin forwarding these additional metrics within one collection interval.

### Step 7: Deploy Fleet-Wide Alerting Rules

Create alerting rules that evaluate across the entire fleet using aggregated Thanos data:

```bash
oc apply -f manifests/custom-alerting-rules.yaml
```

Key alerts included:

| Alert | Condition | Severity |
|-------|-----------|----------|
| `ManagedClusterHighCPU` | Average CPU > 85% for 15 min | warning |
| `ManagedClusterHighMemory` | Average memory > 90% for 10 min | critical |
| `ManagedClusterNodeNotReady` | Node NotReady for 5 min | critical |
| `ManagedClusterAPIServerDown` | API server unreachable for 3 min | critical |
| `ManagedClusterEtcdHighLatency` | etcd WAL fsync p99 > 500ms for 10 min | warning |
| `ObservabilityMetricsCollectionLag` | No metrics for 10 min | warning |
| `ThanosCompactHalted` | Compact process stopped | warning |

These rules differ from per-cluster Prometheus rules because they run on the hub and can use the `cluster` label to identify which cluster is affected. The `ObservabilityMetricsCollectionLag` alert is especially important -- it tells you when a cluster has gone silent, which could mean the cluster is down or the collector is broken.

### Step 8: Import Custom Grafana Dashboards

ACM Observability includes several pre-built dashboards, but you will want custom views for your fleet:

```bash
oc apply -f manifests/grafana-dashboard-fleet-overview.yaml
```

Access the Grafana UI:

```bash
# Get the Grafana route
oc get route grafana -n open-cluster-management-observability \
  -o jsonpath='https://{.spec.host}{"\n"}'
```

Log in with your OpenShift credentials (OAuth-integrated). Navigate to Dashboards to find the "Fleet Overview" dashboard.

The pre-built ACM dashboards include:
- **ACM - Clusters Overview**: Health status of all managed clusters
- **ACM - Resource Optimization**: CPU and memory efficiency across the fleet
- **ACM - Etcd**: etcd performance metrics per cluster
- **ACM - Kubernetes API**: API server request rates and latencies

### Step 9: Configure Multi-Cluster Log Forwarding

Deploy an ACM policy to ensure the Logging operator and `ClusterLogForwarder` are configured on all managed clusters:

```bash
# Deploy the policy that installs logging on all managed clusters
oc apply -f manifests/acm-observability-policy.yaml
```

This policy:
1. Ensures the OpenShift Logging operator Subscription exists on each managed cluster
2. Creates a `ClusterLogging` instance with Vector as the collector
3. Is enforced automatically via ACM's policy engine

For the log forwarding configuration (pointing logs to your central Loki/Elasticsearch), deploy the `ClusterLogForwarder` via GitOps or apply it through an additional ACM policy:

```bash
# Review the ClusterLogForwarder configuration
cat manifests/clusterlogforwarder-hub.yaml

# Deploy to managed clusters via ACM or GitOps
# Note: Update the cluster label and central log store URLs first
```

The `ClusterLogForwarder` in `manifests/clusterlogforwarder-hub.yaml` defines three pipelines:
- **Application logs** to central Loki (with tenant-per-namespace)
- **Infrastructure logs** to central Loki
- **Audit logs** to central Elasticsearch (for compliance requirements)

### Step 10: Query Across Clusters with PromQL

With everything deployed, you can now run PromQL queries that span your entire fleet. In the Grafana Explore view or via the Thanos Query API:

```promql
# CPU utilization per cluster (fleet heatmap)
avg by (cluster) (
  1 - rate(node_cpu_seconds_total{mode="idle"}[5m])
) * 100

# Memory pressure across all clusters
avg by (cluster) (
  1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)
) * 100

# Total pods across the fleet
sum by (cluster) (kube_pod_info)

# API server error rate per cluster
sum by (cluster) (
  rate(apiserver_request_total{code=~"5.."}[5m])
) /
sum by (cluster) (
  rate(apiserver_request_total[5m])
) * 100

# Find the busiest cluster by workload count
topk(5,
  count by (cluster, namespace) (kube_pod_info)
)
```

You can also query via the CLI using the Thanos Query endpoint:

```bash
# Get the Thanos Query route (if exposed)
THANOS_QUERY=$(oc get route thanos-query \
  -n open-cluster-management-observability \
  -o jsonpath='{.spec.host}' 2>/dev/null)

# Query via API
curl -sk "https://${THANOS_QUERY}/api/v1/query" \
  --data-urlencode 'query=count by (cluster) (up)' \
  -H "Authorization: Bearer $(oc whoami -t)" | jq .
```

## Verification

Run the provided verification script to check all components:

```bash
./scripts/verify-observability.sh
```

Expected output for a healthy deployment:

```
============================================
  ACM Observability Health Check
============================================

[1] MultiClusterObservability CR Status
  [PASS] MultiClusterObservability is Ready

[2] Thanos Component Pods
  [PASS] thanos-receive: 3/3 running
  [PASS] thanos-store: 3/3 running
  [PASS] thanos-query: 2/2 running
  [PASS] thanos-query-frontend: 2/2 running
  [PASS] thanos-compact: 1/1 running
  [PASS] thanos-rule: 2/2 running

[3] Grafana
  [PASS] Grafana: 2 pod(s) running
  [PASS] Grafana route: https://grafana-open-cluster-management-observability.apps.hub.example.com

[4] AlertManager
  [PASS] AlertManager: 3 pod(s) running

[5] Observability Addon Status on Managed Clusters
  [PASS] Cluster 'cluster-east': addon available
  [PASS] Cluster 'cluster-west': addon available
  [PASS] Cluster 'local-cluster': addon available

[6] Object Storage
  [PASS] Thanos object storage secret exists
  [PASS] Thanos Compact logs look healthy

[7] Persistent Volume Claims
  [PASS] All 10 PVCs are Bound

============================================
  Summary
============================================
  Passed: 16
  Warnings: 0
  Failed: 0

  Status: HEALTHY
```

Additionally, verify manually:

```bash
# Check that metrics from managed clusters are flowing
oc exec -n open-cluster-management-observability \
  $(oc get pod -l app.kubernetes.io/name=thanos-query \
    -n open-cluster-management-observability \
    -o jsonpath='{.items[0].metadata.name}') \
  -- thanos query stores

# Verify managed cluster labels in metrics
# (in Grafana Explore, run this query:)
#   count by (cluster) (up)
# Should show one entry per managed cluster
```

## Failure Modes and Recovery

### Metrics-Collector Addon Fails on a Managed Cluster

**Symptoms**: No metrics from a specific cluster. `ObservabilityMetricsCollectionLag` alert fires.

**Diagnosis**:
```bash
# Check addon status
oc get managedclusteraddon observability-controller -n <cluster-name>
oc describe managedclusteraddon observability-controller -n <cluster-name>

# On the managed cluster, check the collector pod
oc get pods -n open-cluster-management-addon-observability
oc logs -n open-cluster-management-addon-observability \
  -l component=metrics-collector --tail=100
```

**Common causes**:
- Network connectivity between managed cluster and hub (firewall rules, proxy configuration)
- Expired mTLS certificates (auto-renewed, but check if cert-manager is healthy)
- Managed cluster Prometheus is down or resource-starved

**Recovery**:
```bash
# Restart the addon on the managed cluster
oc delete managedclusteraddon observability-controller -n <cluster-name>
# ACM will automatically recreate it
```

### Thanos Compact Halts

**Symptoms**: `ThanosCompactHalted` alert fires. Old data is not downsampled. Object storage usage grows faster than expected.

**Diagnosis**:
```bash
oc logs -n open-cluster-management-observability \
  -l app.kubernetes.io/name=thanos-compact --tail=200
```

**Common causes**:
- Overlapping blocks from a previous crash or misconfiguration
- Object storage connectivity issues or permission errors
- Insufficient local disk for compaction working space

**Recovery**:
```bash
# Check for overlapping blocks
oc logs -n open-cluster-management-observability \
  -l app.kubernetes.io/name=thanos-compact | grep "overlapping"

# If overlapping blocks are the issue, you may need to delete the
# problematic blocks from object storage. Identify them from the logs,
# then remove them from the S3 bucket.

# Restart compact
oc delete pod -n open-cluster-management-observability \
  -l app.kubernetes.io/name=thanos-compact
```

### Thanos Receive Out of Memory

**Symptoms**: Thanos Receive pods are OOMKilled. Metrics ingestion pauses.

**Diagnosis**:
```bash
oc get events -n open-cluster-management-observability \
  --field-selector reason=OOMKilled

oc describe pod -n open-cluster-management-observability \
  -l app.kubernetes.io/name=thanos-receive
```

**Recovery**: Increase memory limits in the `MultiClusterObservability` CR:
```bash
oc edit multiclusterobservability observability
# Under spec.advanced.receive.resources.limits.memory, increase the value
```

As a rule of thumb, each managed cluster contributing metrics requires approximately 200-500 MB of memory on Thanos Receive, depending on the number of active time series.

### Object Storage Unreachable

**Symptoms**: All Thanos components log errors. New metrics are buffered in Thanos Receive's WAL but not uploaded. Queries for historical data fail.

**Diagnosis**:
```bash
# Check Store logs
oc logs -n open-cluster-management-observability \
  -l app.kubernetes.io/name=thanos-store --tail=50 | grep -i error

# Check connectivity from a Thanos pod
oc exec -n open-cluster-management-observability \
  $(oc get pod -l app.kubernetes.io/name=thanos-store \
    -n open-cluster-management-observability \
    -o jsonpath='{.items[0].metadata.name}') \
  -- wget -qO- --timeout=5 https://s3.us-east-1.amazonaws.com/ 2>&1 || true
```

**Recovery**:
- Verify S3 credentials have not expired or been rotated
- Check network/proxy configuration
- If using NooBaa, verify the ODF cluster is healthy
- Thanos Receive buffers data in its WAL; once storage is restored, buffered data will be uploaded

### Hub Cluster Goes Down

**Impact**: Metrics collection continues on managed clusters (Prometheus runs locally). Centralized alerting and dashboards are unavailable. Metrics-collectors buffer data and retry delivery.

**Recovery**:
- Restore the hub cluster (see L3-M1.4 for etcd backup/restore)
- The `MultiClusterObservability` CR is stored in etcd; once the hub is restored, all Thanos components restart automatically
- Metrics-collectors will flush buffered data once connectivity is restored
- There will be a gap in centralized alerting during the outage; local Prometheus alerts on each managed cluster still fire

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift (with ACM) |
|--------|-----------|---------------------|
| Multi-cluster metrics | Manual: deploy Thanos/Cortex/Mimir, configure remote-write, manage object storage, build dashboards | `MultiClusterObservability` CR: one YAML deploys entire Thanos stack with auto-addon on managed clusters |
| Metrics collection | Configure remote-write or federation on each cluster manually | `metrics-collector` addon auto-deployed and managed via ACM lifecycle |
| Object storage | Provision and configure independently; manage IAM, buckets, lifecycle rules | Configured via Secret; supports S3, GCS, Azure, ODF/NooBaa; integrated with OpenShift storage |
| Grafana dashboards | Build from scratch or import community dashboards | Pre-built fleet dashboards included; custom dashboards via ConfigMap with `grafana-custom-dashboard` label |
| Cross-cluster alerting | Write custom recording rules; deploy Alertmanager federation | PrometheusRules in hub namespace evaluate against aggregated data; `cluster` label auto-injected |
| Log aggregation | Deploy and configure Fluentd/Vector on each cluster; manage credentials and TLS per cluster | ACM policies enforce Logging operator + ClusterLogForwarder across all managed clusters simultaneously |
| Retention management | Configure Thanos Compact manually; set retention, downsampling, and garbage collection | `retentionConfig` in MCO CR; Compact runs with production defaults; three resolution tiers automatic |
| Addon lifecycle | N/A (no concept of cluster addons) | ACM manages addon installation, upgrade, and health across all managed clusters |
| Authentication | Configure OAuth proxy or Dex for Grafana/Thanos manually | Integrated with OpenShift OAuth; SSO across ACM console, Grafana, and cluster access |
| Scaling | Size and tune each Thanos component independently | `spec.advanced` section in MCO CR; resource requests/limits per component |

## Key Takeaways

- **One CR to rule them all**: The `MultiClusterObservability` CR deploys a complete Thanos-based metrics pipeline. ACM handles the complexity of sidecar deployment, mTLS, object storage integration, and query routing.
- **Allowlist-based collection is intentional**: Only explicitly allowlisted metrics are forwarded from managed clusters. This prevents storage explosion at scale but requires you to add application-specific metrics via the `observability-metrics-custom-allowlist` ConfigMap.
- **Thanos downsampling is automatic**: Raw data is retained for 30 days, 5-minute aggregates for 180 days, and 1-hour aggregates for 365 days by default. Queries transparently use the appropriate resolution.
- **Log forwarding uses existing OpenShift Logging infrastructure**: ACM does not reinvent logging. Instead, you use ACM policies to ensure the Logging operator and `ClusterLogForwarder` are consistently deployed across all managed clusters, forwarding to a central store.
- **Monitor the monitor**: The observability pipeline itself needs monitoring. The `ThanosCompactHalted` and `ObservabilityMetricsCollectionLag` alerts are critical for detecting when the observability stack is degraded.

## Cleanup

```bash
# Option 1: Use the teardown script (preserves PVCs by default)
./scripts/teardown-observability.sh

# Option 2: Full cleanup including data
./scripts/teardown-observability.sh --delete-pvcs

# Option 3: Manual cleanup
# Remove custom resources
oc delete -f manifests/custom-alerting-rules.yaml --ignore-not-found
oc delete -f manifests/custom-metrics-allowlist.yaml --ignore-not-found
oc delete -f manifests/grafana-dashboard-fleet-overview.yaml --ignore-not-found
oc delete -f manifests/acm-observability-policy.yaml --ignore-not-found

# Remove the MCO (this also removes addons from managed clusters)
oc delete multiclusterobservability observability

# Remove secrets and namespace
oc delete secret thanos-object-storage \
  -n open-cluster-management-observability --ignore-not-found
oc delete secret multiclusterhub-operator-pull-secret \
  -n open-cluster-management-observability --ignore-not-found
oc delete namespace open-cluster-management-observability

# Clean up all labeled resources
oc delete all -l tutorial-level=3,tutorial-module=M2,app=acm-observability \
  --all-namespaces --ignore-not-found
```

## Next Steps

In **L3-M2.3 — Multi-Cluster GitOps**, you will learn how to use ArgoCD ApplicationSets with ACM Placement policies to deploy and promote applications across your fleet of clusters. You will combine the observability stack from this lesson with GitOps-driven deployments to build a complete multi-cluster platform with both deployment automation and fleet-wide visibility.
