# L1-M2.3 — From Podman AI Lab to Production

**Level:** Foundations
**Duration:** 30 min

## Overview

Podman AI Lab is a prototyping environment. At some point, the model and application you tested locally need to run in production -- on a server with RHEL AI or at scale on an OpenShift AI cluster. This lesson maps each piece of your local Podman AI Lab setup to its production equivalent, walks through the export workflow, and covers how to import custom models and create your own recipe entries.

## Prerequisites

- Completed: [L1-M2.1 — Installing and Exploring Podman AI Lab](../1_installing_and_exploring/)
- Completed: [L1-M2.2 — Recipes Catalog](../2_recipes_catalog/)
- Familiarity with the Podman AI Lab Model Catalog, Model Services, Playground, and Recipes

## Concepts

### The Local-to-Production Gap

What you built in the previous two lessons is a prototype:

- A GGUF-quantized model running on CPU via `llama.cpp`
- An application container talking to that model over localhost
- Configuration tuned by hand in the playground

Production requires different choices:

- Full-precision or GPU-optimized model formats (not GGUF) running on GPU hardware
- A proper model serving runtime (vLLM, TGI) with autoscaling, health checks, and monitoring
- Application containers in a CI/CD pipeline with proper image registries
- Configuration managed declaratively in YAML, not through a GUI

The good news: the workflow is designed so that every decision you make in Podman AI Lab maps directly to a production configuration. The API compatibility (OpenAI format) means your application code does not change -- only the infrastructure underneath it does.

### The Three-Tier Deployment Model

Red Hat's AI stack is organized into three tiers. Podman AI Lab is the entry point:

```
+------------------------------------------------------------------+
|                    Red Hat AI Deployment Tiers                     |
+------------------------------------------------------------------+
|                                                                    |
|  +------------------+     +----------------+     +--------------+ |
|  |  Podman AI Lab   |     |    RHEL AI     |     | OpenShift AI | |
|  |  (Desktop)       | --> |    (Server)    | --> |  (Cluster)   | |
|  +------------------+     +----------------+     +--------------+ |
|                                                                    |
|  WHERE:  Developer laptop   Single server /     Kubernetes cluster |
|                              bare metal         (multi-node)       |
|                                                                    |
|  MODEL    GGUF (quantized)   Full precision     Full precision     |
|  FORMAT:  via llama.cpp      via vLLM            via vLLM / TGIS  |
|                                                                    |
|  GPU:     Optional (CPU OK)  Required            Required          |
|                              (NVIDIA/AMD/Intel)  (NVIDIA/AMD/Intel)|
|                                                                    |
|  SCALE:   Single user        Single server       Multi-model,      |
|           prototyping        production           auto-scaling,     |
|                                                   multi-tenant     |
|                                                                    |
|  WHAT     Choose model,      Serve, fine-tune,   Serve at scale,   |
|  YOU DO:  test prompts,      customize with      notebooks, MLOps, |
|           build recipes      InstructLab          pipelines         |
+------------------------------------------------------------------+
```

Each tier builds on the previous one. What you learn and decide at one tier carries forward to the next.

### What Carries Forward, What Changes

| Component | Podman AI Lab | RHEL AI | OpenShift AI |
|-----------|--------------|---------|-------------|
| **Model choice** | Selected in Catalog | Same model, full-precision format | Same model, served via InferenceService |
| **Model format** | GGUF (quantized) | SafeTensors / full precision | SafeTensors / full precision |
| **Serving runtime** | `llama.cpp` (CPU) | vLLM (GPU) | vLLM via ServingRuntime (GPU) |
| **API format** | OpenAI-compatible | OpenAI-compatible | OpenAI-compatible |
| **Application code** | Recipe container | Same code, different base_url | Same code, different base_url |
| **Configuration** | Playground UI | CLI flags / config files | YAML CRDs (InferenceService, ServingRuntime) |
| **Documents (RAG)** | Local ChromaDB | PostgreSQL + pgvector | PostgreSQL + pgvector on OpenShift |

The critical point: the **API format stays the same** at every tier. Application code that calls `http://localhost:XXXXX/v1/chat/completions` in Podman AI Lab will call the same endpoint path on RHEL AI or OpenShift AI -- only the hostname and port change.

## Step-by-Step

### Step 1: Map Your Model Choice to Production

In L1-M2.1, you chose a model from the catalog (e.g., `granite-3.1-8b-instruct`). Here is how that choice maps to each production tier:

**RHEL AI:**
RHEL AI ships with Granite models pre-installed. The `ilab` CLI serves models via vLLM in full precision:

```bash
# On a RHEL AI server (preview -- you'll do this in M3)
ilab model serve --model-path granite-3.1-8b-instruct
```

The model runs on GPU with vLLM instead of `llama.cpp`. Same model, different runtime, better performance.

**OpenShift AI:**
On OpenShift AI, models are deployed via an `InferenceService` custom resource that references a `ServingRuntime`:

```yaml
# Preview -- you'll create this in the OpenShift AI tutorial
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  name: granite-8b-instruct
spec:
  predictor:
    model:
      modelFormat:
        name: vLLM
      runtime: vllm-runtime
      storage:
        key: s3-credentials
        path: granite-3.1-8b-instruct
```

The model binary moves from your local disk to an S3-compatible bucket (MinIO, ODF, or AWS S3). The serving runtime manages GPU allocation, batching, and autoscaling.

### Step 2: Map Your Application Code to Production

The RAG Chatbot recipe you ran in L1-M2.2 is a containerized application. To deploy it in production:

1. **The application code is already containerized** -- the recipe's Containerfile is your starting point.
2. **Change the inference endpoint** -- swap the local URL for the production model service URL:

```python
# Local (Podman AI Lab)
client = OpenAI(
    base_url="http://localhost:XXXXX/v1",
    api_key="not-needed"
)

# Production (OpenShift AI)
client = OpenAI(
    base_url="https://granite-8b-instruct-my-project.apps.cluster.example.com/v1",
    api_key=os.environ["API_KEY"]  # token-based auth in production
)
```

3. **Push the container image** to an image registry (Quay.io, OpenShift internal registry).
4. **Deploy as a standard OpenShift Deployment** with a Service and Route.

The application code itself does not change. Only the environment configuration (endpoint URL, credentials) differs between local and production.

### Step 3: Map Your Configuration to Production

The playground settings you tuned in L1-M2.1 (temperature, max tokens, system prompt) become production configuration:

| Playground Setting | Production Equivalent |
|---|---|
| Temperature: `0.3` | Request parameter or ServingRuntime default |
| Max Tokens: `512` | Request parameter or model server `--max-model-len` |
| System Prompt | Application-level configuration (environment variable or config map) |
| Top-p: `0.9` | Request parameter |
| Model selection | `InferenceService` model path / `ilab model serve --model-path` |

Export your tested configuration into a format you can use later:

```bash
# Document your working configuration
cat > model-config.env << 'EOF'
MODEL_NAME=granite-3.1-8b-instruct
TEMPERATURE=0.3
MAX_TOKENS=512
TOP_P=0.9
SYSTEM_PROMPT="You are a helpful assistant that answers questions based on provided context."
EOF
```

This file serves as a reference when you configure the model serving runtime in RHEL AI or OpenShift AI.

### Step 4: Import a Custom Model (Optional)

Podman AI Lab is not limited to the built-in catalog. You can import any GGUF model:

1. Download a GGUF model file from Hugging Face or another source:

   ```bash
   # Example: download a specific quantized model
   # (replace with an actual model URL)
   curl -L -o ~/Models/my-custom-model.gguf \
     "https://huggingface.co/TheBloke/some-model/resolve/main/model-Q4_K_M.gguf"
   ```

2. In Podman AI Lab, navigate to the **Catalog**.
3. Look for an **Import** or **Add Model** option.
4. Point it to the downloaded GGUF file on your local filesystem.
5. Once imported, the model appears in the catalog and can be used in the playground, model services, and recipes just like any built-in model.

This is useful for testing models from Hugging Face that are not yet in the curated catalog, or for working with models that your organization has fine-tuned.

### Step 5: Understand the Full Workflow

Here is the end-to-end workflow from prototype to production:

```
 PODMAN AI LAB (Desktop)              RHEL AI / OPENSHIFT AI (Production)
 ========================              ====================================

 1. Browse Model Catalog          -->  Select same model from registry
    Download GGUF model                Upload full-precision model to S3

 2. Test in Playground            -->  Configure ServingRuntime parameters
    Tune temperature, tokens           (same values, YAML format)

 3. Run Recipe (RAG Chatbot)      -->  Deploy application container
    Test with documents                Connect to production model service
                                       Use production vector database

 4. Validate via curl / SDK       -->  Validate via same curl / SDK
    http://localhost:XXXXX/v1          https://model.apps.cluster.com/v1

 5. Export decisions:
    - Model name + version
    - Configuration parameters
    - Application container image
    - Document corpus
```

The transition is not a rewrite -- it is a configuration change. The model, the API, and the application architecture remain the same.

### Step 6: Review Reference Material

Red Hat provides a structured learning path for this transition:

- **"From Podman AI Lab to OpenShift AI"** -- a Red Hat Developer learning path that walks through the full workflow with a concrete example
- **Podman AI Lab documentation** at [podman-desktop.io/docs/ai-lab](https://podman-desktop.io/docs/ai-lab) -- covers custom model import and recipe development
- **RHEL AI documentation** at [docs.redhat.com](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux_ai/1.5) -- the next tier in the deployment model

These resources complement the hands-on work you will do in M3 (RHEL AI) and in the OpenShift AI tutorial.

## Verification

| Check | How to verify |
|-------|---------------|
| Model mapping understood | You can explain how a GGUF model in Podman AI Lab corresponds to a full-precision model served by vLLM on RHEL AI / OpenShift AI |
| Application portability clear | You can describe what changes (endpoint URL, auth) and what stays the same (API format, application code) when moving to production |
| Configuration exported | You have a `model-config.env` file (or equivalent notes) documenting your tested model choice and parameters |
| Custom model import understood | You know how to add a GGUF model from Hugging Face to the Podman AI Lab catalog |
| Workflow end-to-end understood | You can trace the path from "prototype in AI Lab" to "deploy on OpenShift AI" and identify what happens at each step |

## Key Takeaways

- **Podman AI Lab is the starting point, not the destination.** It is designed for rapid prototyping -- choosing models, testing prompts, validating AI patterns -- before committing to production infrastructure.
- **The OpenAI-compatible API is the bridge between tiers.** Application code that works against `localhost` in Podman AI Lab works against vLLM on RHEL AI and OpenShift AI with only a URL change.
- **Model format changes across tiers but the model identity stays the same.** GGUF (quantized, CPU) locally becomes SafeTensors (full precision, GPU) in production. Same Granite model, different packaging for different hardware.
- **Configuration transitions from GUI to YAML.** Playground settings become `InferenceService` and `ServingRuntime` parameters in OpenShift AI. Document your working settings so the transition is straightforward.
- **Custom models and recipes make Podman AI Lab extensible.** Import any GGUF model or create your own recipes to prototype with your organization's specific models and use cases.

## Next Steps

In [L1-M3.1 — RHEL AI Architecture and Concepts](../../M3_rhel_ai/1_architecture_and_concepts/), you will explore the next tier: RHEL AI -- a bootable container image that turns a bare-metal server into a purpose-built AI platform with InstructLab for model customization and vLLM for GPU-accelerated serving.
