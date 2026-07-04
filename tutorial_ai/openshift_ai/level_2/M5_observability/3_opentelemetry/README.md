# L2-M5.3 -- OpenTelemetry for Inference

**Level:** Practitioner
**Duration:** 45 min


## Overview

MLflow tracing (covered in [L2-M5.2](../2_agent_tracing/)) captures ML-specific semantics -- tool calls, retrieval steps, LLM invocations. But when an inference request travels from a client through an OpenShift Route, into KServe, and down to vLLM, you need infrastructure-level distributed tracing to see the full picture: network latency, queue wait time, token generation duration, and every hop in between. OpenTelemetry (OTel) is the CNCF standard for this. vLLM ships with built-in OTel instrumentation, and OpenShift provides operator-managed OTel Collectors. This lesson deploys the tracing pipeline -- Collector and Jaeger -- configures vLLM to emit traces, and sends instrumented inference requests so you can visualize the entire request path end to end.


## Prerequisites

- Completed: [L2-M5.2 -- Agent Tracing with MLflow](../2_agent_tracing/) (concepts of tracing, spans, and trace context)
- A model serving endpoint running with KServe/vLLM (from Level 1 Module 2 deployment lessons)
- OpenShift cluster with `oc` CLI authenticated
- Basic understanding of distributed tracing (spans, traces, context propagation)
- Python 3.11+ available (for the tracing client script)


## Concepts

### OTel vs MLflow Tracing -- Complementary, Not Competing

A common source of confusion: MLflow has tracing, and now we are adding OpenTelemetry tracing. Are they redundant? No -- they operate at different layers and answer different questions:

| Aspect | MLflow Tracing | OpenTelemetry |
|--------|---------------|---------------|
| **Scope** | ML workflow semantics (agent steps, tool calls, retrieval) | Infrastructure and network (HTTP requests, queue latency, service hops) |
| **Instrumentation** | SDK-level, in your Python code | Automatic (vLLM built-in) + manual (client SDK) |
| **Storage** | MLflow tracking server | Jaeger, Tempo, or any OTel-compatible backend |
| **Audience** | Data scientists, ML engineers | Platform engineers, SREs |
| **Key question** | "Why did the agent choose this tool?" | "Where did the 2-second latency spike come from?" |

In production, you use both. MLflow traces tell you what the model and agent did. OTel traces tell you how fast the infrastructure delivered it and where bottlenecks occurred. When you propagate trace context (W3C `traceparent` headers) end to end, you can correlate the two -- jumping from an MLflow agent trace to the corresponding OTel infrastructure trace in Jaeger.


### The OpenTelemetry Collector

The OTel Collector is the central component of any OTel deployment. It is a vendor-agnostic telemetry pipeline with three stages:

```
  +-----------+      +------------+      +-----------+
  | Receivers | ---> | Processors | ---> | Exporters |
  +-----------+      +------------+      +-----------+
```

- **Receivers** accept telemetry data. The OTLP receiver (both gRPC on port 4317 and HTTP on port 4318) is the standard choice -- every OTel SDK speaks OTLP natively.
- **Processors** transform data in flight. The `batch` processor groups spans into batches for efficient export. The `memory_limiter` processor prevents the collector from consuming unbounded memory.
- **Exporters** send data to backends. We export to Jaeger for trace visualization. In production, you might also export to Prometheus (for metrics) or Loki (for logs).

The Collector's configuration is a YAML file mounted as a ConfigMap. You define which receivers, processors, and exporters to use, then wire them into named pipelines.

Our collector configuration (`manifests/otel-collector.yaml`) defines a single `traces` pipeline:

```
receivers: [otlp]  --->  processors: [memory_limiter, batch]  --->  exporters: [otlphttp/jaeger, debug]
```

The `debug` exporter also logs spans to the collector's stdout, which is useful during setup.


### Trace Context Propagation

A distributed trace is a tree of spans that share a single trace ID. For the trace to span multiple services -- client, Route, KServe, vLLM -- each service must propagate the trace context to the next hop. The W3C Trace Context standard defines two HTTP headers for this:

```
traceparent: 00-<trace-id>-<span-id>-<trace-flags>
tracestate:  <vendor-specific key-value pairs>
```

When the client sends an inference request, the OTel SDK injects the `traceparent` header. vLLM's built-in OTel instrumentation reads this header and creates child spans under the same trace ID. The result is a single trace in Jaeger that shows every span from client to model and back.

If you do not propagate the context, vLLM still creates traces -- but they are disconnected root traces with their own trace IDs, making correlation difficult.


### vLLM's Built-in OTel Instrumentation

vLLM has native OpenTelemetry support. When you set the `OTEL_EXPORTER_OTLP_ENDPOINT` environment variable on the vLLM container, it automatically:

1. Creates spans for each inference request
2. Records attributes like model name, prompt token count, completion token count, and generation parameters
3. Tracks internal timings: queue wait time, prefill duration, decode duration
4. Propagates trace context from incoming requests (W3C `traceparent`)
5. Exports spans via OTLP to the configured collector endpoint

The key environment variables are:

| Variable | Purpose | Example Value |
|----------|---------|---------------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTel Collector endpoint | `http://otel-collector:4317` |
| `OTEL_SERVICE_NAME` | Service name in traces | `vllm-inference` |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | Export protocol | `grpc` |

No code changes to vLLM are needed -- tracing activates purely through environment variables.


### Jaeger for Trace Visualization

Jaeger is an open-source distributed tracing platform originally developed at Uber. It provides:

- **Trace search** -- find traces by service name, operation name, tags, or time range
- **Trace detail view** -- a Gantt-chart-style timeline showing every span, its duration, and its relationship to other spans
- **Trace comparison** -- overlay two traces to identify latency differences
- **Service dependency graph** -- auto-generated from trace data, showing how services communicate

In this lesson we deploy Jaeger in "all-in-one" mode (in-memory storage) for simplicity. In production, you would use Jaeger with persistent storage (Elasticsearch or Cassandra) or switch to a managed backend like Red Hat distributed tracing (based on Tempo).


## Step-by-Step

### Step 1: Create the Project Namespace

Create a dedicated namespace for the tracing infrastructure:

```bash
oc new-project otel-tracing
```

Add tutorial labels for easy cleanup:

```bash
oc label namespace otel-tracing tutorial-level=2 tutorial-module=M5
```


### Step 2: Deploy Jaeger

Deploy the Jaeger all-in-one instance. This provides both the trace storage backend and the web UI for visualization.

Review the manifest:

```yaml
# manifests/jaeger.yaml (key sections)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: jaeger
  labels:
    app: jaeger
    tutorial-level: "2"
    tutorial-module: "M5"
spec:
  replicas: 1
  ...
  template:
    spec:
      containers:
        - name: jaeger
          image: quay.io/jaegertracing/all-in-one:1.62
          ports:
            - containerPort: 16686    # Jaeger UI
              name: ui
            - containerPort: 14268    # Collector HTTP (legacy)
              name: collector-http
            - containerPort: 4317     # OTLP gRPC receiver
              name: otlp-grpc
            - containerPort: 4318     # OTLP HTTP receiver
              name: otlp-http
          env:
            - name: COLLECTOR_OTLP_ENABLED
              value: "true"
```

The `COLLECTOR_OTLP_ENABLED=true` environment variable enables the native OTLP receiver in Jaeger, so the OTel Collector can export traces using the OTLP protocol rather than the legacy Jaeger protocol.

The manifest also includes a Service (exposing all four ports) and an OpenShift Route for the Jaeger UI with edge TLS termination.

Apply it:

```bash
oc apply -f manifests/jaeger.yaml
```

Expected output:

```
deployment.apps/jaeger created
service/jaeger created
route.route.openshift.io/jaeger-ui created
```

Wait for the pod to be ready:

```bash
oc get pods -l app=jaeger -w
```

Expected output:

```
NAME                      READY   STATUS    RESTARTS   AGE
jaeger-6d4f8b7c9a-k2m5n   1/1     Running   0          30s
```

Press `Ctrl+C` to stop watching.


### Step 3: Deploy the OpenTelemetry Collector

The OTel Collector sits between the trace producers (vLLM, client scripts) and the trace backend (Jaeger). It receives OTLP spans, batches them, and forwards them to Jaeger.

Review the collector configuration in the ConfigMap:

```yaml
# manifests/otel-collector.yaml -- ConfigMap section
data:
  otel-collector-config.yaml: |
    receivers:
      otlp:
        protocols:
          grpc:
            endpoint: 0.0.0.0:4317
          http:
            endpoint: 0.0.0.0:4318

    processors:
      batch:
        timeout: 5s
        send_batch_size: 512
        send_batch_max_size: 1024
      memory_limiter:
        check_interval: 5s
        limit_mib: 256
        spike_limit_mib: 64

    exporters:
      otlphttp/jaeger:
        endpoint: http://jaeger:4318
        tls:
          insecure: true
      debug:
        verbosity: basic

    service:
      pipelines:
        traces:
          receivers: [otlp]
          processors: [memory_limiter, batch]
          exporters: [otlphttp/jaeger, debug]
```

Key points in this configuration:

- **Receivers:** OTLP on both gRPC (4317) and HTTP (4318) -- vLLM uses gRPC by default, the Python client can use either
- **Processors:** `memory_limiter` runs first to protect the collector from OOM; `batch` groups spans for efficient export
- **Exporters:** `otlphttp/jaeger` sends spans to Jaeger's native OTLP HTTP endpoint; `debug` logs spans to stdout for troubleshooting
- **Pipeline:** a single `traces` pipeline wires everything together

Apply the collector manifests:

```bash
oc apply -f manifests/otel-collector.yaml
```

Expected output:

```
configmap/otel-collector-config created
deployment.apps/otel-collector created
service/otel-collector created
```

Wait for the collector pod:

```bash
oc get pods -l app=otel-collector -w
```

Expected output:

```
NAME                              READY   STATUS    RESTARTS   AGE
otel-collector-7f9a8b6c5d-x3n7p   1/1     Running   0          25s
```

Press `Ctrl+C` to stop watching.

Verify the collector is receiving data by checking its logs:

```bash
OC_POD=$(oc get pods -l app=otel-collector -o jsonpath='{.items[0].metadata.name}')
oc logs "$OC_POD" --tail=10
```

You should see startup messages indicating the OTLP receivers are listening:

```
...
2024-01-15T10:30:00.000Z  info  otlpreceiver@v0.115.0/otlp.go:112  Starting GRPC server  {"kind": "receiver", "name": "otlp", "endpoint": "0.0.0.0:4317"}
2024-01-15T10:30:00.000Z  info  otlpreceiver@v0.115.0/otlp.go:169  Starting HTTP server  {"kind": "receiver", "name": "otlp", "endpoint": "0.0.0.0:4318"}
...
```


### Step 4: Access the Jaeger UI

Get the Jaeger UI Route URL:

```bash
JAEGER_URL="https://$(oc get route jaeger-ui -o jsonpath='{.spec.host}')"
echo "Jaeger UI: $JAEGER_URL"
```

Open the URL in your browser. You will see the Jaeger search page with a "Service" dropdown. It will be empty initially -- services appear once traces are received.


### Step 5: Configure vLLM to Emit Traces

To enable OTel tracing on your existing vLLM deployment, you need to set environment variables on the vLLM container. The approach depends on how vLLM is deployed.

**Option A: vLLM deployed via InferenceService (KServe)**

If your model is served via a KServe InferenceService, patch the predictor container with OTel environment variables:

```bash
oc patch inferenceservice <your-isvc-name> \
  -n <your-model-namespace> \
  --type merge \
  -p '{
    "spec": {
      "predictor": {
        "containers": [{
          "name": "kserve-container",
          "env": [
            {"name": "OTEL_EXPORTER_OTLP_ENDPOINT", "value": "http://otel-collector.otel-tracing.svc.cluster.local:4317"},
            {"name": "OTEL_SERVICE_NAME", "value": "vllm-inference"},
            {"name": "OTEL_EXPORTER_OTLP_PROTOCOL", "value": "grpc"}
          ]
        }]
      }
    }
  }'
```

Replace `<your-isvc-name>` with your InferenceService name and `<your-model-namespace>` with the namespace where the model is deployed.

**Option B: vLLM deployed as a standalone Deployment**

If vLLM runs as a plain Deployment, patch the container environment:

```bash
oc set env deployment/<your-vllm-deployment> \
  -n <your-model-namespace> \
  OTEL_EXPORTER_OTLP_ENDPOINT="http://otel-collector.otel-tracing.svc.cluster.local:4317" \
  OTEL_SERVICE_NAME="vllm-inference" \
  OTEL_EXPORTER_OTLP_PROTOCOL="grpc"
```

In both cases, the OTel Collector endpoint uses the cross-namespace Service DNS name: `otel-collector.otel-tracing.svc.cluster.local:4317`. This works because Kubernetes Services are accessible across namespaces by default.

After patching, the vLLM pod will restart. Wait for it to be ready:

```bash
oc get pods -n <your-model-namespace> -l <your-model-label> -w
```

Verify OTel is active by checking the vLLM logs for OTel initialization messages:

```bash
VLLM_POD=$(oc get pods -n <your-model-namespace> -l <your-model-label> -o jsonpath='{.items[0].metadata.name}')
oc logs "$VLLM_POD" -n <your-model-namespace> | grep -i "otel\|opentelemetry\|tracing"
```

You should see a line indicating the OTLP exporter is configured.


### Step 6: Install Python Dependencies

Install the OpenTelemetry SDK and exporter packages needed by the tracing client script:

```bash
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc requests
```


### Step 7: Send Traced Inference Requests

The `scripts/trace_inference.py` script demonstrates client-side OTel instrumentation. It:

1. Configures a `TracerProvider` with an OTLP gRPC exporter pointing at the collector
2. Creates a root span `inference-request` with three child spans: `prepare-request`, `call-inference`, `parse-response`
3. Injects the W3C `traceparent` header into the HTTP request so vLLM can continue the trace
4. Prints the trace ID so you can look it up in Jaeger

Review the key section of the script -- the trace context injection:

```python
# Inject W3C trace context into HTTP headers so vLLM can
# continue the same trace on the server side
headers = {"Content-Type": "application/json"}
inject(headers)
```

The `inject()` call from `opentelemetry.propagate` adds the `traceparent` header to the outgoing request. When vLLM receives this header, it creates its spans as children of the client's span, producing one unified trace.

Set up the environment variables and run the script. If the OTel Collector is running in your cluster and you are running the script from your workstation, you need to port-forward the collector:

```bash
oc port-forward svc/otel-collector 4317:4317 &
PF_PID=$!
```

Then set the environment variables:

```bash
export INFERENCE_URL="https://$(oc get route <your-model-route> -n <your-model-namespace> -o jsonpath='{.spec.host}')"
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
export MODEL_NAME="<your-model-name>"
```

Replace the placeholder values with your actual model route and model name.

Run the script:

```bash
python3 scripts/trace_inference.py
```

Expected output:

```
Configuring OpenTelemetry...
  OTLP endpoint: http://localhost:4317
  Inference URL: https://my-model-my-project.apps.cluster.example.com
  Model:         granite-3.3-8b-instruct

--- Request 1 of 1 ---
Prompt: What are the three main benefits of using OpenTelemetry for observability?

Response: The three main benefits of OpenTelemetry are: 1) Vendor-neutral ...
  ... (truncated)

  Trace ID:    a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6
  Latency:     1523.45 ms
  Tokens used: 187
  Model:       granite-3.3-8b-instruct

All spans exported. Open Jaeger UI to view traces.
Search for service 'inference-client' to find the traces above.
```

Note the **Trace ID** -- you will use it to find this exact trace in Jaeger.

Run a batch of requests to generate comparison data:

```bash
python3 scripts/trace_inference.py --requests 5 --prompt "Summarize the benefits of container orchestration."
```


### Step 8: Explore Traces in Jaeger

Open the Jaeger UI (the URL from Step 4). You should now see services in the "Service" dropdown:

- **inference-client** -- spans from the Python client script
- **vllm-inference** -- spans from vLLM's built-in instrumentation (if vLLM OTel was configured in Step 5)

To find a specific trace:

1. Select `inference-client` from the Service dropdown
2. Click "Find Traces"
3. You will see a list of traces, each with a trace ID, duration, and span count

Click on a trace to open the detail view. You will see a timeline showing:

```
inference-request                   [========================]  1523 ms
  prepare-request                   [=]                            2 ms
  call-inference                    [=====================]     1518 ms
  parse-response                    [=]                            3 ms
```

If vLLM OTel is configured, the `call-inference` span will have child spans from vLLM showing internal processing:

```
inference-request                   [========================]  1523 ms
  prepare-request                   [=]                            2 ms
  call-inference                    [=====================]     1518 ms
    vllm.generate                   [====================]      1510 ms
      vllm.prefill                  [====]                       120 ms
      vllm.decode                   [===============]           1390 ms
  parse-response                    [=]                            3 ms
```

Click on any span to see its attributes:

- **inference-request:** `model.name`, `inference.endpoint`, `tokens.total`, `inference.latency_ms`
- **call-inference:** `http.method`, `http.url`, `http.status_code`
- **parse-response:** `response.length`, `tokens.prompt`, `tokens.completion`

Use the **Compare** feature to overlay two traces and identify why one request was slower than another -- was it queue wait time? Decode time? Network latency?


### Step 9: Correlate OTel and MLflow Traces

If you have MLflow tracing enabled from [L2-M5.2](../2_agent_tracing/), you can correlate OTel infrastructure traces with MLflow agent traces. The key is trace context propagation -- passing the same trace ID through both systems.

The approach:

1. Start an OTel trace in your client code (as in `trace_inference.py`)
2. Extract the trace ID
3. Pass the trace ID as a tag in your MLflow run
4. In Jaeger, find the infrastructure trace by trace ID
5. In MLflow, search for the run with that trace ID tag

Example code for correlation:

```python
import mlflow
from opentelemetry import trace

# Get the current OTel trace ID
span = trace.get_current_span()
trace_id = format(span.get_span_context().trace_id, "032x")

# Log it as an MLflow tag for cross-referencing
mlflow.set_tag("otel.trace_id", trace_id)
```

This pattern gives you two views of the same request: the ML-semantic view in MLflow (what tools were called, what the agent decided) and the infrastructure view in Jaeger (how long each network hop took, where latency spiked).


### Step 10: Clean Up Port Forwarding

If you started a port-forward in Step 7, stop it:

```bash
kill $PF_PID 2>/dev/null
```


## Verification

Run through this checklist to confirm the lesson is complete:

1. **Jaeger pod is running:**

```bash
oc get pods -l app=jaeger -n otel-tracing --no-headers | grep Running
```

2. **OTel Collector pod is running:**

```bash
oc get pods -l app=otel-collector -n otel-tracing --no-headers | grep Running
```

3. **Jaeger UI is accessible:**

```bash
JAEGER_URL="https://$(oc get route jaeger-ui -n otel-tracing -o jsonpath='{.spec.host}')"
curl -sk -o /dev/null -w "%{http_code}" "$JAEGER_URL"
```

Expected: `200`

4. **Traces appear in Jaeger:**

```bash
curl -sk "$JAEGER_URL/api/services" | python3 -c "
import json, sys
data = json.load(sys.stdin)
services = data.get('data', [])
print(f'Services with traces: {len(services)}')
for svc in services:
    print(f'  - {svc}')
"
```

Expected output (after running the tracing script):

```
Services with traces: 2
  - inference-client
  - vllm-inference
```

If vLLM OTel was not configured, only `inference-client` will appear.

5. **OTel Collector received spans:**

```bash
OC_POD=$(oc get pods -l app=otel-collector -n otel-tracing -o jsonpath='{.items[0].metadata.name}')
oc logs "$OC_POD" -n otel-tracing | grep -c "TracesExporter"
```

A non-zero count confirms the collector processed and exported spans.

| Check | How to verify |
|-------|---------------|
| Jaeger running | `oc get pods -l app=jaeger -n otel-tracing` shows `1/1 Running` |
| OTel Collector running | `oc get pods -l app=otel-collector -n otel-tracing` shows `1/1 Running` |
| Jaeger UI accessible | Route URL returns HTTP 200 |
| Traces visible | Jaeger API `/api/services` lists `inference-client` |
| vLLM traces (optional) | Jaeger API `/api/services` lists `vllm-inference` |


## Key Takeaways

- **OTel and MLflow tracing are complementary** -- MLflow captures ML-specific semantics (agent reasoning, tool calls), while OTel captures infrastructure-level distributed tracing (network latency, queue times, service hops). Use both in production for full observability.
- **The OTel Collector is a telemetry pipeline** -- it receives spans via OTLP, processes them (batching, memory limiting), and exports them to backends like Jaeger. A single ConfigMap defines the entire pipeline configuration.
- **vLLM has built-in OTel support** -- set `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_SERVICE_NAME` as environment variables on the vLLM container, and it automatically emits spans for every inference request with detailed timing attributes. No code changes required.
- **W3C trace context propagation** (`traceparent` header) is what makes distributed tracing work -- without it, client traces and server traces are disconnected. The OTel SDK's `inject()` function handles this automatically.
- **Jaeger provides the visualization layer** -- search by service, filter by tags, compare traces side by side to identify latency regressions or bottlenecks in the inference path.
- **Cross-referencing OTel and MLflow traces** -- by logging the OTel trace ID as an MLflow tag, you can jump between the infrastructure view (Jaeger) and the ML view (MLflow) for the same request.


## Cleanup

Remove the tracing infrastructure:

```bash
oc delete -f manifests/otel-collector.yaml
oc delete -f manifests/jaeger.yaml
oc delete project otel-tracing
```

If you patched a vLLM deployment or InferenceService with OTel environment variables (Step 5), remove them:

```bash
oc set env deployment/<your-vllm-deployment> \
  -n <your-model-namespace> \
  OTEL_EXPORTER_OTLP_ENDPOINT- \
  OTEL_SERVICE_NAME- \
  OTEL_EXPORTER_OTLP_PROTOCOL-
```

> **Note:** If you are continuing to [L2-M5.4 -- TrustyAI Model Monitoring](../4_trustyai_monitoring/), you may want to keep the OTel Collector running -- TrustyAI can export metrics through it.


## Next Steps

In the next lesson, [L2-M5.4 -- TrustyAI Model Monitoring](../4_trustyai_monitoring/), you will deploy TrustyAI to monitor model behavior in production -- tracking fairness metrics, detecting data drift, and generating explainability reports for inference decisions.
