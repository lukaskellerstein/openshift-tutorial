# L3-M3.4 — Cost Management

**Level:** Expert
**Duration:** 30 min

## Overview

In Kubernetes, tracking what each team or application actually costs is an exercise in stitching together Prometheus metrics, node pricing data, and custom dashboards. OpenShift provides the **Cost Management Operator** (based on the upstream **koku-metrics-operator**, formerly known as **korekuta/kostrate**) as a first-party solution that collects CPU, memory, and storage usage data, correlates it with cloud infrastructure costs, and feeds it into Red Hat's Cost Management service or your own reporting pipeline. This lesson covers the full cost-management lifecycle: deploying the operator, configuring metering collection, building chargeback models for multi-tenant clusters, generating resource optimization recommendations, and integrating with cloud provider cost tools (AWS Cost Explorer, Azure Cost Management, GCP Billing).

## Prerequisites

- Completed: L3-M1.5 (Resource Management & Quotas)
- OpenShift cluster running (CRC for local exercises; production or cloud cluster for full cost integration)
- `cluster-admin` access (`kubeadmin` on CRC)
- Familiarity with ResourceQuotas, LimitRanges, and ClusterResourceQuotas from L3-M1.5
- Understanding of Prometheus metrics and monitoring from L1-M6
- (Optional) AWS, Azure, or GCP account for cloud cost integration exercises

## K8s Context

Kubernetes provides the raw metrics for cost tracking but no built-in cost management:

- **Metrics Server** exposes current CPU and memory usage per pod and node, but stores no history.
- **Prometheus** (self-installed) can scrape `kube_pod_resource_request`, `kube_pod_resource_limit`, and `node_cpu_seconds_total` to build usage data, but you must write the queries, retention policies, and dashboards yourself.
- **Third-party tools** like Kubecost, OpenCost, or CloudHealth provide cost allocation, but they are external add-ons with their own deployment and licensing.
- **No chargeback model** exists natively. Teams tracking cost-per-namespace must build custom pipelines: scrape metrics, join with cloud billing data, aggregate by labels, and produce reports.

The fundamental challenge: Kubernetes knows resource consumption but has no concept of cost. Bridging the gap requires infrastructure pricing data that lives outside the cluster.

## Concepts

### Cost Management Architecture on OpenShift

```
+----------------------------------------------------------------------+
|                   Cost Management Architecture                       |
+----------------------------------------------------------------------+
|                                                                      |
|  OpenShift Cluster                                                   |
|  +----------------------------------------------------------------+  |
|  |  Cost Management Operator (koku-metrics-operator)              |  |
|  |  +----------------------------------------------------------+  |  |
|  |  |  Collectors:                                              |  |  |
|  |  |    - CPU/Memory usage per pod, namespace, node            |  |  |
|  |  |    - PVC storage utilization                              |  |  |
|  |  |    - Node capacity and allocatable resources              |  |  |
|  |  |    - Labels and annotations for cost attribution          |  |  |
|  |  +----------------------------------------------------------+  |  |
|  |           |                                                     |  |
|  |           v                                                     |  |
|  |  +----------------------------------------------------------+  |  |
|  |  |  CSV Reports (stored in PVC or uploaded)                  |  |  |
|  |  |    - Usage data in 1-hour intervals                       |  |  |
|  |  |    - Compressed CSV files (~1-5 MB/day)                   |  |  |
|  |  +----------------------------------------------------------+  |  |
|  +----------------------------------------------------------------+  |
|           |                          |                               |
|           v                          v                               |
|  +------------------+    +---------------------------+               |
|  | Red Hat Hybrid   |    | Local S3 / MinIO          |               |
|  | Cloud Console    |    | (air-gapped alternative)  |               |
|  | (console.redhat  |    +---------------------------+               |
|  |  .com/openshift/ |               |                                |
|  |  cost-management)|               v                                |
|  +------------------+    +---------------------------+               |
|           |              | Custom Reporting Pipeline  |               |
|           v              | (Grafana, BI tools, etc.)  |               |
|  +------------------+    +---------------------------+               |
|  | Cost Reports:    |                                                |
|  |  - By project    |    Cloud Provider Billing APIs                 |
|  |  - By team       |    +---------------------------+               |
|  |  - By service    |    | AWS Cost Explorer          |              |
|  |  - By cluster    |    | Azure Cost Management      |              |
|  +------------------+    | GCP Cloud Billing           |              |
|                          +---------------------------+               |
+----------------------------------------------------------------------+
```

### How Cost Collection Works

The Cost Management Operator runs as a deployment in the `cost-management` namespace. It:

1. **Queries Prometheus** for pod-level CPU and memory usage metrics at regular intervals (default: hourly).
2. **Queries the Kubernetes API** for node capacity, PVC sizes, and resource requests/limits.
3. **Reads labels and annotations** on namespaces and pods for cost attribution (team, cost-center, environment).
4. **Generates CSV reports** containing hourly aggregated usage data.
5. **Uploads reports** to Red Hat's Hybrid Cloud Console (SaaS), or stores them locally in a PVC for air-gapped environments.

### Chargeback vs Showback

| Model | Definition | Use Case |
|-------|-----------|----------|
| **Showback** | Display costs per team/project without billing | Awareness and voluntary optimization |
| **Chargeback** | Actually bill teams for their resource consumption | Formal cost allocation, departmental budgets |

Most organizations start with showback to build awareness, then move to chargeback once the cost model is validated and accepted.

### Cost Attribution Labels

Cost management relies on consistent labeling. These labels on namespaces and workloads drive cost reporting:

| Label | Purpose | Example |
|-------|---------|---------|
| `cost-center` | Maps to financial cost center | `cost-center: "CC-4521"` |
| `team` | Owning team | `team: "platform-engineering"` |
| `environment` | Deployment tier | `environment: "production"` |
| `service` | Business service name | `service: "payment-gateway"` |
| `app` | Application name | `app: "checkout-api"` |

### Resource Optimization Recommendations

The Cost Management Operator can generate resource optimization recommendations by comparing actual usage against requests and limits:

```
Resource Optimization Decision Tree:

  [Actual CPU usage < 20% of request]
       |
       v
  RECOMMENDATION: Reduce CPU request
  Savings: (current_request - recommended_request) * cost_per_cpu_hour
       |
       v
  [Actual Memory usage < 30% of request]
       |
       v
  RECOMMENDATION: Reduce memory request
  Savings: (current_request - recommended_request) * cost_per_gb_hour
       |
       v
  [Pod count > 1 AND avg utilization < 40%]
       |
       v
  RECOMMENDATION: Reduce replica count or enable HPA
  Savings: eliminated_pods * (cpu_request + mem_request) * cost_per_hour
```

Right-sizing recommendations require at least 7 days of usage data to account for workload variability (business hours, batch jobs, traffic spikes).

## Step-by-Step

### Step 1: Create the Cost Management Namespace and RBAC

Set up the namespace where the Cost Management Operator will run, along with the service account and cluster-level permissions it needs.

```bash
# Log in as cluster-admin
oc login -u kubeadmin -p <password> https://api.crc.testing:6443

# Create the cost-management namespace
oc apply -f manifests/cost-management-namespace.yaml

# Apply RBAC (ClusterRole and ClusterRoleBinding for metrics access)
oc apply -f manifests/cost-management-rbac.yaml
```

```yaml
# From manifests/cost-management-namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: cost-management
  labels:
    app: cost-management
    tutorial-level: "3"
    tutorial-module: "M3"
```

The operator needs cluster-wide read access to query Prometheus, list namespaces, read node metrics, and inspect PVC usage.

### Step 2: Install the Cost Management Operator

Install the operator via an OperatorHub subscription. In production, this is typically done through the Web Console or GitOps.

```bash
# Apply the OperatorGroup and Subscription
oc apply -f manifests/cost-management-operatorgroup.yaml
oc apply -f manifests/cost-management-subscription.yaml

# Wait for the operator to install
oc wait --for=condition=Available deployment/koku-metrics-operator \
  -n cost-management --timeout=180s

# Verify the operator is running
oc get csv -n cost-management
```

```yaml
# From manifests/cost-management-subscription.yaml
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: koku-metrics-operator
  namespace: cost-management
  labels:
    app: cost-management
    tutorial-level: "3"
    tutorial-module: "M3"
spec:
  channel: stable
  installPlanApproval: Automatic
  name: koku-metrics-operator
  source: redhat-operators
  sourceNamespace: openshift-marketplace
```

### Step 3: Configure the KokuMetricsConfig Custom Resource

The `KokuMetricsConfig` CR tells the operator what to collect and where to send the data. For local or air-gapped environments, configure local storage instead of uploading to console.redhat.com.

```bash
# Create PVC for local report storage (air-gapped mode)
oc apply -f manifests/cost-reports-pvc.yaml

# Apply the KokuMetricsConfig CR
oc apply -f manifests/koku-metrics-config.yaml

# Verify the config was accepted
oc get kokumetricsconfig -n cost-management
```

```yaml
# From manifests/koku-metrics-config.yaml
apiVersion: koku-metrics-cfg.openshift.io/v1beta1
kind: KokuMetricsConfig
metadata:
  name: koku-metrics
  namespace: cost-management
  labels:
    app: cost-management
    tutorial-level: "3"
    tutorial-module: "M3"
spec:
  authentication:
    type: basic
  packaging:
    max_reports_to_store: 60
    max_size_MB: 100
  prometheus_config:
    collect_previous_data: true
    context_timeout: 120
    disable_metrics_collection_cost_management: false
    disable_metrics_collection_resource_optimization: false
  source:
    check_cycle: 1440
    create_source: false
    name: openshift-local-cluster
  upload:
    upload_toggle: false
    upload_cycle: 360
  volume_claim_template:
    spec:
      accessModes:
        - ReadWriteOnce
      resources:
        requests:
          storage: 10Gi
```

Key configuration options:

- `upload_toggle: false` -- stores reports locally instead of uploading to console.redhat.com (use `true` for production with Red Hat subscription)
- `collect_previous_data: true` -- backfills data from Prometheus retention on first run
- `disable_metrics_collection_resource_optimization: false` -- enables right-sizing recommendations
- `max_reports_to_store: 60` -- retains 60 hourly reports (~2.5 days) locally

### Step 4: Label Namespaces for Cost Attribution

Cost reports are only useful if workloads are properly attributed. Apply cost-tracking labels to existing projects.

```bash
# Label existing projects with cost-attribution metadata
oc label namespace default cost-center="CC-0000" team="platform" environment="system"
oc label namespace openshift-monitoring cost-center="CC-1000" team="platform" environment="infrastructure"

# Create sample team projects with proper cost labels
oc new-project cost-demo-frontend --display-name="Frontend Team"
oc label namespace cost-demo-frontend \
  cost-center="CC-2001" \
  team="frontend" \
  environment="development" \
  service="web-portal"

oc new-project cost-demo-backend --display-name="Backend Team"
oc label namespace cost-demo-backend \
  cost-center="CC-2002" \
  team="backend" \
  environment="development" \
  service="api-gateway"

oc new-project cost-demo-data --display-name="Data Team"
oc label namespace cost-demo-data \
  cost-center="CC-2003" \
  team="data-engineering" \
  environment="development" \
  service="analytics-pipeline"
```

### Step 5: Deploy Sample Workloads with Varying Resource Profiles

Deploy workloads that represent different cost profiles to generate meaningful data.

```bash
# Deploy workloads across the three team projects
oc apply -f manifests/workload-frontend.yaml -n cost-demo-frontend
oc apply -f manifests/workload-backend.yaml -n cost-demo-backend
oc apply -f manifests/workload-data.yaml -n cost-demo-data

# Verify deployments are running
oc get deployments -n cost-demo-frontend
oc get deployments -n cost-demo-backend
oc get deployments -n cost-demo-data
```

The workloads are sized to demonstrate different cost profiles:

| Workload | CPU Request | Memory Request | Replicas | Cost Profile |
|----------|-------------|----------------|----------|-------------|
| web-portal | 100m | 128Mi | 3 | Low: lightweight frontends |
| api-gateway | 250m | 512Mi | 2 | Medium: stateless API pods |
| analytics-worker | 500m | 1Gi | 1 | High: compute-intensive batch |

### Step 6: Verify Data Collection

After the operator runs its first collection cycle (usually within 15-30 minutes), verify that data is being collected.

```bash
# Check operator logs for collection status
oc logs deployment/koku-metrics-operator -n cost-management --tail=50

# Check if reports are being generated
oc get kokumetricsconfig koku-metrics -n cost-management -o yaml | \
  grep -A 10 "status:"

# If using local storage, check the PVC for CSV files
oc debug deployment/koku-metrics-operator -n cost-management -- \
  ls -la /tmp/koku-metrics-operator-reports/
```

Expected log output:
```
INFO  Starting metrics collection for cost management
INFO  Querying Prometheus for CPU usage data
INFO  Querying Prometheus for memory usage data
INFO  Querying Prometheus for node data
INFO  Querying Prometheus for storage data
INFO  Generated report: 2026-06-24T00-00-00.csv.gz
INFO  Stored report locally (upload disabled)
```

### Step 7: Build a Chargeback Model

With usage data being collected, define a chargeback model that maps resource consumption to costs. The script below calculates hourly costs based on your infrastructure pricing.

```bash
# Run the chargeback calculation script
bash scripts/chargeback-report.sh
```

The script (see `scripts/chargeback-report.sh`) performs the following:

1. Queries Prometheus for per-namespace CPU and memory usage over the last 24 hours.
2. Applies a cost rate (configurable: default $0.031/CPU-hour, $0.004/GB-hour based on typical cloud pricing).
3. Groups costs by the `cost-center` and `team` labels on namespaces.
4. Outputs a table showing cost per team and cost center.

Example output:
```
=== Chargeback Report (Last 24 Hours) ===
Date: 2026-06-24

Cost Rates: CPU=$0.031/core-hour  Memory=$0.004/GB-hour

Team                  Namespace              CPU ($)    Memory ($)   Total ($)
----                  ---------              -------    ----------   ---------
frontend              cost-demo-frontend       0.22        0.01        0.23
backend               cost-demo-backend        0.37        0.05        0.42
data-engineering      cost-demo-data           0.37        0.10        0.47
platform              openshift-monitoring      1.49        0.96        2.45

TOTAL                                          2.45        1.12        3.57
```

### Step 8: Generate Resource Optimization Recommendations

Query Prometheus for over-provisioned workloads and generate right-sizing recommendations.

```bash
# Run the optimization recommendation script
bash scripts/optimization-report.sh
```

The script identifies:

- **Over-provisioned pods**: actual usage is below 30% of requests for more than 7 days
- **Under-provisioned pods**: actual usage exceeds 80% of limits (throttling risk)
- **Idle workloads**: pods with near-zero CPU usage that could be scaled down or removed

Example output:
```
=== Resource Optimization Recommendations ===

OVER-PROVISIONED (reduce requests to save cost):
  Namespace: cost-demo-frontend
  Deployment: web-portal
    CPU: requested 100m, avg usage 23m -> recommended 50m (save $0.06/day)
    Memory: requested 128Mi, avg usage 45Mi -> recommended 64Mi (save $0.01/day)

UNDER-PROVISIONED (increase limits to prevent throttling):
  Namespace: cost-demo-data
  Deployment: analytics-worker
    CPU: limit 500m, p99 usage 480m -> recommended limit 750m
    Memory: limit 1Gi, p99 usage 920Mi -> recommended limit 1.5Gi

IDLE WORKLOADS (consider removal or scale-to-zero):
  (none detected)
```

### Step 9: Configure Alerts for Cost Anomalies

Set up PrometheusRule alerts that fire when a namespace's resource consumption exceeds expected thresholds.

```bash
# Apply cost anomaly alerts
oc apply -f manifests/cost-alerts.yaml -n openshift-monitoring
```

```yaml
# From manifests/cost-alerts.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: cost-management-alerts
  namespace: openshift-monitoring
  labels:
    app: cost-management
    tutorial-level: "3"
    tutorial-module: "M3"
spec:
  groups:
    - name: cost-management
      rules:
        - alert: NamespaceCPUCostSpike
          expr: |
            (
              sum by (namespace) (rate(container_cpu_usage_seconds_total{container!="POD",container!=""}[1h]))
              /
              sum by (namespace) (kube_pod_container_resource_requests{resource="cpu"})
            ) > 0.9
          for: 30m
          labels:
            severity: warning
            cost_impact: "high"
          annotations:
            summary: "Namespace {{ $labels.namespace }} CPU usage exceeds 90% of requests"
            description: >
              CPU usage in namespace {{ $labels.namespace }} has exceeded 90% of
              total CPU requests for more than 30 minutes. This may indicate
              under-provisioning (risk of throttling) or an unexpected workload spike.
              Review resource requests and consider scaling.
        - alert: NamespaceOverProvisionedCPU
          expr: |
            (
              sum by (namespace) (rate(container_cpu_usage_seconds_total{container!="POD",container!=""}[24h]))
              /
              sum by (namespace) (kube_pod_container_resource_requests{resource="cpu"})
            ) < 0.2
          for: 7d
          labels:
            severity: info
            cost_impact: "medium"
          annotations:
            summary: "Namespace {{ $labels.namespace }} is over-provisioned (CPU < 20% of requests)"
            description: >
              CPU usage in namespace {{ $labels.namespace }} has been below 20% of
              total CPU requests for 7 days. Consider reducing resource requests to
              lower costs without impacting performance.
        - alert: PVCStorageWaste
          expr: |
            (
              kubelet_volume_stats_used_bytes
              /
              kubelet_volume_stats_capacity_bytes
            ) < 0.1
          for: 7d
          labels:
            severity: info
            cost_impact: "low"
          annotations:
            summary: "PVC {{ $labels.persistentvolumeclaim }} in {{ $labels.namespace }} is less than 10% utilized"
            description: >
              The PVC {{ $labels.persistentvolumeclaim }} has been using less than
              10% of its provisioned capacity for 7 days. Consider resizing the PVC
              or migrating to a smaller volume to reduce storage costs.
```

## Verification

After completing all steps, verify the cost management stack is functioning:

```bash
# 1. Operator is running
oc get deployment koku-metrics-operator -n cost-management
# Expected: READY 1/1, AVAILABLE 1

# 2. KokuMetricsConfig exists and is configured
oc get kokumetricsconfig -n cost-management
# Expected: koku-metrics listed

# 3. Cost-attribution labels are applied to demo namespaces
for ns in cost-demo-frontend cost-demo-backend cost-demo-data; do
  echo "--- $ns ---"
  oc get namespace $ns -o jsonpath='{.metadata.labels}' | python3 -m json.tool
done
# Expected: cost-center, team, environment, service labels on each

# 4. Sample workloads are running
oc get deployments -n cost-demo-frontend
oc get deployments -n cost-demo-backend
oc get deployments -n cost-demo-data
# Expected: web-portal (3 replicas), api-gateway (2 replicas), analytics-worker (1 replica)

# 5. Operator is collecting metrics (check logs)
oc logs deployment/koku-metrics-operator -n cost-management --tail=20 | grep -i "collect\|report\|upload"
# Expected: log lines showing metric collection and report generation

# 6. PrometheusRule for cost alerts is active
oc get prometheusrule cost-management-alerts -n openshift-monitoring
# Expected: rule exists

# 7. Chargeback report runs successfully
bash scripts/chargeback-report.sh
# Expected: table output with per-team cost breakdown
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Cost management operator | None built-in; use Kubecost, OpenCost | Cost Management Operator (koku-metrics) |
| Metering data collection | DIY with Prometheus queries | Operator collects and packages CSV reports |
| Cloud cost integration | Manual API integration with each provider | Red Hat Hybrid Cloud Console aggregates cloud + cluster costs |
| Chargeback reporting | Build custom pipelines | Console-based reports by project, team, cluster |
| Resource optimization | Third-party tools (Kubecost, Goldilocks) | Built-in optimization recommendations via operator |
| Multi-cluster cost view | No native solution | Hybrid Cloud Console aggregates across clusters |
| Namespace cost labeling | Convention only (no enforcement) | Labels + ClusterResourceQuota (L3-M1.5) for enforcement |
| Storage cost tracking | DIY PVC usage monitoring | Operator tracks PVC utilization in cost reports |
| Air-gapped support | N/A (no built-in tool) | Local PVC storage mode for disconnected clusters |
| Cost alerts | DIY PrometheusRules | DIY PrometheusRules (same) + console-level alerts |

## Key Takeaways

- **The Cost Management Operator bridges the gap** between raw Prometheus metrics and actionable cost data. It automates the collection, packaging, and (optionally) upload of usage data that would otherwise require custom pipelines in vanilla Kubernetes.
- **Consistent labeling is the foundation of cost management.** Without `cost-center`, `team`, and `environment` labels on namespaces and workloads, usage data cannot be attributed to business owners. Enforce labeling standards via admission webhooks or OPA/Kyverno policies.
- **Start with showback, graduate to chargeback.** Display per-team costs for 2-3 months to build trust in the data before using it for actual billing. Inaccurate chargeback destroys credibility.
- **Resource optimization recommendations require historical data.** At least 7 days of usage data is needed to generate meaningful right-sizing suggestions. Do not act on recommendations from less than a week of data -- workload patterns vary by business cycle.
- **Cost management and resource quotas are complementary.** Quotas (L3-M1.5) enforce hard limits to prevent overconsumption; cost management provides visibility into what is actually used and what is wasted within those limits.

## Failure Modes & Recovery

### Operator Not Collecting Data

**Symptom:** `oc get kokumetricsconfig` shows the CR but no reports are generated. Operator logs show Prometheus connection errors.

**Recovery:**

1. Verify Prometheus is accessible from the operator's namespace:
   ```bash
   oc logs deployment/koku-metrics-operator -n cost-management | grep -i "prometheus\|error"
   ```
2. Check the `prometheus_config.context_timeout` -- increase it if the cluster has many namespaces (>100).
3. Ensure the operator's ServiceAccount has the correct ClusterRoleBinding:
   ```bash
   oc get clusterrolebinding | grep cost-management
   ```
4. Restart the operator:
   ```bash
   oc rollout restart deployment/koku-metrics-operator -n cost-management
   ```

### Upload Failures (Connected Mode)

**Symptom:** Reports are generated but not uploaded. Operator logs show HTTP 401 or 403 errors.

**Recovery:**

1. Verify the cluster is registered with console.redhat.com:
   ```bash
   oc get secret pull-secret -n openshift-config -o jsonpath='{.data.\.dockerconfigjson}' | base64 -d | python3 -m json.tool | grep cloud.openshift.com
   ```
2. Ensure the `authentication.type` in KokuMetricsConfig matches your setup (`token` for connected, `basic` for service account).
3. Switch to local storage mode (`upload_toggle: false`) as a temporary fallback.

### PVC Full -- Reports Stop Writing

**Symptom:** Operator logs show "no space left on device" errors. New reports are not created.

**Recovery:**

1. Check PVC usage:
   ```bash
   oc exec deployment/koku-metrics-operator -n cost-management -- df -h /tmp/koku-metrics-operator-reports/
   ```
2. Reduce `max_reports_to_store` in the KokuMetricsConfig or increase the PVC size.
3. Manually delete old reports if the PVC is critically full:
   ```bash
   oc exec deployment/koku-metrics-operator -n cost-management -- \
     find /tmp/koku-metrics-operator-reports/ -name "*.csv.gz" -mtime +3 -delete
   ```

### Inaccurate Cost Attribution

**Symptom:** Chargeback reports show large "unattributed" costs, or costs are assigned to the wrong team.

**Recovery:**

1. Audit namespace labels:
   ```bash
   oc get namespaces -o custom-columns=NAME:.metadata.name,COST_CENTER:.metadata.labels.cost-center,TEAM:.metadata.labels.team
   ```
2. Identify namespaces missing cost-center or team labels and apply them.
3. Consider enforcing labels via an admission webhook or OPA policy to prevent unlabeled namespaces from being created.

### Stale Optimization Recommendations

**Symptom:** Recommendations suggest reducing resources for workloads that have since scaled up, leading to performance issues if followed blindly.

**Recovery:**

1. Always verify recommendations against current usage before applying:
   ```bash
   oc adm top pods -n <namespace>
   ```
2. Use a 14-day window instead of 7 days for workloads with variable patterns.
3. Apply recommendations gradually: adjust requests by 20-30% at a time and monitor for 48 hours before further adjustments.

## Cleanup

```bash
# Log in as cluster-admin
oc login -u kubeadmin -p <password> https://api.crc.testing:6443

# Delete cost anomaly alerts
oc delete prometheusrule cost-management-alerts -n openshift-monitoring

# Delete sample workload projects
oc delete project cost-demo-frontend cost-demo-backend cost-demo-data

# Delete the KokuMetricsConfig CR
oc delete kokumetricsconfig koku-metrics -n cost-management

# Delete the operator subscription and CSV
oc delete subscription koku-metrics-operator -n cost-management
oc delete csv -n cost-management -l operators.coreos.com/koku-metrics-operator.cost-management

# Delete the cost-management namespace (removes operator, RBAC, PVC)
oc delete project cost-management

# Remove cluster-level RBAC
oc delete clusterrole cost-management-reader
oc delete clusterrolebinding cost-management-reader-binding
```

## Next Steps

In **L3-M4.1 (OpenShift Virtualization / KubeVirt)**, you will learn how to run virtual machines alongside containers on OpenShift. Understanding cost management is directly relevant -- VMs consume significant compute and storage resources, and tracking their cost alongside containerized workloads is essential for accurate chargeback in organizations running mixed VM and container estates.
