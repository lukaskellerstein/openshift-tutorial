# L1-M5.3 -- Serving Metrics and Grafana Dashboards

**Level:** Foundations
**Duration:** 30 min

## Overview

vLLM exposes a rich set of Prometheus metrics -- latency histograms, cache utilization gauges, throughput counters, and queue depth indicators. In this lesson you will connect those metrics to the OpenShift built-in monitoring stack, create alert rules for SLO violations, and deploy a Grafana dashboard that gives you real-time visibility into your model serving performance.

If you have used Prometheus `ServiceMonitor` and `PrometheusRule` CRDs on vanilla Kubernetes, the mechanics are identical here. What OpenShift adds is a pre-installed, pre-configured monitoring stack (Prometheus, Alertmanager, Grafana) and a user-workload monitoring feature that lets you scrape metrics from your own namespaces without touching the cluster monitoring infrastructure.

## Prerequisites

- Completed: L1-M2.2 (Deploying Gemma) -- you need a running vLLM-based InferenceService
- OpenShift cluster with user-workload monitoring enabled (sandbox or self-managed)
- `oc` CLI authenticated to the cluster
- Basic familiarity with PromQL (Prometheus query language)

## K8s Context

On vanilla Kubernetes, setting up monitoring for a custom application requires:

1. Installing the Prometheus Operator (via Helm or manually)
2. Deploying Prometheus and Alertmanager instances
3. Creating `ServiceMonitor` CRDs to tell Prometheus what to scrape
4. Creating `PrometheusRule` CRDs for alert definitions
5. Optionally deploying Grafana and importing dashboards

Each of these is a separate install-and-maintain step. You manage the Prometheus Operator lifecycle, storage, retention, and Grafana separately.

## Concepts

### vLLM Prometheus Metrics

vLLM exposes metrics on port 8080 at the `/metrics` endpoint in Prometheus exposition format. These are the key metrics for production monitoring:

**Latency Histograms** (bucket/sum/count pattern):

| Metric | What It Measures |
|--------|-----------------|
| `vllm:time_to_first_token_seconds` | Time from request receipt to first output token -- the "thinking" delay users experience |
| `vllm:inter_token_latency_seconds` | Time between consecutive output tokens -- controls perceived streaming speed |
| `vllm:e2e_request_latency_seconds` | Total request duration from receipt to final token |

**Gauges** (instantaneous values):

| Metric | What It Measures |
|--------|-----------------|
| `vllm:num_requests_running` | Requests currently being processed by the engine |
| `vllm:num_requests_waiting` | Requests queued, waiting for KV cache space |
| `vllm:kv_cache_usage_perc` | Fraction of KV cache blocks in use (0.0 to 1.0) |
| `vllm:gpu_cache_usage_perc` | GPU memory cache utilization (0.0 to 1.0) |

**Counters** (monotonically increasing):

| Metric | What It Measures |
|--------|-----------------|
| `vllm:prompt_tokens_total` | Total prompt (input) tokens processed |
| `vllm:generation_tokens_total` | Total generation (output) tokens produced |
| `vllm:request_success_total` | Number of successfully completed requests |
| `vllm:request_failure_total` | Number of failed requests |

The KV cache metrics are especially important. When `kv_cache_usage_perc` approaches 1.0, new requests must wait in the queue (`num_requests_waiting` rises), latency spikes, and eventually requests time out. Monitoring cache pressure is the single most important operational signal for vLLM.

### OpenShift Monitoring Stack

OpenShift ships with a complete monitoring stack:

- **Cluster monitoring** -- a dedicated Prometheus instance in the `openshift-monitoring` namespace that scrapes OpenShift platform components (API server, etcd, kubelet, etc.). This is always on and not configurable by non-admin users.
- **User-workload monitoring** -- a separate Prometheus instance in `openshift-user-workload-monitoring` that scrapes metrics from user namespaces. This must be explicitly enabled.
- **Alertmanager** -- routes alerts from both Prometheus instances.
- **Thanos Querier** -- a unified query layer that federates across both Prometheus instances, so the OpenShift web console can show cluster and user metrics together.

User-workload monitoring is enabled via a ConfigMap in the `openshift-monitoring` namespace:

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

On the Red Hat Developer Sandbox, user-workload monitoring is already enabled.

### ServiceMonitor

The `ServiceMonitor` CRD is the standard Prometheus Operator mechanism for declaring scrape targets. Instead of editing a Prometheus configuration file, you create a `ServiceMonitor` in the same namespace as your application, and Prometheus automatically picks it up.

A `ServiceMonitor` uses label selectors to find Kubernetes `Service` objects. The Prometheus instance in `openshift-user-workload-monitoring` watches for `ServiceMonitor` resources in user namespaces and adds the matching services to its scrape configuration.

### PrometheusRule

The `PrometheusRule` CRD defines alerting and recording rules. Rules are evaluated by Prometheus at a fixed interval (typically every 30 seconds). When an alerting rule's expression evaluates to true for longer than the `for` duration, the alert fires and is sent to Alertmanager.

### Grafana Dashboards

In newer versions of OpenShift (4.11+), the built-in Grafana instance is read-only and primarily used for platform metrics. For user-workload dashboards, you have two options:

1. **OpenShift Console Metrics UI** -- use the Developer perspective > Observe > Metrics tab to write ad-hoc PromQL queries. This works without any additional setup.
2. **Dashboard ConfigMap** -- create a ConfigMap with the dashboard JSON and appropriate labels so it appears in the monitoring UI.
3. **Standalone Grafana** -- deploy a separate Grafana instance via the Grafana Operator for full dashboard editing capabilities.

In this lesson, we provide a ConfigMap-based dashboard that works with both the OpenShift console and standalone Grafana instances.

## Step-by-Step

### Step 1: Verify User-Workload Monitoring Is Enabled

Check whether the user-workload monitoring stack is running:

```bash
oc get pods -n openshift-user-workload-monitoring
```

Expected output (the exact pod names will vary):

```
NAME                                   READY   STATUS    RESTARTS   AGE
prometheus-user-workload-0             6/6     Running   0          2d
prometheus-user-workload-1             6/6     Running   0          2d
thanos-ruler-user-workload-0           4/4     Running   0          2d
thanos-ruler-user-workload-1           4/4     Running   0          2d
```

If the namespace is empty or does not exist, user-workload monitoring is not enabled. On a self-managed cluster, an admin must apply the `cluster-monitoring-config` ConfigMap shown in the Concepts section. On the Developer Sandbox, it is already enabled.

### Step 2: Verify vLLM Exposes Metrics

Confirm that your vLLM-based InferenceService is running and exposing metrics. First, find the predictor pod:

```bash
oc get pods -l component=predictor -n gemma-model
```

Expected output:

```
NAME                                              READY   STATUS    RESTARTS   AGE
my-model-predictor-00001-deployment-xxxxx-yyy     3/3     Running   0          1h
```

Port-forward to the metrics endpoint and check that Prometheus-format metrics are being served:

```bash
oc port-forward deployment/my-model-predictor-00001-deployment 8080:8080 -n gemma-model &
curl -s http://localhost:8080/metrics | grep "vllm:" | head -20
```

Expected output (partial):

```
vllm:num_requests_running 0
vllm:num_requests_waiting 0
vllm:kv_cache_usage_perc 0.0
vllm:gpu_cache_usage_perc 0.0
vllm:prompt_tokens_total 0
vllm:generation_tokens_total 0
vllm:request_success_total 0
vllm:request_failure_total 0
# HELP vllm:time_to_first_token_seconds Histogram of time to first token in seconds.
# TYPE vllm:time_to_first_token_seconds histogram
vllm:time_to_first_token_seconds_bucket{le="0.001"} 0
...
```

Stop the port-forward when done:

```bash
kill %1
```

If you see `vllm:` prefixed metrics in the output, the serving runtime is correctly exposing them.

### Step 3: Identify the Service Labels

The `ServiceMonitor` needs to select the correct Kubernetes `Service` object by label. Find the service that fronts your predictor:

```bash
oc get svc -n gemma-model -l component=predictor --show-labels
```

Expected output:

```
NAME                            TYPE        CLUSTER-IP     PORT(S)   AGE    LABELS
my-model-predictor-00001        ClusterIP   172.30.x.y     80/TCP    1h     component=predictor,...
```

Note the labels on the service -- the `ServiceMonitor` selector must match. The manifest provided in this lesson uses `component: predictor`, which matches the default KServe predictor service labels. If your service uses different labels, adjust the `spec.selector.matchLabels` field in the `ServiceMonitor`.

### Step 4: Apply the ServiceMonitor

Review the ServiceMonitor manifest:

```yaml
# manifests/servicemonitor.yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: vllm-metrics
  labels:
    app: vllm-serving
    tutorial-level: "1"
    tutorial-module: "M5"
spec:
  selector:
    matchLabels:
      component: predictor
  endpoints:
    - port: http
      path: /metrics
      interval: 30s
      scheme: http
      metricRelabelings:
        - sourceLabels: [__name__]
          regex: "vllm:.*"
          action: keep
  namespaceSelector:
    matchNames:
      - gemma-model
```

Key fields:

- **selector.matchLabels** -- selects Service objects with `component: predictor`. Adjust this to match your InferenceService.
- **endpoints[0].port** -- the named port on the Service to scrape. KServe predictor services typically expose an `http` port.
- **endpoints[0].path** -- `/metrics` is the standard Prometheus metrics endpoint.
- **endpoints[0].interval** -- how often Prometheus scrapes (30 seconds is a good default for LLM serving).
- **metricRelabelings** -- keeps only `vllm:` prefixed metrics to avoid scraping irrelevant metrics from the same endpoint.
- **namespaceSelector.matchNames** -- limits scraping to your project namespace (`gemma-model` in this tutorial).

Apply it:

```bash
oc apply -f manifests/servicemonitor.yaml -n gemma-model
```

Expected output:

```
servicemonitor.monitoring.coreos.com/vllm-metrics created
```

### Step 5: Verify Prometheus Is Scraping

After about 30-60 seconds, check that Prometheus has picked up the new target. Use the OpenShift web console:

1. Navigate to **Observe > Targets** in the Administrator perspective.
2. Filter by namespace (`gemma-model`).
3. You should see a target entry for `vllm-metrics` with state `UP`.

Alternatively, verify via the CLI by querying a metric through the Thanos Querier:

```bash
# Get the Thanos Querier route
THANOS_URL=$(oc get route thanos-querier -n openshift-monitoring -o jsonpath='{.spec.host}')

# Get an authentication token
TOKEN=$(oc whoami -t)

# Query a vLLM metric
curl -sk -H "Authorization: Bearer ${TOKEN}" \
  "https://${THANOS_URL}/api/v1/query?query=vllm:num_requests_running" | python3 -m json.tool
```

Expected output (the value will be `0` if no requests are in flight):

```json
{
    "status": "success",
    "data": {
        "resultType": "vector",
        "result": [
            {
                "metric": {
                    "__name__": "vllm:num_requests_running",
                    ...
                },
                "value": [1719500000, "0"]
            }
        ]
    }
}
```

If `result` is an empty array, wait another minute for Prometheus to complete its first scrape and try again.

### Step 6: Apply the PrometheusRule for Alerts

Review the alert rules. The manifest defines alerts across three groups:

- **vllm.latency** -- fires when P99 end-to-end latency exceeds 10 seconds or P95 TTFT exceeds 3 seconds.
- **vllm.capacity** -- fires when KV cache usage exceeds 90% or GPU cache usage exceeds 95%.
- **vllm.errors** -- fires when the request failure rate exceeds 5% or the request queue depth stays above 10 for 10 minutes.

Apply the rules:

```bash
oc apply -f manifests/prometheusrule.yaml -n gemma-model
```

Expected output:

```
prometheusrule.monitoring.coreos.com/vllm-alerts created
```

Verify the rules are loaded:

```bash
oc get prometheusrules -n gemma-model
```

Expected output:

```
NAME          AGE
vllm-alerts   5s
```

You can also verify in the web console under **Observe > Alerting > Alerting Rules**. Filter by namespace to see your rules.

### Step 7: Test an Alert (Optional)

To see an alert fire, you can temporarily lower a threshold. For example, change the KV cache alert to fire above 0% (which will trigger immediately if any requests have been processed):

```bash
# Create a temporary test version of the rule
oc patch prometheusrule vllm-alerts -n gemma-model --type='json' \
  -p='[{"op": "replace", "path": "/spec/groups/1/rules/0/expr", "value": "vllm:kv_cache_usage_perc > 0"}]'
```

After a few minutes, check the alert state:

```bash
# View firing alerts through the Thanos Querier
curl -sk -H "Authorization: Bearer ${TOKEN}" \
  "https://${THANOS_URL}/api/v1/alerts" | python3 -m json.tool | grep -A5 "VLLMHighKVCacheUsage"
```

When done testing, restore the original threshold:

```bash
oc apply -f manifests/prometheusrule.yaml -n gemma-model
```

### Step 8: Deploy the Grafana Dashboard

The dashboard ConfigMap contains a complete Grafana dashboard JSON with panels for all the key vLLM metrics.

Review the dashboard layout:

| Row | Panels |
|-----|--------|
| **Overview** | Request Rate, Running Requests, Waiting Requests, KV Cache %, GPU Cache %, Error Rate (6 stat panels) |
| **Latency** | TTFT (p50/p90/p99), ITL (p50/p90/p99), E2E Latency (p50/p90/p99) (3 time-series panels) |
| **Throughput** | Token Throughput (prompt + generation tokens/s), Request Rate success vs failure (2 time-series panels) |
| **Cache and Queue** | KV Cache Usage over time, GPU Cache Usage over time, Running vs Waiting Requests (3 time-series panels) |

Apply the ConfigMap:

```bash
oc apply -f manifests/grafana-dashboard-configmap.yaml -n gemma-model
```

Expected output:

```
configmap/vllm-grafana-dashboard created
```

### Step 9: View Metrics in the OpenShift Console

Even without a standalone Grafana instance, you can query all vLLM metrics through the OpenShift console:

1. Switch to the **Developer** perspective in the web console.
2. Navigate to **Observe > Metrics**.
3. Enter a PromQL query, for example:

```promql
histogram_quantile(0.95, rate(vllm:time_to_first_token_seconds_bucket[5m]))
```

4. Click **Run Queries** to see a time-series graph of the P95 TTFT.

Try these additional queries:

```promql
# KV cache utilization over time
vllm:kv_cache_usage_perc

# Total token throughput (prompt + generation)
sum(rate(vllm:prompt_tokens_total[5m])) + sum(rate(vllm:generation_tokens_total[5m]))

# Request queue depth
vllm:num_requests_waiting
```

### Step 10: (Optional) Deploy Standalone Grafana

If you want the full dashboard editing experience with the JSON dashboard from Step 8, deploy a Grafana instance using the Grafana Operator:

1. Install the **Grafana Operator** from OperatorHub (in the web console, go to Operators > OperatorHub, search for "Grafana").
2. Create a `Grafana` instance in your project.
3. Create a `GrafanaDatasource` pointing to the Thanos Querier.
4. The Grafana sidecar will automatically discover the dashboard ConfigMap because it has the `grafana_dashboard: "1"` label.

This step is optional. The OpenShift console Metrics UI and the ConfigMap-based dashboard cover most monitoring needs without a standalone Grafana deployment.

## Verification

Run through this checklist to confirm everything is working:

1. **ServiceMonitor is active:**

```bash
oc get servicemonitor vllm-metrics -n gemma-model
```

Expected: the resource exists.

2. **Prometheus is scraping the target:**

```bash
# Check via Thanos Querier
curl -sk -H "Authorization: Bearer $(oc whoami -t)" \
  "https://$(oc get route thanos-querier -n openshift-monitoring -o jsonpath='{.spec.host}')/api/v1/query?query=up{job='vllm-metrics'}" \
  | python3 -m json.tool | grep '"value"'
```

Expected: the value is `1` (target is up).

3. **Alert rules are loaded:**

```bash
oc get prometheusrules vllm-alerts -n gemma-model -o jsonpath='{.spec.groups[*].name}'
```

Expected output: `vllm.latency vllm.capacity vllm.errors`

4. **Dashboard ConfigMap exists:**

```bash
oc get configmap vllm-grafana-dashboard -n gemma-model -o jsonpath='{.metadata.labels}'
```

Expected: labels include `console.openshift.io/dashboard: "true"`.

5. **Metrics are queryable:**

Open the Developer perspective > Observe > Metrics in the web console and run `vllm:num_requests_running`. You should see a time series graph.

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Monitoring stack | Install Prometheus Operator + Prometheus + Alertmanager + Grafana manually | Pre-installed, pre-configured, always running |
| User-app scraping | Create a Prometheus instance or configure the shared one | Enable `enableUserWorkload: true` in a ConfigMap -- no Prometheus management needed |
| ServiceMonitor | Same CRD, same behavior | Same CRD, auto-discovered by the user-workload Prometheus |
| PrometheusRule | Same CRD, same behavior | Same CRD, auto-loaded by user-workload Prometheus |
| Alert routing | Configure Alertmanager yourself | Alertmanager is pre-configured, alerts visible in web console |
| Dashboards | Deploy Grafana, import JSON manually | Console Metrics UI built in; ConfigMap-based dashboards also supported |
| Query federation | Set up Thanos yourself | Thanos Querier pre-deployed, federates cluster + user metrics |
| Authentication | Configure separately (often OIDC) | Integrated with OpenShift OAuth -- `oc whoami -t` works for API queries |

## Key Takeaways

- vLLM exposes comprehensive Prometheus metrics covering latency (TTFT, ITL, E2E), throughput (tokens/sec), cache utilization (KV, GPU), and queue depth -- everything needed for production monitoring
- OpenShift ships with a complete monitoring stack (Prometheus, Alertmanager, Thanos Querier) so you never install or manage Prometheus yourself
- `ServiceMonitor` and `PrometheusRule` CRDs work identically to vanilla Kubernetes -- if you know the Prometheus Operator, you already know how to monitor workloads on OpenShift
- KV cache usage (`vllm:kv_cache_usage_perc`) is the most important operational metric for vLLM -- when it approaches 1.0, requests queue and latency spikes
- User-workload monitoring must be enabled on self-managed clusters but is already on in the Developer Sandbox

## Cleanup

```bash
# Remove the monitoring resources
oc delete servicemonitor vllm-metrics -n gemma-model
oc delete prometheusrule vllm-alerts -n gemma-model
oc delete configmap vllm-grafana-dashboard -n gemma-model

# Verify cleanup
oc get servicemonitor,prometheusrule,configmap -l tutorial-module=M5 -n gemma-model
```

The InferenceService itself is left running -- it was created in a previous module and may be needed for subsequent lessons.

## Next Steps

In the next module, [L1-M6.1 -- AutoML Dashboard](../../M6_automl/1_automl_dashboard/), you will explore OpenShift AI's AutoML capability, which automates model selection and hyperparameter tuning through the dashboard UI.
