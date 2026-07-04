# L1-M2.2 -- Deploying Gemma4-e4b with vLLM

**Level:** Foundations
**Duration:** 45 min

## Overview

In this lesson you deploy a real large language model on OpenShift AI. You create a ServingRuntime that configures vLLM as the inference engine, then create an InferenceService that launches the model on a GPU node. By the end you will have Google's Gemma4-e4b model running inside your cluster, serving an OpenAI-compatible API that you can call with `curl`. This is the hands-on deployment that puts the KServe concepts from L1-M2.1 into practice.

## Prerequisites

- Completed: [L1-M2.1 -- KServe Fundamentals](../1_kserve_fundamentals/)
- OpenShift AI cluster with at least one GPU node (T4 minimum, L40S recommended)
- `oc` CLI authenticated to the cluster
- Internet access from the cluster (the model downloads from Hugging Face at startup)

Verify GPU availability before proceeding:

```bash
oc get nodes -l nvidia.com/gpu.present=true
```

If no nodes are returned, your cluster does not have GPU nodes available. You need at least one node with an NVIDIA GPU to complete this lesson.

## K8s Context

On vanilla Kubernetes, deploying a model with vLLM means writing a Deployment, a Service, and an Ingress yourself. You choose the container image, configure GPU resource requests, set up health checks, and wire everything together manually. If you want autoscaling, you install KEDA or write an HPA. If you want canary rollouts, you set up Istio or another service mesh.

On OpenShift AI, you express the same deployment as two purpose-built CRDs -- `ServingRuntime` and `InferenceService` -- and the KServe controller handles the Deployment, Service, Route, and scaling for you. The operator also integrates with the OpenShift AI dashboard, so your model appears in a central UI alongside metrics and endpoint URLs.

## Concepts

### Choosing a Model: Gemma4-e4b

Gemma4-e4b is a ~4 billion parameter model from Google's Gemma family. The "E4B" notation stands for "Efficient 4 Billion" -- it is an instruction-tuned model small enough to run on a single GPU while still producing useful outputs for chat, summarization, and code generation tasks.

We use Gemma4-e4b in this lesson for three practical reasons:

1. **Size** -- at ~4B parameters, it fits comfortably in the VRAM of a T4 (16 GB) or L40S (48 GB) GPU
2. **Quality** -- instruction-tuned for conversational use, so you get coherent responses out of the box
3. **vLLM support** -- the community vLLM image includes a Gemma4-specific build (`vllm-openai:gemma4`)

Red Hat AI also provides optimized and quantized model versions on Hugging Face under the [RedHatAI](https://huggingface.co/RedHatAI) organization. These are pre-validated for vLLM and OpenShift AI deployments. For this lesson we use the upstream `google/gemma-4-E4B-it` model directly with the community vLLM image.

### vLLM as the Inference Engine

vLLM is a high-performance inference engine for large language models. It implements PagedAttention for efficient GPU memory management and continuous batching for high throughput. On OpenShift AI, vLLM runs inside a container defined by the ServingRuntime and exposes an OpenAI-compatible REST API.

Key vLLM flags you will see in the ServingRuntime manifest:

| Flag | Purpose |
|------|---------|
| `--dtype=half` | Use FP16 (half-precision) to halve memory usage compared to FP32 |
| `--max-model-len=8192` | Maximum sequence length (prompt + response tokens) |
| `--gpu-memory-utilization=0.95` | Use 95% of GPU VRAM for KV cache and model weights |
| `--enforce-eager` | Disable CUDA graphs; improves compatibility at a small throughput cost |
| `--served-model-name={{.Name}}` | Template variable -- KServe injects the InferenceService name at runtime |

### SCC Compatibility: Why HOME=/tmp?

OpenShift's default Security Context Constraint (`restricted`) prevents containers from writing to the default HOME directory (`/root` or `/home`). Many ML frameworks -- including vLLM, Hugging Face Transformers, and Triton -- write cache files to HOME on startup. If they cannot write, the pod crashes.

The solution is straightforward: set environment variables to redirect all caches to `/tmp`, which is writable under the `restricted` SCC:

```
HOME=/tmp
HF_HOME=/tmp/hf_home
XDG_CACHE_HOME=/tmp/.cache
VLLM_CACHE_DIR=/tmp/.cache/vllm
NUMBA_CACHE_DIR=/tmp/numba_cache
TRITON_CACHE_DIR=/tmp/.triton
```

This is a pattern you will see in every vLLM ServingRuntime on OpenShift. It is not a hack -- it is the standard approach for running ML workloads under OpenShift's security model.

### Online Model Download

The environment variable `HF_HUB_OFFLINE=0` tells the Hugging Face client to download the model from the Hugging Face Hub at container startup. This means:

- The pod's first startup takes 5-15 minutes depending on network speed (the model is ~4 GB)
- Subsequent restarts on the same node may be faster if the image layer cache is warm
- The cluster needs outbound internet access to `huggingface.co`

In production, you would typically pre-download models to a PersistentVolume or an S3-compatible object store. For this lesson, the online download keeps things simple.

## Step-by-Step

### Step 1: Create the Project Namespace

Create a dedicated namespace for the model deployment:

```bash
oc new-project gemma-model
```

Expected output:

```
Now using project "gemma-model" on server "https://api.example.com:6443".
```

### Step 2: Create the ServingRuntime

The ServingRuntime defines how vLLM runs -- the container image, command-line flags, environment variables, and which model formats it supports. Review the manifest before applying it.

Open `manifests/gemma4-e4b-servingruntime.yaml` and walk through each section:

**Metadata annotations** -- these register the runtime with the OpenShift AI dashboard:

```yaml
metadata:
  annotations:
    opendatahub.io/apiProtocol: REST
    opendatahub.io/recommended-accelerators: '["nvidia.com/gpu"]'
    opendatahub.io/template-display-name: vLLM NVIDIA GPU ServingRuntime for KServe
    opendatahub.io/template-name: vllm-cuda-runtime-template
    openshift.io/display-name: Gemma 4 E4B vLLM Runtime
  labels:
    opendatahub.io/dashboard: "true"
```

The `opendatahub.io/dashboard: "true"` label makes this runtime visible in the OpenShift AI dashboard. Without it, the runtime still works but does not appear in the UI. The `opendatahub.io/recommended-accelerators` annotation tells the dashboard to show a GPU badge.

**Container spec** -- the vLLM process configuration:

```yaml
containers:
  - args:
      - --port=8080
      - --model=google/gemma-4-E4B-it
      - --served-model-name={{.Name}}
      - --dtype=half
      - --max-model-len=8192
      - --gpu-memory-utilization=0.95
      - --enforce-eager
    command:
      - python3
      - -m
      - vllm.entrypoints.openai.api_server
```

The `command` launches vLLM's built-in OpenAI-compatible API server. The `--model` flag specifies the Hugging Face model ID to download and load. The `{{.Name}}` template variable is a KServe feature -- at deployment time, KServe replaces it with the name of the InferenceService (in our case, `gemma-4-e4b`).

**Container image**:

```yaml
image: docker.io/vllm/vllm-openai:gemma4
```

This is the community vLLM image with Gemma4 support. The `:gemma4` tag includes the specific model architecture support needed for the Gemma4 family.

**Environment variables** -- SCC-compatible cache paths:

```yaml
env:
  - name: HOME
    value: /tmp
  - name: HF_HOME
    value: /tmp/hf_home
  - name: HF_HUB_OFFLINE
    value: "0"
  - name: TRANSFORMERS_OFFLINE
    value: "0"
```

As discussed in the Concepts section, all cache directories are redirected to `/tmp` for OpenShift SCC compatibility. `HF_HUB_OFFLINE=0` enables downloading the model from Hugging Face at startup. `TRANSFORMERS_OFFLINE=0` allows the Hugging Face Transformers library to fetch tokenizer files.

Apply the manifest:

```bash
oc apply -f manifests/gemma4-e4b-servingruntime.yaml
```

Expected output:

```
servingruntime.serving.kserve.io/gemma-4-e4b created
```

Verify the runtime was created:

```bash
oc get servingruntime -n gemma-model
```

Expected output:

```
NAME          DISABLED   MODELTYPE   CONTAINERS         AGE
gemma-4-e4b                          kserve-container   5s
```

### Step 3: Create the InferenceService

The InferenceService tells KServe to deploy a model using the ServingRuntime you just created. Review `manifests/gemma4-e4b-inferenceservice.yaml`:

**Metadata annotations** -- deployment mode and dashboard integration:

```yaml
metadata:
  annotations:
    openshift.io/display-name: gemma-4-e4b
    serving.kserve.io/deploymentMode: RawDeployment
    security.opendatahub.io/enable-auth: "false"
    opendatahub.io/model-type: generative
```

- `serving.kserve.io/deploymentMode: RawDeployment` -- uses a standard Kubernetes Deployment instead of a Knative Service. RawDeployment is simpler and does not require the Knative Serving component to be installed. It trades scale-to-zero capability for straightforward Deployment semantics.
- `security.opendatahub.io/enable-auth: "false"` -- disables Authorino-based authentication on the endpoint. In production you would enable this; for learning we keep it off so you can call the endpoint directly with `curl`.
- `opendatahub.io/model-type: generative` -- tells the OpenShift AI dashboard to categorize this as a generative AI model (as opposed to a classification or embedding model).

**Labels**:

```yaml
labels:
  opendatahub.io/dashboard: "true"
  opendatahub.io/genai-asset: "true"
```

The `dashboard: "true"` label makes the model visible in the OpenShift AI dashboard. The `genai-asset: "true"` label tags it as a generative AI asset for filtering.

**Predictor spec** -- resource allocation and runtime binding:

```yaml
spec:
  predictor:
    maxReplicas: 1
    minReplicas: 1
    model:
      modelFormat:
        name: vLLM
      resources:
        limits:
          cpu: "4"
          memory: 24Gi
          nvidia.com/gpu: "1"
        requests:
          cpu: "1"
          memory: 8Gi
          nvidia.com/gpu: "1"
      runtime: gemma-4-e4b
```

- `minReplicas: 1`, `maxReplicas: 1` -- a single replica with no autoscaling. Autoscaling is covered in L1-M2.4.
- `nvidia.com/gpu: "1"` -- requests exactly one NVIDIA GPU. The Kubernetes scheduler places the pod on a node that has a GPU available.
- `runtime: gemma-4-e4b` -- links this InferenceService to the ServingRuntime by name. KServe uses the runtime's container spec to build the pod.
- Memory requests (8 Gi) vs limits (24 Gi): the request ensures the pod gets scheduled; the limit allows it to burst up to 24 Gi during model loading and inference.

Apply the manifest:

```bash
oc apply -f manifests/gemma4-e4b-inferenceservice.yaml
```

Expected output:

```
inferenceservice.serving.kserve.io/gemma-4-e4b created
```

### Step 4: Monitor the Deployment

After creating the InferenceService, KServe creates a Deployment and a pod. The pod downloads the model from Hugging Face and loads it into GPU memory. This takes 5-15 minutes depending on network speed and GPU type.

Watch the pod come up:

```bash
oc get pods -n gemma-model -w
```

You will see the pod progress through these states:

```
NAME                                          READY   STATUS              RESTARTS   AGE
gemma-4-e4b-predictor-xxxxx-yyyyy             0/1     ContainerCreating   0          10s
gemma-4-e4b-predictor-xxxxx-yyyyy             0/1     Running             0          30s
gemma-4-e4b-predictor-xxxxx-yyyyy             1/1     Running             0          8m
```

Press `Ctrl+C` to stop watching once the pod shows `1/1 Running`.

To see detailed progress, tail the logs of the vLLM container:

```bash
# Get the pod name
POD_NAME=$(oc get pods -n gemma-model -l serving.kserve.io/inferenceservice=gemma-4-e4b -o jsonpath='{.items[0].metadata.name}')

# Follow the logs
oc logs -f $POD_NAME -c kserve-container -n gemma-model
```

Expected log output during model loading:

```
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO 01-01 00:00:00 api_server.py:...] vLLM API server version 0.x.x
INFO 01-01 00:00:00 api_server.py:...] args: Namespace(model='google/gemma-4-E4B-it', ...)
INFO 01-01 00:00:05 model_runner.py:...] Loading model weights took X.XX GB
INFO 01-01 00:00:10 gpu_executor.py:...] # GPU blocks: XXXX, # CPU blocks: XXXX
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080
```

When you see `Uvicorn running on http://0.0.0.0:8080`, the model is loaded and ready to serve requests.

### Step 5: Verify the InferenceService

Check that the InferenceService reports as ready:

```bash
oc get inferenceservice gemma-4-e4b -n gemma-model
```

Expected output:

```
NAME          URL                                                  READY   PREV   LATEST   AGE
gemma-4-e4b   https://gemma-4-e4b-gemma-model.apps.example.com     True                    10m
```

The key indicators:

- **READY = True** -- the model is loaded and the health check is passing
- **URL** -- the external endpoint where the model is accessible

If READY shows `False` or `Unknown`, the model is still loading or something went wrong. Check the pod logs (Step 4) for details.

### Step 6: Get the Endpoint URL

The InferenceService creates a Route automatically. Get the endpoint URL:

```bash
# Internal cluster URL (from the InferenceService status)
oc get inferenceservice gemma-4-e4b -n gemma-model -o jsonpath='{.status.url}'
```

```bash
# External URL (via the OpenShift Route)
oc get routes -n gemma-model -l serving.kserve.io/inferenceservice=gemma-4-e4b
```

Expected output:

```
NAME                    HOST/PORT                                         PATH   SERVICES                PORT    TERMINATION     AGE
gemma-4-e4b-predictor   gemma-4-e4b-gemma-model.apps.example.com                 gemma-4-e4b-predictor   <all>   edge/Redirect   10m
```

Save the route URL for the next step:

```bash
ROUTE_URL=$(oc get route -n gemma-model -l serving.kserve.io/inferenceservice=gemma-4-e4b -o jsonpath='{.items[0].spec.host}')
echo "Model endpoint: https://${ROUTE_URL}"
```

### Step 7: Make Your First Inference Call

Send a chat completion request to the model using the OpenAI-compatible API:

```bash
ROUTE_URL=$(oc get route -n gemma-model -l serving.kserve.io/inferenceservice=gemma-4-e4b -o jsonpath='{.items[0].spec.host}')

curl -s "https://${ROUTE_URL}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma-4-e4b",
    "messages": [
      {"role": "user", "content": "What is OpenShift in one sentence?"}
    ],
    "max_tokens": 100,
    "temperature": 0.7
  }' | python3 -m json.tool
```

Expected output:

```json
{
    "id": "chatcmpl-abc123",
    "object": "chat.completion",
    "created": 1700000000,
    "model": "gemma-4-e4b",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "OpenShift is Red Hat's enterprise Kubernetes platform that adds developer tools, built-in CI/CD, and enhanced security on top of standard Kubernetes."
            },
            "finish_reason": "stop"
        }
    ],
    "usage": {
        "prompt_tokens": 14,
        "completion_tokens": 32,
        "total_tokens": 46
    }
}
```

Notice the response format is identical to the OpenAI API. The `model` field reflects the `--served-model-name` from the ServingRuntime, which KServe set to the InferenceService name `gemma-4-e4b`.

Try a follow-up request with a different prompt:

```bash
curl -s "https://${ROUTE_URL}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma-4-e4b",
    "messages": [
      {"role": "system", "content": "You are a Kubernetes expert. Be concise."},
      {"role": "user", "content": "What is the difference between a Deployment and a StatefulSet?"}
    ],
    "max_tokens": 200,
    "temperature": 0.3
  }' | python3 -m json.tool
```

### Step 8: View the Model in the OpenShift AI Dashboard

Open the OpenShift AI dashboard in your browser. You can find the URL with:

```bash
oc get route -n redhat-ods-applications -l app=rhods-dashboard -o jsonpath='{.items[0].spec.host}'
```

In the dashboard:

1. Navigate to **Model Serving** in the left sidebar.
2. You should see the `gemma-model` project listed.
3. Click into the project to see the **gemma-4-e4b** model.
4. The dashboard shows:
   - **Status** -- a green indicator when the model is ready
   - **Endpoint URL** -- the same Route URL you used with `curl`
   - **Model type** -- "Generative" (from the `opendatahub.io/model-type` annotation)
   - **Runtime** -- "Gemma 4 E4B vLLM Runtime" (from the `openshift.io/display-name` annotation on the ServingRuntime)

The dashboard provides a convenient way to monitor deployed models without using the CLI.

## Verification

Confirm the following before moving on:

| Check | How to verify |
|-------|---------------|
| ServingRuntime created | `oc get servingruntime -n gemma-model` shows `gemma-4-e4b` |
| InferenceService ready | `oc get inferenceservice gemma-4-e4b -n gemma-model` shows `READY=True` |
| Pod running | `oc get pods -n gemma-model` shows `1/1 Running` |
| Route created | `oc get routes -n gemma-model` returns a route with a hostname |
| API responding | `curl` to `/v1/chat/completions` returns a JSON response with a model completion |
| Dashboard visibility | Model appears in OpenShift AI dashboard under Model Serving |

## Troubleshooting

### Pod stuck in Pending

The pod cannot be scheduled. Most likely there are no GPU nodes available:

```bash
oc describe pod -n gemma-model -l serving.kserve.io/inferenceservice=gemma-4-e4b | grep -A 5 "Events"
```

Look for `FailedScheduling` events mentioning `nvidia.com/gpu`. Verify GPU nodes exist with `oc get nodes -l nvidia.com/gpu.present=true`.

### Pod in CrashLoopBackOff

The vLLM process is crashing. Common causes:

- **Out of GPU memory** -- the model does not fit in VRAM. Check logs for `CUDA out of memory`. Try reducing `--max-model-len` in the ServingRuntime or use a GPU with more VRAM.
- **Incompatible image** -- the vLLM image tag does not support the model architecture. Verify the image tag matches the model family.
- **SCC permission denied** -- a cache directory is not writable. Check logs for `Permission denied` and verify all `env` variables in the ServingRuntime point to `/tmp`.

```bash
POD_NAME=$(oc get pods -n gemma-model -l serving.kserve.io/inferenceservice=gemma-4-e4b -o jsonpath='{.items[0].metadata.name}')
oc logs $POD_NAME -c kserve-container -n gemma-model --previous
```

### Pod running but InferenceService not Ready

The health check is failing. vLLM may still be downloading or loading the model:

```bash
oc logs -f $POD_NAME -c kserve-container -n gemma-model
```

Wait for the `Uvicorn running on http://0.0.0.0:8080` message. Model download can take up to 15 minutes on slower connections.

### OOMKilled

The pod was killed for exceeding its memory limit. Increase the memory limit in the InferenceService:

```yaml
resources:
  limits:
    memory: 32Gi  # increase from 24Gi
```

### Model download hangs or fails

The cluster may not have outbound internet access to `huggingface.co`. Verify:

```bash
oc debug -n gemma-model --image=registry.access.redhat.com/ubi9/ubi-minimal -- curl -s -o /dev/null -w "%{http_code}" https://huggingface.co
```

If this returns anything other than `200`, check your cluster's egress network policies or proxy configuration.

## K8s vs OpenShift AI Comparison

| Aspect | Kubernetes | OpenShift AI |
|--------|-----------|--------------|
| Model deployment | Write Deployment + Service + Ingress manually | Two CRDs: ServingRuntime + InferenceService |
| Inference engine config | Embed vLLM args in Deployment spec | ServingRuntime abstracts runtime configuration, reusable across models |
| External access | Create Ingress + configure ingress controller | Route created automatically by KServe |
| GPU scheduling | Standard resource requests (`nvidia.com/gpu`) | Same resource requests, but integrated with dashboard monitoring |
| Container security | Varies by cluster; often permissive | `restricted` SCC enforced; must redirect caches to `/tmp` |
| Monitoring | Set up Prometheus scraping manually | `prometheus.io/path` and `prometheus.io/port` annotations, integrated with cluster monitoring |
| Dashboard | No built-in model management UI | OpenShift AI dashboard shows model status, endpoints, and metrics |
| Authentication | Configure auth proxy or API gateway separately | Authorino integration via single annotation (`enable-auth`) |
| Deployment mode | Always standard Deployment | Choice of RawDeployment (standard) or Serverless (Knative-based, scale-to-zero) |
| Model format abstraction | None -- you manage container images directly | `supportedModelFormats` in ServingRuntime declares compatible formats |

## Key Takeaways

- Deploying a model on OpenShift AI requires two manifests: a **ServingRuntime** (how the inference engine runs) and an **InferenceService** (which model to deploy with what resources).
- The **`restricted` SCC** means all cache directories must be redirected to `/tmp` via environment variables -- this is standard practice for ML workloads on OpenShift, not a workaround.
- vLLM downloads the model from Hugging Face at startup when `HF_HUB_OFFLINE=0`, which means first deployment takes 5-15 minutes but requires no pre-staging of model files.
- The **OpenAI-compatible API** (`/v1/chat/completions`) means any client library or tool that speaks the OpenAI protocol works with your deployed model unchanged.
- OpenShift AI **dashboard annotations and labels** (`opendatahub.io/dashboard`, `opendatahub.io/model-type`) make your deployment visible in the web UI for centralized monitoring and management.

## Cleanup

Delete all resources created in this lesson:

```bash
oc delete inferenceservice gemma-4-e4b -n gemma-model
oc delete servingruntime gemma-4-e4b -n gemma-model
oc delete project gemma-model
```

> **Note:** If you are continuing to [L1-M2.3 -- OpenAI-Compatible API Deep Dive](../3_openai_compatible_api/), **skip this cleanup**. The next lesson uses the same deployed model to explore the API in detail.

## Next Steps

In [L1-M2.3 -- OpenAI-Compatible API Deep Dive](../3_openai_compatible_api/), you will explore the full range of the OpenAI-compatible API that vLLM exposes -- streaming responses, token usage tracking, parameter tuning, and integrating with the OpenAI Python SDK. You will use the same Gemma4-e4b model deployed in this lesson.
