# L2-M1.1 -- RAG Architecture with OGX

**Level:** Practitioner
**Duration:** 45 min

## Overview

Retrieval-Augmented Generation (RAG) is the dominant pattern for grounding LLM responses in external knowledge without fine-tuning. In Level 1 you deployed a model and fine-tuned it -- but fine-tuning is expensive, slow, and the model's knowledge is frozen at training time. RAG solves this by retrieving relevant documents at query time and injecting them into the prompt, giving the model access to current, domain-specific information.

This lesson lays the architectural foundation for the entire RAG module. You will learn how OGX (Open GenAI Stack) provides a unified API layer for RAG on OpenShift AI, compare three reference architectures for building RAG systems on the platform, and understand when to choose each approach.

## Prerequisites

- Completed: Level 1 of this OpenShift AI tutorial (all modules)
- Completed: `tutorial_ai/ogx/` sub-tutorial (Level 1) -- OGX fundamentals, deployment, and basic API usage
- Familiarity with LLM concepts: embeddings, vector similarity, prompt engineering
- No cluster required -- this is a conceptual lesson

## K8s Context

On vanilla Kubernetes, building a RAG system means assembling disparate pieces yourself: a vector database (Weaviate, Qdrant, Milvus, pgvector), an embedding model served via some inference runtime, a retrieval layer (typically LangChain or LlamaIndex), and an LLM endpoint. You deploy each component independently, manage their networking, and write the glue code that connects retrieval to generation. There is no standard Kubernetes API for "do RAG" -- you build it from primitives.

OpenShift AI offers three paths that reduce this integration burden to varying degrees: OGX's built-in RAG API (the most integrated), a framework-based approach using LangChain with vLLM and a vector database (the most flexible), or Red Hat's Validated Patterns (pre-built, tested GitOps deployments).

## Concepts

### RAG Fundamentals Recap

You already know how LLMs work: they generate text based on patterns learned during training. The problem is that training data has a cutoff date, lacks domain-specific knowledge, and the model will confidently hallucinate when it doesn't know something.

RAG addresses this with a simple pipeline:

1. **Query** -- the user asks a question
2. **Retrieve** -- find relevant documents from an external knowledge base using vector similarity search
3. **Augment** -- inject the retrieved documents into the LLM prompt as context
4. **Generate** -- the LLM generates a response grounded in the retrieved context

```mermaid
graph LR
    Q[User Query] --> E[Embed Query]
    E --> R[Vector Similarity Search]
    R --> D[(Vector Database)]
    D --> C[Retrieved Documents]
    C --> A[Augmented Prompt]
    A --> L[LLM Inference]
    L --> Resp[Grounded Response]

    subgraph "Retrieval"
        E
        R
        D
        C
    end

    subgraph "Generation"
        A
        L
        Resp
    end
```

The key components are:

| Component | Purpose | OpenShift AI Options |
|-----------|---------|---------------------|
| Embedding model | Convert text to vector representations | vLLM (`/v1/embeddings`), OGX Inference API |
| Vector database | Store and search document embeddings | pgvector, Milvus, FAISS, Elasticsearch |
| Retrieval layer | Query the vector DB and rank results | OGX Memory/RAG API, LangChain, LlamaIndex |
| LLM | Generate responses from retrieved context | vLLM (`/v1/chat/completions`), OGX Inference API |
| Orchestration | Wire the pipeline together | OGX RAG API, LangChain, custom code |

This lesson focuses on the architecture and orchestration layer -- the vector database and document ingestion are covered in subsequent lessons (L2-M1.2 and L2-M1.3).

---

### OGX (Open GenAI Stack / Llama Stack) Architecture

OGX is Red Hat's productization of Meta's [Llama Stack](https://github.com/meta-llama/llama-stack) project. Despite the "Llama" name, OGX is not limited to Llama models -- it is a provider-agnostic API layer that standardizes how applications interact with GenAI infrastructure.

Think of OGX as a GenAI middleware: it provides a unified REST API that abstracts away the underlying inference engine, vector store, and tool execution framework. Your application talks to OGX; OGX talks to vLLM, pgvector, MCP servers, and other backends.

#### OGX API Surface

OGX exposes five core APIs:

```mermaid
graph TB
    subgraph "OGX / Llama Stack APIs"
        INF["Inference API<br/>/v1/inference/chat-completion<br/>/v1/inference/embeddings"]
        MEM["Memory API<br/>/v1/memory/banks<br/>/v1/memory/insert<br/>/v1/memory/query"]
        RAG["RAG API<br/>/v1/rag/insert<br/>/v1/rag/query"]
        TOOL["Tool API<br/>/v1/tool-runtime/invoke<br/>/v1/tool-runtime/list"]
        AGENT["Agent API<br/>/v1alpha/agents/create<br/>/v1alpha/agents/turn"]
    end

    subgraph "Backends (Provider Plugins)"
        V1[vLLM]
        V2[TGI]
        V3[Ollama]
        V4["23+ other providers"]
        PG[pgvector]
        MV[Milvus]
        FS[FAISS]
        MCP1[MCP Servers]
        EXT[External Tools]
    end

    INF --> V1 & V2 & V3 & V4
    MEM --> PG & MV & FS
    RAG --> MEM
    RAG --> INF
    TOOL --> MCP1 & EXT
    AGENT --> INF & MEM & TOOL

    APP[Your Application] --> INF & MEM & RAG & TOOL & AGENT

    style RAG fill:#2d5016,stroke:#4a8c2a,color:#fff
    style MEM fill:#2d5016,stroke:#4a8c2a,color:#fff
```

| API | Purpose | Key Endpoints | RAG Role |
|-----|---------|---------------|----------|
| **Inference API** | Model serving -- chat completions, embeddings, text completions | `/v1/inference/chat-completion`, `/v1/inference/embeddings` | Generates embeddings for documents and queries; generates the final response |
| **Memory API** | Vector store management -- create memory banks, insert documents, query by similarity | `/v1/memory/banks`, `/v1/memory/insert`, `/v1/memory/query` | Stores document embeddings and performs retrieval |
| **RAG API** | Built-in retrieval-augmented generation -- combines Memory and Inference APIs | `/v1/rag/insert`, `/v1/rag/query` | The integrated RAG pipeline -- insert docs and ask questions in one API |
| **Tool API** | External tool integration -- invoke tools, list available tools | `/v1/tool-runtime/invoke`, `/v1/tool-runtime/list` | Optional: agents can use tools alongside RAG for richer workflows |
| **Agent API** | Autonomous agent orchestration -- create agents, execute multi-turn conversations with tool use | `/v1alpha/agents/create`, `/v1alpha/agents/turn` | Optional: agents can combine RAG with tool calling for complex tasks |

The RAG API is the key differentiator for this module. It wraps the Memory API (retrieval) and Inference API (generation) into a single pipeline, so your application can insert documents and query them with augmented generation through one API layer.

#### OGX Is Not Limited to Llama Models

A common misconception: because OGX is built on Llama Stack, people assume it only works with Llama models. This is incorrect.

OGX supports **23+ inference providers** through its plugin architecture:

| Provider Category | Examples |
|-------------------|----------|
| Self-hosted inference servers | vLLM, TGI (Text Generation Inference), Ollama, llama.cpp |
| Cloud APIs | AWS Bedrock, Google Vertex AI, Azure AI |
| Model families | Llama, Gemma, Granite, Mistral, Qwen, Phi, Falcon, and any model the provider supports |

In this tutorial, you deployed Gemma4-e4b on vLLM in Level 1. OGX can use that same vLLM endpoint as its inference backend -- you configure OGX to point at your existing `InferenceService`, and OGX routes inference requests to it. No model migration required.

The same flexibility applies to vector stores (pgvector, Milvus, FAISS, Chroma, Weaviate) and tool runtimes (MCP servers, custom functions).

---

### OGX Operator on OpenShift AI

The OGX Operator (`llamastackoperator`) is a Tier 1 DSC component -- you enable it by setting `managementState: Managed` in the `DataScienceCluster` CR:

```yaml
apiVersion: datasciencecluster.opendatahub.io/v2
kind: DataScienceCluster
metadata:
  name: default-dsc
spec:
  components:
    llamastackoperator:
      managementState: Managed    # Enable OGX
    kserve:
      managementState: Managed    # Required for inference backend
    dashboard:
      managementState: Managed
```

The operator introduces the `LlamaStackDistribution` CRD (expected to be renamed to an OGX-specific name in a future release). This CRD defines an OGX server instance:

```yaml
apiVersion: llamastack.io/v1alpha1
kind: LlamaStackDistribution
metadata:
  name: my-ogx-server
  labels:
    app: my-ogx-server
spec:
  distribution: remote-vllm     # Use vLLM as the inference backend
  config:
    inference:
      provider: remote::vllm
      url: http://gemma4-e4b:8080/v1   # Your existing vLLM endpoint
    memory:
      provider: remote::pgvector
      url: postgresql://user:pass@pgvector:5432/vectors
```

**Status:** Technology Preview as of OpenShift AI 3.4-3.5. The operator is functional but APIs may change between releases. Production deployments should plan for API migration when it reaches GA.

**Deployment model:** The operator creates a pod running the Llama Stack server, configured to use the backends you specify (vLLM for inference, pgvector for memory, etc.). Your application connects to the OGX server's API endpoint, and OGX handles routing to the backends.

```mermaid
graph LR
    subgraph "OpenShift AI Cluster"
        subgraph "User's Data Science Project"
            APP[Your RAG App] --> OGX[OGX Server Pod<br/>LlamaStackDistribution CR]
            OGX --> VLLM[vLLM Pod<br/>InferenceService CR]
            OGX --> PGV[(pgvector Pod)]
        end

        subgraph "Operator Namespace"
            OP[OGX Operator<br/>llamastackoperator] -.manages.-> OGX
        end
    end
```

---

### RAG Reference Architectures on OpenShift AI

There are three viable approaches for building RAG on OpenShift AI. Each makes different tradeoffs between integration, flexibility, and operational maturity.

#### Architecture 1: OGX-Native RAG

Use OGX's built-in Memory API and RAG API for a fully integrated approach. The OGX server manages the entire pipeline -- embedding, storage, retrieval, and augmented generation -- behind a single API.

```mermaid
graph TB
    subgraph "OGX-Native RAG"
        Client[Client Application]
        OGX_S[OGX Server]
        
        Client -->|"POST /v1/rag/insert<br/>(documents)"| OGX_S
        Client -->|"POST /v1/rag/query<br/>(question)"| OGX_S
        
        OGX_S -->|"Embed + Store"| VDB[(pgvector / Milvus)]
        OGX_S -->|"Embed Query + Retrieve"| VDB
        OGX_S -->|"Generate with Context"| VLLM[vLLM Endpoint]
    end

    style OGX_S fill:#2d5016,stroke:#4a8c2a,color:#fff
```

**How it works:**
1. Insert documents via `POST /v1/rag/insert` -- OGX chunks, embeds, and stores them in the configured vector database
2. Query via `POST /v1/rag/query` -- OGX embeds the query, retrieves relevant chunks, constructs an augmented prompt, and calls the LLM
3. The response includes the generated answer and the source documents used

**Advantages:**
- Fewest moving parts -- one API for the entire RAG pipeline
- Consistent API across different backends (swap pgvector for Milvus without changing application code)
- Native integration with OGX Agent API (agents can use RAG as a built-in capability)
- Platform-managed lifecycle via the OGX Operator

**Limitations:**
- Technology Preview -- API may change
- Less control over chunking strategy, retrieval parameters, and prompt construction
- Tied to OGX's supported vector store providers
- Newer ecosystem with less community tooling and documentation

#### Architecture 2: LangChain + vLLM + Vector DB

Use LangChain (or LlamaIndex) as the orchestration framework, vLLM directly for inference, and a separately deployed vector database. This is the "bring your own framework" approach.

```mermaid
graph TB
    subgraph "LangChain-Based RAG"
        Client[Client Application]
        LC[LangChain / LlamaIndex<br/>Application Pod]
        
        Client -->|"REST API"| LC
        
        LC -->|"Embed documents/queries<br/>POST /v1/embeddings"| VLLM_E[vLLM - Embedding Model]
        LC -->|"Retrieve similar docs"| VDB[(pgvector / Milvus)]
        LC -->|"Generate with context<br/>POST /v1/chat/completions"| VLLM_L[vLLM - LLM]
    end

    style LC fill:#1a3a5c,stroke:#2d6da3,color:#fff
```

**How it works:**
1. You write a LangChain application that orchestrates the RAG pipeline in Python
2. The application calls vLLM's `/v1/embeddings` endpoint directly to embed documents and queries
3. It queries the vector database using LangChain's vector store integrations
4. It constructs the augmented prompt and calls vLLM's `/v1/chat/completions` for generation
5. You deploy the application as a standard OpenShift Deployment + Service + Route

**Advantages:**
- Maximum flexibility -- full control over chunking, retrieval, re-ranking, prompt templates
- Mature ecosystem -- LangChain has integrations for hundreds of tools and services
- Large community with extensive documentation, examples, and support
- No dependency on Technology Preview components
- Easy to add advanced RAG patterns: hybrid search, re-ranking, multi-step retrieval, query decomposition

**Limitations:**
- More components to deploy and manage independently
- Application code owns the RAG logic -- more code to write and maintain
- Framework lock-in (LangChain or LlamaIndex)
- No unified management through a single CRD

#### Architecture 3: Validated Patterns

Use Red Hat's pre-built, tested deployment patterns. The "AI Generation with LLM and RAG" Validated Pattern provides a GitOps-deployable RAG stack with ArgoCD, including model serving, vector database, and a sample RAG application.

```mermaid
graph TB
    subgraph "Validated Pattern: RAG with LLM"
        ARGO[ArgoCD] -->|"GitOps sync"| NS[OpenShift Namespace]
        
        subgraph NS[Deployed Components]
            APP_VP[RAG Application]
            VLLM_VP[vLLM Model Server]
            VDB_VP[(Vector Database)]
            IC[Ingestion Pipeline]
        end
        
        APP_VP --> VLLM_VP
        APP_VP --> VDB_VP
        IC --> VDB_VP
    end

    GIT[(Git Repository<br/>Helm + Kustomize)] --> ARGO

    style ARGO fill:#5c3a1a,stroke:#a36d2d,color:#fff
```

**How it works:**
1. Clone the Validated Pattern repository
2. Configure your environment (cluster, storage, model choice)
3. ArgoCD deploys the entire stack: model server, vector database, RAG application, ingestion pipeline
4. The pattern includes tested, version-locked component configurations

**Advantages:**
- Fastest path to a working RAG deployment -- minutes, not hours
- Tested by Red Hat -- component versions are validated together
- GitOps-native -- infrastructure as code from day one
- Good starting point that you can customize

**Limitations:**
- Opinionated architecture -- may not match your requirements
- Less flexibility in component choices
- Pattern updates may lag behind component releases
- May include components you don't need

**Reference:** [Validated Patterns -- AI Generation with LLM and RAG](https://validatedpatterns.io/patterns/rag-llm-gitops/)

---

### Decision Matrix

Use this matrix to choose the right RAG architecture for your use case:

| Criterion | OGX-Native RAG | LangChain + vLLM + Vector DB | Validated Patterns |
|-----------|---------------|-------------------------------|-------------------|
| **Complexity** | Low -- single API | Medium -- multiple components, custom code | Low -- GitOps deployment |
| **Flexibility** | Limited to OGX's supported patterns | Maximum -- full control over every step | Medium -- customizable but opinionated |
| **Maturity** | Technology Preview | GA (all components are stable) | GA (tested configurations) |
| **Setup time** | ~30 min (after OGX operator is installed) | ~2-3 hours (deploy and wire components) | ~30 min (clone, configure, deploy) |
| **Advanced RAG patterns** | Basic retrieval + generation | Hybrid search, re-ranking, query decomposition, multi-step retrieval | Depends on pattern version |
| **Agent integration** | Native -- OGX Agent API includes RAG | Via LangChain tool abstraction | Not included by default |
| **Framework dependency** | OGX / Llama Stack | LangChain or LlamaIndex | Varies by pattern |
| **Operational overhead** | Low -- operator-managed | Higher -- manage each component | Low -- ArgoCD-managed |
| **Best for** | Prototyping, OGX-native agents, platform-integrated RAG | Production RAG with custom requirements, existing LangChain codebases | Quick POCs, reference architectures, GitOps-first teams |
| **OpenShift AI integration** | Deep -- DSC component, dashboard features (AutoRAG) | Moderate -- uses KServe endpoints, standard deployments | Moderate -- uses OpenShift primitives |

#### Recommendation by Scenario

- **"I want RAG working as fast as possible for a demo"** -- Validated Patterns or OGX-Native RAG
- **"I have an existing LangChain codebase I want to deploy on OpenShift"** -- LangChain + vLLM + Vector DB
- **"I want to use AutoRAG (dashboard) to optimize my RAG pipeline"** -- OGX-Native RAG (AutoRAG requires `llamastackoperator`)
- **"I'm building agents that need RAG as one of several capabilities"** -- OGX-Native RAG (Agent API integrates RAG natively)
- **"I need full control over retrieval, re-ranking, and prompt construction"** -- LangChain + vLLM + Vector DB
- **"I want a GitOps-managed RAG deployment from day one"** -- Validated Patterns

In this module, you will implement both OGX-native RAG (L2-M1.4 Option A) and LangChain-based RAG (L2-M1.4 Option B) so you can make an informed choice for your own use case.

---

### How OGX Fits into the OpenShift AI Tier Model

Recall the three-tier architecture from L1-M1.1:

| Tier | OGX Involvement | What You Interact With |
|------|----------------|----------------------|
| **Tier 1: DSC Component** | `llamastackoperator` -- operator deploys and manages OGX server instances | `DataScienceCluster` CR, `LlamaStackDistribution` CR |
| **Tier 2: Dashboard Feature** | AutoRAG -- the dashboard's automated RAG optimization feature requires `llamastackoperator` | Gen AI Studio > AutoRAG (covered in L2-M1.6) |
| **Tier 3: Python Library** | Llama Stack client SDK (`llama-stack-client`) -- used in workbenches and application code | `pip install llama-stack-client`, then call OGX REST APIs |

The `llamastackoperator` component is the foundation that enables both the operator-managed OGX server (Tier 1) and the AutoRAG dashboard feature (Tier 2). If you only need LangChain-based RAG, you do not need to enable `llamastackoperator` -- but you will miss out on AutoRAG and native agent integration.

## Verification

Since this is a conceptual lesson, verify your understanding by answering these questions:

1. **What are the five OGX APIs?** Inference, Memory, RAG, Tool, and Agent APIs.
2. **Is OGX limited to Llama models?** No -- OGX supports 23+ inference providers including vLLM, TGI, Ollama, and cloud APIs, with any model those providers support.
3. **What CRD does the OGX Operator introduce?** `LlamaStackDistribution` (expected to be renamed in a future release).
4. **Which DSC component must be enabled for OGX?** `llamastackoperator` (set `managementState: Managed`).
5. **What is the key difference between OGX-native RAG and LangChain-based RAG?** OGX-native RAG provides a single API for the entire pipeline (insert + query), while LangChain-based RAG gives you full control but requires you to wire together embedding, retrieval, and generation yourself.
6. **Which RAG architecture is required for the AutoRAG dashboard feature?** OGX-native RAG -- AutoRAG requires the `llamastackoperator` component.
7. **Name the three RAG reference architectures covered in this lesson.** OGX-native RAG, LangChain + vLLM + Vector DB, Validated Patterns.

## Key Takeaways

- RAG grounds LLM responses in external knowledge by retrieving relevant documents at query time and injecting them into the prompt -- it is the primary alternative to fine-tuning for domain-specific knowledge
- OGX (Open GenAI Stack) is Red Hat's productization of Meta's Llama Stack, providing a unified API layer for inference, memory (vector stores), RAG, tools, and agents
- OGX is provider-agnostic -- it supports 23+ inference providers and multiple vector store backends, not just Llama models
- The OGX Operator (`llamastackoperator`) is a Tier 1 DSC component that deploys and manages OGX server instances via the `LlamaStackDistribution` CRD
- Three RAG architectures are available on OpenShift AI: OGX-native (most integrated), LangChain-based (most flexible), and Validated Patterns (fastest to deploy)
- OGX-native RAG is required for the AutoRAG dashboard feature and native agent integration; LangChain-based RAG offers maximum flexibility for production customization
- The OGX Operator is in Technology Preview as of OpenShift AI 3.4-3.5 -- plan for potential API changes

## Cleanup

No resources to clean up -- this was a conceptual lesson.

## Next Steps

In the next lesson, [L2-M1.2 -- Vector Database Setup](../2_vector_database/), you will deploy pgvector on OpenShift, serve an embedding model on vLLM, and store your first vector embeddings -- the retrieval foundation for the RAG architectures covered here.
