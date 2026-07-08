# Red Hat AI Ecosystem Tutorial: Syllabus

## Purpose

Learn the full Red Hat AI ecosystem — from local desktop experimentation to enterprise-scale deployment. This tutorial covers the three-tier journey that Red Hat provides for AI adoption: **Podman AI Lab** (desktop), **RHEL AI** (server/bare-metal), and how they connect to **OpenShift AI** (platform/cluster). It also covers the Granite model family, modular model customization with Docling/SDG Hub/Training Hub, model optimization, and Red Hat Validated Patterns for production-ready reference architectures.

## Why a Separate Tutorial?

The main OpenShift AI tutorial covers the platform in depth, but Red Hat's AI story is broader. Developers and architects need to understand the full journey: prototyping locally with Podman AI Lab, running single-server AI workloads with RHEL AI, and scaling to clusters with OpenShift AI. This tutorial provides the ecosystem context and hands-on experience with the tools that sit outside (or below) the OpenShift AI platform.

**Scope boundary with the OpenShift AI tutorial:** This track teaches everything *below* the OpenShift AI platform — desktop tools, single-server deployment, model optimization, and the Granite ecosystem. The [OpenShift AI tutorial](../02_openshift_ai/) covers platform-level features: KServe, distributed training, agents/MCP, governance, observability, and multi-tenant GPU management. The on-ramp lesson (L1-4.1) previews what OpenShift AI adds but directs learners to the OpenShift AI tutorial for hands-on coverage.

## Target Audience

- Developers evaluating Red Hat's AI stack who want the big picture
- Teams deciding where to run AI workloads (laptop vs server vs cluster)
- Anyone starting the OpenShift AI tutorial who wants ecosystem context first
- IT architects designing an AI platform strategy on Red Hat infrastructure

## Technical Stack

- **Podman AI Lab**: Latest extension for Podman Desktop
- **Podman Desktop**: 1.28+ with Podman 6.0+ (or Podman 5.8+ with upgrade path)
- **Red Hat AI / RHEL AI**: 3.4 GA (bootable container image, Red Hat AI Inference Server, Model Adaptation Toolkit)
- **Model Customization**: Docling (document processing), SDG Hub (synthetic data generation), Training Hub (SFT, LoRA/QLoRA)
- **Model Optimization**: Red Hat AI Model Optimization Toolkit (LLM Compressor)
- **CLI**: `ilab` (InstructLab CLI — still ships as the getting-started interface)
- **Models**: IBM Granite 4.x family (Apache 2.0 licensed)
- **RedHatAI HuggingFace**: Pre-quantized models (FP8, INT8, GPTQ, AWQ, MXFP4)
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
- **Red Hat AI / RHEL AI Documentation 3.4**: https://docs.redhat.com/en/documentation/red_hat_enterprise_linux_ai/3.4
- **Red Hat AI Getting Started**: https://docs.redhat.com/en/documentation/red_hat_enterprise_linux_ai/3.4/html/getting_started/
- **Red Hat AI CLI Reference**: https://docs.redhat.com/en/documentation/red_hat_enterprise_linux_ai/3.4/html/cli_reference/
- **Red Hat AI Model Customization**: https://docs.redhat.com/en/documentation/red_hat_enterprise_linux_ai/3.4/html/model_customization/
- **RedHatAI on HuggingFace**: https://huggingface.co/RedHatAI
- **IBM Granite Models**: https://huggingface.co/ibm-granite
- **SDG Hub**: https://github.com/Red-Hat-AI-Innovation-Team/sdg_hub
- **Training Hub**: https://github.com/Red-Hat-AI-Innovation-Team/training_hub
- **Docling**: https://github.com/docling-project/docling
- **Validated Patterns**: https://validatedpatterns.io/
- **RAG + LLM GitOps Pattern**: https://validatedpatterns.io/patterns/rag-llm-gitops/
- **From Podman AI Lab to OpenShift AI**: https://developers.redhat.com/learn/openshift-ai/podman-ai-lab-openshift-ai
- **AI on OpenShift Community**: https://ai-on-openshift.io/

---

# LEVEL 1 — RED HAT AI FOUNDATIONS

*Goal: Understand the Red Hat AI platform, experiment locally with Podman AI Lab, understand RHEL AI as an inference and model adaptation platform, and know the Granite model family.*
*Estimated time: ~7-9 hours*

---

## L1-M1: The Red Hat AI Platform

### L1-1.1 — Red Hat AI Vision, Architecture, and Portfolio
**Duration:** 30 min
**Topics:**
- Red Hat AI Enterprise: the unified "metal-to-agent" platform (announced Feb 2026)
- Four products in the portfolio:
  - **Red Hat AI Inference Server** — vLLM-based, high-throughput model serving
  - **RHEL AI** — bootable container image for single-server AI (inference + model adaptation)
  - **OpenShift AI** — Kubernetes-native MLOps platform
  - **Red Hat AI Enterprise** — unified subscription bundling all three
- The three-tier deployment model:
  - **Tier 1: Desktop** — Podman AI Lab (prototype, experiment, zero cost)
  - **Tier 2: Server** — RHEL AI (single server, inference + fine-tuning)
  - **Tier 3: Platform** — OpenShift AI (cluster-scale MLOps, distributed training, agents)
- When to use each tier
- Red Hat's relationship with upstream projects (updated):
  - InstructLab → modular libraries: Docling, SDG Hub, Training Hub
  - vLLM → Red Hat AI Inference Server
  - Open Data Hub → OpenShift AI operator
  - Llama Stack → OGX Operator
  - llm-d → distributed inference engine
- Red Hat vs other enterprise AI platforms: open source, no proprietary model lock-in, Apache 2.0 models

**Deliverables:**
- Architecture diagram: Red Hat AI Enterprise portfolio
- Decision matrix: which tier for which use case

---

### L1-1.2 — Model Strategy: Granite, Validated Models, and the Model Catalog
**Duration:** 30 min
**Topics:**
- IBM Granite model family (Apache 2.0 licensed):
  - **Granite 4.x Language**: Dense (2B–30B) and MoE variants, up to 128K–512K context
  - **Granite Code**: code generation and completion (3B to 34B)
  - **Granite Guardian**: safety and content moderation
  - **Granite Embedding**: text embeddings for RAG
  - **Granite Speech**: multilingual ASR and translation
  - **Granite Vision**: multimodal vision-language models
- Why Red Hat bets on Granite: Apache 2.0, transparent training data, enterprise indemnification
- RedHatAI on HuggingFace:
  - Pre-quantized models (FP8, INT8, GPTQ, AWQ, MXFP4)
  - Monthly validated model collections (Red Hat tests models on vLLM + OpenShift AI)
  - Not limited to Granite: validates Llama, Mistral, DeepSeek, Qwen, Gemma, and others
- Red Hat AI Model Optimization Toolkit overview (quantization, compression, sparsity)
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
- System requirements: Podman Desktop 1.28+, Podman 6.0+, 12+ GB RAM recommended
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
- Gen AI Studio: the cloud-equivalent playground on OpenShift AI (preview — taught in the OpenShift AI tutorial)
- Reference: "From Podman AI Lab to OpenShift AI" (Red Hat Developer learning path)

**Deliverables:**
- Understanding of the local → production workflow
- Configuration exported for deployment on OpenShift AI

---

## L1-M3: Red Hat AI on a Single Server

### L1-3.1 — RHEL AI Architecture: Inference and Model Adaptation
**Duration:** 45 min
**Topics:**
- What is RHEL AI? Foundation model platform as a bootable container image
- Reframed architecture for Red Hat AI 3.x:
  - **Primary focus: inference** — Red Hat AI Inference Server (vLLM-based)
  - **Secondary focus: model adaptation** — Model Adaptation Toolkit (Docling, SDG Hub, Training Hub)
  - **Model optimization** — Model Optimization Toolkit (LLM Compressor)
  - **Image Mode for RHEL**: manage your AI platform as a container image
  - **`ilab` CLI**: still the getting-started interface for all operations
- Components bundled in the image:
  - Red Hat AI Inference Server (vLLM-based): high-throughput inference
  - Model Adaptation Toolkit: Docling, SDG Hub, Training Hub
  - Model Optimization Toolkit: LLM Compressor (quantization, sparsity)
  - PyTorch: model training framework
- Hardware support (expanded for 3.x):
  - NVIDIA GPUs: A100, H100, H200, B200, B300 (Blackwell)
  - AMD GPUs: MI300X, MI325X
  - Intel GPUs: Gaudi 3
  - CPU inference: tech preview for small models
- The `ilab` CLI: updated command reference
  - New in 3.x: `ilab model upload`, `-dt` detach flag, `ilab process list/attach`
- RHEL AI vs OpenShift AI comparison (updated for 3.x)

**Deliverables:**
- Architecture diagram: RHEL AI 3.x components
- Decision matrix: RHEL AI vs OpenShift AI

---

### L1-3.2 — Serving and Chatting with Models on RHEL AI
**Duration:** 45 min
**Prerequisites:** Access to a RHEL AI instance (or conceptual walkthrough)
**Topics:**
- Focus on INFERENCE — the primary use case for RHEL AI
- Installing RHEL AI:
  - Download the bootable container image (updated registry path for 3.x)
  - Deploy on bare metal or VM
  - First boot configuration
- The inference workflow:
  1. **Initialize**: `ilab config init` — configure the environment
  2. **Download model**: `ilab model download` — fetch a Granite model
  3. **Serve**: `ilab model serve` — start the Red Hat AI Inference Server
  4. **Chat**: `ilab model chat` — interactive chat with the model
- Red Hat AI Inference Server: what it does under the hood (vLLM-based)
- OpenAI-compatible API: use from Python, curl, applications
- `ilab model upload`: pushing models to registries (new in 3.x)

**Deliverables:**
- Model served and chatted with via the `ilab` CLI
- API endpoint working and tested with curl
- Understanding of the Red Hat AI Inference Server

---

### L1-3.3 — Fine-Tuning with the ilab CLI
**Duration:** 45 min
**Prerequisites:** Completed L1-3.2
**Topics:**
- The InstructLab fine-tuning workflow:
  1. **Create taxonomy**: `ilab taxonomy diff` — define knowledge and skills
  2. **Generate synthetic data**: `ilab data generate` — SDG from taxonomy
  3. **Train**: `ilab model train` — fine-tuning with multi-phase training
  4. **Evaluate**: `ilab model evaluate` — benchmark the fine-tuned model
  5. **Serve the fine-tuned model**: `ilab model serve --model-path <path>`
- Understanding the LAB method:
  - Taxonomy: structured knowledge and skills definitions
  - Synthetic Data Generation: LLM generates training data from taxonomy
  - Multi-phase training: knowledge tuning → skills tuning → alignment
- Background process management (new in 3.x):
  - `-dt` flag: detach training/SDG processes
  - `ilab process list`: view running background processes
  - `ilab process attach`: reattach to a running process
- Preview: "In Level 2, we'll use the modular Python libraries (Docling, SDG Hub, Training Hub) for more control over each step"

**Deliverables:**
- Understanding of the full InstructLab fine-tuning workflow
- Fine-tuned model (or conceptual understanding if no GPU available)

---

## L1-M4: Scaling to OpenShift AI

### L1-4.1 — From RHEL AI to OpenShift AI
**Duration:** 30 min
**Topics:**
- When to scale: multi-user, governance, GPU sharing, distributed inference
- What transfers from RHEL AI to OpenShift AI:
  - Models: direct upload to S3 → deploy via KServe
  - Taxonomy: same taxonomy files work with OpenShift AI's Training Hub
  - Configuration: vLLM parameters carry over to ServingRuntime
- What changes:
  - `ilab` CLI → OpenShift AI dashboard + `oc` CLI
  - Single vLLM instance → KServe-managed InferenceService
  - Local storage → S3 / OCI model storage
  - Manual evaluation → LMEvalJob / EvalHub
- Preview of what OpenShift AI adds (not taught here — see the OpenShift AI tutorial):
  - AI Hub and Gen AI Studio (collaborative model playground)
  - Models-as-a-Service (MaaS) for multi-tenant model sharing
  - MCP deployment and AI agent orchestration (10 lessons in openshift_ai)
  - Governance: RBAC, Authorino, NeMo Guardrails (5 lessons in openshift_ai)
  - Observability: MLflow, OpenTelemetry, TrustyAI (5 lessons in openshift_ai)
  - Distributed inference with llm-d
- Hybrid patterns: fine-tune on RHEL AI → serve on OpenShift AI

**Deliverables:**
- Understanding of what transfers and what changes
- Migration plan: RHEL AI fine-tuned model → OpenShift AI deployment

---

### L1-4.2 — Red Hat Validated Patterns for AI
**Duration:** 45 min
**Topics:**
- What are Validated Patterns? GitOps-ready reference architectures
  - Pre-built, tested, production-ready deployment patterns
  - ArgoCD-based GitOps deployment (clone repo, configure, deploy)
  - Maintained by Red Hat and the community
- AI-relevant patterns:
  - **RAG + LLM on GPU**: complete RAG deployment with vLLM, vector database, embedding model, UI, monitoring
  - **Chatbot Application**: conversational AI deployment
- Pattern anatomy:
  - Helm charts for all components
  - ArgoCD Applications for GitOps sync
  - Kustomize overlays for environment customization
  - `values-*.yaml` for site-specific configuration
- Using a Validated Pattern as a starting point:
  1. Fork the pattern repository
  2. Configure for your environment
  3. Deploy via ArgoCD
  4. Customize: swap models, add components
- Comparison: building from scratch (OpenShift AI tutorial) vs starting from a pattern

**Deliverables:**
- Validated Pattern explored and understood
- Understanding of when to use patterns vs build from scratch

---

### Level 1 Summary

| Module | Lessons | Estimated Time |
|--------|---------|---------------|
| M1: The Red Hat AI Platform | 2 lessons | ~1 hour |
| M2: Podman AI Lab | 3 lessons | ~2 hours |
| M3: Red Hat AI on a Single Server | 3 lessons | ~2.25 hours |
| M4: Scaling to OpenShift AI | 2 lessons | ~1.25 hours |
| **Total** | **10 lessons** | **~7-9 hours** |

---

# LEVEL 2 — PRACTITIONER

*Goal: Advanced Podman AI Lab customization, modular model customization with Python libraries, model optimization, production deployment, cross-tier workflows.*
*Estimated time: ~7-9 hours*

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

## L2-M2: Model Customization Deep Dive

### L2-2.1 — Modular Model Customization: Docling, SDG Hub, and Training Hub
**Duration:** 1 hour
**Topics:**
- The evolution: `ilab` monolith → modular Python libraries
  - Why the change: scalability, flexibility, programmatic control
  - When to use `ilab` CLI vs Python libraries
- **Docling**: processing enterprise documents
  - PDF, HTML, Markdown, DOCX → structured data
  - Document chunking and preprocessing for fine-tuning and RAG
  - Cross-reference: openshift_ai L2-1.3 covers Docling in RAG pipelines on OpenShift AI
- **SDG Hub**: building synthetic data generation pipelines
  - Configuring SDG pipelines programmatically
  - Custom teacher models and generation strategies
  - Quality filtering and data review
- **Training Hub**: flexible fine-tuning
  - SFT (Supervised Fine-Tuning)
  - LoRA/QLoRA via Unsloth (parameter-efficient fine-tuning)
  - Continual learning
  - Cross-reference: openshift_ai L1-M3 covers Training Hub on OpenShift AI
- **Red Hat AI Python Index**: enterprise-grade, hardened packages
  - `pip install --index-url` from the Red Hat AI Python Index
  - Versioning and compatibility guarantees
- Hands-on: Jupyter notebook walkthrough of Docling → SDG Hub → Training Hub pipeline

**Deliverables:**
- Jupyter notebook running a Docling → SDG Hub → Training Hub pipeline
- Understanding of when to use modular libraries vs `ilab` CLI

---

### L2-2.2 — Model Optimization for Production
**Duration:** 45 min
**Topics:**
- Red Hat AI Model Optimization Toolkit (LLM Compressor)
  - What it does: reduce model size and inference cost
  - When to use: deployment to smaller GPUs, cost reduction, latency improvement
- Quantization methods:
  - FP8: 50% memory reduction, minimal quality loss (production default)
  - INT4/GPTQ: 75% memory reduction, grouped quantization
  - AWQ: activation-aware 4-bit, better quality than GPTQ
  - MXFP4: microscaling 4-bit for latest hardware
- Sparsity and compression techniques:
  - Weight pruning: remove near-zero weights
  - Knowledge distillation: train a smaller model from a larger one
- Speculative decoding with the Speculators library:
  - 1.5-3x latency reduction
  - Draft model + verification approach
  - Compatible models and configuration
- Hands-on: quantize a Granite model, benchmark quality vs speed vs VRAM
- Cross-reference: openshift_ai L3-3.2 covers the same techniques on OpenShift AI

**Deliverables:**
- Model quantized using LLM Compressor
- Benchmark comparison: FP16 vs FP8 vs INT4 (quality, speed, VRAM)

---

### L2-2.3 — RHEL AI Production Deployment
**Duration:** 45 min
**Topics:**
- Production RHEL AI configuration:
  - Systemd service for the Red Hat AI Inference Server (persistent model serving)
  - TLS configuration for secure inference endpoints
  - Resource management: GPU allocation, memory limits
  - Logging and monitoring with journald
- Multi-model serving:
  - Running multiple models on one RHEL AI instance
  - Port management and GPU memory partitioning
- Backup and versioning:
  - Backing up fine-tuned models
  - Version management for taxonomies and training data
- Upgrading RHEL AI:
  - Image-based upgrades (Image Mode for RHEL)
  - Model compatibility across versions
- Monitoring:
  - Prometheus metrics endpoint
  - Key vLLM metrics and health checking

**Deliverables:**
- RHEL AI running as a production service (systemd)
- Multi-model serving configuration

---

## L2-M3: Cross-Tier Workflows

### L2-3.1 — End-to-End: Desktop → Server → Platform
**Duration:** 1 hour
**Topics:**
- Complete workflow walkthrough (updated for Red Hat AI 3.x):
  1. **Discover**: test models in Podman AI Lab Playground (5 min)
  2. **Prototype**: build a RAG recipe in Podman AI Lab (30 min)
  3. **Fine-tune**: create taxonomy, fine-tune on RHEL AI (hours)
  4. **Evaluate**: benchmark on RHEL AI with `ilab model evaluate` (30 min)
  5. **Deploy**: push model to S3, create InferenceService on OpenShift AI (30 min)
  6. **Serve**: deploy the full application on OpenShift AI (1 hour)
  7. **Monitor**: set up observability on OpenShift AI (30 min)
- Automation options (updated):
  - CI/CD with SDG Hub + Training Hub Python APIs
  - Scripts for model export/import between tiers
  - Tekton/GitHub Actions pipelines for training → deployment
- When to skip tiers
- Team role recommendations:
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
- Updated Granite model lineup:
  - Granite 4.x Language, Code, Guardian, Embedding, Speech, Vision
  - Dense vs MoE architecture trade-offs
- Compressed model variants:
  - RedHatAI pre-quantized models (FP8, AWQ, GPTQ, MXFP4)
  - Naming convention on HuggingFace
- Granite across the stack:
  - GGUF format in Podman AI Lab (llama.cpp backend)
  - Safetensors format on RHEL AI (vLLM backend)
  - OCI image or S3 on OpenShift AI (KServe + vLLM)
- Granite vs community models:
  - Granite: Apache 2.0, enterprise indemnification, Red Hat support
  - Community (Llama, Qwen, Mistral, DeepSeek): more variety, larger sizes
  - Mixing models: Granite for core workloads, community for specialized tasks
- RedHatAI validated model collections:
  - Monthly validation against vLLM + OpenShift AI
  - What "validated" means vs what "supported" means

**Deliverables:**
- Granite model deployed and compared with a community model
- Understanding of quantization trade-offs with benchmark results

---

### Level 2 Summary

| Module | Lessons | Estimated Time |
|--------|---------|---------------|
| M1: Advanced Podman AI Lab | 2 lessons | ~1.75 hours |
| M2: Model Customization Deep Dive | 3 lessons | ~2.5 hours |
| M3: Cross-Tier Workflows | 2 lessons | ~1.75 hours |
| **Total** | **7 lessons** | **~7-9 hours** |

---

# Complete Course Summary

| Level | Focus | Lessons | Time |
|-------|-------|---------|------|
| **Level 1 — Foundations** | Red Hat AI platform, Podman AI Lab, RHEL AI (inference + adaptation), Granite, Scaling to OpenShift AI, Validated Patterns | 10 lessons | ~7-9 hours |
| **Level 2 — Practitioner** | Custom catalogs, modular model customization (Docling/SDG Hub/Training Hub), model optimization, production deployment, cross-tier workflows, Granite in practice | 7 lessons | ~7-9 hours |
| **Total** | | **17 lessons** | **~14-18 hours** |

---

## Red Hat AI Ecosystem Coverage Matrix

| Component | Level 1 | Level 2 |
|-----------|---------|---------|
| Red Hat AI Platform | Portfolio, four products, three-tier model | — |
| Granite Models | Family overview, licensing, HuggingFace | Quantization, model selection, cross-platform formats |
| Podman AI Lab | Install, model catalog, playground, recipes, export | Custom models, catalogs, application development |
| RHEL AI | Architecture (inference + adaptation), serving, fine-tuning, scaling path | Production deployment (systemd, TLS, multi-model) |
| Modular Customization | — | Docling, SDG Hub, Training Hub (Jupyter notebooks) |
| Model Optimization | Overview (in model strategy lesson) | LLM Compressor, quantization, sparsity, speculative decoding |
| Validated Patterns | RAG pattern tour, when to use | — |
| Cross-Tier Workflows | — | End-to-end demo, automation, team role workflows |
| RedHatAI HuggingFace | Overview | Validated model collections, quantization variants |

## Scope Boundary with OpenShift AI Tutorial

| Topic | This Tutorial (redhat_ai) | OpenShift AI Tutorial |
|-------|--------------------------|----------------------|
| Agents / MCP | Not covered | 10 lessons (L2-M2, L2-M3) |
| Governance / RBAC | Not covered | 5 lessons (L3-M1) |
| Observability | Not covered | 5 lessons (L2-M5, L3-M2) |
| AI Hub / Gen AI Studio | Mentioned in on-ramp (L1-4.1) | Taught hands-on |
| Distributed Inference (llm-d) | Not covered | Covered (L3-M3) |
| Model Optimization | Local/server optimization (L2-2.2) | Same techniques on OpenShift AI (L3-3.2) |
| Training Hub | Modular Python libraries (L2-2.1) | On OpenShift AI with K8s (L1-M3) |
| Docling | Document processing for fine-tuning (L2-2.1) | In RAG pipelines on OpenShift AI (L2-1.3) |
