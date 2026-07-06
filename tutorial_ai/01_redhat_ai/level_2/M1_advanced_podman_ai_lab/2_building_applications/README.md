# L2-1.2 — Building Applications with Podman AI Lab

**Level:** Practitioner
**Duration:** 1 hour

## Overview

Podman AI Lab's Playground is great for experimentation, but production applications need code. In this lesson you will build a local AI application stack that connects to the Podman AI Lab model service via the OpenAI-compatible API, adds a vector database for retrieval-augmented generation (RAG), and orchestrates everything with Podman Compose. You will also integrate the local model service with developer tools like VS Code Continue and MCP servers.

## Prerequisites

- Completed [L2-1.1 — Custom Models and Catalogs](../1_custom_models_and_catalogs/)
- Podman Desktop with Podman AI Lab extension installed and a model service running
- Python 3.11+ (for Python examples)
- Node.js 18+ (for JavaScript examples)
- Podman Compose installed (`pip install podman-compose` or `pipx install podman-compose`)
- Basic familiarity with REST APIs and at least one of Python or JavaScript

## Concepts

### OpenAI-Compatible API

Every model service in Podman AI Lab exposes an **OpenAI-compatible REST API** on localhost. This means any code, library, or tool that works with the OpenAI API also works with your local model -- zero code changes. The API provides:

- `POST /v1/chat/completions` -- chat-style inference (the most common endpoint)
- `POST /v1/completions` -- text completion
- `POST /v1/embeddings` -- text embeddings (if the model supports it)
- `GET /v1/models` -- list available models

The key insight: **your application code does not care whether the model is running locally in Podman AI Lab, on a RHEL AI server, or on OpenShift AI with KServe.** The API is the same. This is what makes the Red Hat AI three-tier model practical -- you develop locally and deploy anywhere.

### Local AI Application Stack

A typical local AI application has three layers:

1. **Model server** -- Podman AI Lab's model service (llama.cpp serving a GGUF model)
2. **Application logic** -- your code: prompt engineering, chains, agents (LangChain, LangGraph, or plain SDK calls)
3. **Data layer** -- vector database for RAG (Qdrant, ChromaDB), document storage, conversation history

All three run as containers, connected via Podman's container networking.

### Podman Compose

Podman Compose is the Podman-native equivalent of Docker Compose. It reads `docker-compose.yaml` / `podman-compose.yaml` files and manages multi-container stacks. For local AI development, this gives you a one-command setup: `podman-compose up` starts your model server, application, vector database, and UI together.

## Step-by-Step

### Step 1: Start a Model Service in Podman AI Lab

Before writing application code, ensure you have a model service running:

1. Open **Podman Desktop > AI Lab > Model Services**
2. Click **New Model Service**
3. Select a model (e.g., `granite-3.3-8b-instruct` or the model you imported in L2-1.1)
4. Click **Start**
5. Note the **port number** displayed (e.g., `38081`)

Verify the service is running:

```bash
# Replace <PORT> with the actual port from the AI Lab UI
export MODEL_PORT=38081
export MODEL_BASE_URL="http://localhost:${MODEL_PORT}/v1"

# List available models
curl -s ${MODEL_BASE_URL}/models | python3 -m json.tool

# Quick test
curl -s ${MODEL_BASE_URL}/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Say hello in one word."}],
    "max_tokens": 10
  }' | python3 -m json.tool
```

### Step 2: Connect with curl (REST API)

The most direct way to interact with the model service. Useful for debugging, scripting, and understanding the raw API.

**Basic chat completion:**

```bash
curl -s http://localhost:${MODEL_PORT}/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "system", "content": "You are a concise technical assistant."},
      {"role": "user", "content": "What is retrieval-augmented generation?"}
    ],
    "temperature": 0.3,
    "max_tokens": 200
  }' | python3 -m json.tool
```

**Streaming response** (useful for real-time UIs):

```bash
curl -N http://localhost:${MODEL_PORT}/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Explain containers in 3 sentences."}],
    "stream": true,
    "max_tokens": 150
  }'
```

Each streamed chunk arrives as a Server-Sent Event (`data: {...}`). The final chunk contains `"finish_reason": "stop"`.

### Step 3: Connect with Python (OpenAI SDK)

The OpenAI Python SDK works with any OpenAI-compatible endpoint. Point `base_url` to your local model service and set `api_key` to any non-empty string (the local server does not require authentication).

Create a project directory:

```bash
mkdir -p ~/ai-app && cd ~/ai-app
python3 -m venv .venv
source .venv/bin/activate
pip install openai langchain-openai
```

**`chat_basic.py`** -- basic chat with the OpenAI SDK:

```python
"""Basic chat using the OpenAI SDK against Podman AI Lab model service."""

import os
from openai import OpenAI

client = OpenAI(
    base_url=os.getenv("MODEL_BASE_URL", "http://localhost:38081/v1"),
    api_key="not-needed",  # local server, no auth required
)

response = client.chat.completions.create(
    model="granite-3.3-8b-instruct",  # model name from AI Lab
    messages=[
        {"role": "system", "content": "You are a helpful assistant for developers."},
        {"role": "user", "content": "What are the benefits of running LLMs locally?"},
    ],
    temperature=0.7,
    max_tokens=300,
)

print(response.choices[0].message.content)
```

Run it:

```bash
export MODEL_BASE_URL="http://localhost:${MODEL_PORT}/v1"
python3 chat_basic.py
```

**`chat_langchain.py`** -- using LangChain for prompt templates and chains:

```python
"""LangChain integration with Podman AI Lab model service."""

import os
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

llm = ChatOpenAI(
    base_url=os.getenv("MODEL_BASE_URL", "http://localhost:38081/v1"),
    api_key="not-needed",
    model="granite-3.3-8b-instruct",
    temperature=0.3,
    max_tokens=500,
)

# Create a reusable prompt template
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a {role}. Answer concisely."),
    ("user", "{question}"),
])

# Build a chain: prompt -> LLM -> output
chain = prompt | llm

# Invoke the chain
result = chain.invoke({
    "role": "Kubernetes expert",
    "question": "What is the difference between a Deployment and a StatefulSet?",
})

print(result.content)
```

### Step 4: Connect with JavaScript (OpenAI npm Package)

The OpenAI Node.js SDK works identically with the local model service.

```bash
mkdir -p ~/ai-app-js && cd ~/ai-app-js
npm init -y
npm install openai
```

**`chat.mjs`**:

```javascript
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: process.env.MODEL_BASE_URL || "http://localhost:38081/v1",
  apiKey: "not-needed",
});

const response = await client.chat.completions.create({
  model: "granite-3.3-8b-instruct",
  messages: [
    { role: "system", content: "You are a helpful assistant for developers." },
    { role: "user", content: "Explain what Podman is and how it differs from Docker." },
  ],
  temperature: 0.7,
  max_tokens: 300,
});

console.log(response.choices[0].message.content);
```

Run it:

```bash
export MODEL_BASE_URL="http://localhost:${MODEL_PORT}/v1"
node chat.mjs
```

**Streaming example** (`chat_stream.mjs`):

```javascript
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: process.env.MODEL_BASE_URL || "http://localhost:38081/v1",
  apiKey: "not-needed",
});

const stream = await client.chat.completions.create({
  model: "granite-3.3-8b-instruct",
  messages: [
    { role: "user", content: "Write a haiku about containers." },
  ],
  stream: true,
});

for await (const chunk of stream) {
  const content = chunk.choices[0]?.delta?.content;
  if (content) process.stdout.write(content);
}
console.log();
```

### Step 5: Add a Vector Database for RAG

A RAG (Retrieval-Augmented Generation) application needs a vector database to store and search document embeddings. We will use **ChromaDB** as it is lightweight and easy to run in a container.

Start ChromaDB with Podman:

```bash
podman run -d --name chromadb \
  -p 8000:8000 \
  -v chroma-data:/chroma/chroma \
  chromadb/chroma:latest
```

**`rag_app.py`** -- a simple RAG application:

```python
"""Simple RAG application using ChromaDB and Podman AI Lab model service."""

import os
import chromadb
from openai import OpenAI

# Connect to the local model service
llm_client = OpenAI(
    base_url=os.getenv("MODEL_BASE_URL", "http://localhost:38081/v1"),
    api_key="not-needed",
)

# Connect to ChromaDB
chroma_client = chromadb.HttpClient(host="localhost", port=8000)

# Create (or get) a collection for our documents
collection = chroma_client.get_or_create_collection(
    name="company_docs",
    metadata={"hnsw:space": "cosine"},
)

# --- Ingestion: add documents to the vector database ---
# ChromaDB uses its own default embedding model for simplicity.
# In production, use a dedicated embedding model (e.g., Granite Embedding).
documents = [
    "To reset your password, go to Settings > Security > Change Password.",
    "VPN access requires submitting a ticket to IT with your manager's approval.",
    "The CI/CD pipeline runs on every push to main. Check Jenkins for build status.",
    "Code reviews require at least two approvals before merging.",
    "On-call rotations are managed in PagerDuty. Swap shifts via the #on-call Slack channel.",
]

collection.upsert(
    documents=documents,
    ids=[f"doc_{i}" for i in range(len(documents))],
)
print(f"Indexed {len(documents)} documents into ChromaDB.")

# --- Query: search for relevant documents and generate an answer ---
query = "How do I get VPN access?"

# Step 1: Retrieve relevant documents
results = collection.query(query_texts=[query], n_results=3)
context_docs = results["documents"][0]

# Step 2: Build a prompt with retrieved context
context = "\n".join(f"- {doc}" for doc in context_docs)
prompt = f"""Use the following context to answer the question. If the context
does not contain the answer, say "I don't have information about that."

Context:
{context}

Question: {query}

Answer:"""

# Step 3: Generate the answer using the local LLM
response = llm_client.chat.completions.create(
    model="granite-3.3-8b-instruct",
    messages=[
        {"role": "system", "content": "You are a helpful internal support assistant."},
        {"role": "user", "content": prompt},
    ],
    temperature=0.3,
    max_tokens=200,
)

print(f"\nQuestion: {query}")
print(f"Answer: {response.choices[0].message.content}")
```

Install dependencies and run:

```bash
pip install chromadb
python3 rag_app.py
```

### Step 6: Orchestrate with Podman Compose

Now combine everything into a single stack: model server, RAG application, vector database, and a web UI. Create a `podman-compose.yaml` file.

```bash
mkdir -p ~/ai-stack && cd ~/ai-stack
```

**`podman-compose.yaml`**:

```yaml
version: "3.8"

services:
  # --- Model Server ---
  # Uses llama.cpp to serve a GGUF model with an OpenAI-compatible API.
  # In production, this would be vLLM on RHEL AI or KServe on OpenShift AI.
  model-server:
    image: ghcr.io/ggerganov/llama.cpp:server
    ports:
      - "8081:8080"
    volumes:
      - ~/ai-models:/models:ro
    command: >
      --model /models/granite-3.3-2b-instruct-Q4_K_M.gguf
      --host 0.0.0.0
      --port 8080
      --ctx-size 4096
      --n-gpu-layers 0
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s

  # --- Vector Database ---
  # ChromaDB for document storage and similarity search.
  # In production, consider pgvector (PostgreSQL) or Milvus.
  vector-db:
    image: chromadb/chroma:latest
    ports:
      - "8000:8000"
    volumes:
      - chroma-data:/chroma/chroma

  # --- RAG Application ---
  # Your application code: connects to model server and vector DB.
  app:
    build:
      context: ./app
      dockerfile: Containerfile
    ports:
      - "8501:8501"
    environment:
      MODEL_BASE_URL: "http://model-server:8080/v1"
      MODEL_NAME: "granite-3.3-2b-instruct"
      CHROMA_HOST: "vector-db"
      CHROMA_PORT: "8000"
    depends_on:
      model-server:
        condition: service_healthy
      vector-db:
        condition: service_started

volumes:
  chroma-data:
```

Create the application directory:

```bash
mkdir -p ~/ai-stack/app
```

**`app/Containerfile`**:

```dockerfile
FROM registry.access.redhat.com/ubi9/python-311:latest

WORKDIR /opt/app-root/src

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8501"]
```

**`app/requirements.txt`**:

```
fastapi==0.115.0
uvicorn==0.30.0
openai==1.50.0
chromadb==0.5.0
jinja2==3.1.4
python-multipart==0.0.9
```

**`app/main.py`**:

```python
"""RAG application for the local AI stack."""

import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from openai import OpenAI
import chromadb

app = FastAPI(title="Local RAG App")
templates = Jinja2Templates(directory="templates")

# Configuration from environment variables — same vars work on OpenShift
llm = OpenAI(
    base_url=os.getenv("MODEL_BASE_URL", "http://localhost:8081/v1"),
    api_key="not-needed",
)
model_name = os.getenv("MODEL_NAME", "granite-3.3-2b-instruct")

chroma = chromadb.HttpClient(
    host=os.getenv("CHROMA_HOST", "localhost"),
    port=int(os.getenv("CHROMA_PORT", "8000")),
)
collection = chroma.get_or_create_collection("documents")


@app.post("/api/ingest")
async def ingest(request: Request):
    """Ingest documents into the vector database."""
    body = await request.json()
    docs = body.get("documents", [])
    if not docs:
        return {"status": "error", "message": "No documents provided"}

    collection.upsert(
        documents=docs,
        ids=[f"doc_{i}" for i in range(len(docs))],
    )
    return {"status": "ok", "count": len(docs)}


@app.post("/api/query")
async def query(request: Request):
    """Answer a question using RAG."""
    body = await request.json()
    question = body.get("question", "")

    # Retrieve relevant context
    results = collection.query(query_texts=[question], n_results=3)
    context_docs = results["documents"][0] if results["documents"] else []

    # Build the augmented prompt
    context = "\n".join(f"- {doc}" for doc in context_docs)
    prompt = f"""Answer the question using the context below.
If the context doesn't help, say so.

Context:
{context}

Question: {question}"""

    # Generate answer
    response = llm.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=300,
    )

    return {
        "answer": response.choices[0].message.content,
        "sources": context_docs,
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
```

**`app/templates/index.html`**:

```html
<!DOCTYPE html>
<html>
<head>
  <title>Local RAG Application</title>
  <style>
    body { font-family: sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; }
    textarea { width: 100%; padding: 10px; font-size: 14px; }
    button { padding: 10px 20px; margin: 10px 5px 10px 0; cursor: pointer; }
    .answer { background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 10px 0; }
    .sources { font-size: 12px; color: #666; margin-top: 10px; }
    .sources li { margin: 5px 0; }
  </style>
</head>
<body>
  <h1>Local RAG Application</h1>

  <h3>Ingest Documents</h3>
  <textarea id="docs" rows="5" placeholder="Enter documents, one per line..."></textarea>
  <br><button onclick="ingest()">Ingest</button>
  <span id="ingest-status"></span>

  <h3>Ask a Question</h3>
  <textarea id="question" rows="2" placeholder="Ask something..."></textarea>
  <br><button onclick="ask()">Ask</button>

  <div id="result"></div>

  <script>
    async function ingest() {
      const docs = document.getElementById('docs').value.split('\n').filter(d => d.trim());
      const res = await fetch('/api/ingest', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({documents: docs})
      });
      const data = await res.json();
      document.getElementById('ingest-status').textContent = `Ingested ${data.count} documents.`;
    }

    async function ask() {
      const question = document.getElementById('question').value;
      document.getElementById('result').innerHTML = '<p>Thinking...</p>';
      const res = await fetch('/api/query', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({question})
      });
      const data = await res.json();
      let html = `<div class="answer">${data.answer}</div>`;
      if (data.sources && data.sources.length > 0) {
        html += '<div class="sources"><strong>Sources used:</strong><ul>';
        data.sources.forEach(s => { html += `<li>${s}</li>`; });
        html += '</ul></div>';
      }
      document.getElementById('result').innerHTML = html;
    }
  </script>
</body>
</html>
```

Create the templates directory and start the stack:

```bash
mkdir -p ~/ai-stack/app/templates
# Copy index.html into ~/ai-stack/app/templates/

# Start the entire stack
cd ~/ai-stack
podman-compose up --build -d
```

Monitor the startup:

```bash
# Watch logs (model server takes longest to start)
podman-compose logs -f model-server

# Check all services are running
podman-compose ps
```

### Step 7: Test the Full Stack

Once all services are healthy:

```bash
# 1. Ingest some documents
curl -s -X POST http://localhost:8501/api/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "documents": [
      "To request GPU resources, submit a ticket in ServiceNow under category Infrastructure.",
      "Our staging environment uses OpenShift 4.16 on AWS with 3 worker nodes.",
      "Database backups run nightly at 2 AM UTC. Retention policy is 30 days.",
      "To deploy to production, create a PR to the main branch and get 2 approvals.",
      "Monitoring dashboards are available at grafana.internal.company.com."
    ]
  }'

# 2. Ask a question
curl -s -X POST http://localhost:8501/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How do I deploy to production?"}' | python3 -m json.tool
```

Open `http://localhost:8501` in your browser for the web UI.

### Step 8: Integrate with Development Tools

#### VS Code + Continue (AI Code Assistant)

[Continue](https://continue.dev/) is an open-source AI code assistant for VS Code that supports any OpenAI-compatible endpoint. Configure it to use your local Podman AI Lab model service:

1. Install the **Continue** extension in VS Code
2. Open Continue settings (`~/.continue/config.json` or via the Continue sidebar)
3. Add a local model configuration:

```json
{
  "models": [
    {
      "title": "Granite Local (Podman AI Lab)",
      "provider": "openai",
      "model": "granite-3.3-8b-instruct",
      "apiBase": "http://localhost:38081/v1",
      "apiKey": "not-needed"
    }
  ]
}
```

Now you can use Granite as your AI code assistant: highlight code, ask questions, generate tests -- all running on your local machine with zero data leaving your network.

#### Connecting MCP Servers to Local Model Service

Model Context Protocol (MCP) servers extend AI assistants with tools and data sources. If you are using an MCP-compatible client (Claude Desktop, Continue, or a custom agent), you can point it at your local model service as the LLM backend.

Example: configure a custom LangChain agent that uses MCP tools with your local model:

```python
"""Agent using local model service with custom tools."""

import os
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate

llm = ChatOpenAI(
    base_url=os.getenv("MODEL_BASE_URL", "http://localhost:38081/v1"),
    api_key="not-needed",
    model="granite-3.3-8b-instruct",
    temperature=0.1,
)


@tool
def get_pod_count(namespace: str) -> str:
    """Get the number of pods running in a Kubernetes namespace."""
    import subprocess
    result = subprocess.run(
        ["kubectl", "get", "pods", "-n", namespace, "--no-headers"],
        capture_output=True, text=True,
    )
    lines = [l for l in result.stdout.strip().split("\n") if l]
    return f"There are {len(lines)} pods in namespace '{namespace}'."


tools = [get_pod_count]
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a Kubernetes operations assistant. Use the tools available to answer questions."),
    ("user", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

result = executor.invoke({"input": "How many pods are running in the default namespace?"})
print(result["output"])
```

> **Note:** Tool-calling capability depends on the model. Granite 3.3 8B and larger models support function calling via the OpenAI-compatible API. Smaller models may not support this reliably.

### Step 9: Environment Variable Configuration Pattern

Notice that every component in this stack uses environment variables for configuration. This is deliberate -- the same application code runs locally, on RHEL AI, and on OpenShift AI. Only the environment variables change:

| Variable | Local (Podman Compose) | RHEL AI | OpenShift AI |
|----------|----------------------|---------|-------------|
| `MODEL_BASE_URL` | `http://model-server:8080/v1` | `http://rhel-ai-host:8000/v1` | `https://model-route.apps.cluster/v1` |
| `MODEL_NAME` | `granite-3.3-2b-instruct` | `granite-3.3-8b-instruct` | `granite-3.3-8b-instruct` |
| `CHROMA_HOST` | `vector-db` | `chroma.internal` | `vector-db.namespace.svc` |
| `CHROMA_PORT` | `8000` | `8000` | `8000` |

This pattern -- **build locally with Podman Compose, deploy anywhere with the same images** -- is the core workflow of the Red Hat AI ecosystem.

## Verification

| Check | How to verify |
|-------|---------------|
| Model server responds | `curl http://localhost:8081/v1/models` returns model list |
| Python SDK works | `python3 chat_basic.py` prints a coherent response |
| JavaScript SDK works | `node chat.mjs` prints a coherent response |
| ChromaDB is running | `curl http://localhost:8000/api/v1/heartbeat` returns `{"nanosecond heartbeat": ...}` |
| RAG ingest works | `/api/ingest` returns `{"status": "ok", "count": N}` |
| RAG query works | `/api/query` returns an answer with source documents |
| Full stack is up | `podman-compose ps` shows all 3 services running |
| Web UI loads | `http://localhost:8501` displays the RAG application |
| Continue integration | VS Code Continue responds using the local model |

## Key Takeaways

- The OpenAI-compatible API is the universal interface across the Red Hat AI stack. Code written against your local Podman AI Lab model service works unchanged against RHEL AI (vLLM) and OpenShift AI (KServe). Switch environments by changing a URL, not your code.
- Python (`openai`, `langchain-openai`) and JavaScript (`openai`) SDKs connect to local model services with a single configuration change: set `base_url`/`baseURL` to your local endpoint.
- Podman Compose orchestrates multi-container AI stacks (model server + application + vector DB) with a single `podman-compose up` command. This is the local equivalent of a Kubernetes deployment.
- The environment variable pattern (`MODEL_BASE_URL`, `MODEL_NAME`) makes your application portable across all three tiers of the Red Hat AI ecosystem without code changes.
- Developer tools like VS Code Continue can use local models as AI code assistants, keeping all data on your machine -- a significant advantage for proprietary codebases.

## Cleanup

```bash
# Stop and remove the Podman Compose stack
cd ~/ai-stack
podman-compose down --volumes

# Stop the standalone ChromaDB container (if running separately)
podman stop chromadb 2>/dev/null
podman rm chromadb 2>/dev/null

# Stop the model service in Podman AI Lab UI:
# AI Lab > Model Services > select your model > Stop

# Remove project directories (optional)
rm -rf ~/ai-app ~/ai-app-js ~/ai-stack
```

## Next Steps

In [L2-2.1 — Modular Model Customization](../../M2_model_customization/1_modular_model_customization/), you will dive deep into RHEL AI's model customization workflow using the modular Python libraries: Docling for document processing, SDG Hub for synthetic data generation, and Training Hub for fine-tuning. The models you customize there can be converted to GGUF and brought back into the local development stack you built in this lesson.
