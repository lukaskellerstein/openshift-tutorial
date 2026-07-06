# L1-2.2 — Recipes Catalog: Pre-Built AI Applications

**Level:** Foundations
**Duration:** 45 min

## Overview

Podman AI Lab includes a Recipes Catalog -- a collection of pre-built, containerized AI applications that you can launch with a few clicks. Each recipe bundles application code, a model, and container configuration into a ready-to-run stack. In this lesson you explore the catalog, run the RAG Chatbot recipe with your own documents, and examine how recipes are built so you can understand the architecture behind them.

## Prerequisites

- Completed: [L1-2.1 — Installing and Exploring Podman AI Lab](../1_installing_and_exploring/)
- Podman AI Lab installed with at least one model downloaded
- Podman Desktop running with a Podman machine active
- ~4 GB additional disk space for recipe containers

## Concepts

### What Are Recipes?

Recipes are pre-built AI applications packaged as container compositions. Each recipe is a working application that demonstrates a specific AI pattern:

| Recipe | What It Does | Typical Stack |
|--------|-------------|---------------|
| **Chatbot** | General-purpose conversational AI | Streamlit + LLM |
| **Summarizer** | Condenses long text into summaries | Python + LLM |
| **Code Generation** | Generates code from natural language prompts | Streamlit + code-tuned LLM |
| **RAG Chatbot** | Answers questions grounded in your documents | LangChain + ChromaDB + LLM |
| **Object Detection** | Identifies objects in images | Computer vision model |
| **Audio Processing** | Transcribes and processes speech | Whisper-based model |

The catalog evolves with each release of Podman AI Lab, so you may see additional or different recipes than listed above.

### How Recipes Work

Each recipe is a multi-container application, similar to a `podman compose` stack. When you launch a recipe, Podman AI Lab:

1. **Pulls the application container** -- contains the application code (usually Python with LangChain, Streamlit, or FastAPI).
2. **Starts the model inference container** -- runs `llama.cpp` with the model you select, exposing the OpenAI-compatible API internally.
3. **Connects the containers** -- the application container calls the inference container's API on an internal network.
4. **Exposes a browser UI** -- the application is accessible on a localhost port.

This is the same containerized architecture you would build for production -- a front-end application container talking to a model-serving container over HTTP.

### RAG (Retrieval-Augmented Generation)

The RAG Chatbot recipe is particularly useful because it demonstrates a production-relevant pattern. RAG works in three stages:

1. **Ingest** -- documents are split into chunks and converted into vector embeddings, then stored in a vector database (ChromaDB in this recipe).
2. **Retrieve** -- when a user asks a question, the system finds the most relevant document chunks by comparing the question's embedding against the stored embeddings.
3. **Generate** -- the retrieved chunks are included in the prompt as context, and the LLM generates an answer grounded in your actual documents.

This pattern is how enterprise AI applications avoid hallucination and keep answers tied to real data.

## Step-by-Step

### Step 1: Browse the Recipes Catalog

1. Open **Podman Desktop** and click the **AI Lab** icon.
2. Navigate to **Recipes Catalog**.
3. Browse the available recipes. Each card shows:
   - Recipe name and description
   - The AI pattern it demonstrates
   - Compatible models
   - A screenshot or preview

Take a moment to read through the descriptions. Notice that recipes span different AI modalities: text generation, code, vision, and audio.

### Step 2: Launch the RAG Chatbot Recipe

1. Click the **RAG Chatbot** recipe card.
2. On the recipe detail page, review the description and requirements.
3. Select a **model** for the recipe. Choose the Granite model you downloaded in L1-2.1, or let the recipe download a recommended model.
4. Click **Start**.

Podman AI Lab pulls the application container image (if not already cached), starts the inference server with your selected model, and launches the application. This may take 1-2 minutes on first run.

Once the recipe is running, the UI shows:

- **Status**: Running
- **Port**: the localhost port where the application is accessible
- **Containers**: the individual containers in the recipe stack

5. Click the **Open** button (or navigate to the displayed `localhost` URL in your browser).

The RAG Chatbot interface opens in your browser. It will have a chat input and a way to upload or manage documents.

### Step 3: Test with Default Documents

The recipe comes with sample documents pre-loaded. Try asking a question about the sample content:

```
What topics are covered in the loaded documents?
```

Observe how the response references specific content from the documents. This is RAG in action -- the model is not relying on its training data alone but is retrieving relevant passages from the vector database and using them to construct an answer.

### Step 4: Add Your Own Documents

Now make the recipe useful with your own data:

1. Prepare a few documents. Good candidates:
   - A markdown or text file with technical documentation
   - A PDF of a product guide or specification
   - A set of FAQ entries in plain text

   For example, create a simple test document:

   ```bash
   cat > /tmp/openshift-notes.txt << 'EOF'
   OpenShift Routes vs Kubernetes Ingress

   OpenShift Routes predate Kubernetes Ingress and provide built-in TLS
   termination with three modes: edge, passthrough, and re-encrypt.
   The HAProxy-based router is installed by default, eliminating the need
   to install a separate ingress controller.

   Routes support automatic certificate management and integrate with
   the OpenShift OAuth system for authentication at the edge.

   Key difference: In vanilla Kubernetes you must install and configure
   an ingress controller (NGINX, Traefik, etc.). In OpenShift, the
   router is ready out of the box.
   EOF
   ```

2. In the RAG Chatbot interface, look for a document upload or ingestion option.
3. Upload your document(s).
4. Wait for ingestion to complete (the application will chunk the text, generate embeddings, and store them in ChromaDB).

### Step 5: Query Your Documents

Once your documents are ingested, ask questions that should be answered from your content:

```
How does OpenShift handle TLS termination for Routes?
```

```
What is the difference between OpenShift Routes and Kubernetes Ingress?
```

The answers should be grounded in the document you uploaded. Compare this to asking the same question in the L1-2.1 playground (without RAG) -- the playground model may give a generic answer from training data, while the RAG chatbot cites your specific document content.

### Step 6: Examine the Recipe Architecture

Understanding how a recipe is built will help you build your own AI applications later. Examine the running containers:

```bash
# List the containers started by the recipe
podman ps --filter label=ai-lab-recipe

# If the label filter doesn't match, list all running containers
# and identify the recipe containers by name or image
podman ps --format "table {{.Names}}\t{{.Image}}\t{{.Ports}}"
```

You should see at least two containers:

1. **Application container** -- runs the RAG application (Python, LangChain, Streamlit or similar)
2. **Model inference container** -- runs `llama.cpp` serving the model

Inspect the application container to see its architecture:

```bash
# Replace <container-name> with the actual application container name
podman inspect <container-name> --format '{{.Config.Env}}'
```

Look for environment variables that configure the connection to the model service, such as:

- `MODEL_ENDPOINT` or `INFERENCE_SERVER_URL` -- the URL of the inference container
- `MODEL_NAME` -- which model the application expects
- `EMBEDDING_MODEL` -- the model used for generating embeddings (may be the same or different)

### Step 7: Explore the Recipe Source Code (Optional)

Podman AI Lab recipes are open source. To see how the RAG chatbot is built:

1. In Podman AI Lab, the recipe detail page may include a link to the source repository.
2. Alternatively, browse the [Podman AI Lab Recipes repository](https://github.com/containers/podman-desktop-extension-ai-lab).

Key files to look at in a typical recipe:

```
recipe-name/
  Containerfile          # How the application container is built
  app/
    main.py              # Application entry point
    requirements.txt     # Python dependencies (LangChain, Streamlit, etc.)
  config.yaml            # Model and recipe configuration
```

Notice the pattern: the application code communicates with the model through the OpenAI-compatible API. The application does not load the model directly -- it makes HTTP calls to the inference server, just like you did with `curl` in L1-2.1.

### Step 8: Stop the Recipe

When you are done exploring, stop the recipe to free resources:

1. In Podman AI Lab, navigate to **Running** recipes or the recipe detail page.
2. Click **Stop**.

Or stop via the command line:

```bash
# Stop all recipe-related containers
podman stop $(podman ps --filter label=ai-lab-recipe -q) 2>/dev/null

# If the label doesn't match, stop by name
podman ps --format "{{.Names}}" | grep -i rag
podman stop <container-names>
```

## Verification

| Check | How to verify |
|-------|---------------|
| Recipe catalog accessible | Recipes Catalog page displays available recipes |
| RAG Chatbot running | Recipe status shows "Running" and browser UI is accessible |
| Default documents queryable | Asking about pre-loaded content returns grounded answers |
| Custom documents ingested | Your uploaded documents appear in the application and questions about them return relevant answers |
| Architecture understood | You can identify the application container and inference container, and explain how they communicate |

## Key Takeaways

- **Recipes are ready-to-run AI applications** that demonstrate production-relevant patterns -- chatbots, RAG, summarization, code generation, and more -- all running locally in containers.
- **RAG (Retrieval-Augmented Generation) grounds model responses in your data**, reducing hallucination and making LLMs useful for domain-specific questions. This is the most common enterprise AI pattern.
- **Recipes follow a two-container architecture**: an application container (Python/LangChain) that calls a model inference container (`llama.cpp`) over the OpenAI-compatible API. This is the same separation of concerns you would use in production.
- **Recipes are open source and inspectable** -- you can examine the Containerfile, application code, and configuration to understand exactly how each AI pattern is implemented.
- **Starting from a recipe is faster than starting from scratch** -- modify a working recipe rather than building a RAG pipeline from zero.

## Next Steps

In [L1-2.3 — From Podman AI Lab to Production](../3_to_production/), you will learn how to take what you have built locally -- model choices, application code, and configuration -- and map it to a production deployment on RHEL AI or OpenShift AI.
