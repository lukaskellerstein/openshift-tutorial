# L1-M6.2 — Alerts & Metrics

**Level:** Foundations
**Duration:** 30 min

## Overview

In Kubernetes, you define alerting rules by writing Prometheus rule files and loading them into Prometheus -- or, if you use the Prometheus Operator, by creating `PrometheusRule` custom resources. OpenShift ships with the Prometheus Operator pre-installed and hundreds of default alerting rules for cluster health. In this lesson, you will create custom `PrometheusRule` resources to fire alerts on your own application metrics, explore how Alertmanager routes and manages those alerts, and use `ServiceMonitor` to tell Prometheus which application endpoints to scrape. Everything happens through CRDs -- no manual Prometheus configuration required.

## Prerequisites

- Completed: L1-M6.1 (Built-in Monitoring Stack)
- User workload monitoring enabled (done in L1-M6.1, Step 3)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in via `oc login`
- `kubeadmin` access for Alertmanager configuration (Step 4)

## K8s Context

In vanilla Kubernetes with the Prometheus Operator installed, you:

1. Create `PrometheusRule` resources containing PromQL-based alerting rules
2. Configure Alertmanager via a `Secret` or the `AlertmanagerConfig` CRD to route alerts to receivers (Slack, PagerDuty, email, webhooks)
3. Create `ServiceMonitor` resources to tell Prometheus which Service endpoints to scrape
4. View firing alerts through the Alertmanager UI or Grafana

The workflow is the same in OpenShift -- but the Prometheus Operator, Alertmanager, and the entire alerting pipeline are pre-installed and managed. You create the same CRDs; OpenShift handles the rest.

## Concepts

### PrometheusRule -- Defining Custom Alerts

A `PrometheusRule` is a custom resource that defines alerting rules (and optionally recording rules) using PromQL expressions. When a rule's expression evaluates to true for the specified duration, Prometheus fires an alert and sends it to Alertmanager.

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: my-app-alerts
spec:
  groups:
    - name: my-app.rules
      rules:
        - alert: HighErrorRate
          expr: rate(http_requests_total{code=~"5.."}[5m]) > 0.1
          for: 2m
          labels:
            severity: warning
          annotations:
            summary: "High error rate detected"
            description: "More than 10% of requests are failing with 5xx errors."
```

Key fields:

- **`alert`**: The name of the alert (appears in the Web Console and Alertmanager).
- **`expr`**: A PromQL expression. When this evaluates to a non-empty result, the alert enters the `pending` state.
- **`for`**: How long the expression must remain true before the alert fires (`firing` state). This prevents transient spikes from triggering alerts.
- **`labels`**: Added to the alert. The `severity` label is commonly used by Alertmanager for routing (e.g., `critical` goes to PagerDuty, `warning` goes to Slack).
- **`annotations`**: Human-readable text for notifications. `summary` and `description` are conventions used by most notification templates.

In OpenShift, when you create a PrometheusRule in a user project, the user workload Prometheus automatically picks it up. No restart, no configuration reload -- the Prometheus Operator watches for PrometheusRule resources and updates Prometheus in real time.

### Alertmanager -- Routing and Managing Alerts

Alertmanager receives fired alerts from Prometheus and handles:

- **Grouping**: Combines related alerts into a single notification (e.g., all alerts from the same application).
- **Inhibition**: Suppresses lower-severity alerts when a higher-severity alert is already firing.
- **Silencing**: Temporarily mutes alerts (useful during maintenance windows).
- **Routing**: Sends alerts to the right receiver based on labels (severity, namespace, team).

OpenShift runs Alertmanager in the `openshift-monitoring` namespace with a default configuration. Cluster admins can customize it through a `Secret` named `alertmanager-main` in that namespace.

For user workloads, OpenShift 4.11+ supports the `AlertmanagerConfig` CRD, which lets application teams define routing rules in their own namespace without touching the cluster-wide Alertmanager configuration.

### ServiceMonitor -- Connecting Your App to Prometheus

You already created a `ServiceMonitor` in L1-M6.1. Here is a recap of how it works:

1. You deploy an application that exposes a `/metrics` endpoint in Prometheus format.
2. You create a `Service` that targets the application pods.
3. You create a `ServiceMonitor` that selects the Service by label and tells Prometheus which port to scrape and how often.

The user workload Prometheus discovers the ServiceMonitor, resolves the Service endpoints, and starts scraping. Metrics become available in the Web Console and can be used in PrometheusRule expressions.

### Alert States

Alerts move through three states:

| State | Meaning |
|-------|---------|
| **Inactive** | The PromQL expression evaluates to empty (no match). Everything is normal. |
| **Pending** | The expression matches, but the `for` duration has not elapsed yet. |
| **Firing** | The expression has matched continuously for the `for` duration. Alertmanager is notified. |

## Step-by-Step

### Step 1: Create a Project and Deploy a Sample App

Log in as `developer` and set up the project:

```bash
oc login -u developer -p developer https://api.crc.testing:6443
oc new-project l1-m6-alerts --display-name="L1-M6.2: Alerts & Metrics Demo"
```

Deploy a sample application that exposes Prometheus metrics. We will use the `quay.io/brancz/prometheus-example-app` image, which exposes `http_requests_total` and `version` metrics on port 8080 at `/metrics`:

```bash
oc create deployment alerts-demo \
  --image=quay.io/brancz/prometheus-example-app \
  --port=8080

oc label deployment alerts-demo \
  tutorial-level=1 tutorial-module=M6
```

Expose the deployment as a Service with a named port (the ServiceMonitor needs the port name):

```bash
oc create service clusterip alerts-demo \
  --tcp=8080:8080
```

> **Note**: The `oc create service` command creates a Service, but it does not automatically set the port name. We will apply a manifest with the correct port name in the next step.

Delete the auto-created service and apply the correct one from the manifests directory:

```bash
oc delete service alerts-demo
oc apply -f manifests/servicemonitor.yaml
```

Wait -- we also need the Service. Let's create the full stack with manifests. First, let's clean up and start with manifests:

```bash
oc delete deployment alerts-demo 2>/dev/null
```

Apply the deployment, service, and ServiceMonitor from the manifests directory:

```bash
# Deploy the sample app
oc create deployment alerts-demo \
  --image=quay.io/brancz/prometheus-example-app \
  --port=8080

# Add labels for tutorial tracking
oc label deployment alerts-demo \
  app=alerts-demo \
  tutorial-level=1 \
  tutorial-module=M6

# Ensure pods also get the app label
oc patch deployment alerts-demo --type=merge -p '{
  "spec": {
    "selector": {
      "matchLabels": {"app": "alerts-demo"}
    },
    "template": {
      "metadata": {
        "labels": {"app": "alerts-demo"}
      }
    }
  }
}'
```

Create a Service with a named port:

```bash
oc expose deployment alerts-demo --port=8080 --target-port=8080 --name=alerts-demo
oc label service alerts-demo app=alerts-demo tutorial-level=1 tutorial-module=M6
```

Wait for the pod to be ready:

```bash
oc get pods -l app=alerts-demo -w
```

Expected output:

```
NAME                          READY   STATUS    RESTARTS   AGE
alerts-demo-7f8c9d6b5-x2k4m  1/1     Running   0          15s
```

Press `Ctrl+C` once the pod shows `1/1 Running`.

Verify the app is exposing metrics:

```bash
oc exec deploy/alerts-demo -- curl -s http://localhost:8080/metrics | head -10
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

### Step 2: Create a ServiceMonitor

Apply the ServiceMonitor manifest to tell Prometheus to scrape the sample app:

```bash
oc apply -f manifests/servicemonitor.yaml
```

Let's look at what we are applying:

```yaml
# manifests/servicemonitor.yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: alerts-demo
  labels:
    app: alerts-demo
    tutorial-level: "1"
    tutorial-module: "M6"
spec:
  selector:
    matchLabels:
      app: alerts-demo
  endpoints:
    - port: http
      interval: 15s
      path: /metrics
```

The ServiceMonitor selects the `alerts-demo` Service by its `app: alerts-demo` label and scrapes the port named `http` every 15 seconds at the `/metrics` path.

Verify the ServiceMonitor was created:

```bash
oc get servicemonitor -n l1-m6-alerts
```

Expected output:

```
NAME          AGE
alerts-demo   5s
```

### Step 3: Create a PrometheusRule for Custom Alerts

Now create the alerting rules. Apply the PrometheusRule manifest:

```bash
oc apply -f manifests/prometheusrule.yaml
```

Let's examine what we are deploying:

```yaml
# manifests/prometheusrule.yaml (key sections)
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: alerts-demo
spec:
  groups:
    - name: alerts-demo.rules
      rules:
        - alert: AlertsDemoDown
          expr: up{job="alerts-demo"} == 0
          for: 1m
          labels:
            severity: critical
          annotations:
            summary: "alerts-demo application is down"
            description: "The alerts-demo application has been unreachable for more than 1 minute."
        - alert: AlertsDemoHighRequestRate
          expr: rate(http_requests_total{job="alerts-demo"}[2m]) > 0.5
          for: 1m
          labels:
            severity: warning
          annotations:
            summary: "High request rate on alerts-demo"
            description: "alerts-demo is receiving more than 0.5 requests per second (current value: {{ $value }})."
```

This creates two alert rules:

1. **AlertsDemoDown** (critical): Fires when the `up` metric for the `alerts-demo` job equals 0, meaning Prometheus cannot reach the application's metrics endpoint. The `for: 1m` means it waits 1 minute before firing to avoid alerting on brief pod restarts.

2. **AlertsDemoHighRequestRate** (warning): Fires when the application receives more than 0.5 requests per second sustained over 2 minutes. The `{{ $value }}` in the description is a Go template variable that gets replaced with the actual rate value.

Verify the PrometheusRule was created:

```bash
oc get prometheusrule -n l1-m6-alerts
```

Expected output:

```
NAME          AGE
alerts-demo   5s
```

### Step 4: View Alerts in the Web Console

Open the OpenShift Web Console and view the alerts:

```
https://console-openshift-console.apps-crc.testing
```

**As developer (Developer perspective):**

1. Log in as `developer`
2. Switch to the **Developer** perspective
3. Select project `l1-m6-alerts`
4. Navigate to **Observe > Alerts**
5. You should see your two custom alerts listed:
   - `AlertsDemoDown` -- should be **Inactive** (the app is running)
   - `AlertsDemoHighRequestRate` -- should be **Inactive** (no traffic yet)

**As kubeadmin (Administrator perspective):**

1. Log in as `kubeadmin`
2. Switch to the **Administrator** perspective
3. Navigate to **Observe > Alerting**
4. Click the **Alerting Rules** tab
5. Filter by "Source: User" to see only user-defined rules (not cluster alerts)
6. You should see both `AlertsDemoDown` and `AlertsDemoHighRequestRate`

### Step 5: Trigger an Alert

Let's trigger the `AlertsDemoHighRequestRate` alert by generating sustained traffic. Create a Route and send continuous requests:

```bash
oc login -u developer -p developer https://api.crc.testing:6443
oc project l1-m6-alerts

oc expose service/alerts-demo
ROUTE_URL=$(oc get route alerts-demo -o jsonpath='{.spec.host}')

# Generate sustained traffic for 3 minutes
echo "Sending requests to http://$ROUTE_URL ..."
for i in $(seq 1 200); do
  curl -s http://$ROUTE_URL > /dev/null
  sleep 0.5
done &
echo "Traffic generation running in background (PID: $!)"
```

While the traffic is running, watch the alert status in the Web Console:

1. Navigate to **Observe > Alerts** (Developer perspective, project `l1-m6-alerts`)
2. After about 1 minute, `AlertsDemoHighRequestRate` should change from **Inactive** to **Pending**
3. After another 1 minute (the `for: 1m` duration), it should change to **Firing**

You can also check from the CLI:

```bash
oc get prometheusrule alerts-demo -o jsonpath='{.spec.groups[0].rules[*].alert}'
```

Expected output:

```
AlertsDemoDown AlertsDemoHighRequestRate
```

To see the actual alert state, use the Web Console -- the PrometheusRule resource shows the rule definitions, not the current state.

### Step 6: Test the Critical Alert (AlertsDemoDown)

Scale the deployment to zero to simulate the application going down:

```bash
oc scale deployment alerts-demo --replicas=0
```

Now the `up{job="alerts-demo"}` metric will report `0` because Prometheus cannot reach any endpoints. After 1 minute, the `AlertsDemoDown` alert will transition from **Inactive** to **Pending**, then to **Firing** after the full `for: 1m` duration.

Check the Web Console:

1. Navigate to **Observe > Alerts** (Developer perspective)
2. `AlertsDemoDown` should show **Pending**, then **Firing** after 1 minute

Bring the application back up:

```bash
oc scale deployment alerts-demo --replicas=1
```

After the pod is running and Prometheus successfully scrapes it, the `up` metric returns to `1`, and the alert transitions back to **Inactive** (this may take 1-2 minutes depending on the scrape interval).

### Step 7: Explore Alertmanager Configuration (Cluster Admin)

Alertmanager configuration is managed at the cluster level. Log in as `kubeadmin`:

```bash
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
```

View the current Alertmanager configuration:

```bash
oc get secret alertmanager-main -n openshift-monitoring -o jsonpath='{.data.alertmanager\.yaml}' | base64 -d
```

Expected output (default configuration):

```yaml
global:
  resolve_timeout: 5m
route:
  group_by: ['namespace']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 12h
  receiver: 'default'
receivers:
  - name: 'default'
```

Key configuration concepts:

- **`group_by`**: Groups alerts by the specified label. Alerts from the same namespace are grouped into a single notification.
- **`group_wait`**: How long to wait before sending the first notification for a new group (allows time for related alerts to arrive).
- **`group_interval`**: How long to wait before sending notifications about new alerts added to an existing group.
- **`repeat_interval`**: How long to wait before re-sending a notification for an alert that is still firing.
- **`receiver`**: Where to send the notifications. The default receiver does nothing -- in production, you would configure Slack, PagerDuty, email, or webhook receivers.

> **Note**: Modifying the Alertmanager `Secret` directly requires cluster admin privileges. For user-scoped alert routing, OpenShift 4.11+ supports the `AlertmanagerConfig` CRD, which is covered in L2-M1.

## Verification

Confirm everything is working:

```bash
oc login -u developer -p developer https://api.crc.testing:6443
oc project l1-m6-alerts
```

```bash
# 1. ServiceMonitor exists and matches the app
oc get servicemonitor alerts-demo -n l1-m6-alerts
```

Expected: `alerts-demo` listed with an age.

```bash
# 2. PrometheusRule exists with both alerts
oc get prometheusrule alerts-demo -n l1-m6-alerts -o jsonpath='{.spec.groups[0].rules[*].alert}'
```

Expected: `AlertsDemoDown AlertsDemoHighRequestRate`

```bash
# 3. The sample app is running and exposing metrics
oc exec deploy/alerts-demo -- curl -s http://localhost:8080/metrics | grep http_requests_total
```

Expected: lines showing the `http_requests_total` counter.

```bash
# 4. Alerts are visible in the Web Console
# Open: https://console-openshift-console.apps-crc.testing
# Developer perspective > Observe > Alerts (project: l1-m6-alerts)
# Both AlertsDemoDown and AlertsDemoHighRequestRate should be listed
```

```bash
# 5. Metrics are queryable
# Developer perspective > Observe > Metrics
# Query: up{job="alerts-demo"}
# Expected: value of 1 (if app is running)
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| PrometheusRule CRD | Available if you install Prometheus Operator | Available out of the box |
| Alertmanager | Install and configure yourself | Pre-installed in `openshift-monitoring` |
| Alertmanager config | Edit Secret or AlertmanagerConfig CRD | Same CRDs, but Alertmanager is already running |
| ServiceMonitor CRD | Available if you install Prometheus Operator | Available out of the box |
| Alert visibility | Access Alertmanager UI or Grafana externally | Alerts integrated into the Web Console |
| User alert rules | Loaded into same Prometheus instance | Separate user workload Prometheus picks them up |
| Default alerts | None unless you create them | Hundreds of pre-configured cluster health alerts |
| Multi-tenancy | No isolation -- all rules in one Prometheus | User rules scoped to their namespace, isolated from platform |
| Alert routing (user) | Edit global Alertmanager config | `AlertmanagerConfig` CRD for namespace-scoped routing (4.11+) |
| Lifecycle | You manage upgrades and maintenance | Managed by the Cluster Monitoring Operator |

## Key Takeaways

- **PrometheusRule lets you define custom alerts declaratively**: Create a PrometheusRule in your namespace and the user workload Prometheus picks it up automatically. No manual configuration reload needed.
- **Alertmanager is pre-installed and ready**: It handles grouping, inhibition, silencing, and routing of alerts. The default configuration groups alerts by namespace. Cluster admins can add receivers (Slack, PagerDuty, email) by editing the Alertmanager Secret.
- **ServiceMonitor connects your application to Prometheus**: By matching Services via labels, ServiceMonitor tells Prometheus what to scrape, which port to use, and how often. This is the same pattern used in vanilla Kubernetes with the Prometheus Operator.
- **Alerts are visible in the Web Console**: Both developers and administrators can view alert states (Inactive, Pending, Firing) directly in the OpenShift console without needing external tools.
- **The separation of cluster and user workload monitoring extends to alerting**: Your PrometheusRules and ServiceMonitors live in your namespace, scoped to your applications. They cannot interfere with platform-level alerting rules.

## Cleanup

Remove the resources created in this lesson:

```bash
oc login -u developer -p developer https://api.crc.testing:6443

# Kill any background traffic generation
kill %1 2>/dev/null

# Delete the project (removes all resources within it)
oc delete project l1-m6-alerts
```

> **Note**: User workload monitoring (enabled in L1-M6.1) remains active. Do not disable it if you plan to continue with subsequent lessons.

## Next Steps

In **L1-M6.3 -- Logging with OpenShift Logging**, you will explore OpenShift's centralized logging stack. You will learn about the ClusterLogging and ClusterLogForwarder CRDs, how logs are collected from all pods and nodes, and how to search and filter logs in the Web Console -- all without installing Elasticsearch, Fluentd, or Kibana yourself.
