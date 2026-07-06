# L2-M5.5 -- Production Dashboards

**Level:** Practitioner
**Duration:** 45 min

## Overview

Throughout this module you have instrumented individual layers of the AI platform -- MLflow for experiment tracking, distributed tracing for agent calls, OpenTelemetry for telemetry collection, and TrustyAI for fairness and drift monitoring. Each of these produces metrics, but in production you need a single pane of glass that surfaces the signals that matter across all layers simultaneously.

This lesson builds a unified Grafana dashboard that combines vLLM inference performance, GPU resource utilization (DCGM), agent and pipeline health, and TrustyAI fairness metrics into one view. You will also define PrometheusRule alert definitions that encode SLO thresholds, so the platform notifies you before users notice degradation.

If you have built Grafana dashboards on vanilla Kubernetes, the panel definitions and PromQL queries are identical here. What OpenShift adds is the dashboard-as-ConfigMap pattern for auto-discovery and the pre-integrated alert routing through the built-in Alertmanager.

## Prerequisites

- Completed: L2-M5.4 -- TrustyAI Model Monitoring
- Completed: L2-M5.1 through L2-M5.3 (MLflow, tracing, OpenTelemetry)
- Completed: L1-M5.3 -- Serving Metrics and Grafana Dashboards (vLLM ServiceMonitor already deployed)
- OpenShift cluster with user-workload monitoring enabled
- `oc` CLI authenticated to the cluster
- Basic familiarity with PromQL and Grafana dashboard JSON structure

## Concepts

### The Four Pillars of AI Platform Observability

Production AI platforms have four distinct observability domains, each with its own metric sources and failure modes:

| Pillar | What You Monitor | Metric Source | Why It Matters |
|--------|-----------------|---------------|----------------|
| **Inference Performance** | Latency (TTFT, TPOT), throughput, error rates, queue depth, KV cache | vLLM Prometheus metrics | Directly impacts user experience -- a slow or erroring model is a broken product |
| **GPU Resources** | Utilization, memory, temperature, power draw | NVIDIA DCGM exporter | GPUs are expensive and constrained -- underuse wastes money, overuse causes OOM kills and thermal throttling |
| **Agent & Pipeline Health** | Trace duration, tool call counts, error rates, pipeline run status | MLflow metrics export, Data Science Pipelines | Agents and pipelines are multi-step -- a failure in step 3 of 7 is invisible without tracing |
| **Model Fairness** | Bias metrics (SPD, DIR), data drift scores | TrustyAI | Regulatory and ethical requirements -- a model can be fast and accurate but still discriminatory |

A dashboard that covers only one pillar gives you a partial picture. When inference latency spikes, is it because KV cache is full (pillar 1), GPU memory is exhausted (pillar 2), or the upstream agent is sending malformed prompts (pillar 3)? Cross-pillar dashboards let you correlate signals and find root causes faster.

---

### Why TTFT and TPOT Matter More Than Raw Latency

For traditional REST APIs, end-to-end latency (time from request to response) is the primary performance metric. LLM serving is different because responses are streamed token by token:

- **Time to First Token (TTFT)** -- the delay between the user sending a prompt and seeing the first word appear. This is the "thinking" delay. Users perceive TTFT as responsiveness. A TTFT above 3-5 seconds feels broken, even if the total generation is fast.

- **Time Per Output Token (TPOT)** -- the average time between consecutive tokens during generation. This controls the perceived "typing speed" of the model. A TPOT above 100ms makes streaming feel sluggish.

- **End-to-end latency** is TTFT + (TPOT x number of output tokens). For a 500-token response with 2s TTFT and 50ms TPOT, E2E is 27 seconds -- but the user started reading after 2 seconds and saw smooth streaming throughout. The same 27 seconds with 25s TTFT and 4ms TPOT would feel terrible despite the same total time.

This is why the dashboard separates TTFT and TPOT into distinct panels rather than showing only E2E latency.

---

### KV Cache as a Leading Indicator

The KV (key-value) cache stores attention keys and values for in-flight requests. It is allocated from GPU memory at model startup. When the cache fills:

1. New requests queue in `num_requests_waiting` (queue depth rises)
2. TTFT spikes because queued requests wait for cache slots
3. If the queue grows unbounded, requests time out and the error rate rises

The critical insight is that KV cache utilization is a **leading indicator** -- it rises before latency and errors do. Alerting on `vllm:gpu_cache_usage_perc > 0.9` gives you a 5-10 minute warning window to scale up before users are affected. Alerting only on latency or errors means you are already in an incident.

---

### DCGM Metrics and the NVIDIA GPU Operator

The NVIDIA GPU Operator on OpenShift deploys the **DCGM (Data Center GPU Manager) exporter** as a DaemonSet on every GPU node. DCGM exposes GPU hardware metrics in Prometheus format:

| Metric | Description | Unit |
|--------|-------------|------|
| `DCGM_FI_DEV_GPU_UTIL` | GPU compute utilization | Percentage (0-100) |
| `DCGM_FI_DEV_FB_USED` | Framebuffer (GPU) memory used | MiB |
| `DCGM_FI_DEV_FB_FREE` | Framebuffer (GPU) memory free | MiB |
| `DCGM_FI_DEV_GPU_TEMP` | GPU die temperature | Celsius |
| `DCGM_FI_DEV_POWER_USAGE` | GPU power consumption | Watts |
| `DCGM_FI_DEV_MEM_COPY_UTIL` | Memory controller utilization | Percentage (0-100) |
| `DCGM_FI_DEV_ENC_UTIL` | Encoder utilization | Percentage (0-100) |
| `DCGM_FI_DEV_DEC_UTIL` | Decoder utilization | Percentage (0-100) |

These metrics are automatically scraped by OpenShift's cluster monitoring Prometheus. They are available in the Thanos Querier alongside your user-workload metrics, which means you can display vLLM application metrics and DCGM hardware metrics on the same dashboard.

On the Developer Sandbox, DCGM metrics may not be available if the sandbox does not expose GPU node metrics to user namespaces. In that case, the GPU panels will show "No data" -- this is expected.

---

### Dashboard-as-Code with ConfigMaps

In L1-M5.3 you learned that OpenShift supports dashboard provisioning via ConfigMaps. This pattern is central to production operations because it enables **dashboard-as-code**:

- Dashboards are stored as JSON inside ConfigMaps
- ConfigMaps live in your Git repository alongside application manifests
- Changes are applied via `oc apply` or GitOps (ArgoCD)
- Dashboard versions are tracked in Git history
- Multiple environments (dev, staging, prod) get the same dashboards

The ConfigMap must include the label `grafana_dashboard: "1"` for Grafana sidecar auto-discovery, and optionally `console.openshift.io/dashboard: "true"` for the OpenShift console monitoring UI.

---

### PrometheusRule and SLO-Based Alerting

A `PrometheusRule` CR defines alerting rules that Prometheus evaluates at a fixed interval. When an expression evaluates to true for longer than the `for` duration, the alert fires and is routed to Alertmanager.

**SLO-based alerting** means you define alerts based on service-level objectives, not arbitrary thresholds. For example:

| SLO | Alert Threshold | Rationale |
|-----|----------------|-----------|
| 99% of requests should have TTFT < 5s | P99 TTFT > 5s for 5 min | Directly encodes the SLO -- if this fires, you are violating it |
| GPU memory should stay below 90% | GPU memory > 90% for 10 min | Leading indicator -- gives time to react before OOM |
| Model error rate should be < 5% | Error rate > 5% for 5 min | Quality gate -- more than 5% failures means something is wrong |
| Bias metrics must stay within bounds | SPD absolute value > 0.1 for 30 min | Regulatory/ethical -- sustained bias violation requires investigation |

**Alert severity levels** follow a standard convention:

- **`info`** -- worth knowing, no action required (e.g., deployment completed)
- **`warning`** -- investigate within the current business day (e.g., cache pressure rising)
- **`critical`** -- requires immediate attention (e.g., error rate exceeding SLO)

Alertmanager routes alerts based on severity labels. In a production setup, `critical` alerts page on-call engineers, `warning` alerts create tickets, and `info` alerts go to a Slack channel.

## Step-by-Step

### Step 1: Verify Prerequisites

Confirm that the monitoring stack is running and that you have metrics flowing from the L1-M5.3 ServiceMonitor:

```bash
# Verify user-workload monitoring
oc get pods -n openshift-user-workload-monitoring

# Verify vLLM ServiceMonitor from L1-M5.3
oc get servicemonitor vllm-metrics -n my-ai-project

# Verify vLLM metrics are being scraped
TOKEN=$(oc whoami -t)
THANOS_URL=$(oc get route thanos-querier -n openshift-monitoring -o jsonpath='{.spec.host}')
curl -sk -H "Authorization: Bearer ${TOKEN}" \
  "https://${THANOS_URL}/api/v1/query?query=vllm:num_requests_running" \
  | python3 -m json.tool | head -20
```

Expected output for the metrics query:

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

If the ServiceMonitor does not exist, go back to L1-M5.3 and deploy it first. The production dashboard depends on metrics being scraped.

### Step 2: Review the Dashboard Architecture

The unified dashboard is organized into four rows, one per observability pillar:

| Row | Title | Panels | Metric Source |
|-----|-------|--------|---------------|
| 1 | **Inference Performance** | Request Rate, TTFT (p50/p90/p99), TPOT (p50/p90/p99), Tokens/sec, KV Cache %, Error Rate | vLLM Prometheus metrics |
| 2 | **GPU Resources** | GPU Utilization, Memory Used vs Total, Temperature, Power Usage | DCGM exporter |
| 3 | **Agent & Pipeline** | Agent Trace Duration (p50/p90/p99), Pipeline Runs by Status, Model Registry Versions | MLflow export, DS Pipelines, Model Registry |
| 4 | **TrustyAI** | Statistical Parity Difference (SPD), Disparate Impact Ratio (DIR), Drift Score | TrustyAI metrics |

The dashboard JSON is stored in a ConfigMap. Review the full manifest:

```bash
cat manifests/grafana-dashboard.yaml
```

Key structural elements in the JSON:

- **`templating.list`** -- defines a `datasource` variable so the dashboard works with any Prometheus data source name
- **Row panels** (`"type": "row"`) -- collapsible section headers that group related panels
- **Stat panels** (`"type": "stat"`) -- single-value KPI displays with color-coded thresholds (green/yellow/red)
- **Time series panels** (`"type": "timeseries"`) -- line charts with percentile breakdowns and legends showing mean/max
- **`refresh: "30s"`** -- auto-refreshes every 30 seconds to match the default Prometheus scrape interval

### Step 3: Apply the Dashboard ConfigMap

```bash
oc apply -f manifests/grafana-dashboard.yaml -n my-ai-project
```

Expected output:

```
configmap/ai-platform-dashboard created
```

Verify the ConfigMap was created with the correct labels:

```bash
oc get configmap ai-platform-dashboard -n my-ai-project \
  -o jsonpath='{.metadata.labels}' | python3 -m json.tool
```

Expected output:

```json
{
    "app": "ai-platform-dashboard",
    "console.openshift.io/dashboard": "true",
    "grafana_dashboard": "1",
    "tutorial-level": "2",
    "tutorial-module": "M5"
}
```

The `grafana_dashboard: "1"` label ensures auto-discovery by the Grafana sidecar. The `console.openshift.io/dashboard: "true"` label makes it visible in the OpenShift console monitoring UI.

### Step 4: Review the Alert Definitions

The PrometheusRule manifest defines seven alerts across four groups. Review the alert structure:

```bash
cat manifests/prometheusrule-alerts.yaml
```

The alerts are organized into groups that correspond to the dashboard rows:

| Group | Alert | Threshold | Severity |
|-------|-------|-----------|----------|
| `ai-platform.inference` | `InferenceLatencyHigh` | P99 TTFT > 5s for 5 min | warning |
| `ai-platform.inference` | `InferenceQueueBacklog` | Queue > 50 requests for 5 min | warning |
| `ai-platform.inference` | `ModelErrorRateHigh` | Error rate > 5% for 5 min | critical |
| `ai-platform.gpu` | `GPUMemoryPressure` | GPU memory > 90% for 10 min | warning |
| `ai-platform.gpu` | `GPUTemperatureWarning` | GPU temp > 80C for 10 min | warning |
| `ai-platform.agents` | `AgentTraceErrorRate` | Agent error rate > 10% for 5 min | warning |
| `ai-platform.fairness` | `BiasMetricViolation` | |SPD| > 0.1 for 30 min | critical |

Note the severity choices:

- **`critical`** for `ModelErrorRateHigh` -- a sustained error rate means users are getting failures, requiring immediate investigation
- **`critical`** for `BiasMetricViolation` -- bias violations may have regulatory implications and need prompt attention
- **`warning`** for resource-related alerts (GPU memory, temperature, queue depth) -- these are leading indicators that give you time to act before users are impacted

### Step 5: Apply the PrometheusRule

```bash
oc apply -f manifests/prometheusrule-alerts.yaml -n my-ai-project
```

Expected output:

```
prometheusrule.monitoring.coreos.com/ai-platform-alerts created
```

Verify the rules are loaded:

```bash
oc get prometheusrules -n my-ai-project
```

Expected output:

```
NAME                  AGE
vllm-alerts           2d     # From L1-M5.3
ai-platform-alerts    5s     # Just created
```

Verify the rule groups:

```bash
oc get prometheusrule ai-platform-alerts -n my-ai-project \
  -o jsonpath='{.spec.groups[*].name}' | tr ' ' '\n'
```

Expected output:

```
ai-platform.inference
ai-platform.gpu
ai-platform.agents
ai-platform.fairness
```

### Step 6: Verify Alert Rules in the Web Console

Navigate to the OpenShift web console to see the alerts:

1. Switch to the **Administrator** perspective
2. Navigate to **Observe > Alerting > Alerting Rules**
3. Filter by namespace: `my-ai-project`
4. You should see both the L1-M5.3 vLLM alerts and the new platform-wide alerts

Alternatively, check alert status via the API:

```bash
TOKEN=$(oc whoami -t)
THANOS_URL=$(oc get route thanos-querier -n openshift-monitoring -o jsonpath='{.spec.host}')

curl -sk -H "Authorization: Bearer ${TOKEN}" \
  "https://${THANOS_URL}/api/v1/rules" \
  | python3 -m json.tool | grep -A2 '"name": "ai-platform'
```

Expected output:

```json
            "name": "ai-platform.inference",
            "file": "/etc/prometheus/rules/prometheus-user-workload-...",
            "rules": [
--
            "name": "ai-platform.gpu",
            "file": "/etc/prometheus/rules/prometheus-user-workload-...",
            "rules": [
--
            "name": "ai-platform.agents",
            "file": "/etc/prometheus/rules/prometheus-user-workload-...",
            "rules": [
--
            "name": "ai-platform.fairness",
            "file": "/etc/prometheus/rules/prometheus-user-workload-...",
            "rules": [
```

### Step 7: Query Metrics from Each Pillar

Test that metrics from each observability pillar are queryable through the OpenShift console. Navigate to **Developer** perspective > **Observe > Metrics** and run these queries:

**Inference Performance:**

```promql
# P99 TTFT over the last 5 minutes
histogram_quantile(0.99, rate(vllm:time_to_first_token_seconds_bucket[5m]))
```

**GPU Resources** (requires NVIDIA GPU Operator with DCGM exporter):

```promql
# GPU utilization per device
DCGM_FI_DEV_GPU_UTIL
```

**Agent Health** (requires MLflow metrics export from L2-M5.1):

```promql
# Agent trace duration P99
histogram_quantile(0.99, rate(mlflow_trace_duration_seconds_bucket[5m]))
```

**TrustyAI** (requires TrustyAI from L2-M5.4):

```promql
# Statistical parity difference
trustyai_spd
```

Some of these metrics may not be present if the corresponding components are not deployed or have not received traffic yet. The dashboard panels will show "No data" for missing metrics -- this is expected and not an error.

### Step 8: Test an Alert (Optional)

To verify the alerting pipeline is working end-to-end, temporarily lower a threshold on a metric you know has data. For example, set the inference queue backlog alert to fire at 0 pending requests:

```bash
oc patch prometheusrule ai-platform-alerts -n my-ai-project --type='json' \
  -p='[{"op": "replace", "path": "/spec/groups/0/rules/1/expr", "value": "sum(vllm:num_requests_waiting) >= 0"}]'
```

Wait 5-6 minutes (the `for: 5m` duration must elapse), then check if the alert is firing:

```bash
curl -sk -H "Authorization: Bearer $(oc whoami -t)" \
  "https://$(oc get route thanos-querier -n openshift-monitoring -o jsonpath='{.spec.host}')/api/v1/alerts" \
  | python3 -m json.tool | grep -A5 "InferenceQueueBacklog"
```

Expected output when the alert is firing:

```json
                "labels": {
                    "alertname": "InferenceQueueBacklog",
                    "severity": "warning",
                    ...
                },
                "state": "firing",
```

Restore the original rule when done:

```bash
oc apply -f manifests/prometheusrule-alerts.yaml -n my-ai-project
```

### Step 9: Understand Alert Routing

When an alert fires, Prometheus sends it to Alertmanager. On OpenShift, Alertmanager is pre-configured and routes alerts based on labels. You can view the current Alertmanager configuration:

```bash
oc get secret alertmanager-main -n openshift-monitoring \
  -o jsonpath='{.data.alertmanager\.yaml}' | base64 -d
```

In a production setup, you would extend Alertmanager to route alerts to external receivers:

| Receiver | Use Case |
|----------|----------|
| PagerDuty | Page on-call for `critical` alerts |
| Slack | Notify a channel for `warning` alerts |
| Email | Send summaries for `info` alerts |
| Webhook | Integrate with incident management (Jira, ServiceNow) |

Configuring Alertmanager receivers is a cluster-admin operation and is beyond the scope of this lesson. The key point is that the `severity` label on your alerts controls how they are routed.

### Step 10: Dashboard GitOps Integration

Because the dashboard is a ConfigMap and the alerts are a PrometheusRule CR, both are standard Kubernetes resources that can be managed through GitOps. If you deployed ArgoCD in L2-M4 (Pipelines), you can include these manifests in your ArgoCD application:

```bash
# Example: include monitoring manifests in a Kustomize overlay
ls manifests/
# grafana-dashboard.yaml
# prometheusrule-alerts.yaml
```

Add them to your Kustomize `kustomization.yaml`:

```yaml
resources:
  - grafana-dashboard.yaml
  - prometheusrule-alerts.yaml
```

This ensures that dashboard changes go through code review, are version-controlled, and are automatically applied when merged. Teams can iterate on dashboards by editing the JSON in Git, creating a PR, and having the updated dashboard deployed via ArgoCD sync.

## Verification

Run through this checklist to confirm everything is working:

1. **Dashboard ConfigMap exists with correct labels:**

```bash
oc get configmap ai-platform-dashboard -n my-ai-project \
  -o jsonpath='{.metadata.labels.grafana_dashboard}'
```

Expected: `1`

2. **PrometheusRule is loaded with all four groups:**

```bash
oc get prometheusrule ai-platform-alerts -n my-ai-project \
  -o jsonpath='{.spec.groups[*].name}'
```

Expected: `ai-platform.inference ai-platform.gpu ai-platform.agents ai-platform.fairness`

3. **Alert count is correct (7 alerts across 4 groups):**

```bash
oc get prometheusrule ai-platform-alerts -n my-ai-project \
  -o jsonpath='{range .spec.groups[*]}{.name}{": "}{range .rules[*]}{.alert}{", "}{end}{"\n"}{end}'
```

Expected output:

```
ai-platform.inference: InferenceLatencyHigh, InferenceQueueBacklog, ModelErrorRateHigh,
ai-platform.gpu: GPUMemoryPressure, GPUTemperatureWarning,
ai-platform.agents: AgentTraceErrorRate,
ai-platform.fairness: BiasMetricViolation,
```

4. **vLLM metrics are still flowing** (sanity check that the L1-M5.3 ServiceMonitor was not disrupted):

```bash
curl -sk -H "Authorization: Bearer $(oc whoami -t)" \
  "https://$(oc get route thanos-querier -n openshift-monitoring -o jsonpath='{.spec.host}')/api/v1/query?query=vllm:num_requests_running" \
  | python3 -c "import sys,json; r=json.load(sys.stdin); print('OK' if r['data']['result'] else 'NO DATA')"
```

Expected: `OK`

5. **Dashboard JSON is valid** (optional sanity check):

```bash
oc get configmap ai-platform-dashboard -n my-ai-project \
  -o jsonpath='{.data.ai-platform-dashboard\.json}' | python3 -m json.tool > /dev/null && echo "Valid JSON"
```

Expected: `Valid JSON`

## Key Takeaways

- Production AI platforms require monitoring across four pillars: inference performance (vLLM), GPU resources (DCGM), agent and pipeline health (MLflow/DS Pipelines), and model fairness (TrustyAI) -- a single-pillar dashboard gives an incomplete picture
- TTFT and TPOT are more meaningful than end-to-end latency for LLM serving because responses are streamed -- users perceive TTFT as responsiveness and TPOT as typing speed
- KV cache utilization (`vllm:gpu_cache_usage_perc`) is a leading indicator of latency and error spikes -- alert on it before it reaches 100% to get a warning window before users are impacted
- Dashboard-as-code via ConfigMaps enables GitOps workflows -- dashboards are version-controlled, reviewed in PRs, and deployed alongside application manifests
- SLO-based alerting encodes your service-level objectives directly into PrometheusRule expressions -- this is more actionable than arbitrary thresholds because each alert corresponds to a concrete user impact
- Alert severity labels (`warning` vs `critical`) drive Alertmanager routing -- use `critical` for user-impacting issues that need immediate attention and `warning` for leading indicators that give you time to act
- DCGM metrics from the NVIDIA GPU Operator are automatically available in the OpenShift monitoring stack -- no additional ServiceMonitor is needed for GPU hardware metrics

## Cleanup

```bash
# Remove the production dashboard and alert resources
oc delete configmap ai-platform-dashboard -n my-ai-project
oc delete prometheusrule ai-platform-alerts -n my-ai-project

# Verify cleanup
oc get configmap,prometheusrule -l tutorial-module=M5 -n my-ai-project
```

The vLLM ServiceMonitor and L1-M5.3 alert rules are left in place -- they were created in a prior lesson.

## Next Steps

This lesson completes Module 5 (Observability). You now have a comprehensive monitoring stack for your AI platform: experiment tracking (MLflow), distributed tracing (OpenTelemetry), model fairness monitoring (TrustyAI), and unified production dashboards with SLO-based alerting.

In the next module, [L2-M6.1 -- KubeRay](../../M6_distributed/1_kuberay/), you will explore distributed computing on OpenShift AI using KubeRay to run Ray clusters for scalable inference and training workloads.
