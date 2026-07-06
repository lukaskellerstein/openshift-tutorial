# LP-L07 — Monitoring & Logging: Prometheus + Loki

**Level:** Personalized
**Duration:** 1.5–2 hrs

## Overview

OpenShift ships with a complete monitoring stack — Prometheus, Alertmanager, and a managed Grafana — pre-installed and pre-configured for cluster infrastructure. In this lesson you build an observability stack for your applications:

1. **Prometheus** — custom metrics from all three Python services (counters, histograms, gauges)
2. **Loki** — centralized log aggregation for all pods across all namespaces

All three ShopInsights Python services (Products, Orders, Analytics) ship with Prometheus instrumentation built in — request-rate counters, latency histograms, and DuckDB query timers. In this lesson you enable Prometheus to scrape those metrics via ServiceMonitors, define alerting rules, and deploy Loki for centralized logging — all viewable through the OpenShift Web Console (Observe > Metrics, Observe > Logs).

> **What about Grafana dashboards?** L12 covers deploying a custom Grafana instance with unified dashboards for metrics, logs, traces, and alerts.

> **Automation:** This lesson includes `scripts/setup.sh` to install everything automatically. You can run it end-to-end or follow the manual steps below to understand each component.

## Prerequisites

- Completed: L01 through L06
- OpenShift cluster running on **AWS** (CRC or Developer Sandbox for Prometheus-only; AWS cluster with admin for the full stack)
- ShopInsights stack deployed in the `shopinsights` project
- Cluster-admin access (needed for operators, user workload monitoring, and logging)
- `oc` CLI installed and on PATH

## K8s Context

In vanilla Kubernetes, monitoring and logging are entirely DIY:

- **Metrics:** Install the Prometheus Operator (or kube-prometheus-stack Helm chart), configure scrape targets, set up Alertmanager, deploy Grafana, and maintain all of it yourself.
- **Logging:** Install a logging stack (EFK, Loki+Promtail, etc.), configure log collection agents, manage storage backends, and handle retention policies.
- **Dashboards:** Deploy Grafana, create datasources, and build dashboards manually.

On OpenShift, the monitoring stack is **pre-installed and managed by the Cluster Monitoring Operator**. Logging is installed via operators with CRD-based configuration — no Helm charts or manual YAML wrangling.

## Concepts

### The Built-In Monitoring Stack

OpenShift deploys these components in the `openshift-monitoring` namespace:

- **Prometheus** — scrapes cluster components (API server, etcd, kubelet, node-exporter)
- **Alertmanager** — routes alerts from Prometheus rules to notification channels
- **Grafana** — pre-built dashboards for cluster health (read-only, managed by the operator — cannot be customized)
- **Thanos Querier** — provides a unified query endpoint across multiple Prometheus instances

You do not install, upgrade, or configure any of these. They are managed by the **Cluster Monitoring Operator**.

> **Where are the native UIs?** In vanilla Kubernetes, Prometheus has a web UI at `:9090/graph`, Alertmanager at `:9093`, and you'd deploy Grafana separately. On OpenShift, these native UIs are **not exposed** — the routes only serve `/api` endpoints. The **OpenShift Console** (Observe > Metrics, Observe > Logs, Observe > Alerts) is the unified frontend that wraps all of them. Loki has **no UI at all** — it's a pure API backend queried by the Console. To access the native Prometheus or Alertmanager UIs for debugging, use `oc port-forward` (see TEST.md for commands).

### User Workload Monitoring

By default, the built-in Prometheus only scrapes OpenShift infrastructure. To monitor your own applications you must enable **user workload monitoring** by setting `enableUserWorkload: true` in the `cluster-monitoring-config` ConfigMap.

Once enabled, OpenShift deploys a **second Prometheus instance** in the `openshift-user-workload-monitoring` namespace. This instance is dedicated to scraping user applications — it reads ServiceMonitor and PodMonitor CRs from your project namespaces.

### ServiceMonitor & PrometheusRule

A `ServiceMonitor` tells Prometheus which Service to scrape (via label selectors), which port and path to hit, and how often. A `PrometheusRule` defines alerting and recording rules using PromQL expressions. Both are CRDs from the Prometheus Operator — identical to vanilla Kubernetes if you install the operator yourself.

### Prometheus Metric Types (Python)

The `prometheus_client` Python library provides four metric types:

| Type | Purpose | Example |
|------|---------|---------|
| **Counter** | Monotonically increasing total | Total HTTP requests |
| **Histogram** | Distribution of values in buckets | Request latency |
| **Gauge** | Value that goes up and down | Active connections |
| **Summary** | Similar to Histogram but with quantiles | (less common) |

In this lesson we use Counter, Histogram, and Gauge.

### OpenShift Logging Stack (Loki + Vector)

OpenShift provides a managed logging stack through two operators:

- **Loki Operator** — deploys and manages LokiStack, a horizontally-scalable log storage backend that indexes logs using labels (namespace, pod, container) rather than full-text indexing. Loki stores log data in S3-compatible object storage.
- **Cluster Logging Operator** — deploys Vector-based collector pods (DaemonSet) that read container logs from every node and forward them to LokiStack.

Together they provide centralized log aggregation visible in the OpenShift Console under **Observe > Logs**.

### LokiStack

A `LokiStack` CR defines the Loki deployment:

- **Size:** `1x.extra-small` (demo/dev) through `1x.medium` (production). Each size determines the number of replicas and resource requests.
- **Object Storage:** Loki requires S3-compatible storage for log chunks and index. On AWS clusters, the Cloud Credential Operator (CCO) can auto-provision IAM credentials for an S3 bucket.
- **Tenancy:** `openshift-logging` mode separates logs into `application`, `infrastructure`, and `audit` tenants with RBAC-based access.

### ClusterLogForwarder

A `ClusterLogForwarder` CR configures log collection pipelines:

- **Inputs:** `application` (user workload logs), `infrastructure` (OpenShift system logs), `audit` (API server audit logs). Custom inputs can filter by namespace and container name.
- **Outputs:** Where to send logs — LokiStack, CloudWatch, Elasticsearch, Kafka, etc.
- **Pipelines:** Connect inputs to outputs with optional filters

OpenShift Logging 6.x uses the `observability.openshift.io/v1` API version and Vector as the default collector.

## Architecture

```mermaid
graph TD
    Browser[Browser] --> DashUI[Dashboard UI]
    DashUI --> PS[Products Service :8080]
    DashUI --> OS[Orders Service :8080]
    DashUI --> AS[Analytics Service :8080]

    PS --> MW1[Middleware<br/>counters + histograms]
    OS --> MW2[Middleware<br/>counters + histograms]
    AS --> MW3[Middleware<br/>counters + histograms]

    PS --> STDOUT1[stdout logs]
    OS --> STDOUT2[stdout logs]
    AS --> STDOUT3[stdout logs]

    MW1 --> ME1[/metrics]
    MW2 --> ME2[/metrics]
    MW3 --> ME3[/metrics]

    ME1 --> Prom[Prometheus<br/>user-workload]
    ME2 --> Prom
    ME3 --> Prom

    STDOUT1 --> Vec[Vector Collector<br/>DaemonSet]
    STDOUT2 --> Vec
    STDOUT3 --> Vec

    Prom --> Thanos[Thanos Querier<br/>unified PromQL]
    Vec --> Loki[LokiStack<br/>openshift-logging]

    Thanos --> Console1[OpenShift Console<br/>Observe > Metrics]
    Loki --> Console2[OpenShift Console<br/>Observe > Logs]

    Prom --> AM[Alertmanager<br/>PrometheusRule → alerts]

    style Prom fill:#e8f5e9,stroke:#388e3c
    style Loki fill:#e3f2fd,stroke:#1565c0
    style Console1 fill:#e8f5e9,stroke:#388e3c
    style Console2 fill:#e3f2fd,stroke:#1565c0
```

## Step-by-Step

> **Quick start:** Run `scripts/setup.sh` to install all components automatically. The steps below explain what the script does.

### Step 1: Enable User Workload Monitoring

This requires cluster-admin privileges. You only need to do this once per cluster.

```bash
oc apply -f manifests/enable-user-workload-monitoring.yaml
```

```yaml
# manifests/enable-user-workload-monitoring.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cluster-monitoring-config
  namespace: openshift-monitoring
data:
  config.yaml: |
    enableUserWorkload: true
```

Wait for the user workload monitoring pods to start:

```bash
oc get pods -n openshift-user-workload-monitoring -w
```

You should see `prometheus-user-workload-*` and `thanos-ruler-user-workload-*` pods reach `Running` state (1-2 minutes).

### Step 2: Understand the Built-In Metrics Instrumentation

All three ShopInsights Python services (Products, Orders, Analytics) already include Prometheus instrumentation via `prometheus_client`. Open `shared_app/products-service/app.py` to see the pattern — the other two services follow the same approach.

Each service defines four custom metrics:

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `http_requests_total` | Counter | `method`, `endpoint`, `status` | Total HTTP requests |
| `http_request_duration_seconds` | Histogram | `method`, `endpoint` | Request latency distribution |
| `duckdb_query_duration_seconds` | Histogram | `query_type` | Database query duration |
| `active_connections` | Gauge | — | Currently active connections |

A FastAPI middleware automatically tracks every request (except `/metrics` itself), and DuckDB queries are wrapped with timing. The `/metrics` endpoint is mounted via `make_asgi_app()` and serves Prometheus text format.

> **No rebuild needed:** The metrics instrumentation is baked into the service images from the start. In lessons L01–L06, the `/metrics` endpoint simply goes unscraped — it causes no errors and adds negligible overhead.

### Step 3: Create ServiceMonitors and PrometheusRule

```bash
oc apply -f manifests/products-servicemonitor.yaml
oc apply -f manifests/orders-servicemonitor.yaml
oc apply -f manifests/analytics-servicemonitor.yaml
oc apply -f manifests/products-prometheusrule.yaml
```

The ServiceMonitors tell Prometheus to scrape `/metrics` on port `http` every 15 seconds for each service. The PrometheusRule creates two alerts:

1. **ProductsHighLatency** — fires when average latency exceeds 500ms for 5 minutes
2. **ProductsHighErrorRate** — fires when 5xx error rate exceeds 5% for 5 minutes

Verify in the Web Console: **Observe > Targets** (look for `products-service-monitor`, `orders-service-monitor`, and `analytics-service-monitor` — all should be UP) and **Observe > Alerting** (both alerts should be Inactive).

> **Note:** Prometheus renames our app's `endpoint` label to `exported_endpoint` because `endpoint` is reserved by ServiceMonitors. Use `exported_endpoint` in all PromQL queries that filter by path.

### Step 4: Install the Loki Operator

Create the namespace and install the operator:

```bash
oc apply -f manifests/ns-openshift-operators-redhat.yaml
oc apply -f manifests/operator-loki.yaml
```

Wait for the operator CSV to reach `Succeeded`:

```bash
oc get csv -n openshift-operators-redhat -w
```

### Step 5: Install the Cluster Logging Operator

```bash
oc apply -f manifests/ns-openshift-logging.yaml
oc apply -f manifests/operator-cluster-logging.yaml
```

Wait for the CSV:

```bash
oc get csv -n openshift-logging -w
```

### Step 6: Provision S3 Storage and Deploy LokiStack

LokiStack requires S3-compatible object storage. On AWS clusters, the Cloud Credential Operator (CCO) auto-provisions IAM credentials:

```bash
# Create a CredentialsRequest — CCO provisions an IAM user with S3 permissions
oc apply -f manifests/loki-s3-credentials-request.yaml

# Wait for the Secret to appear
oc get secret logging-loki-aws -n openshift-logging -w
```

The `setup.sh` script then creates an S3 bucket using a one-shot Job with those credentials and adds bucket/region/endpoint fields to the Secret. Finally it deploys the LokiStack:

```bash
oc apply -f manifests/lokistack.yaml
```

Wait for LokiStack to become Ready (3-5 minutes):

```bash
oc get lokistack logging-loki -n openshift-logging -w
```

### Step 7: Deploy ClusterLogForwarder

The ClusterLogForwarder tells Vector collectors which logs to collect and where to send them. Our CLF uses a custom input that filters to only the ShopInsights application containers (products-service, orders-service, analytics-service, dashboard-ui):

```bash
# Grant the collector SA log-reading and writing permissions
oc adm policy add-cluster-role-to-user collect-application-logs \
  -z cluster-logging-operator -n openshift-logging
oc adm policy add-cluster-role-to-user logging-collector-logs-writer \
  -z cluster-logging-operator -n openshift-logging

oc apply -f manifests/clusterlogforwarder.yaml
```

Verify collector pods are running:

```bash
oc get pods -n openshift-logging -l app.kubernetes.io/component=collector
```

Once collectors are running, logs from the ShopInsights services flow into Loki. View them in the Web Console under **Observe > Logs**.

### Step 8: Generate Traffic and Explore

Run the demo script to generate traffic and verify all three pillars:

```bash
./scripts/demo.sh
```

Or generate traffic manually:

```bash
# From inside the cluster
for i in $(seq 1 50); do
  oc exec deploy/dashboard-ui -- curl -s http://products-service:8080/products > /dev/null
done
```

Then explore:

1. **Console > Observe > Metrics** — Run PromQL queries:
   ```promql
   sum(rate(http_requests_total{namespace="shopinsights"}[5m])) by (exported_endpoint, method)
   ```

2. **Console > Observe > Logs** — Filter by namespace `shopinsights` to see access logs from all ShopInsights services

## Verification

```bash
# 1. User workload monitoring is enabled
oc get pods -n openshift-user-workload-monitoring | grep prometheus-user-workload

# 2. All three ServiceMonitors and PrometheusRule exist
oc get servicemonitor,prometheusrule -n shopinsights

# 3. Loki is running
oc get lokistack -n openshift-logging

# 4. Collectors are forwarding logs
oc get pods -n openshift-logging -l app.kubernetes.io/component=collector
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Prometheus | Install yourself (Helm chart, Operator) | Pre-installed, managed by Cluster Monitoring Operator |
| Alertmanager | Install and configure yourself | Pre-installed, accessible in Web Console |
| ServiceMonitor CRD | Available if you install Prometheus Operator | Available out of the box |
| PrometheusRule CRD | Available if you install Prometheus Operator | Available out of the box |
| User workload monitoring | Configure scrape targets manually | Flip one flag, create ServiceMonitors |
| Log aggregation | Install EFK/Loki stack yourself | Loki Operator + Cluster Logging Operator (managed) |
| Log collection | Deploy Promtail/Fluentd/Vector DaemonSet | ClusterLogForwarder CR deploys Vector collectors automatically |
| Log storage | Provision and manage object storage | CCO auto-provisions S3 credentials on AWS clusters |
| Log viewing | Port-forward to Grafana or Kibana | Built-in Console Observe > Logs with LogQL |
| Metrics UI | Port-forward to Prometheus/Grafana | Built-in Web Console Observe tab with PromQL editor |
| Maintenance | You upgrade and patch everything | Operators handle upgrades automatically |

## Key Takeaways

- OpenShift's monitoring stack (Prometheus, Alertmanager) is **pre-installed and managed** — you never install or upgrade it yourself
- Enable user workload monitoring with `enableUserWorkload: true` to start scraping your applications
- The **Loki Operator + Cluster Logging Operator** provide centralized log aggregation with a `ClusterLogForwarder` CR — no manual DaemonSet configuration
- LokiStack requires S3-compatible storage; on AWS, the **Cloud Credential Operator** auto-provisions IAM credentials
- The `prometheus_client` Python library makes instrumentation straightforward: define metrics, add middleware, mount `/metrics`. All three ShopInsights services include this from the start

## Cleanup

Run the cleanup script to remove all monitoring and logging components:

```bash
./scripts/cleanup.sh
```

This removes (in reverse order): ClusterLogForwarder, LokiStack, S3 bucket, CredentialsRequest, operator subscriptions, logging namespaces, ServiceMonitors, and PrometheusRule. User workload monitoring is **not** disabled (other lessons may use it).

## Next Steps

Your services are now fully observable with custom metrics and centralized logs, all viewable through the OpenShift Console. In [L08: CI/CD Pipeline](../L08_cicd_pipeline/), you will set up OpenShift Pipelines (Tekton) to automate building, testing, and deploying the ShopInsights stack.

In **L12 — Custom Monitoring Dashboards**, you will deploy a custom Grafana instance with unified dashboards for metrics, logs, traces, and alerts — bringing all observability data into a single pane of glass.
