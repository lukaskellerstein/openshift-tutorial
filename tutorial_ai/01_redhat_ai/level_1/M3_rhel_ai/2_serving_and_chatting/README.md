# L1-3.2 — Serving and Chatting with Models on RHEL AI

**Level:** Foundations
**Duration:** 45 min

## Overview

The primary use case for RHEL AI is model inference. This lesson walks through downloading a Granite model, serving it with the Red Hat AI Inference Server (via the `ilab` CLI), chatting with it interactively, and using the OpenAI-compatible API from external applications. By the end, you will have a running inference endpoint and know how to connect to it from any language or tool that speaks the OpenAI API format.

## Prerequisites

- Completed: [L1-3.1 — RHEL AI Architecture: Inference and Model Adaptation](../1_architecture_and_concepts/)
- RHEL AI instance with GPU access (or CPU for small models)
- SSH access to the RHEL AI server

## Concepts

### Red Hat AI Inference Server

When you run `ilab model serve`, RHEL AI starts a **Red Hat AI Inference Server** — vLLM v0.13.0 under the hood. It exposes an OpenAI-compatible API at `http://localhost:8000/v1` and supports PagedAttention for efficient GPU memory use, continuous batching for high throughput, and tensor parallelism across multiple GPUs.

This is the same vLLM engine used by OpenShift AI's KServe runtime. Code you write against this API works at every tier — Podman AI Lab, RHEL AI, and OpenShift AI — by changing only the endpoint URL.

### System Profiles

Running `ilab config init` auto-detects your hardware (GPU type, VRAM, CPU capabilities) and selects a **system profile**. Profiles configure optimal inference settings — batch sizes, memory allocation, quantization defaults — for your specific GPU. You can override the profile in `~/.config/instructlab/config.yaml` if needed.

### Model Download

The `ilab model download` command pulls models from HuggingFace by default. You can also download from OCI registries for air-gapped or enterprise environments. Downloaded models are stored in `~/.local/share/instructlab/models/`.

## Step-by-Step

### Step 1: Initialize the Environment

Initialize InstructLab to detect your hardware and create the configuration file:

```bash
ilab config init
```

This creates `~/.config/instructlab/config.yaml` with your auto-detected system profile. Review the output to confirm your GPU was detected correctly.

### Step 2: Download a Model

Download the default Granite model:

```bash
ilab model download
```

Or specify a particular model:

```bash
ilab model download --repository RedHatAI/granite-4.1-8b-instruct
```

The download may take several minutes depending on your connection speed. Models are stored in `~/.local/share/instructlab/models/`.

### Step 3: List Downloaded Models

Verify the model is available:

```bash
ilab model list
```

You should see the downloaded model with its path and size.

### Step 4: Serve the Model

Start the inference server:

```bash
ilab model serve
```

Or specify a model path explicitly:

```bash
ilab model serve --model-path ~/.local/share/instructlab/models/granite-4.1-8b-instruct
```

The server starts on port 8000 by default. Watch the startup logs — you will see vLLM report GPU memory allocation, the loaded model, and the API endpoint. Wait until you see a message indicating the server is ready before proceeding.

### Step 5: Chat Interactively

Open a **new terminal** (the server occupies the first one) and start an interactive chat session:

```bash
ilab model chat
```

Type questions and get responses in a REPL-style interface. Try a few prompts:

```
>>> What is OpenShift?
>>> Explain the difference between a Pod and a Deployment in Kubernetes.
>>> Write a Python function that reads a CSV file.
```

Type `/quit` to exit the chat.

### Step 6: Use the API with curl

In another terminal, call the inference server directly using the OpenAI-compatible API:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "granite-4.1-8b-instruct",
    "messages": [{"role": "user", "content": "What is OpenShift?"}],
    "temperature": 0.3,
    "max_tokens": 256
  }'
```

The response is standard OpenAI format — any library or tool that supports the OpenAI API can connect to this endpoint.

You can also list available models:

```bash
curl http://localhost:8000/v1/models
```

### Step 7: Use the API with Python

Install the OpenAI Python SDK if not already present, then connect to the local server:

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="unused")

response = client.chat.completions.create(
    model="granite-4.1-8b-instruct",
    messages=[{"role": "user", "content": "Explain pods in Kubernetes."}]
)
print(response.choices[0].message.content)
```

The `api_key` is required by the SDK but not validated by the local server — any string works. To connect from a remote machine, replace `localhost` with the server's IP address.

### Step 8: Upload a Model to a Registry (Optional)

After serving or fine-tuning a model, you can push it to a registry for team sharing or scaling to OpenShift AI:

```bash
ilab model upload --model-path ~/.local/share/instructlab/models/granite-4.1-8b-instruct \
  --destination docker://registry.example.com/models/granite-4.1-8b-instruct:latest
```

This packages the model as an OCI artifact that can be pulled by OpenShift AI's KServe runtime.

## Verification

| Check | Command | Expected Result |
|-------|---------|-----------------|
| Model downloaded | `ilab model list` | Model name and path displayed |
| Server running | `curl http://localhost:8000/v1/models` | JSON response listing the served model |
| Chat working | `ilab model chat` | Interactive responses to prompts |
| API responding | `curl http://localhost:8000/v1/chat/completions -H "Content-Type: application/json" -d '{"model":"granite-4.1-8b-instruct","messages":[{"role":"user","content":"Hello"}]}'` | JSON response with `choices[0].message.content` |
| Python SDK connecting | Run the Python script from Step 7 | Printed model response |

## Key Takeaways

- `ilab model serve` starts a Red Hat AI Inference Server (vLLM) with an OpenAI-compatible API on port 8000.
- The same API format works at all three tiers (Podman AI Lab, RHEL AI, OpenShift AI) — application code changes only the endpoint URL between environments.
- `ilab model chat` provides a quick interactive REPL for testing models before integrating them into applications.
- Any OpenAI-compatible SDK or tool (Python, curl, LangChain, LlamaIndex) can connect to the server without modification.
- `ilab model upload` enables pushing models to OCI registries for team sharing or scaling to OpenShift AI.

## Next Steps

Continue to [L1-3.3 — Fine-Tuning with InstructLab](../3_fine_tuning_with_ilab/) to learn how to adapt a Granite model to your domain using the InstructLab taxonomy-based workflow.
