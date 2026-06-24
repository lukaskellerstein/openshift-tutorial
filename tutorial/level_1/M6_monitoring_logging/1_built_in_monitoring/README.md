# L1-M6.1 — Built-in Monitoring Stack

**Level:** Foundations
**Duration:** 30 min

## Overview

In Kubernetes, monitoring is a "bring your own stack" affair -- you install Prometheus, Grafana, and alerting yourself (or use a managed service). OpenShift ships with a fully pre-installed, pre-configured monitoring stack based on Prometheus, Alertmanager, and Grafana. This lesson explores the built-in cluster monitoring stack, shows you how to enable user workload monitoring (a separate Prometheus instance for your own applications), and teaches you how to create a ServiceMonitor so OpenShift automatically scrapes metrics from your custom services.

## Prerequisites

- Completed: L1-M3.1 (oc new-app & Source-to-Image)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in via `oc login`
- `kubeadmin` access is required for enabling user workload monitoring (Step 3)

## K8s Context

In vanilla Kubernetes, there is no built-in monitoring. You typically:

1. Install the `kube-prometheus-stack` Helm chart (Prometheus Operator + Grafana + Alertmanager)
2. Configure Prometheus to discover targets via ServiceMonitors or PodMonitors
3. Set up Grafana dashboards manually or import community dashboards
4. Configure Alertmanager with notification channels (Slack, PagerDuty, email)
5. Manage upgrades, storage, and retention yourself

This works, but it is a significant operational burden. Every cluster needs its own monitoring setup, and keeping it running reliably is a full-time job. The Prometheus Operator helps, but you still install and manage it yourself.

## Concepts

### The Built-in Cluster Monitoring Stack

OpenShift 4.x ships with a fully managed monitoring stack in the `openshift-monitoring` namespace. You do not install it -- it is there from day one:

| Component | Purpose |
|-----------|---------|
| **Prometheus** (cluster) | Scrapes metrics from all OpenShift components (API server, etcd, kubelet, controllers, nodes) |
| **Alertmanager** | Routes alerts to notification channels (email, Slack, PagerDuty, webhooks) |
| **Thanos Querier** | Provides a unified query endpoint across Prometheus instances |
| **Grafana** (read-only) | Pre-built dashboards for cluster health, node utilization, and pod metrics |
| **kube-state-metrics** | Exposes Kubernetes object state as Prometheus metrics |
| **node-exporter** | Exposes node-level metrics (CPU, memory, disk, network) |
| **Prometheus Adapter** | Feeds custom metrics into the Kubernetes metrics API (for HPA) |

This stack is **managed by the Cluster Monitoring Operator (CMO)**. You do not upgrade it manually -- it is upgraded automatically as part of OpenShift cluster upgrades. You configure it through ConfigMaps, not by editing Prometheus configuration files directly.

### Cluster Monitoring vs User Workload Monitoring

OpenShift separates monitoring into two tiers:

1. **Cluster monitoring** (`openshift-monitoring` namespace) -- monitors the OpenShift platform itself. This is always on and managed by the cluster admin. Regular users cannot modify it.

2. **User workload monitoring** (`openshift-user-workload-monitoring` namespace) -- a separate Prometheus instance dedicated to scraping metrics from your applications. This is **disabled by default** and must be enabled by a cluster admin.

**Why the separation?**

- **Security**: Application owners should not be able to see or disrupt platform metrics.
- **Resource isolation**: A misbehaving application metric endpoint cannot overwhelm the cluster Prometheus.
- **Multi-tenancy**: Each project's metrics are isolated -- users only see metrics from namespaces they have access to.

### Enabling User Workload Monitoring

User workload monitoring is enabled by setting a single key in a ConfigMap in the `openshift-monitoring` namespace:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cluster-monitoring-config
  namespace: openshift-monitoring
data:
  config.yaml: |
    enableUserWorkload: true
```

When this is applied, OpenShift automatically deploys a second Prometheus instance (plus Thanos Ruler) in the `openshift-user-workload-monitoring` namespace. No manual installation required.

### ServiceMonitor -- Telling Prometheus What to Scrape

A `ServiceMonitor` is a custom resource (from the Prometheus Operator) that tells Prometheus how to discover and scrape metrics from a Service. Instead of editing a Prometheus configuration file, you declare a ServiceMonitor in your application's namespace:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: my-app-monitor
spec:
  selector:
    matchLabels:
      app: my-app        # Match Services with this label
  endpoints:
    - port: metrics       # Name of the port on the Service
      interval: 30s       # How often to scrape
```

The user workload Prometheus automatically discovers ServiceMonitors in your namespace and starts scraping the matched endpoints. This is the same mechanism used in vanilla Kubernetes with the Prometheus Operator -- but in OpenShift it is pre-installed and ready to use.

## Step-by-Step

### Step 1: Explore the Built-in Monitoring Stack

First, let's see what OpenShift has running in the monitoring namespace. Log in as `kubeadmin` to see cluster-level resources:

```bash
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
```

List the pods in the `openshift-monitoring` namespace:

```bash
oc get pods -n openshift-monitoring
```

Expected output (your pod names will vary):

```
NAME                                           READY   STATUS    RESTARTS   AGE
alertmanager-main-0                            6/6     Running   0          3d
cluster-monitoring-operator-5d8c4b9f6-abcde    2/2     Running   0          3d
kube-state-metrics-7f9c8d7b4-fghij             3/3     Running   0          3d
node-exporter-klmno                            2/2     Running   0          3d
prometheus-adapter-6b4c5d8e9-pqrst             1/1     Running   0          3d
prometheus-k8s-0                               6/6     Running   0          3d
prometheus-operator-7a8b9c0d1-uvwxy            2/2     Running   0          3d
thanos-querier-5e6f7a8b9-zabcd                 6/6     Running   0          3d
```

Notice that Prometheus, Alertmanager, Thanos Querier, kube-state-metrics, and node-exporter are all running without you having installed anything.

### Step 2: Access Monitoring in the Web Console

Open the OpenShift Web Console:

```
https://console-openshift-console.apps-crc.testing
```

1. Log in as `kubeadmin`
2. Switch to the **Administrator** perspective (left sidebar)
3. Navigate to **Observe > Dashboards** -- you will see pre-built Grafana dashboards for cluster health
4. Navigate to **Observe > Metrics** -- this is a built-in PromQL query interface
5. Try a sample query:

```promql
node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes * 100
```

This shows available memory as a percentage across all nodes. The metrics are already being collected -- no configuration needed.

6. Navigate to **Observe > Alerting** -- you will see pre-configured alerts for cluster health (etcd quorum, node pressure, API server latency, etc.)

### Step 3: Enable User Workload Monitoring

By default, the Prometheus instance only monitors OpenShift platform components. To monitor your own applications, you need to enable user workload monitoring. This requires `kubeadmin` (cluster admin) access.

Apply the ConfigMap from this lesson's manifests:

```bash
oc apply -f manifests/cluster-monitoring-config.yaml
```

This creates (or updates) the `cluster-monitoring-config` ConfigMap in the `openshift-monitoring` namespace with `enableUserWorkload: true`.

Wait for the user workload monitoring pods to appear:

```bash
oc get pods -n openshift-user-workload-monitoring -w
```

Expected output (after 1-2 minutes):

```
NAME                                   READY   STATUS    RESTARTS   AGE
prometheus-operator-6b4c5d8e9-abcde    2/2     Running   0          30s
prometheus-user-workload-0             6/6     Running   0          25s
thanos-ruler-user-workload-0           4/4     Running   0          20s
```

Press `Ctrl+C` to stop watching once all pods show `Running`.

A second Prometheus instance is now running, dedicated to scraping your applications. This happened automatically -- you only set one ConfigMap key.

### Step 4: Create a Project and Deploy a Sample App with Metrics

Switch to the `developer` user and create a project for this lesson:

```bash
oc login -u developer -p developer https://api.crc.testing:6443
oc new-project l1-m6-monitoring --display-name="L1-M6: Monitoring Demo"
```

Deploy a sample application that exposes Prometheus metrics. We will use the `quay.io/brancz/prometheus-example-app` image, which exposes a `/metrics` endpoint on port 8080:

```bash
oc apply -f manifests/deployment.yaml
oc apply -f manifests/service.yaml
```

Wait for the pod to be ready:

```bash
oc get pods -l app=prometheus-example-app -w
```

Expected output:

```
NAME                                      READY   STATUS    RESTARTS   AGE
prometheus-example-app-5d8b9f7c6-abc12    1/1     Running   0          15s
```

Press `Ctrl+C` once the pod shows `1/1 Running`.

Verify the app is exposing metrics by checking the `/metrics` endpoint from inside the cluster:

```bash
oc exec deploy/prometheus-example-app -- curl -s http://localhost:8080/metrics | head -15
```

Expected output:

```
# HELP http_requests_total Count of all HTTP requests
# TYPE http_requests_total counter
http_requests_total{code="200",method="get"} 0
# HELP version Version information about this binary
# TYPE version gauge
version{version="v0.5.0"} 1
```

The app is exposing Prometheus-format metrics. Now we need to tell OpenShift's Prometheus to scrape them.

### Step 5: Create a ServiceMonitor

Apply the ServiceMonitor manifest:

```bash
oc apply -f manifests/service-monitor.yaml
```

Verify the ServiceMonitor was created:

```bash
oc get servicemonitor -n l1-m6-monitoring
```

Expected output:

```
NAME                     AGE
prometheus-example-app   5s
```

Let's examine what the ServiceMonitor does:

```bash
oc get servicemonitor prometheus-example-app -o yaml
```

Key fields:

```yaml
spec:
  selector:
    matchLabels:
      app: prometheus-example-app   # Matches our Service
  endpoints:
    - port: metrics                 # Scrape the port named "metrics"
      interval: 15s                 # Every 15 seconds
```

The user workload Prometheus discovers this ServiceMonitor, finds the matching Service, resolves its endpoints (pods), and starts scraping the `/metrics` path on the `metrics` port every 15 seconds.

### Step 6: Query Your Application Metrics

Generate some traffic so there are metrics to see:

```bash
oc expose service/prometheus-example-app
ROUTE_URL=$(oc get route prometheus-example-app -o jsonpath='{.spec.host}')
for i in $(seq 1 20); do curl -s http://$ROUTE_URL > /dev/null; done
echo "Generated 20 requests"
```

Now query the metrics. Open the Web Console:

1. Log in as `developer`
2. Switch to the **Developer** perspective
3. Navigate to **Observe > Metrics**
4. Enter this PromQL query:

```promql
http_requests_total{namespace="l1-m6-monitoring"}
```

You should see the `http_requests_total` counter from your application. The graph shows the metric increasing as requests come in.

Alternatively, query from the CLI using the Thanos Querier (requires `kubeadmin`):

```bash
oc login -u kubeadmin -p <password> https://api.crc.testing:6443

# Get the Thanos Querier route
THANOS_URL=$(oc get route thanos-querier -n openshift-monitoring -o jsonpath='{.spec.host}')

# Get a token for authentication
TOKEN=$(oc whoami -t)

# Query a metric
curl -s -k -H "Authorization: Bearer $TOKEN" \
  "https://$THANOS_URL/api/v1/query?query=http_requests_total{namespace='l1-m6-monitoring'}" | python3 -m json.tool
```

### Step 7: View Monitoring in the Web Console (Developer Perspective)

Log back in as `developer` and explore the monitoring features available to application developers:

1. Open the Web Console and switch to the **Developer** perspective
2. Select project `l1-m6-monitoring`
3. Navigate to **Observe > Dashboard** -- see CPU, memory, and network usage for your project
4. Navigate to **Observe > Metrics** -- run PromQL queries scoped to your project
5. Navigate to **Observe > Alerts** -- see any firing alerts for your project (none yet -- you will create alerts in L1-M6.2)

Notice that as `developer`, you can only see metrics from namespaces you have access to. This is the multi-tenancy benefit of separating user workload monitoring from cluster monitoring.

## Verification

Confirm the monitoring stack is working end-to-end:

```bash
# 1. Cluster monitoring is running
oc get pods -n openshift-monitoring --no-headers | wc -l
```

Expected: a positive number (typically 8-12 pods).

```bash
# 2. User workload monitoring is enabled
oc get pods -n openshift-user-workload-monitoring --no-headers | wc -l
```

Expected: 3 or more pods.

```bash
# 3. ServiceMonitor is created
oc get servicemonitor -n l1-m6-monitoring
```

Expected: `prometheus-example-app` listed.

```bash
# 4. The sample app is running and exposing metrics
oc login -u developer -p developer https://api.crc.testing:6443
oc project l1-m6-monitoring
oc exec deploy/prometheus-example-app -- curl -s http://localhost:8080/metrics | grep http_requests_total
```

Expected: lines showing the `http_requests_total` counter.

```bash
# 5. Metrics are queryable in the Web Console
# Open: https://console-openshift-console.apps-crc.testing
# Developer perspective > Observe > Metrics
# Query: http_requests_total{namespace="l1-m6-monitoring"}
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Monitoring stack | Install yourself (kube-prometheus-stack, Helm) | Pre-installed and managed by the platform |
| Prometheus | Deploy and configure manually | Runs in `openshift-monitoring`, auto-configured |
| Grafana | Install, configure datasources, import dashboards | Pre-installed with built-in dashboards (read-only) |
| Alertmanager | Install and configure routing rules | Pre-installed with default cluster alerts |
| ServiceMonitor CRD | Available if you install Prometheus Operator | Available out of the box |
| User app monitoring | Same Prometheus scrapes everything | Separate Prometheus instance for user workloads |
| Multi-tenancy | No built-in metric isolation | Users only see metrics from their own namespaces |
| Upgrades | You manage Prometheus/Grafana upgrades | Upgraded automatically with the OpenShift cluster |
| Configuration | Edit Prometheus config files or Operator CRs | ConfigMap in `openshift-monitoring` namespace |
| Web Console integration | External Grafana URL | Metrics, dashboards, and alerts built into the Console |

## Key Takeaways

- **Monitoring is pre-installed in OpenShift**: Prometheus, Alertmanager, Grafana, and supporting components run out of the box in the `openshift-monitoring` namespace. You do not need to install or manage them.
- **User workload monitoring is separate and opt-in**: A dedicated Prometheus instance for your applications runs in the `openshift-user-workload-monitoring` namespace. Enable it with a single ConfigMap key (`enableUserWorkload: true`). This separation provides security and resource isolation.
- **ServiceMonitors are the standard way to expose metrics**: Create a ServiceMonitor in your application's namespace, and the user workload Prometheus automatically discovers and scrapes your metrics endpoints. This is the same Prometheus Operator pattern used in Kubernetes, but pre-configured.
- **Multi-tenancy is built in**: Users can only query metrics from namespaces they have access to. The Web Console's Observe section provides project-scoped dashboards and PromQL queries.
- **The Web Console is your monitoring UI**: Unlike Kubernetes where you access Grafana separately, OpenShift integrates metrics, dashboards, and alerts directly into the Web Console for both administrators and developers.

## Cleanup

Remove the resources created in this lesson:

```bash
# Switch to developer user
oc login -u developer -p developer https://api.crc.testing:6443

# Delete the project (removes all resources within it)
oc delete project l1-m6-monitoring
```

If you want to disable user workload monitoring (as kubeadmin):

```bash
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
oc delete configmap cluster-monitoring-config -n openshift-monitoring
```

> **Note**: In a real environment, you would typically leave user workload monitoring enabled. Only disable it here if you are cleaning up a CRC environment and need to reclaim resources.

## Next Steps

In **L1-M6.2 -- Alerts & Metrics**, you will learn how to define PrometheusRules for custom alerting, configure Alertmanager notification routing, and create custom ServiceMonitors for more advanced metric collection patterns. You will build on the user workload monitoring stack enabled in this lesson.
