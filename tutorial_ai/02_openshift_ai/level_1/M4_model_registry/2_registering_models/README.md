# L1-M4.2 — Registering and Managing Models

**Level:** Foundations
**Duration:** 30 min

## Overview

The Model Registry is running, but it is empty. In this lesson you populate it with the two models you have been working with throughout Level 1: the base Gemma4-e4b and the fine-tuned version. You will register models three ways -- through the dashboard UI, the Python SDK, and the REST API -- so you understand all the access patterns.

By the end, you will have a versioned registry of your models with metadata, labels, and custom properties. You will also deploy a model directly from the registry, closing the loop from "model exists in S3" to "model is serving inference, and the registry tracks it all."

## Prerequisites

- Completed: [L1-M4.1 — Model Registry Setup](../1_registry_setup/) (registry running with MySQL backend)
- Completed: [L1-M2.2 — Deploying Gemma4-e4b](../../M2_model_serving/2_deploying_gemma/) (base model deployed)
- Completed: [L1-M3.3 — Deploying the Fine-Tuned Model](../../M3_fine_tuning/3_deploying_fine_tuned/) (fine-tuned model deployed)
- OpenShift cluster running with `oc` CLI authenticated
- Python 3.10+ available (in a workbench or locally)
- The `model-registry` Python package installed: `pip install model-registry`

## K8s Context

In Kubernetes, model management is ad hoc. You might track models in a spreadsheet, a README, or an external tool like MLflow. Deploying a model means manually copying the S3 URI into a KServe InferenceService YAML file. There is no standard API for "list all models," "what versions exist," or "deploy version X." Each team invents their own system.

OpenShift AI standardizes this with the Kubeflow Model Registry. Every model gets a consistent record -- name, version, artifact location, metadata. The dashboard shows all models across the platform. Deployment is integrated: click "Deploy" on a version in the dashboard, or use the `model-registry://` URI scheme in an InferenceService. The Python SDK and REST API let you automate registration from notebooks, pipelines, and CI/CD systems.

## Concepts

### Model Lifecycle

The Model Registry supports a simple lifecycle for model management:

```
Experiment (notebook/training)
    |
    v
Register (create RegisteredModel + ModelVersion + ModelArtifact)
    |
    v
Version (create new ModelVersion for improvements)
    |
    v
Deploy (create InferenceService from registry)
    |
    v
Archive (soft-delete when no longer needed)
```

This is not enforced -- you can register models at any point. But the pattern encourages tracking models from the moment they are ready for serving.

### Custom Properties and Labels

Every registry entity (RegisteredModel, ModelVersion, ModelArtifact) supports:

- **Custom Properties** -- Typed key-value pairs stored in the database. Values can be strings, integers, floats, or booleans. Use these for structured metadata like accuracy scores, training parameters, or dataset references.
- **Labels** -- Simple string tags for categorization and filtering. Use these for quick visual identification in the dashboard (e.g., "production", "fine-tuned", "LoRA").

### Three Ways to Access the Registry

| Method | Best For | Details |
|--------|----------|---------|
| **Dashboard UI** | Manual registration, browsing, one-click deployment | Navigate to AI Hub > Registry |
| **Python SDK** | Notebook workflows, pipeline automation | `pip install model-registry`, `ModelRegistry` class |
| **REST API** | CI/CD integration, custom tooling, language-agnostic access | `GET/POST/PATCH` on `/api/model_registry/v1alpha3/` |

All three methods access the same data -- a model registered via the SDK appears in the dashboard and vice versa.

### The Python SDK

The `model-registry` package provides a high-level Python interface:

```python
from model_registry import ModelRegistry

registry = ModelRegistry(
    server_address="http://model-registry-tutorial-registry.rhoai-model-registries.svc.cluster.local",
    port=8080,
    author="tutorial-user",
    is_secure=False
)
```

The key method is `register_model()`, which creates (or updates) a RegisteredModel, ModelVersion, and ModelArtifact in a single call.

### REST API Endpoints

The REST API follows a predictable pattern:

| Resource | List | Create | Get | Update |
|----------|------|--------|-----|--------|
| RegisteredModel | `GET /registered_models` | `POST /registered_models` | `GET /registered_models/{id}` | `PATCH /registered_models/{id}` |
| ModelVersion | `GET /model_versions` | `POST /registered_models/{id}/versions` | `GET /model_versions/{id}` | `PATCH /model_versions/{id}` |
| ModelArtifact | `GET /model_artifacts` | `POST /model_versions/{id}/artifacts` | `GET /model_artifacts/{id}` | `PATCH /model_artifacts/{id}` |

There is no DELETE endpoint. To remove a model, you PATCH its state to `ARCHIVED`. This is a soft delete -- the metadata is preserved but hidden from active queries.

## Step-by-Step

### Step 1: Register the Base Model via Dashboard

Open the OpenShift AI dashboard and navigate to **AI Hub > Registry > tutorial-registry**.

1. Click **Register model**
2. Fill in the model details:
   - **Model name**: `gemma4-e4b`
   - **Model description**: `Google Gemma 4 E4B instruction-tuned model. Base (unmodified) model served via vLLM.`
3. Fill in the version details:
   - **Version name**: `v1-base`
   - **Version description**: `Original base model from Hugging Face (google/gemma-4-E4B-it). No fine-tuning applied.`
   - **Source model format**: `vLLM`
   - **Model location**: Enter the model URI or S3 path where your base model is stored (e.g., `s3://models/gemma4-e4b/base/` or the Hugging Face URI `hf://google/gemma-4-E4B-it`)
4. Click **Register model**

You should see the model appear in the registry table with version `v1-base`.

### Step 2: Add Labels and Properties via Dashboard

Click on the registered model `gemma4-e4b` to open its details page.

1. On the **Details** tab, click **Add label**
2. Add these labels:
   - `base-model`
   - `gemma`
   - `instruction-tuned`
3. Navigate to the **Versions** tab and click on `v1-base`
4. Add custom properties:
   - `parameter_count` (integer): `4000000000`
   - `quantization` (string): `half` (FP16)
   - `max_model_len` (integer): `8192`
   - `source` (string): `huggingface`

These properties are searchable and will help you distinguish versions later.

### Step 3: Register the Fine-Tuned Model via Python SDK

Now register the fine-tuned version using the Python SDK. This is the approach you would use in notebooks and automated pipelines.

Start a port-forward to the registry service (if working outside the cluster):

```bash
oc port-forward svc/model-registry-tutorial-registry 8080:8080 \
  -n rhoai-model-registries &
```

Run the registration script:

```bash
python3 scripts/register_models.py
```

Or execute the following in a notebook or Python environment:

```python
from model_registry import ModelRegistry

# Connect to the registry
# If running inside a workbench on the cluster, use the in-cluster service address:
#   server_address="http://model-registry-tutorial-registry.rhoai-model-registries.svc.cluster.local"
# If running locally with port-forward:
#   server_address="http://localhost"
registry = ModelRegistry(
    server_address="http://localhost",
    port=8080,
    author="tutorial-user",
    is_secure=False
)

# Register the fine-tuned model as a new version of gemma4-e4b.
# register_model() upserts: if the RegisteredModel "gemma4-e4b" already
# exists (we created it in the dashboard), it adds a new version to it.
rm = registry.register_model(
    "gemma4-e4b",                                         # model name (must match)
    "s3://models/gemma4-e4b/finetuned-lora-merged/",      # artifact URI
    model_format_name="vLLM",
    model_format_version="1",
    version="v2-finetuned",
    description="LoRA fine-tuned on custom dataset. Adapter merged with base model.",
    metadata={
        "base_model": "google/gemma-4-E4B-it",
        "fine_tuning_method": "LoRA",
        "lora_rank": 16,
        "lora_alpha": 32,
        "training_epochs": 3,
        "training_dataset": "custom-instructions-v1",
        "quantization": "half",
        "is_merged": True,
    }
)

print(f"Registered model: {rm.name}")
print(f"Model ID: {rm.id}")
```

Expected output:

```
Registered model: gemma4-e4b
Model ID: 1
```

### Step 4: List Models and Versions via Python SDK

Verify what is in the registry:

```python
# List all registered models
for model in registry.get_registered_models():
    print(f"Model: {model.name} (ID: {model.id})")
    print(f"  Description: {model.description}")
    print(f"  State: {model.state}")
    print()

# List versions of gemma4-e4b
for version in registry.get_model_versions("gemma4-e4b"):
    print(f"  Version: {version.name} (ID: {version.id})")
    print(f"    Description: {version.description}")
    print(f"    Author: {version.author}")
    print()

# Get a specific version and its artifact
version = registry.get_model_version("gemma4-e4b", "v2-finetuned")
artifact = registry.get_model_artifact("gemma4-e4b", "v2-finetuned")
print(f"Version: {version.name}")
print(f"Artifact URI: {artifact.uri}")
print(f"Model format: {artifact.model_format_name}")
```

Expected output:

```
Model: gemma4-e4b (ID: 1)
  Description: Google Gemma 4 E4B instruction-tuned model. Base (unmodified) model served via vLLM.
  State: LIVE

  Version: v1-base (ID: 1)
    Description: Original base model from Hugging Face (google/gemma-4-E4B-it). No fine-tuning applied.
    Author: tutorial-user

  Version: v2-finetuned (ID: 2)
    Description: LoRA fine-tuned on custom dataset. Adapter merged with base model.
    Author: tutorial-user

Version: v2-finetuned
Artifact URI: s3://models/gemma4-e4b/finetuned-lora-merged/
Model format: vLLM
```

### Step 5: Query the REST API Directly

The REST API is useful for CI/CD pipelines, shell scripts, and tools in any language. Use `curl` to query the registry:

```bash
# Port-forward should still be running from Step 3.
# If not: oc port-forward svc/model-registry-tutorial-registry 8080:8080 -n rhoai-model-registries &

# List all registered models
curl -s http://localhost:8080/api/model_registry/v1alpha3/registered_models | python3 -m json.tool
```

Expected output:

```json
{
    "items": [
        {
            "id": "1",
            "name": "gemma4-e4b",
            "description": "Google Gemma 4 E4B instruction-tuned model...",
            "state": "LIVE",
            "createTimeSinceEpoch": "1720000000000",
            "lastUpdateTimeSinceEpoch": "1720000000000"
        }
    ],
    "nextPageToken": "",
    "pageSize": 0,
    "size": 1
}
```

List versions of a model:

```bash
# Get the model ID first (it's "1" from the output above)
curl -s http://localhost:8080/api/model_registry/v1alpha3/registered_models/1/versions | python3 -m json.tool
```

Get a specific version with all its metadata:

```bash
curl -s http://localhost:8080/api/model_registry/v1alpha3/model_versions/2 | python3 -m json.tool
```

Create a new model via the REST API (to demonstrate the full CRUD):

```bash
# Register a second model via REST API
curl -s -X POST http://localhost:8080/api/model_registry/v1alpha3/registered_models \
  -H "Content-Type: application/json" \
  -d '{
    "name": "gemma4-e4b-quantized",
    "description": "Quantized variant of Gemma4-e4b for lower VRAM usage",
    "customProperties": {
      "quantization_format": {
        "stringValue": "FP8"
      },
      "target_gpu_vram_gb": {
        "intValue": "8"
      }
    }
  }' | python3 -m json.tool
```

### Step 6: Update Model Metadata

Update a version's description using the Python SDK:

```python
# Get the version and update it
version = registry.get_model_version("gemma4-e4b", "v2-finetuned")
version.description = (
    "LoRA fine-tuned on custom-instructions-v1 dataset. "
    "Adapter merged with base model. "
    "Evaluated with LMEvalJob -- see L1-M5.1 for benchmark results."
)
registry.update(version)

print(f"Updated version: {version.name}")
print(f"New description: {version.description}")
```

Or via the REST API:

```bash
# Update a registered model's description
curl -s -X PATCH http://localhost:8080/api/model_registry/v1alpha3/registered_models/1 \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Google Gemma 4 E4B instruction-tuned model. Primary model for the OpenShift AI tutorial series."
  }' | python3 -m json.tool
```

### Step 7: Deploy a Model from the Registry

The registry integrates with KServe to deploy models directly. There are two ways to do this.

**Option A: Deploy from the Dashboard (recommended for manual deployments)**

1. Navigate to **AI Hub > Registry > tutorial-registry**
2. Click on `gemma4-e4b`, then the **Versions** tab
3. Click on `v2-finetuned`
4. Click the **Deploy** button
5. Configure the deployment:
   - **Deployment name**: `gemma4-e4b-finetuned-from-registry`
   - **Serving runtime**: Select the vLLM runtime
   - **Model framework**: `vLLM`
   - **Hardware profile**: Select your GPU profile
   - **Deployment mode**: `Raw Deployment` (recommended)
   - **Endpoint access**: External route (for testing)
6. Click **Deploy**

The dashboard creates an InferenceService CR automatically, with labels linking it back to the registry entry.

**Option B: Deploy programmatically using the registry URI scheme**

You can reference models in an InferenceService using the `model-registry://` URI scheme:

```yaml
# manifests/inferenceservice-from-registry.yaml
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  name: gemma4-e4b-from-registry
  annotations:
    serving.kserve.io/deploymentMode: RawDeployment
    security.opendatahub.io/enable-auth: "false"
  labels:
    opendatahub.io/dashboard: "true"
    modelregistry/registered-model-id: "1"
    modelregistry/model-version-id: "2"
spec:
  predictor:
    model:
      modelFormat:
        name: vLLM
      runtime: gemma-4-e4b
      resources:
        limits:
          nvidia.com/gpu: "1"
        requests:
          nvidia.com/gpu: "1"
      storageUri: "s3://models/gemma4-e4b/finetuned-lora-merged/"
```

The `modelregistry/*` labels link the InferenceService back to the registry, so the dashboard shows deployment status on the registry page.

### Step 8: Verify the Registry State in the Dashboard

Return to the dashboard (**AI Hub > Registry > tutorial-registry**) and verify:

1. **gemma4-e4b** appears with 2 versions (v1-base, v2-finetuned)
2. **gemma4-e4b-quantized** appears (created via REST API in Step 5)
3. Click into `gemma4-e4b` > `v2-finetuned` -- you should see:
   - The custom properties (fine_tuning_method, lora_rank, etc.)
   - The artifact URI
   - The deployment status (if you deployed in Step 7)

Stop the port-forward if it is still running:

```bash
kill %1 2>/dev/null
```

## Verification

Run these checks to confirm the lesson objectives are met:

```bash
# Port-forward for API checks
oc port-forward svc/model-registry-tutorial-registry 8080:8080 -n rhoai-model-registries &

# 1. Two registered models exist
curl -s http://localhost:8080/api/model_registry/v1alpha3/registered_models \
  | python3 -c "import sys,json; data=json.load(sys.stdin); print(f'Registered models: {data[\"size\"]}')"
# Expected: Registered models: 2

# 2. gemma4-e4b has 2 versions
curl -s http://localhost:8080/api/model_registry/v1alpha3/registered_models/1/versions \
  | python3 -c "import sys,json; data=json.load(sys.stdin); print(f'Versions: {data[\"size\"]}')"
# Expected: Versions: 2

# 3. Fine-tuned version has metadata
curl -s http://localhost:8080/api/model_registry/v1alpha3/model_versions/2 \
  | python3 -c "import sys,json; v=json.load(sys.stdin); print(f'Version: {v[\"name\"]}'); print(f'Properties: {list(v.get(\"customProperties\",{}).keys())}')"
# Expected: Version: v2-finetuned
#           Properties: ['base_model', 'fine_tuning_method', 'lora_rank', ...]

kill %1 2>/dev/null
```

## Key Takeaways

- The Model Registry supports three access methods: **dashboard UI** for manual workflows, **Python SDK** for notebook/pipeline automation, and **REST API** for CI/CD and cross-language integration.
- `register_model()` in the Python SDK is an **upsert** -- it creates a new RegisteredModel if the name does not exist, or adds a new version if it does.
- **Custom properties** are typed (string, int, float, bool) and stored in the database. **Labels** are simple string tags for filtering.
- There is **no hard delete** -- models and versions are archived (soft-deleted) by setting their state to `ARCHIVED`.
- Deploying from the registry is integrated: use the dashboard's Deploy button, or add `modelregistry/*` labels to your InferenceService to link it back to the registry.
- The REST API follows a predictable CRUD pattern at `/api/model_registry/v1alpha3/` -- useful for building automation in any language.

## Cleanup

To clean up models registered in this lesson (while keeping the registry running):

```python
# Archive models via Python SDK (soft delete)
from model_registry import ModelRegistry

registry = ModelRegistry(
    server_address="http://localhost",
    port=8080,
    author="tutorial-user",
    is_secure=False
)

# Archive the quantized model (created via REST API)
model = registry.get_registered_model("gemma4-e4b-quantized")
model.state = "ARCHIVED"
registry.update(model)
```

Or via REST API:

```bash
# Archive via REST
curl -s -X PATCH http://localhost:8080/api/model_registry/v1alpha3/registered_models/2 \
  -H "Content-Type: application/json" \
  -d '{"state": "ARCHIVED"}'
```

To remove everything from this module (registry, database, namespace):

```bash
# Delete any InferenceServices deployed from the registry
oc delete inferenceservice gemma4-e4b-from-registry -n gemma-model 2>/dev/null

# Delete the ModelRegistry CR
oc delete modelregistry tutorial-registry -n rhoai-model-registries

# Delete the MySQL database
oc delete -f ../1_registry_setup/manifests/mysql-deployment.yaml -n rhoai-model-registries

# Delete the credentials secret
oc delete secret model-registry-db -n rhoai-model-registries

# Delete the namespace
oc delete project rhoai-model-registries
```

## Next Steps

With models registered and versioned, you are ready to evaluate their quality. In [L1-M5.1 — LMEvalJob](../../M5_evaluation/1_lmevaljob/), you will benchmark both the base and fine-tuned Gemma4-e4b using the TrustyAI LMEvalJob CRD, running standardized benchmarks (MMLU, HellaSwag, ARC) to measure whether fine-tuning improved model quality.
