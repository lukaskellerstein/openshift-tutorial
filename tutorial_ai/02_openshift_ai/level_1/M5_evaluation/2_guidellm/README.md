# L1-M5.2 -- GuideLLM -- Inference Performance Benchmarking

**Level:** Foundations
**Duration:** 30 min

## Overview

You deployed a model in M3 and evaluated its quality with LMEvalJob in M5.1. But quality alone does not tell you whether the endpoint can handle production traffic. GuideLLM is an open-source benchmarking tool from Neural Magic (part of the vLLM ecosystem) that measures inference serving performance -- time to first token, inter-token latency, end-to-end latency, and throughput. In this lesson you will run GuideLLM against the deployed Gemma-4-E4B endpoint and learn to interpret the results.

## Prerequisites

- Completed: L1-M3 (Model Serving -- Gemma-4-E4B deployed and accessible)
- Completed: L1-M5.1 (LMEvalJob -- model quality evaluation)
- OpenShift AI cluster with the `gemma-model` project
- The `gemma-4-e4b` InferenceService is running and healthy

Verify the model endpoint is ready before proceeding:

```bash
oc get inferenceservice gemma-4-e4b -n gemma-model
```

Expected output -- the `READY` column should show `True`:

```
NAME           URL   READY   ...
gemma-4-e4b    ...   True    ...
```

## K8s Context

In vanilla Kubernetes, benchmarking an LLM endpoint means installing a tool on your workstation, pointing it at the service, and running tests manually. You might use `curl` in a loop, `wrk`, `hey`, or a custom script. The challenge is that your local machine introduces network variability -- you are measuring round-trip latency through the cluster ingress, not the actual inference performance.

A better approach is to run the benchmark client inside the cluster as a Kubernetes Job. The client pod sits on the same network as the model server, eliminating external network noise. The Job object handles lifecycle management -- it runs once, captures output in pod logs, and reports completion status. This is the approach we take with GuideLLM.

## Concepts

### What Is GuideLLM?

GuideLLM is a benchmarking tool purpose-built for LLM inference endpoints. Unlike generic HTTP benchmarkers, GuideLLM understands the structure of LLM requests and responses. It sends prompts to an OpenAI-compatible `/v1/completions` or `/v1/chat/completions` endpoint, streams the response tokens, and measures timing at each stage of generation.

GuideLLM is maintained as part of the vLLM ecosystem and is available as a container image at `ghcr.io/neuralmagic/guidellm:latest`.

### Key Metrics

GuideLLM measures the metrics that matter for LLM serving:

| Metric | What It Measures | Why It Matters |
|--------|-----------------|----------------|
| **TTFT** (Time To First Token) | Latency from request sent to first token received | Perceived responsiveness -- users notice this delay |
| **ITL** (Inter-Token Latency) | Time between successive output tokens | Streaming smoothness -- affects the "typing" feel |
| **E2E Latency** | Total time from request to final token | Overall request duration -- drives timeout settings |
| **Throughput** | Output tokens per second across all requests | Capacity -- how many users can the endpoint serve |
| **Request Rate** | Successful requests per second | Reliability under load |

### Load Profiles

GuideLLM supports several load generation strategies:

- **Synchronous** (`--rate synchronous`): Sends one request at a time, waits for completion. Measures baseline single-request performance.
- **Constant rate** (`--rate 2.0`): Sends requests at a fixed rate (e.g., 2 requests/second). Simulates steady-state traffic.
- **Sweep** (`--rate sweep`): Gradually increases load from low to high. Reveals the point where latency degrades and throughput saturates. This is the most informative mode for capacity planning.

### SLO Compliance

Service Level Objectives (SLOs) define acceptable performance thresholds. Common LLM serving SLOs include:

- TTFT p95 < 500ms (95th percentile of time to first token under 500 milliseconds)
- ITL p99 < 100ms (99th percentile of inter-token latency under 100 milliseconds)
- E2E p95 < 10s (for typical prompt/response sizes)

GuideLLM reports percentile distributions (p50, p90, p95, p99) so you can directly compare against your SLOs.

## Step-by-Step

### Step 1: Confirm the Model Endpoint

First, verify the model endpoint is accessible from within the cluster. The Gemma-4-E4B InferenceService deployed in M3 exposes an OpenAI-compatible API on port 8080.

Check the InferenceService status:

```bash
oc get inferenceservice gemma-4-e4b -n gemma-model -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
```

Expected output:

```
True
```

Test the endpoint from within the cluster using a temporary pod:

```bash
oc run curl-test --rm -it --restart=Never \
  --image=registry.access.redhat.com/ubi9/ubi-minimal:latest \
  -n gemma-model \
  -- curl -s http://gemma-4-e4b-predictor.gemma-model.svc.cluster.local:8080/v1/models
```

Expected output (a JSON listing the model):

```json
{
  "object": "list",
  "data": [
    {
      "id": "gemma-4-e4b",
      "object": "model",
      ...
    }
  ]
}
```

If the endpoint is not responding, wait for the model to finish loading. vLLM can take several minutes to load model weights into GPU memory.

### Step 2: Review the GuideLLM Job Manifest

Examine the Job manifest that will run the benchmark:

```yaml
# manifests/guidellm-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: guidellm-benchmark
  namespace: gemma-model
  labels:
    app: guidellm-benchmark
    tutorial-level: "1"
    tutorial-module: "M5"
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 3600
  template:
    metadata:
      labels:
        app: guidellm-benchmark
    spec:
      restartPolicy: Never
      containers:
        - name: guidellm
          image: ghcr.io/neuralmagic/guidellm:latest
          command:
            - "guidellm"
            - "benchmark"
            - "--target"
            - "http://gemma-4-e4b-predictor.gemma-model.svc.cluster.local:8080/v1"
            - "--model"
            - "gemma-4-e4b"
            - "--rate"
            - "sweep"
            - "--max-seconds"
            - "90"
            - "--max-requests"
            - "50"
          resources:
            requests:
              cpu: "1"
              memory: 2Gi
            limits:
              cpu: "2"
              memory: 4Gi
```

Key configuration choices:

- **`--target`**: Points to the internal cluster service URL of the vLLM server. Since the benchmark pod runs in the same namespace, this eliminates external network latency from measurements.
- **`--model`**: The served model name (`gemma-4-e4b`), matching the `--served-model-name` argument in the ServingRuntime.
- **`--rate sweep`**: Runs multiple rounds at increasing request rates to find the throughput ceiling.
- **`--max-seconds 90`**: Caps each rate level at 90 seconds. This keeps the total benchmark time reasonable while collecting enough data for stable percentiles.
- **`--max-requests 50`**: Limits the total number of requests per rate level, preventing runaway benchmarks on slower endpoints.
- **`backoffLimit: 0`**: Do not retry on failure -- benchmark failures should be investigated, not retried.
- **`ttlSecondsAfterFinished: 3600`**: Automatically clean up the completed Job after 1 hour.
- **`restartPolicy: Never`**: The benchmark should run exactly once.

### Step 3: Run the Benchmark

Apply the Job manifest:

```bash
oc apply -f manifests/guidellm-job.yaml
```

Expected output:

```
job.batch/guidellm-benchmark created
```

Monitor the Job status:

```bash
oc get job guidellm-benchmark -n gemma-model -w
```

The Job will transition through these states:

```
NAME                 STATUS    COMPLETIONS   DURATION   AGE
guidellm-benchmark   Running   0/1           5s         5s
guidellm-benchmark   Running   0/1           30s        30s
...
guidellm-benchmark   Complete  1/1           3m45s      3m45s
```

The benchmark typically takes 3-6 minutes depending on the model's inference speed and the sweep range.

### Step 4: Follow the Benchmark in Real Time

While the benchmark is running, you can follow the output in real time:

```bash
oc logs -f job/guidellm-benchmark -n gemma-model
```

You will see GuideLLM's progress output, including:

```
GuideLLM Benchmark
==================
Target: http://gemma-4-e4b-predictor.gemma-model.svc.cluster.local:8080/v1
Model: gemma-4-e4b
Rate: sweep

Running benchmark at rate: synchronous
  Completed 10/50 requests...
  Completed 20/50 requests...
  ...

Running benchmark at rate: 1.0 req/s
  Completed 10/50 requests...
  ...
```

### Step 5: Retrieve and Interpret the Results

Once the Job completes, retrieve the full benchmark output:

```bash
oc logs job/guidellm-benchmark -n gemma-model
```

The output contains a results summary for each rate level. Here is how to read the key sections:

**Synchronous (single request) results:**

```
Rate: synchronous
  Requests completed: 50
  Request throughput: X.XX req/s
  Output token throughput: XX.XX tokens/s

  TTFT (Time to First Token):
    p50: XXXms  p90: XXXms  p95: XXXms  p99: XXXms

  ITL (Inter-Token Latency):
    p50: XXms   p90: XXms   p95: XXms   p99: XXms

  E2E Latency:
    p50: X.XXs  p90: X.XXs  p95: X.XXs  p99: X.XXs
```

**How to interpret these numbers:**

1. **TTFT p50 and p95**: The median and 95th percentile time to first token. For interactive applications (chatbots), aim for p95 under 500ms. For batch processing, this matters less.

2. **ITL p50 and p99**: Inter-token latency. For smooth streaming, p99 should stay under 100ms. Spikes here indicate GPU contention or KV cache pressure.

3. **E2E Latency**: Total request time. Depends heavily on output length. Compare across rate levels to see how it degrades under load.

4. **Output token throughput**: The primary capacity metric. Compare the synchronous throughput (maximum per-request speed) against loaded throughput (sustainable rate with concurrent requests).

**Sweep results** show how performance degrades as load increases:

```
Rate: 0.5 req/s  -> TTFT p95: 200ms, throughput: 45 tokens/s
Rate: 1.0 req/s  -> TTFT p95: 250ms, throughput: 80 tokens/s
Rate: 2.0 req/s  -> TTFT p95: 400ms, throughput: 120 tokens/s
Rate: 4.0 req/s  -> TTFT p95: 1200ms, throughput: 140 tokens/s  <-- degradation
```

The sweet spot is the highest rate where latency percentiles still meet your SLOs.

### Step 6: Save the Results

Save the benchmark output to a local file for later analysis or comparison:

```bash
oc logs job/guidellm-benchmark -n gemma-model > guidellm-results.txt
```

This is useful for:
- Comparing performance before and after configuration changes (e.g., adjusting `--max-model-len` or `--gpu-memory-utilization`)
- Documenting baseline performance for capacity planning
- Sharing results with the team

### Step 7: Run a Targeted Benchmark (Optional)

If the sweep identified a specific rate of interest, you can run a focused constant-rate benchmark. Delete the previous Job first (Job names must be unique):

```bash
oc delete job guidellm-benchmark -n gemma-model
```

Edit the manifest to change the rate from `sweep` to a specific value (e.g., `2.0` requests per second) and increase `--max-seconds` for more stable measurements:

```bash
oc apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: guidellm-benchmark
  namespace: gemma-model
  labels:
    app: guidellm-benchmark
    tutorial-level: "1"
    tutorial-module: "M5"
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 3600
  template:
    metadata:
      labels:
        app: guidellm-benchmark
    spec:
      restartPolicy: Never
      containers:
        - name: guidellm
          image: ghcr.io/neuralmagic/guidellm:latest
          command:
            - "guidellm"
            - "benchmark"
            - "--target"
            - "http://gemma-4-e4b-predictor.gemma-model.svc.cluster.local:8080/v1"
            - "--model"
            - "gemma-4-e4b"
            - "--rate"
            - "2.0"
            - "--max-seconds"
            - "120"
            - "--max-requests"
            - "100"
          resources:
            requests:
              cpu: "1"
              memory: 2Gi
            limits:
              cpu: "2"
              memory: 4Gi
EOF
```

Follow the logs and retrieve results as in Steps 4-6.

## Verification

Confirm the benchmark completed successfully:

```bash
oc get job guidellm-benchmark -n gemma-model \
  -o jsonpath='{.status.conditions[?(@.type=="Complete")].status}'
```

Expected output:

```
True
```

Verify the logs contain benchmark results:

```bash
oc logs job/guidellm-benchmark -n gemma-model | grep -i "throughput"
```

You should see one or more lines reporting token throughput values. If the Job failed, check the pod events:

```bash
oc describe job guidellm-benchmark -n gemma-model
oc logs job/guidellm-benchmark -n gemma-model
```

Common failure reasons:
- **Connection refused**: The model endpoint is not ready. Wait for the InferenceService to become `Ready`.
- **Model not found**: The `--model` argument does not match the served model name. Check with `curl .../v1/models`.
- **OOMKilled**: The benchmark client ran out of memory. Increase the memory limit in the Job spec.

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Running benchmark | Same -- standard Job resource | Same -- `oc apply` works identically to `kubectl apply` |
| Model endpoint URL | Depends on how you deployed the model | KServe InferenceService creates a predictable `<name>-predictor.<namespace>.svc.cluster.local` service |
| Monitoring Job status | `kubectl get job` | `oc get job` (identical) |
| Viewing logs | `kubectl logs job/<name>` | `oc logs job/<name>` (identical), also visible in Web Console |
| Security context | May need to set `securityContext` | SCC `restricted-v2` works fine for the GuideLLM client -- no root needed |
| GPU access | Requires manual device plugin setup | GPU Operator managed by OpenShift, no additional config for the benchmark client |

The GuideLLM Job itself is standard Kubernetes. The OpenShift advantage here is in the model serving side -- KServe on OpenShift AI provides the standardized InferenceService with a predictable internal URL, and the GPU Operator ensures the model server has GPU access without manual device plugin configuration.

## Key Takeaways

- **GuideLLM** is purpose-built for LLM inference benchmarking -- it understands token-level metrics that generic HTTP benchmarkers miss (TTFT, ITL, streaming throughput).
- **Run benchmarks inside the cluster** as Kubernetes Jobs to eliminate external network variability and measure true inference performance.
- **Sweep mode** is the most informative load profile -- it reveals the throughput ceiling and the load level where latency begins to degrade.
- **Percentile distributions** (p50, p90, p95, p99) are more useful than averages for SLO compliance -- a good average can hide a terrible tail latency.
- **Baseline before tuning** -- always capture benchmark results before changing vLLM configuration (model length, GPU memory utilization, batch size) so you can measure the impact of changes.

## Cleanup

Remove the benchmark Job and its pod:

```bash
oc delete job guidellm-benchmark -n gemma-model
```

Remove the saved results file if you no longer need it:

```bash
rm -f guidellm-results.txt
```

The model endpoint remains running for the next lesson.

## Next Steps

In **L1-M5.3 -- Serving Metrics and Grafana Dashboards**, you will connect the vLLM server's built-in Prometheus metrics to the OpenShift monitoring stack. You will create a ServiceMonitor to scrape metrics like `vllm:time_to_first_token_seconds` and `vllm:kv_cache_usage_perc`, build a Grafana dashboard for real-time monitoring, and set up alerts for SLO violations -- turning the point-in-time benchmarks from this lesson into continuous observability.
