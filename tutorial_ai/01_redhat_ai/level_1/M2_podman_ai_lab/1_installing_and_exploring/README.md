# L1-2.1 — Installing and Exploring Podman AI Lab

**Level:** Foundations
**Duration:** 45 min

## Overview

Podman AI Lab is a Podman Desktop extension that turns your local machine into an AI development environment. In this lesson you install the extension, download an open-source Granite model, run it as an OpenAI-compatible inference server, and interact with it through both the built-in playground and a `curl` command. By the end you will have a fully local LLM stack running entirely in containers -- no cloud API keys required.

## Prerequisites

- Podman Desktop **1.28+** installed ([podman-desktop.io](https://podman-desktop.io))
- Podman **6.0+** (installed alongside Podman Desktop or separately)
- At least **12 GB free RAM** (a 7B-parameter model in GGUF format typically needs 6-8 GB)
- ~10 GB free disk space for models

Verify your environment before proceeding:

```bash
podman --version    # 6.0 or later
podman machine info # confirm a machine is running
```

## Concepts

### What is Podman AI Lab?

Podman AI Lab is an extension for Podman Desktop that provides a local, containerized AI development workflow. It bundles three capabilities into a single UI:

1. **Model Catalog** -- a curated list of open-source models you can download with one click. Models are stored in GGUF format, the quantized format designed for efficient CPU inference.
2. **Model Services** -- an inference server (backed by `llama.cpp`) that exposes any downloaded model as an OpenAI-compatible REST API on `localhost`.
3. **Playground** -- an interactive chat interface where you can test prompts, tune parameters, and compare models side by side.

### Why GGUF?

GGUF (GPT-Generated Unified Format) is the standard format for quantized models that run on commodity hardware. Quantization shrinks a model from its full-precision training weights (often 30+ GB for a 7B model) down to 4-5 GB while preserving most of its quality. This is what makes "LLM on a laptop" practical. Podman AI Lab uses `llama.cpp` as the runtime, which loads GGUF files directly.

### Why Granite?

IBM Granite is Red Hat's strategic model family. All Granite models are Apache 2.0 licensed, meaning you can use, modify, and distribute them freely -- including in production. The catalog includes several Granite variants (3B, 8B, different quantization levels). We will use a Granite model throughout this tutorial to stay consistent with the broader Red Hat AI ecosystem.

### OpenAI-compatible API

When you start a Model Service, Podman AI Lab launches a container running `llama.cpp` configured to serve the model over HTTP. The API follows the OpenAI chat completions format (`/v1/chat/completions`), so any application, SDK, or tool that speaks the OpenAI protocol works out of the box -- no code changes needed.

## Step-by-Step

### Step 1: Install the Podman AI Lab Extension

1. Open **Podman Desktop**.
2. Click the **Extensions** icon in the left sidebar (puzzle piece).
3. Select the **Catalog** tab.
4. Find **Podman AI Lab** in the list (or search for "AI Lab").
5. Click **Install**.

The extension installs in seconds. Once complete, a new **AI Lab** icon appears in the left sidebar.

> **Tip:** If you do not see the extension in the catalog, update Podman Desktop to version 1.28 or later.

### Step 2: Explore the Model Catalog

1. Click the **AI Lab** icon in the left sidebar.
2. Select **Catalog** from the AI Lab navigation.

You will see a list of available models organized by category. Each entry shows:

- **Model name** -- e.g., `granite-3.1-8b-instruct`
- **Size** -- download size in GB
- **Format** -- GGUF (all models in the catalog use this format)
- **Description** -- what the model is designed for (chat, code, embedding, etc.)

Browse the catalog and note the variety: Granite models from IBM, Gemma from Google, Qwen from Alibaba, Mistral, and others. All are open-weight models that run locally.

### Step 3: Download a Granite Model

1. In the catalog, find **granite-3.1-8b-instruct** (or the latest Granite instruct model available).
2. Click the **Download** button.

The download takes a few minutes depending on your connection (the 8B GGUF is typically 4-5 GB). You can monitor progress in the download indicator.

> **Note:** If you have limited RAM (< 16 GB), choose a smaller model such as `granite-3.1-3b-instruct` instead. The 3B model requires roughly 3-4 GB of RAM and still provides good results for experimentation.

### Step 4: Test the Model in the Playground

1. Navigate to **Playground** in the AI Lab section.
2. Click **New Playground**.
3. Select your downloaded Granite model from the model dropdown.
4. In the chat input, type a test prompt:

```
What is OpenShift and how does it differ from Kubernetes?
```

5. Press **Send** and observe the response streaming in.

Now experiment with the playground settings:

- **System Prompt** -- Add instructions that shape the model's behavior. Try:
  ```
  You are a senior DevOps engineer who explains concepts concisely with practical examples.
  ```
- **Temperature** -- Controls randomness. `0.1` for factual answers, `0.8` for creative responses. Start with `0.3`.
- **Max Tokens** -- Limits response length. Set to `512` for concise answers or `2048` for detailed explanations.
- **Top-p** -- Nucleus sampling threshold. `0.9` is a good default. Lower values make responses more focused.

Try the same prompt with different temperature values to see how the output changes.

#### Side-by-Side Comparison

If you downloaded more than one model, use the playground's comparison feature:

1. Click **New Playground** again to open a second playground panel.
2. Select a different model.
3. Send the same prompt to both and compare the responses side by side.

This is useful for evaluating which model best fits your use case before committing to one for development.

### Step 5: Start a Model Service

The playground is great for interactive testing, but real applications need an API. Start a Model Service to expose the Granite model as an HTTP endpoint.

1. Navigate to **Services** in the AI Lab section.
2. Click **New Model Service**.
3. Select your downloaded Granite model.
4. Click **Start**.

Podman AI Lab launches a container running `llama.cpp` with the model loaded. Once the service is running, note the **endpoint URL** shown in the UI -- it will be something like:

```
http://localhost:XXXXX/v1
```

The port is dynamically assigned. Copy the full URL including the port number.

### Step 6: Test the API with curl

Open a terminal and send a request to the model service. Replace `XXXXX` with the port shown in the Podman AI Lab UI:

```bash
curl http://localhost:XXXXX/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "granite-3.1-8b-instruct",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Explain Kubernetes pods in two sentences."}
    ],
    "temperature": 0.3,
    "max_tokens": 256
  }'
```

You should receive a JSON response with the model's completion:

```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "A Kubernetes pod is the smallest deployable unit..."
      }
    }
  ]
}
```

This is the same API shape that OpenAI's `gpt-4` uses. Any OpenAI-compatible SDK or library (LangChain, LlamaIndex, the official `openai` Python package) can point at this local endpoint.

### Step 7: Test with the OpenAI Python SDK (Optional)

If you have Python available, you can confirm SDK compatibility:

```bash
pip install openai
```

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:XXXXX/v1",  # replace XXXXX with your port
    api_key="not-needed"                    # local server ignores the key
)

response = client.chat.completions.create(
    model="granite-3.1-8b-instruct",
    messages=[
        {"role": "user", "content": "List 3 benefits of containerized AI inference."}
    ],
    temperature=0.3
)

print(response.choices[0].message.content)
```

This demonstrates a key property of Podman AI Lab: code written against the local Model Service will work unchanged when you later point it at a production inference endpoint on OpenShift AI.

## Verification

Confirm the following before moving on:

| Check | How to verify |
|-------|---------------|
| Podman AI Lab installed | AI Lab icon visible in Podman Desktop sidebar |
| Model downloaded | Model appears in Catalog with a checkmark or "Downloaded" status |
| Playground working | You can send a prompt and receive a streamed response |
| Model Service running | Services page shows the model with "Running" status |
| API responding | `curl` to the `/v1/chat/completions` endpoint returns a JSON response |

## Key Takeaways

- **Podman AI Lab is a local AI development environment** that runs entirely in containers on your machine -- no cloud APIs, no GPU required for initial exploration.
- **The Model Catalog provides curated open-source models** in GGUF format, ready for download and use. Granite models are Apache 2.0 licensed and are Red Hat's strategic choice.
- **Model Services expose an OpenAI-compatible API** backed by `llama.cpp`, so any code or tool that speaks the OpenAI protocol works without modification.
- **The Playground enables rapid experimentation** with prompts, system instructions, and parameter tuning before writing any application code.
- **Code portability is built in** -- the same OpenAI-compatible API format is used from local development through to production on OpenShift AI.

## Next Steps

In [L1-2.2 — Recipes Catalog](../2_recipes_catalog/), you will explore Podman AI Lab's pre-built AI applications -- containerized recipes for chatbots, RAG systems, code generation, and more -- and run a RAG chatbot with your own documents.
