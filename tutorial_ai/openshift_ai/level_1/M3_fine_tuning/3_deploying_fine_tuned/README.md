# L1-M3.3 -- Deploying the Fine-Tuned Model

**Level:** Foundations
**Duration:** 45 min

## Overview

You have a LoRA adapter from L1-M3.2 sitting in S3 as a set of small weight files. The adapter alone cannot serve inference -- it must be combined with the base model to produce a single, complete model that vLLM can load. This lesson walks through merging the adapter into the base model, uploading the merged result to S3, deploying it as a new InferenceService alongside the original Gemma4-e4b, and comparing the two models side by side.

## Prerequisites

- Completed: [L1-M3.2 -- Fine-Tuning Gemma4-e4b with Training Hub](../2_training_hub_lora/) -- LoRA adapter saved and uploaded to S3
- Completed: [L1-M2.2 -- Deploying Gemma4-e4b](../../M2_model_serving/2_deploying_gemma/) -- base model deployed and serving
- OpenShift cluster running with `oc` CLI authenticated
- GPU node available (same requirements as the base model deployment)
- Python environment with `transformers`, `peft`, `torch`, and `boto3` installed
- S3 credentials (from the data connection configured in L1-M1.3)

## K8s Context

On vanilla Kubernetes, deploying a fine-tuned model follows the same pattern as deploying any model: build a container or stage the weights in storage, create a Deployment, expose a Service. There is no built-in concept of model lineage -- you track which model is the base and which is fine-tuned through your own documentation or MLOps tooling. OpenShift AI adds Model Registry (covered in L1-M4) to formalize this lineage, and the KServe CRDs give you a declarative way to point an InferenceService at model weights in S3 without writing custom download logic.

## Concepts

### Why Merge the LoRA Adapter?

LoRA (Low-Rank Adaptation) works by training a small set of low-rank matrices that modify specific layers of the base model. During training, these adapter weights are stored separately from the base model -- typically a few hundred megabytes versus the base model's several gigabytes. This separation is efficient for training but creates a serving challenge.

vLLM's standard serving mode expects a single model directory containing all weights. While vLLM does support serving LoRA adapters dynamically (the `--enable-lora` flag), that approach adds complexity: you must manage the base model and adapters separately, configure adapter paths, and handle potential version mismatches. For a single fine-tuned model, merging is simpler and more predictable.

The merge process:

1. Load the base model weights into memory
2. Load the LoRA adapter weights
3. Apply the adapter matrices to the corresponding base model layers (mathematically: W_merged = W_base + alpha * B * A, where B and A are the low-rank matrices)
4. Save the result as a new, standalone model

After merging, the fine-tuned model is self-contained -- it loads and serves identically to any other model.

### Packaging Options for the Merged Model

Once you have a merged model, you need to make it available to vLLM running on the cluster. There are two main approaches:

**Option A: Upload to S3 (what we do in this lesson)**

Upload the merged model directory to S3-compatible object storage. The InferenceService references the S3 path via `storageUri`, and KServe downloads the model to the pod's local storage at startup.

- Pros: Simple, works with existing S3 data connections, easy to update (just overwrite the S3 path)
- Cons: Slower pod startup (model must be downloaded from S3 each time the pod starts), requires S3 infrastructure

**Option B: Build an OCI image (ModelCar pattern)**

Bake the model weights into a container image. The InferenceService references the image, and Kubernetes pulls it like any other container.

- Pros: Fastest startup (model is part of the container layer cache), works with air-gapped environments, integrates with container image signing and scanning
- Cons: Large image sizes (multi-gigabyte), longer build times, requires rebuilding the image for any model update

For this lesson, we use Option A (S3) because it requires no additional tooling and works with the data connection you already configured. Production deployments on OpenShift AI increasingly use the ModelCar (OCI) pattern for its startup speed and GitOps compatibility.

### Serving the Fine-Tuned Model

The ServingRuntime and InferenceService for the fine-tuned model are nearly identical to the base model's. The key differences:

- The `--model` argument in the ServingRuntime points to `/mnt/models/` (the local path where KServe mounts the S3 download) instead of the Hugging Face model ID
- The InferenceService includes a `storageUri` field pointing to the S3 bucket path
- The `HF_HUB_OFFLINE` environment variable is set to `"1"` since we are not downloading from Hugging Face

Both models can run simultaneously on the same cluster (if GPU resources allow) or you can stop the base model to free the GPU.

## Step-by-Step

### Step 1: Verify the LoRA Adapter in S3

Confirm that the adapter from L1-M3.2 exists in your S3 bucket. The adapter should be in a directory like `gemma-4-e4b-lora-adapter/` containing at minimum `adapter_config.json` and `adapter_model.safetensors`.

If you have the AWS CLI or `mc` (MinIO client) configured with your S3 credentials:

```bash
# Using AWS CLI (adjust endpoint and bucket name for your setup)
aws s3 ls s3://models/gemma-4-e4b-lora-adapter/ --endpoint-url $S3_ENDPOINT
```

Expected output (file sizes will vary based on LoRA rank and target modules):

```
2026-07-01 10:30:00     1234567 adapter_model.safetensors
2026-07-01 10:30:01        1024 adapter_config.json
```

If you used a different S3 path in L1-M3.2, adjust the commands throughout this lesson accordingly.

### Step 2: Merge the LoRA Adapter with the Base Model

Run the merge script from this lesson's `scripts/` directory. The script loads the base model from Hugging Face, applies the LoRA adapter from S3, and saves the merged model locally before uploading it back to S3.

Before running, set the required environment variables. You can find the S3 credentials in your OpenShift data connection:

```bash
# Get S3 credentials from the OpenShift data connection secret
oc get secret <data-connection-name> -n <your-project> -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 -d
oc get secret <data-connection-name> -n <your-project> -o jsonpath='{.data.AWS_SECRET_ACCESS_KEY}' | base64 -d
oc get secret <data-connection-name> -n <your-project> -o jsonpath='{.data.AWS_S3_ENDPOINT}' | base64 -d
oc get secret <data-connection-name> -n <your-project> -o jsonpath='{.data.AWS_S3_BUCKET}' | base64 -d
```

Set the environment variables and run the script:

```bash
export S3_ENDPOINT="https://your-s3-endpoint.example.com"
export S3_BUCKET="models"
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export S3_ADAPTER_PATH="gemma-4-e4b-lora-adapter"
export S3_MERGED_PATH="gemma-4-e4b-finetuned"
export BASE_MODEL="google/gemma-4-E4B-it"
export LOCAL_MERGE_DIR="./merged_model"

python scripts/merge_and_upload.py
```

The script performs four operations:

1. Downloads the LoRA adapter files from S3 to a local directory
2. Loads the base model from Hugging Face and the adapter using the PEFT library
3. Merges the adapter weights into the base model
4. Uploads the complete merged model to S3 at the specified path

Expected output:

```
[1/4] Downloading LoRA adapter from S3...
  Downloaded: adapter_config.json
  Downloaded: adapter_model.safetensors
  Adapter saved to: ./adapter_download

[2/4] Loading base model and LoRA adapter...
  Loading base model: google/gemma-4-E4B-it
  Loading LoRA adapter from: ./adapter_download
  Adapter loaded successfully

[3/4] Merging adapter into base model...
  Merging weights...
  Saving merged model to: ./merged_model
  Merged model saved (X files, Y GB total)

[4/4] Uploading merged model to S3...
  Uploading: config.json
  Uploading: model-00001-of-00002.safetensors
  Uploading: model-00002-of-00002.safetensors
  Uploading: model.safetensors.index.json
  Uploading: tokenizer.json
  Uploading: tokenizer_config.json
  Uploading: special_tokens_map.json
  ...
  Upload complete: s3://models/gemma-4-e4b-finetuned/

Done. Merged model is ready for serving.
```

This step requires significant disk space (the merged model is the same size as the base model, roughly 8-10 GB for Gemma4-e4b) and a Hugging Face token if the base model is gated. Set `HF_TOKEN` before running if needed.

### Step 3: Verify the Merged Model in S3

Confirm the merged model was uploaded successfully:

```bash
aws s3 ls s3://models/gemma-4-e4b-finetuned/ --endpoint-url $S3_ENDPOINT
```

Expected output (files will vary slightly by model):

```
2026-07-01 11:00:00        1234 config.json
2026-07-01 11:00:05  5000000000 model-00001-of-00002.safetensors
2026-07-01 11:00:30  3500000000 model-00002-of-00002.safetensors
2026-07-01 11:00:31        2048 model.safetensors.index.json
2026-07-01 11:00:32      500000 tokenizer.json
2026-07-01 11:00:33        3000 tokenizer_config.json
2026-07-01 11:00:33        1500 special_tokens_map.json
```

The key file is `config.json` -- vLLM reads this to determine the model architecture and loading parameters. The `.safetensors` files contain the actual weights.

### Step 4: Create the ServingRuntime for the Fine-Tuned Model

The ServingRuntime defines how vLLM runs. The fine-tuned version is nearly identical to the base model's runtime, with two changes: the `--model` argument points to `/mnt/models/` (where KServe mounts the S3 download), and `HF_HUB_OFFLINE` is set to `"1"` since the model is loaded from local storage, not Hugging Face.

Review the manifest:

```bash
cat manifests/fine-tuned-servingruntime.yaml
```

```yaml
apiVersion: serving.kserve.io/v1alpha1
kind: ServingRuntime
metadata:
  annotations:
    opendatahub.io/apiProtocol: REST
    opendatahub.io/recommended-accelerators: '["nvidia.com/gpu"]'
    opendatahub.io/template-display-name: vLLM NVIDIA GPU ServingRuntime for KServe
    opendatahub.io/template-name: vllm-cuda-runtime-template
    openshift.io/display-name: Gemma 4 E4B Fine-Tuned vLLM Runtime
  labels:
    opendatahub.io/dashboard: "true"
  name: gemma-4-e4b-finetuned
  namespace: gemma-model
spec:
  annotations:
    prometheus.io/path: /metrics
    prometheus.io/port: "8080"
  containers:
    - args:
        - --port=8080
        - --model=/mnt/models/
        - --served-model-name={{.Name}}
        - --dtype=half
        - --max-model-len=8192
        - --gpu-memory-utilization=0.95
        - --enforce-eager
      command:
        - python3
        - -m
        - vllm.entrypoints.openai.api_server
      env:
        - name: HOME
          value: /tmp
        - name: HF_HOME
          value: /tmp/hf_home
        - name: XDG_CACHE_HOME
          value: /tmp/.cache
        - name: VLLM_CACHE_DIR
          value: /tmp/.cache/vllm
        - name: HF_HUB_OFFLINE
          value: "1"
        - name: TRANSFORMERS_OFFLINE
          value: "1"
        - name: NUMBA_CACHE_DIR
          value: /tmp/numba_cache
        - name: TRITON_CACHE_DIR
          value: /tmp/.triton
      image: docker.io/vllm/vllm-openai:gemma4
      name: kserve-container
      ports:
        - containerPort: 8080
          protocol: TCP
  multiModel: false
  supportedModelFormats:
    - autoSelect: true
      name: vLLM
```

Key differences from the base model runtime (`gemma-4-e4b`):

| Field | Base Model | Fine-Tuned Model |
|-------|-----------|-----------------|
| `metadata.name` | `gemma-4-e4b` | `gemma-4-e4b-finetuned` |
| `--model` arg | `google/gemma-4-E4B-it` (HF download) | `/mnt/models/` (S3 mount) |
| `HF_HUB_OFFLINE` | `"0"` | `"1"` |
| `TRANSFORMERS_OFFLINE` | `"0"` | `"1"` |

Apply the ServingRuntime:

```bash
oc apply -f manifests/fine-tuned-servingruntime.yaml
```

Expected output:

```
servingruntime.serving.kserve.io/gemma-4-e4b-finetuned created
```

Verify it was created:

```bash
oc get servingruntimes -n gemma-model
```

Expected output:

```
NAME                     AGE
gemma-4-e4b              2d
gemma-4-e4b-finetuned    5s
```

### Step 5: Create the InferenceService for the Fine-Tuned Model

The InferenceService for the fine-tuned model adds a `storageUri` field that tells KServe where to download the model from. KServe uses the S3 credentials from the service account's data connection to authenticate.

Before applying, ensure the service account in the `gemma-model` namespace has access to the S3 bucket. If you configured a data connection in L1-M1.3, the credentials are available as a Secret. KServe reads S3 credentials from a Secret annotated with `serving.kserve.io/s3-endpoint`, `serving.kserve.io/s3-usehttps`, etc., or from the default service account's attached secrets.

Create the storage Secret if it does not already exist (adjust values for your S3 setup):

```bash
oc apply -f - <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: s3-storage-secret
  namespace: gemma-model
  annotations:
    serving.kserve.io/s3-endpoint: "your-s3-endpoint.example.com"
    serving.kserve.io/s3-usehttps: "1"
    serving.kserve.io/s3-verifyssl: "0"
type: Opaque
stringData:
  AWS_ACCESS_KEY_ID: "your-access-key"
  AWS_SECRET_ACCESS_KEY: "your-secret-key"
EOF
```

Attach the Secret to the default service account so KServe can use it:

```bash
oc secrets link default s3-storage-secret -n gemma-model
```

Review the InferenceService manifest:

```bash
cat manifests/fine-tuned-inferenceservice.yaml
```

```yaml
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  annotations:
    openshift.io/display-name: gemma-4-e4b-finetuned
    serving.kserve.io/deploymentMode: RawDeployment
    security.opendatahub.io/enable-auth: "false"
    opendatahub.io/model-type: generative
  labels:
    opendatahub.io/dashboard: "true"
    opendatahub.io/genai-asset: "true"
  name: gemma-4-e4b-finetuned
  namespace: gemma-model
spec:
  predictor:
    maxReplicas: 1
    minReplicas: 1
    model:
      modelFormat:
        name: vLLM
      name: ""
      resources:
        limits:
          cpu: "4"
          memory: 24Gi
          nvidia.com/gpu: "1"
        requests:
          cpu: "1"
          memory: 8Gi
          nvidia.com/gpu: "1"
      runtime: gemma-4-e4b-finetuned
      storageUri: s3://models/gemma-4-e4b-finetuned/
```

Key differences from the base model InferenceService:

| Field | Base Model | Fine-Tuned Model |
|-------|-----------|-----------------|
| `metadata.name` | `gemma-4-e4b` | `gemma-4-e4b-finetuned` |
| `model.runtime` | `gemma-4-e4b` | `gemma-4-e4b-finetuned` |
| `model.storageUri` | (not set, HF download) | `s3://models/gemma-4-e4b-finetuned/` |

Apply the InferenceService:

```bash
oc apply -f manifests/fine-tuned-inferenceservice.yaml
```

Expected output:

```
inferenceservice.serving.kserve.io/gemma-4-e4b-finetuned created
```

### Step 6: Wait for the Model to Load

The fine-tuned model pod downloads the weights from S3 before starting vLLM. This can take several minutes depending on model size and S3 bandwidth.

Monitor the pod startup:

```bash
oc get pods -n gemma-model -l serving.kserve.io/inferenceservice=gemma-4-e4b-finetuned -w
```

Expected progression:

```
NAME                                              READY   STATUS     RESTARTS   AGE
gemma-4-e4b-finetuned-predictor-abc123-xyz        0/1     Init:0/1   0          10s
gemma-4-e4b-finetuned-predictor-abc123-xyz        0/1     Init:0/1   0          30s
gemma-4-e4b-finetuned-predictor-abc123-xyz        0/1     PodInitializing   0   2m
gemma-4-e4b-finetuned-predictor-abc123-xyz        0/1     Running    0          2m30s
gemma-4-e4b-finetuned-predictor-abc123-xyz        1/1     Running    0          4m
```

The `Init` phase downloads the model from S3. The transition from `Running 0/1` to `Running 1/1` indicates vLLM has loaded the weights into GPU memory and is ready to serve.

If the pod stays in `Init` for a long time, check the init container logs:

```bash
oc logs -n gemma-model -l serving.kserve.io/inferenceservice=gemma-4-e4b-finetuned -c storage-initializer
```

Check the InferenceService status:

```bash
oc get inferenceservice gemma-4-e4b-finetuned -n gemma-model
```

Expected output when ready:

```
NAME                     URL                                                              READY   PREV   LATEST   AGE
gemma-4-e4b-finetuned    https://gemma-4-e4b-finetuned-gemma-model.apps.<cluster>         True                    5m
```

### Step 7: Test the Fine-Tuned Model

Get the route URL for the fine-tuned model:

```bash
export FINETUNED_URL=$(oc get route gemma-4-e4b-finetuned -n gemma-model -o jsonpath='{.spec.host}')
echo "Fine-tuned model endpoint: https://$FINETUNED_URL"
```

Send a test request:

```bash
curl -s https://$FINETUNED_URL/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma-4-e4b-finetuned",
    "messages": [
      {"role": "user", "content": "Hello, are you working?"}
    ],
    "max_tokens": 100
  }' | python3 -m json.tool
```

Expected output (content will vary):

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "model": "gemma-4-e4b-finetuned",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Yes, I am working! How can I help you today?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 15,
    "total_tokens": 25
  }
}
```

### Step 8: Side-by-Side Comparison -- Base vs Fine-Tuned

Now run the same prompts against both models to see the effect of fine-tuning. Get both endpoint URLs:

```bash
export BASE_URL=$(oc get route gemma-4-e4b -n gemma-model -o jsonpath='{.spec.host}')
export FINETUNED_URL=$(oc get route gemma-4-e4b-finetuned -n gemma-model -o jsonpath='{.spec.host}')
```

If you only have one GPU, you may need to scale down the base model first and then bring it back up, or run these tests sequentially. To scale down the base model temporarily:

```bash
# Scale down base model to free the GPU
oc patch inferenceservice gemma-4-e4b -n gemma-model --type merge -p '{"spec":{"predictor":{"minReplicas":0}}}'

# Wait for pod to terminate, then scale back up when needed
oc patch inferenceservice gemma-4-e4b -n gemma-model --type merge -p '{"spec":{"predictor":{"minReplicas":1}}}'
```

**Test 1: ShopInsights domain question**

If your fine-tuning dataset (from L1-M3.2) was focused on the ShopInsights e-commerce domain, test with a domain-specific prompt:

```bash
# Base model
curl -s https://$BASE_URL/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma-4-e4b",
    "messages": [
      {"role": "system", "content": "You are a ShopInsights analytics assistant."},
      {"role": "user", "content": "Our electronics category saw a 15% drop in conversion rate last week. What are the top 3 things I should investigate?"}
    ],
    "max_tokens": 300,
    "temperature": 0.7
  }' | python3 -c "import sys,json; print('BASE MODEL:'); print(json.load(sys.stdin)['choices'][0]['message']['content'])"

echo "---"

# Fine-tuned model
curl -s https://$FINETUNED_URL/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma-4-e4b-finetuned",
    "messages": [
      {"role": "system", "content": "You are a ShopInsights analytics assistant."},
      {"role": "user", "content": "Our electronics category saw a 15% drop in conversion rate last week. What are the top 3 things I should investigate?"}
    ],
    "max_tokens": 300,
    "temperature": 0.7
  }' | python3 -c "import sys,json; print('FINE-TUNED MODEL:'); print(json.load(sys.stdin)['choices'][0]['message']['content'])"
```

**Test 2: Response style and format**

If your fine-tuning dataset trained the model to respond in a specific format (e.g., structured JSON, bullet points, or a particular tone), test that:

```bash
# Base model
curl -s https://$BASE_URL/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma-4-e4b",
    "messages": [
      {"role": "user", "content": "Summarize the order trends for customer segment \"enterprise\" over the last quarter."}
    ],
    "max_tokens": 300,
    "temperature": 0.7
  }' | python3 -c "import sys,json; print('BASE MODEL:'); print(json.load(sys.stdin)['choices'][0]['message']['content'])"

echo "---"

# Fine-tuned model
curl -s https://$FINETUNED_URL/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma-4-e4b-finetuned",
    "messages": [
      {"role": "user", "content": "Summarize the order trends for customer segment \"enterprise\" over the last quarter."}
    ],
    "max_tokens": 300,
    "temperature": 0.7
  }' | python3 -c "import sys,json; print('FINE-TUNED MODEL:'); print(json.load(sys.stdin)['choices'][0]['message']['content'])"
```

What to look for in the comparison:

- **Domain knowledge**: The fine-tuned model should reference ShopInsights-specific concepts, metrics, and terminology more naturally
- **Response format**: If the training data used a specific structure, the fine-tuned model should follow it more consistently
- **Tone and style**: The fine-tuned model should match the conversational style of the training data
- **Hallucination**: Both models may generate plausible-sounding but fabricated data -- fine-tuning does not add real data knowledge, it adjusts behavior and style

### Step 9: Preview -- Model Registry (L1-M4)

Both models are now deployed, but there is no formal record of their relationship. Which model is the base? Which is fine-tuned? What dataset was used for training? What LoRA configuration was applied?

[L1-M4 (Model Registry)](../../M4_model_registry/) addresses this by introducing the Kubeflow Model Registry, which provides:

- **RegisteredModel**: A named entry for "Gemma4-e4b" that groups all versions
- **ModelVersion**: Individual versions (v1 = base, v2 = fine-tuned with LoRA rank 16 on ShopInsights data)
- **ModelArtifact**: Links to the actual model files (the S3 path or OCI image)

This creates a traceable lineage: you can see that version 2 was derived from version 1, what training configuration was used, and where the artifacts are stored. For now, keep both models running -- you will register them formally in L1-M4.

## Verification

Confirm both models are deployed and responding:

1. Both InferenceServices are ready:

```bash
oc get inferenceservices -n gemma-model
```

Expected output:

```
NAME                     URL                                                              READY   PREV   LATEST   AGE
gemma-4-e4b              https://gemma-4-e4b-gemma-model.apps.<cluster>                   True                    2d
gemma-4-e4b-finetuned    https://gemma-4-e4b-finetuned-gemma-model.apps.<cluster>         True                    10m
```

2. Both ServingRuntimes exist:

```bash
oc get servingruntimes -n gemma-model
```

Expected output:

```
NAME                     AGE
gemma-4-e4b              2d
gemma-4-e4b-finetuned    10m
```

3. The fine-tuned model lists its served name correctly:

```bash
curl -s https://$FINETUNED_URL/v1/models | python3 -m json.tool
```

Expected output:

```json
{
  "object": "list",
  "data": [
    {
      "id": "gemma-4-e4b-finetuned",
      "object": "model",
      "owned_by": "vllm"
    }
  ]
}
```

4. The merged model exists in S3:

```bash
aws s3 ls s3://models/gemma-4-e4b-finetuned/ --endpoint-url $S3_ENDPOINT | wc -l
```

Expected: `7` or more files.

## K8s vs OpenShift AI Comparison

| Aspect | Kubernetes (manual) | OpenShift AI |
|--------|-------------------|--------------|
| **Model storage** | Mount a PVC or configure S3 download in init containers yourself | `storageUri` in InferenceService handles S3 download automatically via KServe storage initializer |
| **S3 credentials** | Create Secrets and mount them in pods manually | Data connections managed via dashboard; KServe reads annotated Secrets from the service account |
| **Model deployment** | Write Deployment + Service + Ingress YAML, manage container args | ServingRuntime + InferenceService CRDs handle runtime config, pod creation, and routing |
| **Side-by-side models** | Deploy two separate Deployments, manage names and routing manually | Two InferenceServices in the same namespace, each with its own Route auto-created |
| **Model lineage** | No built-in tracking -- use external tools or documentation | Model Registry (L1-M4) provides RegisteredModel, ModelVersion, ModelArtifact hierarchy |
| **Dashboard visibility** | No built-in UI for model serving status | Both models visible in OpenShift AI dashboard with endpoint URLs, status, and metrics |

## Key Takeaways

- **Merge before serving.** LoRA adapters must be merged with the base model for standard vLLM serving. The merge process combines the adapter's low-rank matrices into the base model's weight tensors, producing a standalone model.
- **S3 storage is the simplest path for development.** Set `storageUri` in the InferenceService and KServe handles the download. For production, consider OCI images (ModelCar pattern) for faster startup and better GitOps integration.
- **ServingRuntime changes are minimal.** The fine-tuned model uses the same vLLM image and configuration as the base model. The only meaningful change is pointing `--model` at `/mnt/models/` instead of a Hugging Face model ID.
- **Side-by-side comparison reveals fine-tuning impact.** Running the same prompts against both models is the most direct way to verify that fine-tuning achieved the desired behavioral change.
- **Model lineage needs formal tracking.** Without a Model Registry, the relationship between base and fine-tuned models exists only in your documentation. L1-M4 introduces the registry to formalize this.

## Cleanup

To remove only the fine-tuned model resources (keep the base model running for other lessons):

```bash
oc delete inferenceservice gemma-4-e4b-finetuned -n gemma-model
oc delete servingruntime gemma-4-e4b-finetuned -n gemma-model
```

To also remove the model files from S3:

```bash
aws s3 rm s3://models/gemma-4-e4b-finetuned/ --recursive --endpoint-url $S3_ENDPOINT
```

To remove everything from this module (base model, fine-tuned model, namespace):

```bash
oc delete project gemma-model
```

Clean up local files from the merge process:

```bash
rm -rf ./merged_model ./adapter_download
```

## Next Steps

Both models are deployed and you can see the behavioral difference from fine-tuning. However, there is no formal record of which model is which, what training produced the fine-tuned version, or how to compare them systematically.

In [L1-M4.1 -- Model Registry Setup](../../M4_model_registry/1_registry_setup/), you will deploy the Kubeflow Model Registry on OpenShift AI and create a structured catalog of your models with versions, metadata, and artifact links. In [L1-M4.2](../../M4_model_registry/2_registering_models/), you will register both the base and fine-tuned Gemma4-e4b with full lineage tracking.
