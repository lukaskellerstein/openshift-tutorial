# L1-M2.3 -- OpenAI-Compatible API Deep Dive

**Level:** Foundations
**Duration:** 30 min

## Overview

vLLM implements the OpenAI API specification, which means any tool, library, or SDK built for OpenAI works with your self-hosted model -- no code changes beyond swapping the base URL. In this lesson you will explore vLLM's OpenAI-compatible endpoints, learn every important request parameter, and integrate with the Python `openai` SDK and LangChain. If you have written code against the OpenAI API, you already know how to talk to your self-hosted model.

## Prerequisites

- Completed: [L1-M2.2 -- Deploying Gemma4-e4b](../2_deploying_gemma/) (model deployed and running)
- OpenShift cluster with the Gemma 4 E4B InferenceService healthy in the `gemma-model` namespace
- `oc` CLI authenticated to the cluster
- Python 3.10+ with `pip` available locally
- Install Python dependencies:

```bash
pip install openai langchain-openai
```

## K8s Context

On vanilla Kubernetes with KServe, the model serving API is identical -- vLLM exposes the same OpenAI-compatible endpoints regardless of the platform. The differences are in how you reach the endpoint:

- **Kubernetes:** You access the model through an Istio Ingress Gateway or a Kubernetes Ingress resource. You typically need to configure an Ingress controller, set up TLS with cert-manager, and manage authentication through Istio's RequestAuthentication or an external solution.
- **OpenShift AI:** The endpoint is exposed as an OpenShift Route with built-in edge TLS termination. No Ingress controller installation needed. Authentication can be toggled with a single annotation (`security.opendatahub.io/enable-auth`).

The API calls themselves are identical on both platforms. Everything you learn in this lesson about the request format, parameters, and SDK usage applies equally to KServe on vanilla Kubernetes.

## Concepts

### vLLM's OpenAI-Compatible API

vLLM ships with a built-in OpenAI-compatible API server (the `vllm.entrypoints.openai.api_server` entrypoint you saw in the ServingRuntime manifest from L1-M2.2). It implements the following endpoints:

| Endpoint | Purpose | Supported by Gemma 4? |
|----------|---------|----------------------|
| `/v1/chat/completions` | Chat-style interaction with system/user/assistant messages | Yes |
| `/v1/completions` | Raw text completion (legacy, less common) | Yes |
| `/v1/models` | List available models | Yes |
| `/v1/embeddings` | Generate text embeddings | **No** -- requires an embedding model |

**Important:** The `/v1/embeddings` endpoint is only available when serving an embedding model (e.g., `nomic-embed-text`, `bge-large`). Gemma 4 is a generative language model, not an embedding model. If you need embeddings, you must deploy a separate embedding model.

### The OpenAI Compatibility Advantage

The key insight of this lesson: because vLLM implements the OpenAI API specification, the entire ecosystem of OpenAI-compatible tools works with your self-hosted model. This includes:

- The official `openai` Python SDK
- LangChain and LlamaIndex
- Any application that accepts a configurable OpenAI base URL
- curl and any HTTP client

You switch from OpenAI's hosted service to your self-hosted model by changing one line: the `base_url`. No other code changes are needed.

### Request Parameters Reference

These parameters control how the model generates text. They apply to both `/v1/chat/completions` and `/v1/completions`:

| Parameter | Type | Range | Description |
|-----------|------|-------|-------------|
| `temperature` | float | 0.0 -- 2.0 | Controls randomness. 0 = deterministic (always pick the most likely token). 1 = balanced. >1 = more creative/random. |
| `max_tokens` | int | 1 -- model max | Maximum number of tokens in the generated response. |
| `top_p` | float | 0.0 -- 1.0 | Nucleus sampling: only consider tokens whose cumulative probability mass exceeds this value. Lower = more focused. |
| `stream` | bool | true/false | Enable Server-Sent Events (SSE) streaming. Tokens are sent as they are generated. |
| `stop` | list[str] | -- | List of strings that stop generation when encountered. |
| `presence_penalty` | float | -2.0 -- 2.0 | Positive values discourage the model from repeating topics already mentioned. |
| `frequency_penalty` | float | -2.0 -- 2.0 | Positive values discourage the model from repeating the same tokens frequently. |
| `n` | int | 1+ | Number of completions to generate for each prompt. |

**Tip:** For most use cases, start with `temperature=0.7` and `max_tokens=200`. Adjust from there.

## Step-by-Step

### Step 1: Get the Inference Endpoint URL

The model deployed in L1-M2.2 is exposed through an OpenShift Route. Retrieve the URL:

```bash
ROUTE_URL=$(oc get route -l serving.kserve.io/inferenceservice=gemma-4-e4b -n gemma-model -o jsonpath='{.items[0].spec.host}')
export INFERENCE_URL="https://${ROUTE_URL}"
echo $INFERENCE_URL
```

Expected output:

```
https://gemma-4-e4b-gemma-model.apps.<cluster-domain>
```

### Step 2: List Available Models

Use the `/v1/models` endpoint to see which models are available:

```bash
curl -s "${INFERENCE_URL}/v1/models" | python3 -m json.tool
```

Expected output:

```json
{
    "object": "list",
    "data": [
        {
            "id": "gemma-4-e4b",
            "object": "model",
            "created": 1719849600,
            "owned_by": "vllm",
            "root": "google/gemma-4-E4B-it",
            "parent": null,
            "permission": []
        }
    ]
}
```

The model `id` is `gemma-4-e4b` -- this is the value set by `--served-model-name={{.Name}}` in the ServingRuntime, which resolves to the InferenceService name.

### Step 3: Basic Chat Completion with curl

Send a chat completion request using the `/v1/chat/completions` endpoint:

```bash
curl -s "${INFERENCE_URL}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma-4-e4b",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Explain Kubernetes in 3 sentences."}
    ],
    "max_tokens": 200,
    "temperature": 0.7
  }' | python3 -m json.tool
```

Expected output (content will vary):

```json
{
    "id": "chatcmpl-abc123",
    "object": "chat.completion",
    "created": 1719849700,
    "model": "gemma-4-e4b",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "Kubernetes is an open-source container orchestration platform that automates the deployment, scaling, and management of containerized applications. It groups containers into logical units called Pods and manages their lifecycle across a cluster of machines. Kubernetes provides features like service discovery, load balancing, self-healing, and rolling updates out of the box."
            },
            "finish_reason": "stop"
        }
    ],
    "usage": {
        "prompt_tokens": 25,
        "completion_tokens": 62,
        "total_tokens": 87
    }
}
```

Note the `usage` object -- it reports token counts for the prompt and completion, useful for tracking costs and capacity.

### Step 4: Streaming Responses with curl

Streaming sends tokens as they are generated using Server-Sent Events (SSE). Add `"stream": true` to the request:

```bash
curl -N "${INFERENCE_URL}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma-4-e4b",
    "messages": [{"role": "user", "content": "Write a haiku about containers."}],
    "max_tokens": 50,
    "stream": true
  }'
```

Expected output (each line is a separate SSE event):

```
data: {"id":"chatcmpl-xyz","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}

data: {"id":"chatcmpl-xyz","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"Steel"},"finish_reason":null}]}

data: {"id":"chatcmpl-xyz","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":" walls"},"finish_reason":null}]}

...

data: {"id":"chatcmpl-xyz","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

Key things to notice about the SSE format:

- Each event is prefixed with `data: `
- Each chunk contains a `delta` object with the incremental content (not the full response)
- The first chunk has the role (`assistant`) but no content
- The final chunk has `"finish_reason": "stop"` and an empty delta
- The stream ends with `data: [DONE]`

### Step 5: Chat Completion with the Python openai SDK

The `openai` Python SDK works with any OpenAI-compatible endpoint. Point it at your self-hosted model:

```python
from openai import OpenAI

client = OpenAI(
    base_url=f"{INFERENCE_URL}/v1",
    api_key="not-needed"  # Auth is disabled on this endpoint
)

response = client.chat.completions.create(
    model="gemma-4-e4b",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is OpenShift AI?"}
    ],
    max_tokens=200,
    temperature=0.7
)

print(response.choices[0].message.content)
```

Since auth is disabled on the endpoint (via the `security.opendatahub.io/enable-auth: "false"` annotation from L1-M2.2), the `api_key` can be any non-empty string.

Run the full example script:

```bash
export INFERENCE_URL="https://$(oc get route -l serving.kserve.io/inferenceservice=gemma-4-e4b -n gemma-model -o jsonpath='{.items[0].spec.host}')"
python3 scripts/chat_completion.py
```

### Step 6: Streaming with the Python SDK

Streaming in the Python SDK returns an iterator that yields chunks as they arrive:

```python
stream = client.chat.completions.create(
    model="gemma-4-e4b",
    messages=[{"role": "user", "content": "Explain PagedAttention in vLLM."}],
    max_tokens=300,
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()
```

Run the streaming example:

```bash
python3 scripts/streaming_chat.py
```

### Step 7: Token Usage Tracking

Every non-streaming response includes a `usage` object with token counts:

```json
{
  "usage": {
    "prompt_tokens": 25,
    "completion_tokens": 150,
    "total_tokens": 175
  }
}
```

In the Python SDK:

```python
response = client.chat.completions.create(
    model="gemma-4-e4b",
    messages=[{"role": "user", "content": "Hello!"}],
    max_tokens=50
)

print(f"Prompt tokens:     {response.usage.prompt_tokens}")
print(f"Completion tokens: {response.usage.completion_tokens}")
print(f"Total tokens:      {response.usage.total_tokens}")
```

Token tracking is important for:

- **Capacity planning:** Know how many tokens per second your model handles
- **Cost estimation:** If you are comparing self-hosted vs. hosted API costs
- **Debugging:** Unexpectedly high prompt token counts may indicate inefficient prompts

### Step 8: Structured Output (JSON Mode)

vLLM supports guided decoding to produce structured JSON output. Use `response_format` to request JSON:

```python
response = client.chat.completions.create(
    model="gemma-4-e4b",
    messages=[
        {"role": "user", "content": "List 3 benefits of Kubernetes as JSON with keys: benefit, description"}
    ],
    response_format={"type": "json_object"},
    max_tokens=300
)

import json
data = json.loads(response.choices[0].message.content)
print(json.dumps(data, indent=2))
```

Run the structured output example:

```bash
python3 scripts/structured_output.py
```

**Note:** JSON mode constrains the model's output to valid JSON. The model will follow the structure you describe in the prompt, but you should always validate the output -- the model may produce valid JSON that does not match your expected schema.

### Step 9: Using with LangChain

LangChain's `ChatOpenAI` class works with any OpenAI-compatible endpoint. Point it at your self-hosted model:

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url=f"{INFERENCE_URL}/v1",
    api_key="not-needed",
    model="gemma-4-e4b",
    temperature=0.7,
    max_tokens=200
)

response = llm.invoke("What is a Pod in Kubernetes?")
print(response.content)
```

This is the power of OpenAI compatibility: existing LangChain code that was written for OpenAI works with your self-hosted model by changing only `base_url` and `api_key`. Chains, agents, retrievers, and all other LangChain abstractions work without modification.

Run the LangChain example:

```bash
python3 scripts/langchain_example.py
```

## Verification

Run through these checks to verify the lesson:

1. **List models:**

```bash
curl -s "${INFERENCE_URL}/v1/models" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Model: {d[\"data\"][0][\"id\"]}')"
```

Expected: `Model: gemma-4-e4b`

2. **Chat completion returns valid JSON:**

```bash
curl -s "${INFERENCE_URL}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model":"gemma-4-e4b","messages":[{"role":"user","content":"Say hello"}],"max_tokens":10}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])"
```

Expected: A short greeting from the model.

3. **Python SDK works:**

```bash
python3 -c "
from openai import OpenAI
import os
client = OpenAI(base_url=os.environ['INFERENCE_URL']+'/v1', api_key='x')
r = client.chat.completions.create(model='gemma-4-e4b', messages=[{'role':'user','content':'Say hi'}], max_tokens=10)
print(r.choices[0].message.content)
"
```

4. **Streaming works:**

```bash
python3 -c "
from openai import OpenAI
import os
client = OpenAI(base_url=os.environ['INFERENCE_URL']+'/v1', api_key='x')
for chunk in client.chat.completions.create(model='gemma-4-e4b', messages=[{'role':'user','content':'Count to 3'}], max_tokens=20, stream=True):
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end='')
print()
"
```

Expected: Tokens printed incrementally.

## K8s vs OpenShift AI Comparison

| Aspect | Kubernetes (KServe) | OpenShift AI |
|--------|-------------------|--------------|
| API specification | OpenAI-compatible (vLLM) | OpenAI-compatible (vLLM) -- identical |
| Endpoint exposure | Istio Ingress Gateway or K8s Ingress | OpenShift Route (auto-created) |
| TLS | Manual cert-manager + Ingress TLS config | Edge TLS termination by default |
| Endpoint discovery | `kubectl get ingress` or `kubectl get vs` | `oc get route -l serving.kserve.io/inferenceservice=<name>` |
| Authentication | Istio RequestAuthentication / custom | Toggle with annotation (`enable-auth`) |
| Model name resolution | Manual `--served-model-name` config | `{{.Name}}` template resolves to InferenceService name |
| SDK compatibility | Any OpenAI-compatible SDK | Any OpenAI-compatible SDK -- identical |
| Monitoring | Manual Prometheus setup | Built-in Prometheus scraping via annotations |

The API layer is platform-independent. The differences are in networking (Route vs Ingress), TLS (automatic vs manual), and authentication (annotation toggle vs manual config).

## Key Takeaways

- vLLM implements the OpenAI API spec -- any tool built for OpenAI works with your self-hosted model by changing only the `base_url`
- The `/v1/chat/completions` endpoint is the primary interface; `/v1/models` lists available models; `/v1/embeddings` requires a dedicated embedding model (Gemma 4 does not support it)
- Request parameters like `temperature`, `max_tokens`, `top_p`, and `stream` give you fine-grained control over generation behavior
- Token usage tracking (`prompt_tokens`, `completion_tokens`, `total_tokens`) is built into every response for capacity planning and cost estimation
- LangChain, the `openai` SDK, and any OpenAI-compatible library work without modification -- the self-hosted endpoint is a drop-in replacement for the OpenAI API

## Cleanup

No new resources were created in this lesson -- we used the model deployed in L1-M2.2. If you want to clean up, follow the cleanup steps in [L1-M2.2](../2_deploying_gemma/).

## Next Steps

In the next lesson, [L1-M2.4 -- Autoscaling Model Endpoints](../4_autoscaling/), you will configure horizontal scaling for your model endpoint so it can handle varying load -- scaling up under traffic and scaling to zero when idle.
