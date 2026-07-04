# Red Hat AI Ecosystem Tutorial: Syllabus

## Purpose

Learn the full Red Hat AI ecosystem — from local desktop experimentation to enterprise-scale deployment. This tutorial covers the three-tier journey that Red Hat provides for AI adoption: **Podman AI Lab** (desktop), **RHEL AI** (server/bare-metal), and how they connect to **OpenShift AI** (platform/cluster). It also covers the Granite model family and Red Hat Validated Patterns for production-ready reference architectures.

## Why a Separate Tutorial?

The main OpenShift AI tutorial covers the platform in depth, but Red Hat's AI story is broader. Developers and architects need to understand the full journey: prototyping locally with Podman AI Lab, running single-server AI workloads with RHEL AI, and scaling to clusters with OpenShift AI. This tutorial provides the ecosystem context and hands-on experience with the tools that sit outside (or below) the OpenShift AI platform.

## Target Audience

- Developers evaluating Red Hat's AI stack who want the big picture
- Teams deciding where to run AI workloads (laptop vs server vs cluster)
- Anyone starting the OpenShift AI tutorial who wants ecosystem context first
- IT architects designing an AI platform strategy on Red Hat infrastructure

## Technical Stack

- **Podman AI Lab**: Latest extension for Podman Desktop
- **Podman Desktop**: 1.10.3+ with Podman 5.0.1+
- **RHEL AI**: 1.5 (bootable container image, InstructLab, vLLM)
- **Models**: IBM Granite 4.x family (Apache 2.0 licensed)
- **RedHatAI HuggingFace**: Pre-quantized models (FP8, INT8, GPTQ, AWQ)
- **Validated Patterns**: GitOps reference architectures (ArgoCD-based)
- **Container Runtime**: Podman (not Docker)

## Prerequisites

### Required
- Podman Desktop installed (for Podman AI Lab lessons)
- Basic understanding of containers and Podman
- Familiarity with LLM concepts (inference, fine-tuning, embeddings)

### Recommended
- OpenShift knowledge (for understanding the RHEL AI → OpenShift AI progression)
- GPU hardware for RHEL AI lessons (NVIDIA, AMD, or Intel — CPU fallback for exploration)

## Reference Sources

- **Red Hat AI Learning Hub**: https://docs.redhat.com/en/learn/ai
- **Podman AI Lab Documentation**: https://podman-desktop.io/docs/ai-lab
- **Podman AI Lab GitHub**: https://github.com/containers/podman-desktop-extension-ai-lab
- **RHEL AI Documentation 1.5**: https://docs.redhat.com/en/documentation/red_hat_enterprise_linux_ai/1.5
- **RHEL AI Getting Started**: https://docs.redhat.com/en/documentation/red_hat_enterprise_linux_ai/1.5/html/getting_started/
- **RedHatAI on HuggingFace**: https://huggingface.co/RedHatAI
- **IBM Granite Models**: https://huggingface.co/ibm-granite
- **Granite 4.1 Blog**: https://huggingface.co/blog/ibm-granite/granite-4-1
- **Validated Patterns**: https://validatedpatterns.io/
- **RAG + LLM GitOps Pattern**: https://validatedpatterns.io/patterns/rag-llm-gitops/
- **From Podman AI Lab to OpenShift AI**: https://developers.redhat.com/learn/openshift-ai/podman-ai-lab-openshift-ai
- **AI on OpenShift Community**: https://ai-on-openshift.io/

---

# LEVEL 1 — RED HAT AI FOUNDATIONS

*Goal: Understand the Red Hat AI ecosystem, experiment locally with Podman AI Lab, understand RHEL AI, and know the Granite model family.*
*Estimated time: ~6-8 hours*

---

## L1-M1: The Red Hat AI Ecosystem

### L1-1.1 — Red Hat AI Vision and Architecture
**Duration:** 30 min
**Topics:**
- Red Hat's AI strategy: open-source first, hybrid cloud, no vendor lock-in
- The three-tier deployment model:
  - **Tier 1: Desktop** — Podman AI Lab (prototype, experiment, zero cost)
  - **Tier 2: Server** — RHEL AI (single server, InstructLab fine-tuning, vLLM serving)
  - **Tier 3: Platform** — OpenShift AI (cluster-scale MLOps, distributed training, model serving)
- When to use each tier:
  - Podman AI Lab: "Can this model answer my questions?" (minutes to get started)
  - RHEL AI: "Can I fine-tune a model on my data on a single server?" (hours to set up)
  - OpenShift AI: "How do I serve this at scale with governance?" (days to set up)
- The progression path: prototype locally → fine-tune on RHEL AI → deploy on OpenShift AI
- Red Hat's relationship with upstream projects:
  - InstructLab → RHEL AI / OpenShift AI Training Hub
  - Open Data Hub → OpenShift AI operator
  - vLLM → Red Hat AI Inference Server
  - OGX (Llama Stack) → OGX Operator
- Red Hat vs other enterprise AI platforms: open source, no proprietary model lock-in, Apache 2.0 models

**Deliverables:**
- Architecture diagram: three-tier Red Hat AI deployment model
- Decision matrix: which tier for which use case

---

### L1-1.2 — Red Hat AI Model Strategy: Granite and Beyond
**Duration:** 30 min
**Topics:**
- IBM Granite model family (Apache 2.0 licensed):
  - **Granite 4.x Language**: 3B, 8B, 30B dense models, up to 512K context
  - **Granite Code**: code generation and completion (3B to 34B)
  - **Granite Guardian**: safety and content moderation
  - **Granite Embedding**: text embeddings for RAG
  - **Granite Speech**: multilingual ASR and translation
  - **Granite Vision**: multimodal vision-language models
- Why Red Hat bets on Granite: Apache 2.0, transparent training data, enterprise-grade
- RedHatAI on HuggingFace:
  - Pre-quantized models (FP8, INT8, GPTQ, AWQ, NVFP4)
  - Monthly validated model collections (Red Hat tests models on vLLM + OpenShift AI)
  - Not limited to Granite: validates Llama, Mistral, DeepSeek, Qwen, Gemma, and others
- Red Hat AI Validated Models program: what "validated" means (tested on vLLM, certified for OCP)
- Model selection guidance: Granite for enterprise (indemnified), community models for flexibility

**Deliverables:**
- Granite model family overview table (model, params, use case, license)
- Understanding of RedHatAI HuggingFace collections

---

## L1-M2: Podman AI Lab

### L1-2.1 — Installing and Exploring Podman AI Lab
**Duration:** 45 min
**Topics:**
- What is Podman AI Lab? (Podman Desktop extension for local AI development)
- System requirements: Podman Desktop 1.10.3+, Podman 5.0.1+, 12+ GB RAM recommended
- Installing the extension: Extensions > Catalog > Install Podman AI Lab
- Model Catalog tour:
  - Browsing available models (Granite, Gemma, Qwen, and others)
  - Downloading models (GGUF format for local inference)
  - Model metadata: size, format, description
- Model Services:
  - Starting an inference server for a downloaded model
  - OpenAI-compatible API endpoint (localhost)
  - llama.cpp backend (runs GGUF models efficiently on CPU)
- Playground:
  - Interactive chat with downloaded models
  - System prompt experimentation
  - Parameter tuning: temperature, max tokens, top-p
  - Side-by-side model comparison

**Deliverables:**
- Podman AI Lab installed with Granite model downloaded
- Interactive chat working in the Playground
- Model service running with OpenAI-compatible API endpoint

---

### L1-2.2 — Recipes Catalog: Pre-Built AI Applications
**Duration:** 45 min
**Topics:**
- What are recipes? Pre-built containerized AI applications
- Available recipes:
  - **Chatbot**: conversational AI backed by a local LLM
  - **Summarizer**: text summarization
  - **Code Generation**: generate code from natural language
  - **RAG Chatbot**: chat with your own documents (retrieval-augmented generation)
  - **Object Detection**: image analysis with vision models
  - **Audio Processing**: speech-to-text and audio analysis
- Running a recipe:
  - Select recipe → choose model → start
  - Recipe runs as containerized application with embedded model server
  - Access via web browser (localhost)
- Examining recipe architecture:
  - Dockerfile, application code, model configuration
  - How recipes use LangChain, Streamlit, and other frameworks
- Customizing recipes:
  - Modifying the application code
  - Swapping models
  - Adding your own documents (RAG recipe)

**Deliverables:**
- RAG Chatbot recipe running with your own documents
- Understanding of recipe architecture (container + model + app)
- Custom modification of a recipe

---

### L1-2.3 — From Podman AI Lab to Production
**Duration:** 30 min
**Topics:**
- The gap between local prototype and production deployment
- Exporting from Podman AI Lab:
  - Model: download URL → S3 bucket → InferenceService on OpenShift AI
  - Application code: recipe code → containerized service → OpenShift Deployment
  - Configuration: playground settings → ServingRuntime parameters
- Workflow: Podman AI Lab → RHEL AI or OpenShift AI:
  1. Prototype in Podman AI Lab (choose model, test with data)
  2. Export the working model choice and configuration
  3. Deploy on RHEL AI (single server) or OpenShift AI (cluster)
- Custom model import: importing your own GGUF models into AI Lab
- Extensible catalog: creating custom recipes and model entries
- Reference: "From Podman AI Lab to OpenShift AI" (Red Hat Developer learning path)

**Deliverables:**
- Understanding of the local → production workflow
- Configuration exported for deployment on OpenShift AI

---

## L1-M3: RHEL AI

### L1-3.1 — RHEL AI Architecture and Concepts
**Duration:** 45 min
**Topics:**
- What is RHEL AI? Foundation model platform as a bootable container image
- Architecture:
  - **Bootable container image**: RHEL 9 + InstructLab + vLLM + DeepSpeed + PyTorch
  - **Image Mode for RHEL**: manage your AI platform as a container image
  - **InstructLab CLI** (`ilab`): the primary interface for all operations
- Components bundled in the image:
  - InstructLab: taxonomy-based fine-tuning with synthetic data generation
  - vLLM: high-throughput inference server
  - DeepSpeed: distributed training acceleration
  - PyTorch: model training framework
  - LLM Compressor: model quantization
- Granite models included: granite-3.x / granite-4.x (pre-installed, Apache 2.0)
- Hardware support:
  - NVIDIA GPUs: A100, H100, H200 (GA)
  - AMD GPUs: MI300X (GA for inference and full workflow)
  - Intel GPUs: Gaudi (supported)
  - CPU-only: limited but possible for small models
- When to use RHEL AI:
  - Single-server deployments without Kubernetes
  - Fine-tuning on dedicated hardware
  - Air-gapped environments
  - Starting point before scaling to OpenShift AI
- RHEL AI vs OpenShift AI comparison:
  | Aspect | RHEL AI | OpenShift AI |
  |--------|---------|-------------|
  | Deployment | Single server, bootable image | Kubernetes cluster, operator |
  | Fine-tuning | InstructLab CLI | Training Hub, Kubeflow Trainer |
  | Serving | vLLM via `ilab model serve` | KServe + vLLM |
  | Scale | Single node | Multi-node, distributed |
  | MLOps | Manual | Pipelines, registry, monitoring |
  | Cost | Hardware only | Cluster infrastructure |

**Deliverables:**
- Architecture diagram: RHEL AI components
- Decision matrix: RHEL AI vs OpenShift AI

---

### L1-3.2 — RHEL AI Workflow: Serve, Chat, Fine-Tune
**Duration:** 1 hour
**Prerequisites:** Access to a RHEL AI instance (physical or VM with GPU, or conceptual walkthrough)
**Topics:**
- Installing RHEL AI:
  - Download the bootable container image
  - Deploy on bare metal or VM
  - First boot configuration
- The InstructLab workflow:
  1. **Initialize**: `ilab config init` — configure the environment
  2. **Download model**: `ilab model download` — fetch a Granite model
  3. **Serve**: `ilab model serve` — start vLLM inference server
  4. **Chat**: `ilab model chat` — interactive chat with the model
  5. **Create taxonomy**: `ilab taxonomy diff` — define knowledge and skills
  6. **Generate synthetic data**: `ilab data generate` — SDG from taxonomy
  7. **Train**: `ilab model train` — LAB-tuning with multi-phase training
  8. **Evaluate**: `ilab model evaluate` — benchmark the fine-tuned model
  9. **Serve the fine-tuned model**: `ilab model serve --model-path <path>`
- Understanding the LAB method:
  - Taxonomy: structured knowledge and skills definitions
  - Synthetic Data Generation: LLM generates training data from taxonomy
  - Multi-phase training: knowledge tuning → skills tuning → alignment
- Export: moving a fine-tuned model from RHEL AI to OpenShift AI
  - Upload model to S3 or package as OCI image
  - Create InferenceService on OpenShift AI pointing to the model

**Deliverables:**
- Understanding of the full InstructLab workflow
- Model served and chatted with via InstructLab CLI
- Fine-tuned model (or conceptual understanding if no GPU available)

---

### L1-3.3 — RHEL AI as an OpenShift AI On-Ramp
**Duration:** 30 min
**Topics:**
- The scaling path: RHEL AI → OpenShift AI:
  - When single-server capacity is exceeded
  - When multiple users need access to models
  - When governance, monitoring, and pipelines are needed
  - When GPU sharing across teams is required
- What transfers from RHEL AI to OpenShift AI:
  - Models: direct upload to S3 → deploy via KServe
  - Taxonomy: same taxonomy files work with OpenShift AI's Training Hub
  - Configuration: vLLM parameters carry over to ServingRuntime
- What changes:
  - `ilab` CLI → OpenShift AI dashboard + `oc` CLI
  - Single vLLM instance → KServe-managed InferenceService
  - Local storage → S3 / OCI model storage
  - Manual evaluation → LMEvalJob / EvalHub
- Hybrid patterns:
  - Fine-tune on RHEL AI (dedicated GPU server) → serve on OpenShift AI (cluster)
  - Development on RHEL AI → production on OpenShift AI
- Connectivity: RHEL AI machines feeding models to OpenShift AI clusters

**Deliverables:**
- Migration plan: RHEL AI fine-tuned model → OpenShift AI deployment
- Understanding of what transfers and what changes

---

## L1-M4: Red Hat Validated Patterns

### L1-4.1 — Validated Patterns for AI
**Duration:** 45 min
**Topics:**
- What are Validated Patterns? GitOps-ready reference architectures
  - Pre-built, tested, production-ready deployment patterns
  - ArgoCD-based GitOps deployment (clone repo, configure, deploy)
  - Maintained by Red Hat and the community
- AI-relevant patterns:
  - **RAG + LLM on GPU**: complete RAG deployment with:
    - vLLM model serving
    - Vector database (pgvector or Milvus)
    - Embedding model
    - RAG application (Streamlit-based UI)
    - GitOps-managed deployment
  - **Chatbot Application**: conversational AI deployment
- Pattern anatomy:
  - Helm charts for all components
  - ArgoCD Applications for GitOps sync
  - Kustomize overlays for environment customization (dev/staging/prod)
  - `values-*.yaml` for site-specific configuration
- Using a Validated Pattern as a starting point:
  1. Fork the pattern repository
  2. Configure for your environment (cluster, storage, models)
  3. Deploy via ArgoCD
  4. Customize: swap models, add components, modify pipelines
- Comparison: building from scratch (OpenShift AI tutorial) vs starting from a pattern
  - Pattern: faster to production, less flexibility
  - From scratch: deeper understanding, full control

**Deliverables:**
- Validated Pattern explored and understood (architecture, components, deployment flow)
- Understanding of when to use patterns vs build from scratch

---

### Level 1 Summary

| Module | Lessons | Estimated Time |
|--------|---------|---------------|
| M1: Red Hat AI Ecosystem | 2 lessons | ~1 hour |
| M2: Podman AI Lab | 3 lessons | ~2 hours |
| M3: RHEL AI | 3 lessons | ~2.25 hours |
| M4: Validated Patterns | 1 lesson | ~0.75 hours |
| **Total** | **9 lessons** | **~6-8 hours** |

---

# LEVEL 2 — PRACTITIONER

*Goal: Advanced Podman AI Lab customization, RHEL AI fine-tuning in depth, cross-tier workflows.*
*Estimated time: ~5-7 hours*

---

## L2-M1: Advanced Podman AI Lab

### L2-1.1 — Custom Models and Catalogs
**Duration:** 45 min
**Topics:**
- Importing custom models into Podman AI Lab:
  - GGUF format from HuggingFace
  - Fine-tuned models from RHEL AI or OpenShift AI (convert to GGUF)
  - Custom model metadata configuration
- Building custom recipe catalogs:
  - `user-catalog.json` format
  - Adding custom models, recipes, and categories
  - Sharing catalogs across a team
- Custom recipes:
  - Building a custom AI application as a Podman AI Lab recipe
  - Containerizing with Podman (UBI-based)
  - Testing locally before deploying to OpenShift

**Deliverables:**
- Custom model imported into Podman AI Lab
- Custom recipe running in AI Lab

---

### L2-1.2 — Building Applications with Podman AI Lab
**Duration:** 1 hour
**Topics:**
- Using the model service API (OpenAI-compatible) from your own code:
  - Python: `openai` SDK, `langchain-openai`
  - JavaScript: `openai` npm package
  - curl: direct REST API calls
- Building a local AI application stack:
  - Podman AI Lab model service (inference)
  - Your application code (LangChain/LangGraph)
  - Local vector database (Qdrant or ChromaDB container)
- Podman Compose for multi-container AI stacks:
  - Model server + application + vector DB + UI
  - Configuration management with environment variables
- Integration with development tools:
  - VS Code + Continue (AI code assistant backed by local model)
  - Connecting MCP servers to local model service

**Deliverables:**
- Local AI application stack running with Podman Compose
- Application using local model service via OpenAI SDK

---

## L2-M2: RHEL AI Deep Dive

### L2-2.1 — InstructLab Taxonomy and SDG
**Duration:** 1 hour
**Topics:**
- InstructLab taxonomy deep dive:
  - Knowledge contributions: facts, documentation, FAQs
  - Skill contributions: reasoning, coding, formatting, analysis
  - Taxonomy file format: YAML with examples and context
  - Taxonomy validation: `ilab taxonomy diff`
- Synthetic Data Generation (SDG):
  - How SDG works: teacher model generates training data from taxonomy
  - SDG configuration: number of examples, diversity settings
  - Reviewing generated data quality
  - Iterating on taxonomy based on SDG results
- Multi-phase training details:
  - Phase 1: Knowledge tuning (inject new facts)
  - Phase 2: Skills tuning (teach new capabilities)
  - Phase 3: Alignment (maintain helpfulness and safety)
- Comparison: InstructLab LAB-tuning vs LoRA/QLoRA:
  - LAB: generates training data from taxonomy, broader knowledge injection
  - LoRA: uses existing data, targeted fine-tuning, less VRAM

**Deliverables:**
- Custom taxonomy with knowledge and skills contributions
- Synthetic data generated and reviewed
- Model fine-tuned using the full InstructLab workflow

---

### L2-2.2 — RHEL AI Production Deployment
**Duration:** 45 min
**Topics:**
- Production RHEL AI configuration:
  - Systemd service for vLLM (persistent model serving)
  - TLS configuration for secure inference endpoints
  - Resource management: GPU allocation, memory limits
  - Logging and monitoring with journald
- Multi-model serving:
  - Running multiple models on one RHEL AI instance
  - Port management and routing
- Backup and versioning:
  - Backing up fine-tuned models
  - Version management for taxonomies and training data
- Upgrading RHEL AI:
  - Image-based upgrades (Image Mode for RHEL)
  - Model compatibility across versions
- Monitoring vLLM on RHEL AI:
  - Prometheus metrics endpoint
  - Basic health checking

**Deliverables:**
- RHEL AI running as a production service (systemd)
- Multi-model serving configuration

---

## L2-M3: Cross-Tier Workflows

### L2-3.1 — End-to-End: Podman AI Lab → RHEL AI → OpenShift AI
**Duration:** 1 hour
**Topics:**
- Complete workflow walkthrough:
  1. **Discover**: test models in Podman AI Lab Playground (5 min)
  2. **Prototype**: build a RAG recipe in Podman AI Lab (30 min)
  3. **Fine-tune**: create taxonomy, fine-tune on RHEL AI (hours)
  4. **Evaluate**: benchmark on RHEL AI with `ilab model evaluate` (30 min)
  5. **Deploy**: push model to S3, create InferenceService on OpenShift AI (30 min)
  6. **Serve**: deploy the full application (RAG + agent) on OpenShift AI (1 hour)
  7. **Monitor**: set up observability on OpenShift AI (30 min)
- Automation options:
  - Scripts for model export/import between tiers
  - CI/CD integration: RHEL AI training → OpenShift AI deployment
- When to skip tiers:
  - Skip Podman AI Lab: you already know which model works
  - Skip RHEL AI: you have GPU nodes on OpenShift AI for fine-tuning
  - Use all three: full evaluation, fine-tuning, then enterprise deployment
- Red Hat's recommended workflow per team role:
  - Data Scientist: Podman AI Lab + RHEL AI (experiment + fine-tune)
  - ML Engineer: RHEL AI + OpenShift AI (fine-tune + deploy)
  - Platform Engineer: OpenShift AI (governance + operations)

**Deliverables:**
- End-to-end demonstration (or walkthrough) across all three tiers
- Workflow documentation for the team

---

### L2-3.2 — Granite Models in Practice
**Duration:** 45 min
**Topics:**
- Choosing the right Granite model for the task:
  - Granite Language (3B/8B/30B): general-purpose chat, Q&A, summarization
  - Granite Code: code generation, code review, debugging
  - Granite Guardian: content moderation, safety classification
  - Granite Embedding: RAG, semantic search, document retrieval
  - Granite Speech: transcription, translation
- Quantization variants and trade-offs:
  - FP16 (full precision): best quality, most VRAM
  - FP8 (RedHatAI default): ~50% less VRAM, minimal quality loss
  - INT4/GPTQ/AWQ: ~75% less VRAM, some quality loss
  - NVFP4: NVIDIA-specific 4-bit, optimized for Hopper GPUs
- Running Granite models across the Red Hat AI stack:
  - Podman AI Lab: GGUF format, llama.cpp backend
  - RHEL AI: native format, vLLM backend
  - OpenShift AI: OCI image or S3, KServe + vLLM
- Granite vs community models (Gemma, Llama, Qwen):
  - Granite: Apache 2.0, enterprise indemnification, Red Hat support
  - Community: more variety, larger ecosystem, varying licenses
  - Mixing: use Granite for core, community for specialized tasks
- RedHatAI validated model collections:
  - Monthly validation: Red Hat tests community models on vLLM + OpenShift AI
  - Validated = works on the platform, not necessarily endorsed

**Deliverables:**
- Granite model deployed and compared with a community model
- Understanding of quantization trade-offs with benchmark results

---

### Level 2 Summary

| Module | Lessons | Estimated Time |
|--------|---------|---------------|
| M1: Advanced Podman AI Lab | 2 lessons | ~1.75 hours |
| M2: RHEL AI Deep Dive | 2 lessons | ~1.75 hours |
| M3: Cross-Tier Workflows | 2 lessons | ~1.75 hours |
| **Total** | **6 lessons** | **~5-7 hours** |

---

# Complete Course Summary

| Level | Focus | Lessons | Time |
|-------|-------|---------|------|
| **Level 1 — Foundations** | Ecosystem overview, Podman AI Lab, RHEL AI, Granite, Validated Patterns | 9 lessons | ~6-8 hours |
| **Level 2 — Practitioner** | Custom catalogs, InstructLab deep dive, cross-tier workflows, Granite in practice | 6 lessons | ~5-7 hours |
| **Total** | | **15 lessons** | **~11-15 hours** |

---

## Red Hat AI Ecosystem Coverage Matrix

| Component | Level 1 | Level 2 |
|-----------|---------|---------|
| Ecosystem Overview | Architecture, three-tier model, strategy | — |
| Granite Models | Family overview, licensing, HuggingFace | Quantization, model selection, cross-platform |
| Podman AI Lab | Install, model catalog, playground, recipes | Custom models, catalogs, application development |
| RHEL AI | Architecture, InstructLab workflow, scaling path | Taxonomy/SDG deep dive, production deployment |
| Validated Patterns | RAG pattern tour, when to use | — |
| Cross-Tier Workflows | — | End-to-end demo, team role workflows |
| RedHatAI HuggingFace | Overview | Validated model collections, quantization variants |
