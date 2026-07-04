# OpenShift AI Tutorial: Three-Level Course

## Philosophy

This tutorial is structured in three progressive levels:

- **Level 1 — Foundations**: Platform setup, model serving, basic fine-tuning, evaluation. Touch every core capability. Short lessons (~30 min). Goal: deploy a model, fine-tune it, serve the fine-tuned version, and benchmark it.
- **Level 2 — Practitioner**: RAG, MCP servers, AI agent deployment, observability, pipelines. Longer lessons (~1-2 hours). Goal: build and deploy production-style AI workloads.
- **Level 3 — Expert**: Governance, advanced serving, agent evaluation, production operations. Goal: run AI workloads at enterprise scale with proper security, monitoring, and CI/CD.

Each level builds on the previous. A user can stop after Level 1 and have a working mental model of the platform, or continue through Level 3 for full mastery.

## Target Audience

- Developers and ML engineers who know **Kubernetes** and **OpenShift** (completed the main openshift-tutorial or equivalent)
- Familiar with **Python**, **LLMs**, and basic ML concepts
- Have existing experience with **LangChain/LangGraph** and **MCP** (from ai-agents-course)
- Have existing experience with **MLflow** (from mlflow-tutorial)

## Technical Stack

- **Platform**: Red Hat OpenShift AI 3.4-3.5 (Self-Managed) on OpenShift 4.19+
- **Upstream**: Open Data Hub operator
- **CLI**: `oc` (primary), `kubectl` (for K8s comparisons)
- **Model**: Gemma4-e4b (primary), Granite models (secondary/comparison)
- **Inference Server**: vLLM (Red Hat AI Inference Server)
- **Fine-Tuning**: Training Hub (LoRA/QLoRA), Kubeflow Trainer v2
- **Pipelines**: Kubeflow Pipelines v2 (KFP SDK)
- **Model Registry**: Kubeflow Model Registry
- **Evaluation**: TrustyAI (LMEvalJob), GuideLLM, EvalHub
- **RAG**: OGX (Open GenAI Stack / Llama Stack), pgvector / Milvus
- **Agents**: LangChain/LangGraph (containerized), OGX agents API
- **MCP**: MCP Lifecycle Operator, MCP Gateway, MCP Server for OpenShift
- **Observability**: MLflow (managed component), OpenTelemetry, Prometheus/Grafana
- **Safety**: NeMo Guardrails, Guardrails Orchestrator
- **Security**: Authorino, Kuadrant (MaaS rate limiting)
- **Distributed**: KubeRay, Kueue, Kubeflow Trainer
- **Feature Store**: Feast
- **Hardware**: NVIDIA GPUs (recommended), CPU-only mode available for some lessons

## OpenShift AI Component Architecture: Three Tiers

OpenShift AI bundles many open-source tools. Understanding HOW they're installed determines what you need to learn:

### Tier 1: DSC Operator Components

Components with a `managementState` field in the `DataScienceCluster` CR. Set to `Managed` (enabled) or `Removed` (disabled). The OpenShift AI operator handles deployment, upgrades, and lifecycle.

| DSC Field | What It Deploys | Key Sub-Releases (3.4.2) |
|-----------|----------------|--------------------------|
| `dashboard` | OpenShift AI web UI | — |
| `workbenches` | Jupyter/VS Code notebooks | Kubeflow Notebook Controller v1.10.0 |
| `kserve` | Model serving | KServe v0.17.0, vLLM v0.18.0, llm-d scheduler v0.7.1 |
| `modelregistry` | Model Registry | Kubeflow Model Registry |
| `mlflowoperator` | MLflow experiment tracking | MLflow v3.10.1 |
| `trustyai` | Evaluation + safety | TrustyAI operator v1.37.0, LMEval (lm-eval-harness v0.4.8), EvalHub, Guardrails Orchestrator v0.9.4, builtin detectors |
| `aipipelines` | Data Science Pipelines | Kubeflow Pipelines v2.16.0 + Argo Workflows |
| `ray` | Distributed compute | KubeRay v1.4.2 |
| `feastoperator` | Feature store | Feast v0.62.0 |
| `kueue` | GPU job scheduling | — |
| `trainer` | Training Hub (fine-tuning) | Requires JobSet operator |
| `trainingoperator` | Kubeflow Training Operator (legacy) | — |
| `sparkoperator` | Apache Spark | — |
| `llamastackoperator` | OGX / Llama Stack | — |

Example `DataScienceCluster` CR (API version `v2`):

```yaml
apiVersion: datasciencecluster.opendatahub.io/v2
kind: DataScienceCluster
metadata:
  name: default-dsc
spec:
  components:
    dashboard:
      managementState: Managed
    kserve:
      managementState: Managed
    workbenches:
      managementState: Managed
    mlflowoperator:
      managementState: Managed
    trustyai:
      managementState: Managed
    aipipelines:
      managementState: Managed
    ray:
      managementState: Managed
    modelregistry:
      managementState: Managed
    feastoperator:
      managementState: Managed
    trainer:
      managementState: Managed
    llamastackoperator:
      managementState: Removed   # Enable for OGX/RAG features
    kueue:
      managementState: Removed   # Enable for GPU job scheduling
    trainingoperator:
      managementState: Removed   # Legacy, use trainer instead
    sparkoperator:
      managementState: Removed
```

> **Key insight**: vLLM is NOT a separate install — it's a sub-release of `kserve`. EvalHub is NOT a separate component — it's part of `trustyai`. You don't install these individually.

### Tier 2: Dashboard Features

Composite features that appear in the OpenShift AI dashboard when their underlying Tier 1 components are enabled. No separate install step — they're features, not components.

| Feature | Required Tier 1 Components | Where in Dashboard |
|---------|---------------------------|-------------------|
| **AutoRAG** (Technology Preview) | `dashboard` + `aipipelines` + `kserve` + `llamastackoperator` | Gen AI Studio > AutoRAG |
| **AutoML** (Technology Preview) | `dashboard` + `aipipelines` + `workbenches` + `modelregistry` | Dashboard (leaderboard) |
| **GenAI Playground** | `dashboard` + `kserve` | Gen AI Studio > Playground |

These features orchestrate multiple Tier 1 components. For example, AutoRAG runs KFP pipelines that use KServe endpoints and OGX/Llama Stack instances.

### Tier 3: Python Libraries

Tools you `pip install` and use in code. Red Hat documents how to use them on OpenShift AI but doesn't manage their lifecycle via operators.

| Library | How You Use It | Sub-Tutorial |
|---------|---------------|--------------|
| NeMo Guardrails | `pip install nemoguardrails` — Colang 2.0 DSL for safety rails | `tutorial_ai/nemo_guardrails/` |
| LangChain/LangGraph | `pip install langchain langgraph` — agent frameworks | External: `ai-agents-course` |
| AutoRAG (standalone) | `pip install autorag` — local RAG optimization (different from Tier 2 dashboard feature) | `tutorial_ai/autorag/` |
| MLflow SDK | `pip install mlflow` — tracking/tracing API (server is Tier 1 `mlflowoperator`) | External: `mlflow-tutorial` |

> **The practical difference**: Tier 1 = `oc apply` (operator deploys everything). Tier 2 = enable Tier 1 deps, feature appears in UI. Tier 3 = `pip install`, write code. Either way, you interact with the tool's OWN API — OpenShift AI provides infrastructure, not a different API.

## Prerequisites

### Required Knowledge
- OpenShift fundamentals (completed main openshift-tutorial or equivalent)
- Kubernetes concepts (Deployments, Services, Operators, CRDs)
- Python 3.10+
- Basic LLM concepts (inference, fine-tuning, embeddings, RAG)

### Required Environment
- OpenShift 4.19+ cluster with:
  - Minimum 2 worker nodes: 8 CPUs + 32 GiB RAM each
  - At least 1 NVIDIA GPU (A100, H100, L40S, or T4) for serving/fine-tuning lessons
  - CPU-only mode available for select lessons (noted per lesson)
  - Storage: S3-compatible object storage (MinIO for dev, AWS S3 for production)
- `oc` CLI installed and authenticated
- `kfp` Python SDK installed locally (for pipeline lessons)

### Environment Options

| Option | GPU | Cluster-Admin | Cost | Best For |
|--------|-----|--------------|------|----------|
| AWS/GCP/Azure OpenShift cluster | Yes (rent GPU instances) | Yes | $$-$$$ | Full tutorial, production-like |
| ROSA (Red Hat OpenShift on AWS) | Yes | Yes | $$ | Managed cluster, less ops overhead |
| On-prem OpenShift with GPUs | Yes | Yes | Hardware cost | Enterprise labs |
| CRC (OpenShift Local) | No (CPU only) | Yes | Free | Platform exploration, operator install practice |
| Developer Sandbox | No | No | Free | Dashboard exploration only (pre-configured, can't change components) |

> **Note:** CRC has cluster-admin access so you can install the OpenShift AI operator and explore the DataScienceCluster CR, but has no GPU and limited resources (~9 GB RAM default) — most AI workloads will fail. Developer Sandbox has components pre-configured by Red Hat but you cannot enable/disable them (no cluster-admin access). A proper cluster with GPU nodes is strongly recommended for lessons beyond L1-M1.

### Prerequisite External Tutorials

These external tools are used extensively. Complete their sub-tutorials (in `tutorial_ai/`) before the lessons that reference them:

| Tool | Sub-Tutorial | Needed Before | Tier |
|------|-------------|---------------|------|
| OGX (Llama Stack) | `tutorial_ai/ogx/` | L2-M1 (RAG) | Tier 1 (`llamastackoperator`) |
| NeMo Guardrails | `tutorial_ai/nemo_guardrails/` | L3-M1 (Governance) | Tier 3 (Python library) |
| EvalHub | `tutorial_ai/evalhub/` | L3-M2 (Agent Evaluation) | Tier 1 (part of `trustyai`) |
| AutoRAG (standalone) | External: `autorag-tutorial` | L2-M1.6 (AutoRAG Dashboard) | Tier 3 (Python library) / Tier 2 (dashboard) |

> **Note:** vLLM, KFP SDK, and InstructLab are covered inline in the main syllabus lessons — no separate sub-tutorials needed. vLLM is bundled as a sub-release of `kserve`. KFP SDK is introduced in L2-M4. InstructLab is a niche advanced topic in L3-M4.1.

Already-completed tutorials that are referenced:
- **MLflow**: `/Users/lkellers/Projects/github/lukaskellerstein/mlflow-tutorial`
- **MCP**: `/Users/lkellers/Projects/github/lukaskellerstein/ai-agents-course/Version_2/2_MCP`
- **LangChain/LangGraph**: `/Users/lkellers/Projects/github/lukaskellerstein/ai-agents-course/Version_2/6_langchain-ai`

## Reference Sources

- **OpenShift AI Documentation 3.5**: https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5
- **OpenShift AI Documentation**: https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.4
- **Open Data Hub (upstream)**: https://github.com/opendatahub-io/opendatahub-operator
- **RedHatAI Models on Hugging Face**: https://huggingface.co/RedHatAI
- **AI on OpenShift Community**: https://ai-on-openshift.io/
- **Validated Patterns (RAG)**: https://validatedpatterns.io/patterns/rag-llm-gitops/
- **llm-d Project**: https://github.com/llm-d/llm-d
- **Training Hub**: https://github.com/Red-Hat-AI-Innovation-Team/training_hub
- **OpenShift MCP Server**: https://github.com/openshift/openshift-mcp-server
- **OGX / Llama Stack**: https://github.com/ogx-ai

## Version Context

OpenShift AI 3.x launched in November 2025. Key versions:

| Version | Release | Highlights |
|---------|---------|-----------|
| 3.0 | Nov 2025 | llm-d GA, Hardware Profiles, ModelMesh removed, Llama Stack (TP) |
| 3.2 | Early 2026 | Kubeflow Trainer v2 (TP), Feast, GenAI Playground |
| 3.3 | Mar 2026 | AI Hub, GenAI Playground GA, MLflow (Dev Preview) |
| 3.4 | May 2026 | MLflow GA, NeMo Guardrails GA, MaaS GA, EvalHub (TP) |
| 3.5 | Jun 2026 | EvalHub in official docs, AutoRAG/AutoML dashboard features, OGX operator improvements |

This tutorial targets **3.4-3.5** and notes feature status (GA, Tech Preview, Dev Preview) throughout.

> **Note:** The DataScienceCluster API is `v2` as of 3.4.2 (`datasciencecluster.opendatahub.io/v2`).

---
---

# LEVEL 1 — FOUNDATIONS

*Goal: Deploy OpenShift AI, serve a model, fine-tune it, serve the fine-tuned version, benchmark both.*
*Estimated time: ~12-14 hours*

---

## L1-M1: Platform Setup

### L1-1.1 — OpenShift AI Architecture Overview
**Duration:** 30 min
**Topics:**
- What is OpenShift AI? (MLOps + GenAIOps + AgentOps platform)
- Three-tier component architecture:
  - **Tier 1**: DSC operator components (14 components with `managementState`)
  - **Tier 2**: Dashboard features built on Tier 1 (AutoRAG, AutoML, GenAI Playground)
  - **Tier 3**: Python libraries used in workbenches/pods (NeMo Guardrails, LangChain)
- Key CRDs: `DSCInitialization`, `DataScienceCluster` (API `v2`), `InferenceService`, `ServingRuntime`
- Full DSC component table: what each component deploys and its sub-releases
- Relationship to upstream Open Data Hub
- Red Hat AI ecosystem: Podman AI Lab → RHEL AI → OpenShift AI progression
- K8s context: how OpenShift AI builds on operators, CRDs, and namespaces you already know

**Deliverables:**
- Architecture diagram (in README)
- Component-to-CRD mapping reference table

---

### L1-1.2 — Installing OpenShift AI
**Duration:** 45 min
**Prerequisites:** OpenShift 4.19+ cluster with cluster-admin access
**Topics:**
- Installing prerequisite operators: cert-manager, JobSet (required for `trainer`)
- Installing the `rhods-operator` from OperatorHub (stable-3.x channel)
- Creating `DSCInitialization` (monitoring, trusted CAs, applications namespace)
- Creating `DataScienceCluster` (API `v2`):
  - Choosing which components to enable (`Managed` vs `Removed`)
  - Component dependencies (e.g., `kserve` needs cert-manager; `trainer` needs JobSet operator)
  - Full CR example with all 14 components
- Verifying installation: operator pods, dashboard access, component readiness
- Understanding component status conditions (e.g., `KserveReady`, `TrustyAIReady`)
- Configuring S3 storage (MinIO for dev or AWS S3)
- K8s comparison: this is Helm charts + manual installs vs. one operator managing everything
- Environment limitations: CRC (no GPU), Developer Sandbox (no cluster-admin)

**Deliverables:**
- Running OpenShift AI installation with dashboard accessible
- `DataScienceCluster` manifest with all required components enabled

---

### L1-1.3 — Dashboard and AI Hub Tour
**Duration:** 20 min
**Topics:**
- Dashboard navigation: Applications, Data Science Projects, Model Serving, Pipelines
- AI Hub (3.3+): Model Catalog, Model Registry, Deployments, Endpoints, Playground
- Data Science Projects: creating a project, data connections, storage
- Settings: notebook images, serving runtimes, cluster settings
- User roles: `rhods-admins` vs `rhods-users`

**Deliverables:**
- Data Science Project created for the tutorial
- S3 data connection configured

---

### L1-1.4 — Workbenches
**Duration:** 30 min
**Topics:**
- What is a workbench? (IDE running as a container on the cluster)
- Available IDEs: JupyterLab, code-server (VS Code), RStudio (TP)
- Pre-built images: Standard Data Science, CUDA, PyTorch, TensorFlow
- Creating a workbench from the dashboard
- Persistent storage for notebooks
- Environment variables and data connections
- Custom workbench images (UBI-based, `/api` endpoint requirement)
- K8s comparison: `Notebook` CRD (`kubeflow.org/v1`) vs. manually deploying JupyterHub

**Deliverables:**
- JupyterLab workbench running with CUDA image
- Basic notebook verifying GPU access (`torch.cuda.is_available()`)

---

### L1-1.5 — GPU and Hardware Setup
**Duration:** 30 min
**Prerequisites:** Cluster with GPU nodes
**Topics:**
- Node Feature Discovery (NFD) operator
- NVIDIA GPU Operator installation and verification
- Hardware Profiles CRD (`infrastructure.opendatahub.io/v1`): replacing Accelerator Profiles
- Creating hardware profiles for different GPU configurations
- GPU sharing: MIG (Multi-Instance GPU) partitioning vs time-slicing
- Verifying GPU availability: `nvidia-smi`, device plugin pods
- K8s comparison: same GPU operator, but Hardware Profiles are OpenShift AI-specific

**Deliverables:**
- GPU operator running, GPUs visible to workloads
- Hardware profile created for the tutorial's GPU configuration

---

### L1-1.6 — GenAI Playground
**Duration:** 20 min
**Prerequisites:** L1-1.3 completed, at least one model deployed (or use after L1-2.2)
**Topics:**
- GenAI Playground as a Tier 2 dashboard feature (GA in 3.3+)
- Required Tier 1 components: `dashboard` + `kserve`
- Playground capabilities:
  - Interactive prompt testing against deployed models
  - Side-by-side model comparison (Technology Preview)
  - Parameter tuning: temperature, max tokens, top-p in the UI
  - System prompt experimentation
- MCP tool testing in the Playground:
  - Adding MCP server connections
  - Testing tool calling interactively
  - Exporting working configurations as Python code templates
- Use case: rapid prototyping before writing code
- K8s comparison: no equivalent in vanilla Kubernetes — closest is standalone tools like LiteLLM UI

**Deliverables:**
- Interactive prompt testing with a deployed model in the Playground
- Understanding of when to use Playground vs workbench for experimentation

---

## L1-M2: Model Serving and Inference

### L1-2.1 — KServe Fundamentals
**Duration:** 30 min
**Prerequisites:** L1-M1 completed
**Topics:**
- KServe architecture on OpenShift AI: predictor, transformer, explainer
- Two deployment modes: Serverless (Knative, deprecated) vs RawDeployment (recommended)
- Key CRDs: `ServingRuntime`, `InferenceService`
- Available serving runtimes: vLLM (CUDA/ROCm/Gaudi/CPU), OpenVINO, MLServer
- vLLM fundamentals: PagedAttention, continuous batching, OpenAI-compatible API
  - vLLM is bundled as a sub-release of `kserve` — not a separate install
  - Red Hat ships it as "Red Hat AI Inference Server" (UBI-based vLLM image)
- Model storage: OCI/ModelCar, S3, PVC, `hf://` URIs
- K8s comparison: KServe works on vanilla K8s too, but OpenShift AI adds dashboard integration, monitoring, and auth

**Deliverables:**
- Understand which runtime to use for which model type
- Diagram: request flow from client → Route → KServe → vLLM → GPU

---

### L1-2.2 — Deploying Gemma4-e4b with vLLM
**Duration:** 45 min
**GPU Required:** Yes (T4 minimum, L40S recommended)
**Topics:**
- Choosing a model: RedHatAI quantized models on Hugging Face
- Creating a `ServingRuntime` for vLLM
- Creating an `InferenceService` pointing to `Gemma4-e4b`
- Model storage options: OCI image (fastest startup) vs S3 download
- Resource allocation: GPU requests, memory limits
- Verifying the deployment: pod status, model loading, readiness
- First inference: calling the OpenAI-compatible API (`/v1/chat/completions`)
- Dashboard: viewing the deployed model, endpoint URL

**Deliverables:**
- Gemma4-e4b running on vLLM, responding to chat completions
- `curl` commands demonstrating the API
- `ServingRuntime` and `InferenceService` manifests

---

### L1-2.3 — OpenAI-Compatible API Deep Dive
**Duration:** 30 min
**Topics:**
- vLLM's OpenAI-compatible endpoints:
  - `/v1/chat/completions` (chat)
  - `/v1/completions` (text completion)
  - `/v1/embeddings` (embeddings)
  - `/v1/models` (list models)
- Request parameters: temperature, max_tokens, top_p, stream, stop
- Streaming responses (SSE)
- Using the API from Python (`openai` SDK, `requests`, `langchain-openai`)
- Token counting and usage tracking
- Structured output / JSON mode

**Deliverables:**
- Python script calling the deployed model via `openai` SDK
- Streaming chat example
- Embedding generation example (if model supports it)

---

### L1-2.4 — Autoscaling Model Endpoints
**Duration:** 30 min
**Topics:**
- HPA (Horizontal Pod Autoscaler) for RawDeployment mode
  - CPU/memory-based scaling
  - Configuration via `InferenceService` annotations
- KEDA (Kubernetes Event Driven Autoscaling)
  - Prometheus metrics-based scaling (`vllm:num_requests_waiting`)
  - Scale-to-zero support
  - Better for LLM workloads than HPA
- Scaling configuration: min/max replicas, scale-up/down stabilization
- Monitoring scaling behavior

**Deliverables:**
- KEDA-based autoscaling configured for the Gemma4-e4b endpoint
- Load test demonstrating scale-up behavior

---

## L1-M3: Model Fine-Tuning

### L1-3.1 — Fine-Tuning Concepts on OpenShift AI
**Duration:** 30 min
**Topics:**
- Fine-tuning landscape: SFT, LoRA, QLoRA, OSFT
- When to fine-tune vs. prompt engineering vs. RAG
- OpenShift AI fine-tuning options:
  - Training Hub (notebook-based, simplest)
  - Kubeflow Trainer v2 (distributed, production)
  - InstructLab / LAB-tuning (taxonomy-based, advanced)
- Progressive scaling: notebook → single-node → distributed → pipeline
- Hardware requirements per approach
- Key CRDs: `TrainJob`, `ClusterTrainingRuntime`

**Deliverables:**
- Decision tree: which fine-tuning approach for which scenario
- Comparison table: SFT vs LoRA vs QLoRA (VRAM, speed, quality)

---

### L1-3.2 — Fine-Tuning Gemma4-e4b with Training Hub
**Duration:** 1.5 hours
**GPU Required:** Yes (LoRA: ~4 GB VRAM, QLoRA: ~2 GB VRAM)
**Topics:**
- Training Hub Python library (`training_hub`)
- Preparing a training dataset (instruction format: system/user/assistant)
- LoRA fine-tuning in a workbench notebook:
  - Loading the base model
  - Configuring LoRA parameters (rank, alpha, target modules)
  - Training loop with Training Hub
  - Monitoring training loss
- QLoRA variant: 4-bit quantization during training (less VRAM)
- Unsloth backend: ~70% less VRAM, ~2x faster
- Saving adapter weights
- Evaluating the fine-tuned model in the notebook

**Deliverables:**
- Fine-tuned LoRA adapter for Gemma4-e4b on a custom dataset
- Training metrics: loss curves, evaluation results
- Saved adapter weights in S3

---

### L1-3.3 — Deploying the Fine-Tuned Model
**Duration:** 45 min
**Topics:**
- Merging LoRA adapter with base model
- Packaging the merged model for serving:
  - Upload to S3
  - Build OCI image (optional, for production)
- Creating a new `InferenceService` for the fine-tuned model
- Side-by-side comparison: base vs fine-tuned responses
- Registering both models in Model Registry (preview for M4)

**Deliverables:**
- Fine-tuned Gemma4-e4b deployed and serving via vLLM
- Side-by-side API comparison: base vs fine-tuned

---

## L1-M4: Model Registry and Lifecycle

### L1-4.1 — Model Registry Setup
**Duration:** 30 min
**Topics:**
- Model Registry architecture: metadata store (not artifact store)
- Data model: RegisteredModel → ModelVersion → ModelArtifact
- Setting up Model Registry on OpenShift AI (component in DSC)
- Backend database: MySQL (recommended) or PostgreSQL
- CRD: `ModelRegistry` (`modelregistry.opendatahub.io/v1beta1`)
- Dashboard integration: viewing models, versions, artifacts

**Deliverables:**
- Model Registry running with database backend
- Dashboard showing the registry interface

---

### L1-4.2 — Registering and Managing Models
**Duration:** 30 min
**Topics:**
- Registering models via dashboard
- Registering models via Python SDK (`model-registry` package)
- Model versioning: creating versions, adding metadata
- Labels, tags, and custom properties
- Model lifecycle: experiment → registered → deployed
- REST API: `/api/model_registry/v1alpha3/`
- Linking model versions to serving endpoints

**Deliverables:**
- Base and fine-tuned Gemma4-e4b registered with versions
- Python script demonstrating SDK operations
- Model deployed directly from registry

---

## L1-M5: Model Evaluation and Benchmarking

### L1-5.1 — LMEvalJob — Model Quality Benchmarking
**Duration:** 45 min
**Topics:**
- TrustyAI component and LMEvalJob CRD
- EleutherAI LM Evaluation Harness (lm-eval): what it is, how it works
- Available benchmarks: MMLU, HellaSwag, ARC, TruthfulQA, HumanEval, custom
- Unitxt integration for additional tasks
- Creating an `LMEvalJob` to benchmark the base model
- Creating an `LMEvalJob` to benchmark the fine-tuned model
- Comparing results: base vs fine-tuned on the same benchmarks
- Viewing results in dashboard / extracting from job logs

**Deliverables:**
- Benchmark results for base Gemma4-e4b
- Benchmark results for fine-tuned Gemma4-e4b
- Comparison table showing improvement (or regression) per benchmark

---

### L1-5.2 — GuideLLM — Inference Performance Benchmarking
**Duration:** 30 min
**Topics:**
- GuideLLM: SLO-aware inference benchmarking tool (from Neural Magic / vLLM project)
- Measuring serving performance:
  - Time to First Token (TTFT)
  - Inter-Token Latency (ITL)
  - End-to-End Latency
  - Throughput (tokens/second)
- Running GuideLLM against the deployed model endpoint
- Interpreting results: latency percentiles, throughput curves
- SLO compliance: does the endpoint meet latency requirements?

**Deliverables:**
- GuideLLM benchmark report for the deployed Gemma4-e4b
- Latency/throughput analysis

---

### L1-5.3 — Serving Metrics and Grafana Dashboards
**Duration:** 30 min
**Topics:**
- vLLM Prometheus metrics:
  - `vllm:time_to_first_token_seconds`
  - `vllm:inter_token_latency_seconds`
  - `vllm:e2e_request_latency_seconds`
  - `vllm:num_requests_running` / `vllm:num_requests_waiting`
  - `vllm:kv_cache_usage_perc`
  - `vllm:prompt_tokens_total` / `vllm:generation_tokens_total`
- OpenShift monitoring stack integration (built-in Prometheus + Grafana)
- Pre-built Grafana dashboards for vLLM
- Creating `ServiceMonitor` for custom metrics scraping
- Setting up alerts (e.g., KV cache usage > 90%, latency SLO breach)

**Deliverables:**
- Grafana dashboard showing vLLM metrics for the deployed model
- Alert rule for latency SLO violation

---

## L1-M6: AutoML (Dashboard Feature)

### L1-6.1 — AutoML: Automated Model Training
**Duration:** 45 min
**Prerequisites:** L1-M1 completed
**Topics:**
- AutoML as a Tier 2 dashboard feature (Technology Preview, 3.4+)
- Required Tier 1 components: `dashboard` + `aipipelines` + `workbenches` + `modelregistry`
- What AutoML does: automated training, comparison, and selection of ML models
- Creating an AutoML optimization run:
  - Selecting training data and target variable
  - Configuring the optimization (algorithms, hyperparameters, time budget)
  - Monitoring pipeline execution (runs as KFP pipelines)
- Viewing results:
  - Model leaderboard: ranked by performance metrics
  - Generated notebooks: reproducible training code
  - Registering the winning model in Model Registry
- Deploying the best model via KServe
- Limitations: primarily for classical ML / tabular models, not LLM fine-tuning

**Deliverables:**
- AutoML optimization run completed via dashboard
- Model leaderboard with ranked results
- Best model registered and optionally deployed

---

### Level 1 Summary

| Module | Lessons | Estimated Time |
|--------|---------|---------------|
| M1: Platform Setup | 6 lessons | ~2.75 hours |
| M2: Model Serving & Inference | 4 lessons | ~2 hours |
| M3: Model Fine-Tuning | 3 lessons | ~2.75 hours |
| M4: Model Registry & Lifecycle | 2 lessons | ~1 hour |
| M5: Model Evaluation & Benchmarking | 3 lessons | ~1.75 hours |
| M6: AutoML (Dashboard Feature) | 1 lesson | ~0.75 hours |
| **Total** | **19 lessons** | **~12-14 hours** |

### GOAL.md Coverage After Level 1

| Requirement | Status |
|-------------|--------|
| Model deployment/inference (Gemma4-e4b) | **Complete** |
| Model fine-tuning (Gemma4-e4b) | **Complete** |
| Fine-tuned model inference | **Complete** |
| Model testing/benchmarking | **Complete** |
| MCP servers deployments | Level 2 |
| AI agents deployment | Level 2 |
| AI agents observability | Level 2 |
| AI agents evals/benchmarks | Level 3 |
| AI agents governance | Level 3 |
| RAG solution | Level 2 |

---
---

# LEVEL 2 — PRACTITIONER

*Goal: Build RAG solutions, deploy MCP servers, containerize and deploy AI agents, set up observability.*
*Prerequisite: Level 1 completed*
*Estimated time: ~25-30 hours*

---

## L2-M1: RAG on OpenShift AI

### L2-1.1 — RAG Architecture with OGX
**Duration:** 45 min
**Prerequisites:** Sub-tutorial: `tutorial_ai/ogx/` (Level 1)
**Topics:**
- RAG fundamentals recap: retrieval + augmented generation
- OGX (Open GenAI Stack / Llama Stack) architecture:
  - Inference API, Memory API, RAG API, Tool API, Agent API
  - Not limited to Llama models — supports 23 inference providers
- OGX Operator on OpenShift AI (Technology Preview)
- CRDs: `LlamaStackDistribution` (will likely rename to OGX)
- RAG reference architectures:
  - OGX-native RAG
  - LangChain + vLLM + vector DB
  - Validated Patterns: "AI Generation with LLM and RAG"

**Deliverables:**
- Architecture diagram: RAG components on OpenShift AI
- Decision matrix: OGX-native RAG vs LangChain-based RAG

---

### L2-1.2 — Vector Database Setup
**Duration:** 45 min
**Topics:**
- Vector DB options on OpenShift AI:
  - pgvector (PostgreSQL extension) — production-recommended
  - Milvus — high-performance, K8s-native
  - FAISS with SQLite — lightweight dev/test
  - Elasticsearch — certified on OpenShift, GPU-accelerated
- Deploying pgvector on OpenShift (PostgreSQL operator)
- Deploying Milvus on OpenShift (Milvus Operator)
- Configuring OGX to use the vector DB
- Embedding model serving: deploying an embedding model (nomic-embed-text) on vLLM
- Generating and storing embeddings

**Deliverables:**
- pgvector running on OpenShift
- Embedding model deployed on vLLM (`/v1/embeddings` endpoint)
- Test embeddings stored in pgvector

---

### L2-1.3 — Document Ingestion Pipeline
**Duration:** 1 hour
**Topics:**
- Document parsing with Docling (structure-aware PDF/HTML/DOCX parsing)
- Chunking strategies: fixed-size, semantic, document-aware
- Embedding generation via the deployed embedding model
- Ingestion pipeline: parse → chunk → embed → store
- Scaling ingestion with Ray Data (distributed document processing)
- Building the pipeline as a Data Science Pipeline (KFP, preview for M4)
- Metadata management: source tracking, versioning

**Deliverables:**
- Document ingestion pipeline processing a sample document set
- Chunks with embeddings stored in pgvector
- Metadata tracking which documents were ingested

---

### L2-1.4 — End-to-End RAG Application
**Duration:** 1 hour
**Topics:**
- Building a RAG application:
  - Option A: OGX RAG API (native, fewer components)
  - Option B: LangChain + vLLM + pgvector (framework-based)
- Retrieval: similarity search with pgvector
- Augmented generation: injecting context into the LLM prompt
- GenAI Playground: testing RAG with uploaded documents (3.3+)
- Deploying the RAG application as a containerized service on OpenShift
- Exposing via Route

**Deliverables:**
- Working RAG application deployed on OpenShift
- API endpoint accepting questions and returning context-aware answers
- GenAI Playground demonstration with the same model

---

### L2-1.5 — RAG Evaluation
**Duration:** 45 min
**Topics:**
- RAG evaluation dimensions: retrieval quality vs generation quality
- Retrieval metrics: precision@k, recall@k, MRR, NDCG
- Generation metrics: faithfulness, relevance, answer correctness
- Building an evaluation dataset (question + expected answer + source documents)
- Running evaluation with MLflow (reference: mlflow-tutorial L2-M3)
- Comparing RAG configurations: chunking strategies, embedding models, retrieval params
- Tracking evaluation results in MLflow

**Deliverables:**
- RAG evaluation pipeline
- Comparison of 2-3 chunking strategies with tracked metrics

---

### L2-1.6 — AutoRAG: Automated RAG Optimization (Dashboard)
**Duration:** 45 min
**Prerequisites:** L2-M1.1 through L2-M1.5 completed, Sub-tutorial: `tutorial_ai/autorag/` (standalone)
**Topics:**
- AutoRAG as a Tier 2 dashboard feature (Technology Preview, 3.4+)
- Required Tier 1 components: `dashboard` + `aipipelines` + `kserve` + `llamastackoperator`
- Standalone AutoRAG vs dashboard AutoRAG:
  - Standalone (`pip install autorag`): local experimentation, full control, any environment
  - Dashboard: integrated into OpenShift AI, runs as KFP pipelines, uses OGX/Llama Stack
- Creating an AutoRAG optimization run from Gen AI Studio:
  - Configuring generation models (max 2) and embedding models (max 3)
  - Connecting to a Llama Stack instance
  - Providing documents and test data
  - Monitoring pipeline execution
- Viewing results: optimal chunking, embedding, retrieval configuration
- Applying AutoRAG results to your RAG deployment

**Deliverables:**
- AutoRAG optimization run completed via dashboard
- Optimal RAG configuration identified and applied
- Comparison: dashboard AutoRAG vs standalone AutoRAG results

---

## L2-M2: MCP Server Deployment

### L2-2.1 — MCP on OpenShift AI Overview
**Duration:** 30 min
**Prerequisites:** MCP fundamentals (ai-agents-course/Version_2/2_MCP)
**Topics:**
- MCP in the OpenShift AI ecosystem:
  - MCP Lifecycle Operator (declarative server deployment)
  - MCP Server for OpenShift (K8s/OpenShift resource access)
  - MCP Gateway (federation, auth, credential management)
  - MCP Catalog (curated catalog in dashboard, Dev Preview)
  - GenAI Playground MCP (test tool calling)
- Architecture: how MCP servers connect to agents and LLMs on the platform
- Transport: Streamable HTTP (server-to-server on K8s) vs STDIO (local dev)
- Red Hat's membership in AAIF (Agentic AI Foundation)

**Deliverables:**
- Architecture diagram: MCP components on OpenShift AI
- Component status table (GA, TP, Dev Preview)

---

### L2-2.2 — Deploying MCP Servers with the Lifecycle Operator
**Duration:** 45 min
**Topics:**
- MCP Lifecycle Operator (Dev Preview v0.1.0): K8s-native MCP server management
- Deploying a custom MCP server:
  - Building a Python MCP server (reference: ai-agents-course FastMCP examples)
  - Containerizing with Podman (UBI-based image)
  - Creating MCP server deployment via the operator
  - Configuring tools, resources, prompts
- Exposing the MCP server endpoint (Streamable HTTP)
- Testing with a simple client
- Deploying from the MCP Catalog (Dev Preview)

**Deliverables:**
- Custom MCP server deployed on OpenShift via the Lifecycle Operator
- Streamable HTTP endpoint accessible within the cluster
- Client script calling the MCP server's tools

---

### L2-2.3 — MCP Server for OpenShift
**Duration:** 30 min
**Topics:**
- OpenShift MCP Server (`github.com/openshift/openshift-mcp-server`): Technology Preview
- Capabilities: CRUD on any K8s/OpenShift resource (read-only by default)
- RBAC-aware: server operates with the user's permissions
- Available tools: get/list/create/update/delete resources, logs, events
- Deploying the OpenShift MCP Server
- Connecting it to an AI agent (so the agent can manage cluster resources)
- Security implications and access control

**Deliverables:**
- OpenShift MCP Server deployed and accessible
- Agent calling K8s resource tools (list pods, get deployment status, etc.)

---

### L2-2.4 — MCP Gateway
**Duration:** 45 min
**Topics:**
- MCP Gateway (Technology Preview, part of Connectivity Link)
- Architecture: Envoy-based gateway federating multiple MCP servers
- Features:
  - Server federation: single endpoint for multiple MCP servers
  - OAuth2 authentication and credential management
  - Identity-based tool filtering (users see only authorized tools)
  - Health checking and failover
- Deploying the MCP Gateway
- Registering MCP servers behind the gateway
- Configuring authentication and tool access policies
- Testing: agent → gateway → multiple MCP servers

**Deliverables:**
- MCP Gateway deployed with 2+ MCP servers behind it
- OAuth2 authentication configured
- Agent accessing tools from multiple servers via single gateway endpoint

---

### L2-2.5 — Testing MCP in GenAI Playground
**Duration:** 20 min
**Topics:**
- GenAI Playground MCP integration (GA in 3.3+)
- Adding MCP server connections to the playground
- Testing tool calling interactively before production deployment
- Exporting working configurations as Python code templates
- Iterating on tool descriptions and schemas

**Deliverables:**
- MCP tools tested in GenAI Playground
- Exported Python code template for production use

---

## L2-M3: AI Agent Deployment

### L2-3.1 — Agent Deployment Patterns on OpenShift AI
**Duration:** 30 min
**Topics:**
- Agent deployment approaches:
  1. **BYO Framework on vLLM** — containerize LangChain/LangGraph/custom agents, point at vLLM
  2. **OGX Agents API** — native agent support via Llama Stack operator
  3. **Multi-Agent Supervisor** — centralized orchestrator routing to sandboxed agents
  4. **A2A via Kagenti** (planned H2 2026) — auto-discovered agents with zero-trust identity
- Framework-agnostic philosophy: Red Hat doesn't mandate a framework
- Choosing the right pattern for the use case
- Reference: ai-agents-course/Version_2/6_langchain-ai for framework fundamentals

**Deliverables:**
- Decision matrix: which deployment pattern for which use case
- Architecture diagrams for each pattern

---

### L2-3.2 — Deploying LangChain/LangGraph Agents
**Duration:** 1.5 hours
**Topics:**
- Containerizing a LangGraph agent for OpenShift:
  - UBI-based Dockerfile (compatible with OpenShift SCCs)
  - FastAPI/Flask wrapper exposing REST API
  - Environment variables for vLLM endpoint URL
  - Health checks and readiness probes
- Building with Podman, pushing to internal registry or Quay
- Deploying as a standard OpenShift Deployment + Service + Route
- Configuring the agent to use the deployed vLLM endpoint (OpenAI-compatible)
- Connecting MCP servers to the agent for tool calling
- Testing end-to-end: client → agent Route → agent → vLLM + MCP tools
- Reference code: `/Users/lkellers/Projects/github/lukaskellerstein/ai-agents-course/Version_2/6_langchain-ai/2_langgraph/5_agent`

**Deliverables:**
- LangGraph agent deployed on OpenShift with REST API
- Agent using vLLM for inference and MCP server for tool calling
- Deployment manifests (Deployment, Service, Route, ConfigMap)

---

### L2-3.3 — OGX Agents API
**Duration:** 1 hour
**Prerequisites:** Sub-tutorial: `tutorial_ai/ogx/` (agents section)
**Topics:**
- OGX Agents API (`/v1alpha/agents`):
  - Creating agent sessions
  - Agent turn execution
  - Tool calling integration
  - Memory and context management
- Deploying an agent using the OGX operator
- Comparing OGX agents vs LangGraph agents:
  - OGX: unified API, less code, tighter platform integration
  - LangGraph: more flexible, better for complex state machines
- Hybrid: LangGraph agent using OGX for inference and tools

**Deliverables:**
- OGX-native agent deployed and functional
- Comparison: same task implemented with OGX vs LangGraph

---

### L2-3.4 — Agents with MCP Tool Calling
**Duration:** 1 hour
**Topics:**
- Connecting agents to MCP servers:
  - LangGraph agent + MCP tools (via `langchain-mcp-adapters` or direct HTTP)
  - OGX agent + MCP tools (native integration)
- MCP tool calling flow: agent → LLM decides tool → MCP server executes → result back to LLM
- Deploying an agent that manages OpenShift resources via MCP Server for OpenShift
- Real-world scenario: chatbot that can check deployment status, read logs, list pods
- Security: agent permissions = MCP server RBAC = user's OpenShift roles
- Testing in GenAI Playground before production deployment

**Deliverables:**
- Agent managing OpenShift resources via MCP tool calling
- End-to-end demo: "How many pods are running in my project?" → agent → MCP → K8s API → answer

---

### L2-3.5 — Multi-Agent Systems on OpenShift
**Duration:** 1.5 hours
**Topics:**
- Multi-agent patterns:
  - Supervisor agent routing to specialist agents
  - Agent collaboration with shared state
  - Agent handoffs
- Deploying multiple agents as separate OpenShift services
- Inter-agent communication: REST APIs, shared message queue, or LangGraph subgraphs
- OGX multi-agent support
- Service mesh (Istio) for inter-agent traffic management (mTLS, observability)
- Kagenti preview: A2A protocol, AgentCard CRDs, SPIFFE identity (planned H2 2026)
- Reference: `/Users/lkellers/Projects/github/lukaskellerstein/ai-agents-course/Version_2/6_langchain-ai/2_langgraph/6_agents`

**Deliverables:**
- Multi-agent system deployed on OpenShift (supervisor + 2 specialist agents)
- Inter-agent communication via REST
- Architecture diagram with traffic flow

---

## L2-M4: Data Science Pipelines

### L2-4.1 — Pipeline Setup
**Duration:** 30 min
**Prerequisites:** L2-M1 completed
**Topics:**
- Data Science Pipelines architecture on OpenShift AI:
  - DSP Controller manages `DataSciencePipelinesApplication` (DSPA) CRDs
  - Argo Workflows as the backend engine
  - ML Metadata Store for artifact and lineage tracking
  - S3 storage for pipeline artifacts
- KFP v2 SDK fundamentals: `@dsl.component`, `@dsl.pipeline`, `compiler.Compiler()`
  - No separate sub-tutorial needed — KFP SDK is covered inline in this module
  - Backend engine: Argo Workflows (managed by `aipipelines`, not used directly)
- Creating a DSPA instance (dashboard or YAML)
- Configuring S3 backend for artifact storage
- Pipeline server access: dashboard UI and REST API

**Deliverables:**
- Pipeline server running with S3 backend
- Dashboard showing the pipelines interface

---

### L2-4.2 — Building Pipelines with KFP SDK
**Duration:** 1 hour
**Topics:**
- KFP v2 SDK: `@dsl.component`, `@dsl.pipeline`, `compiler.Compiler()`
- Component types: lightweight (Python function), containerized
- Pipeline parameters and artifacts
- Compiling pipelines to YAML
- Uploading and running pipelines from the dashboard
- Uploading and running pipelines from Python (`kfp.Client()`)
- Viewing run results, logs, and artifacts
- Scheduling recurring pipeline runs

**Deliverables:**
- Simple pipeline: fetch data → process → log results
- Pipeline YAML compiled and uploaded to the pipeline server
- Successful run with viewable artifacts

---

### L2-4.3 — Training Pipeline: Data Prep → Train → Evaluate → Register
**Duration:** 1.5 hours
**Topics:**
- End-to-end ML pipeline:
  1. Data preparation component (fetch and format training data)
  2. Fine-tuning component (Training Hub or Kubeflow Trainer)
  3. Evaluation component (LMEvalJob benchmarks)
  4. Registration component (register in Model Registry if quality threshold met)
  5. Deployment component (optional: auto-deploy to KServe)
- Pre-built fine-tuning pipelines: `sft_pipeline`, `osft_pipeline`
- Passing GPU resources to pipeline components
- Pipeline parameters: model name, dataset, LoRA config, evaluation tasks
- Monitoring pipeline execution in dashboard
- Elyra extension: visual pipeline design from JupyterLab (no-code)

**Deliverables:**
- Full training pipeline: data → fine-tune → evaluate → register
- Pipeline parameterized for different models and datasets
- Successful run with model registered and benchmark results

---

### L2-4.4 — RAG Ingestion Pipeline
**Duration:** 45 min
**Topics:**
- Building a pipeline for RAG document ingestion:
  1. Fetch documents from S3 or web source
  2. Parse with Docling (PDF/HTML extraction)
  3. Chunk documents (configurable strategy)
  4. Generate embeddings (via deployed embedding model)
  5. Store in vector database (pgvector/Milvus)
- Scheduling recurring ingestion for new documents
- Triggering re-ingestion when embedding model changes
- Metadata tracking: document source, ingestion timestamp, chunk count

**Deliverables:**
- RAG ingestion pipeline deployed and running
- Scheduled recurring run for new documents

---

## L2-M5: AI Agent Observability

### L2-5.1 — MLflow on OpenShift AI
**Duration:** 45 min
**Prerequisites:** mlflow-tutorial (Level 1 minimum)
**Topics:**
- MLflow as a managed component in OpenShift AI (GA in 3.4, v3.10.1)
- Component in `DataScienceCluster` spec: `mlflowoperator`
- What MLflow provides on the platform:
  - Experiment tracking (runs, parameters, metrics, artifacts)
  - Model registry integration
  - Agent traceability (traces tab)
- Connecting workbenches to the MLflow tracking server
- Viewing experiments and traces in the MLflow UI (accessed via dashboard)
- Relationship to the standalone MLflow tutorial you've already completed

**Deliverables:**
- MLflow accessible on the cluster
- Experiment logged from a workbench with viewable results

---

### L2-5.2 — Agent Tracing with MLflow
**Duration:** 1 hour
**Topics:**
- Auto-tracing LangChain/LangGraph agents: `mlflow.langchain.autolog()`
- Trace structure: spans for tool calls, LLM inference, retrieval steps
- Viewing agent execution traces in MLflow UI
- Manual tracing for custom agent components: `@mlflow.trace`, `mlflow.start_span()`
- Tracing MCP tool calls within agent flows
- Tracing RAG retrieval + generation separately
- Reference: mlflow-tutorial L2-M4 (Advanced Tracing), L2-M5 (Agent Observability)

**Deliverables:**
- LangGraph agent with full tracing visible in MLflow
- Traces showing: user input → LLM reasoning → tool calls → final response
- Performance analysis: identifying slow spans

---

### L2-5.3 — OpenTelemetry for Inference
**Duration:** 45 min
**Topics:**
- OpenTelemetry (OTel) integration in OpenShift AI (GA in 3.0+)
- Distributed tracing for inference requests:
  - Client → Route → KServe → vLLM → response
- OTel collector deployment on OpenShift
- Exporting traces to Jaeger or compatible backends
- Correlating inference traces with agent traces (MLflow)
- End-to-end observability: agent trace (MLflow) + inference trace (OTel) + metrics (Prometheus)

**Deliverables:**
- OTel tracing configured for vLLM inference
- End-to-end trace: agent → vLLM inference → response

---

### L2-5.4 — TrustyAI Model Monitoring
**Duration:** 45 min
**Topics:**
- TrustyAI component (GA, v1.37.0):
  - Bias detection: SPD (Statistical Parity Difference), DIR (Disparate Impact Ratio)
  - Data drift detection: MeanShift, FourierMMD, KSTest
  - Explainability: LIME, SHAP, Counterfactual
- Limitations: bias/drift metrics require tabular models on OpenVINO (not LLMs)
- LLM-relevant TrustyAI features:
  - LMEvalJob for quality monitoring over time
  - Integration with NeMo Guardrails for safety monitoring
- Setting up TrustyAI for a deployed model
- Prometheus metrics from TrustyAI (`trustyai_spd`, `trustyai_dir`)

**Deliverables:**
- TrustyAI monitoring configured for a tabular model on OpenVINO
- Bias metrics visible in Grafana
- Understanding of LLM monitoring limitations and workarounds

---

### L2-5.5 — Production Dashboards
**Duration:** 45 min
**Topics:**
- Comprehensive monitoring dashboard combining:
  - vLLM serving metrics (latency, throughput, cache usage)
  - GPU utilization (NVIDIA DCGM metrics)
  - Agent performance (MLflow metrics export)
  - Pipeline execution status
  - Model registry state
- Pre-built dashboard templates
- Custom Grafana dashboards for the tutorial's workloads
- Alert rules: SLO violations, GPU memory pressure, model errors

**Deliverables:**
- Unified Grafana dashboard for the tutorial's AI workloads
- Alert rules configured for key SLOs

---

## L2-M6: Distributed Workloads

### L2-6.1 — KubeRay and Ray Clusters
**Duration:** 45 min
**Topics:**
- Ray on OpenShift AI: KubeRay operator (v1.4.2)
- CRDs: `RayCluster`, `RayJob`, `RayService`
- CodeFlare SDK: Python interface for Ray cluster management from workbenches
- Creating a Ray cluster for distributed tasks:
  - Document processing (Ray Data)
  - Hyperparameter search (Ray Tune)
  - Distributed inference (Ray Serve)
- Resource management and GPU allocation
- Auto-scaling Ray clusters

**Deliverables:**
- Ray cluster deployed on OpenShift
- Distributed document processing job using Ray Data
- Ray dashboard accessible

---

### L2-6.2 — Kueue: Job Queuing and Quota Management
**Duration:** 30 min
**Topics:**
- Kueue on OpenShift AI: fair-sharing GPU resources across teams
- CRDs: `ClusterQueue`, `LocalQueue`, `Workload`, `ResourceFlavor`
- Configuring GPU quotas per team/project
- Priority-based scheduling: urgent training jobs go first
- Borrowing: teams can use idle GPU capacity from other queues
- Preemption policies: when can a high-priority job evict a low-priority one
- Integration with Kubeflow Trainer and Ray

**Deliverables:**
- Kueue configured with 2 queues (dev/prod) and GPU quotas
- Demonstration of priority-based scheduling

---

### L2-6.3 — Distributed Fine-Tuning with Kubeflow Trainer
**Duration:** 1 hour
**Topics:**
- Kubeflow Trainer v2 (GA in 3.4): unified `TrainJob` API
- Pre-built `ClusterTrainingRuntime`: `torch-distributed`, `training-hub`
- Multi-node multi-GPU fine-tuning:
  - PyTorch FSDP (Fully Sharded Data Parallel)
  - Configuring parallelism: data parallel, tensor parallel, pipeline parallel
- Creating a `TrainJob` for distributed LoRA fine-tuning
- Fault tolerance: JIT checkpointing (PVC or S3)
- Monitoring training with Ray dashboard and Prometheus
- Python SDK for job submission from workbenches
- Comparison: workbench notebook (L1) vs distributed TrainJob (this lesson)

**Deliverables:**
- Distributed fine-tuning job running across 2+ nodes/GPUs
- Checkpoint management and fault recovery demonstration
- Performance comparison: single-GPU vs distributed

---

### L2-6.4 — Apache Spark on OpenShift AI
**Duration:** 45 min
**Topics:**
- Spark Operator in the DSC (`sparkoperator` component)
- When to use Spark vs Ray vs Kubeflow Pipelines:
  - Spark: large-scale structured data processing (ETL, feature engineering)
  - Ray: distributed ML workloads (training, inference, document processing)
  - KFP: pipeline orchestration (sequencing tasks, not running them)
- Deploying Spark applications via the Spark Operator
- CRDs: `SparkApplication`, `ScheduledSparkApplication`
- Use cases for AI workloads:
  - Large-scale feature engineering for ML models
  - Data preprocessing before RAG ingestion (large document corpora)
  - Distributed data validation and quality checks
- Integration with Data Science Pipelines: Spark as a pipeline component
- Resource management: Spark executor pods, GPU allocation
- Monitoring Spark jobs: Spark UI, Prometheus metrics

**Deliverables:**
- Spark application processing a dataset on OpenShift AI
- Understanding of when to choose Spark vs Ray for data processing

---

### Level 2 Summary

| Module | Lessons | Estimated Time |
|--------|---------|---------------|
| M1: RAG on OpenShift AI | 6 lessons | ~5 hours |
| M2: MCP Server Deployment | 5 lessons | ~2.75 hours |
| M3: AI Agent Deployment | 5 lessons | ~5.5 hours |
| M4: Data Science Pipelines | 4 lessons | ~3.75 hours |
| M5: AI Agent Observability | 5 lessons | ~4 hours |
| M6: Distributed Workloads | 4 lessons | ~3 hours |
| **Total** | **29 lessons** | **~24-28 hours** |

### GOAL.md Coverage After Level 2

| Requirement | Status |
|-------------|--------|
| Model deployment/inference (Gemma4-e4b) | **Complete** (L1) |
| Model fine-tuning (Gemma4-e4b) | **Complete** (L1 + L2-M6) |
| Fine-tuned model inference | **Complete** (L1) |
| Model testing/benchmarking | **Complete** (L1) |
| MCP servers deployments | **Complete** |
| AI agents deployment | **Complete** |
| AI agents observability | **Complete** |
| AI agents evals/benchmarks | Level 3 |
| AI agents governance | Level 3 |
| RAG solution | **Complete** |

---
---

# LEVEL 3 — EXPERT

*Goal: Production governance, agent evaluation, advanced serving, enterprise operations.*
*Prerequisite: Levels 1 and 2 completed*
*Estimated time: ~20-25 hours*

---

## L3-M1: AI Agent Governance and Security

### L3-1.1 — RBAC and Network Policies for AI Workloads
**Duration:** 1 hour
**Topics:**
- OpenShift AI role hierarchy:
  - Cluster-level: `rhods-admins`, `rhods-users`
  - Project-level: creator gets `admin`, additional users get `admin` or `edit`
  - Model Registry: auto-created roles and groups per registry instance
- Configuring user access to:
  - Workbenches (who can create/access)
  - Model serving endpoints (who can deploy/call)
  - Pipelines (who can create/run)
  - Model registry (who can register/promote)
- Service accounts for automated workflows (pipelines, agents)
- Audit logging: who did what, when
- Network policies for AI workloads:
  - Restricting which pods can reach model serving endpoints
  - Isolating agent pods from direct cluster API access
  - Allowing only specific namespaces to consume model inference endpoints
  - Network policy for MCP server access control
  - Default deny + explicit allow patterns for AI infrastructure
  - K8s comparison: same NetworkPolicy resource, but OpenShift's SDN enforces by default

**Deliverables:**
- Multi-user RBAC configuration: admin, data scientist, agent consumer roles
- Network policy restricting model endpoint access to authorized namespaces
- Audit trail demonstration

---

### L3-1.2 — Authorino: Auth for Model Endpoints
**Duration:** 45 min
**Topics:**
- Authorino: Kubernetes-native AuthN/AuthZ service (Kuadrant project)
- Enabling auth on model endpoints: `security.opendatahub.io/enable-auth: 'true'` annotation
- CRD: `AuthConfig` (`authorino.kuadrant.io/v1beta3`)
- Authentication methods:
  - Kubernetes ServiceAccount tokens (for internal services/agents)
  - JWT/OIDC (for external clients)
  - API keys
  - mTLS
- Authorization policies: OPA, pattern-matching, external metadata
- Protecting the Gemma4-e4b endpoint with token-based auth
- Agent authentication: service account tokens for agent → model access

**Deliverables:**
- Model endpoint secured with Authorino
- Agent authenticated via ServiceAccount token
- External client authenticated via OIDC/JWT

---

### L3-1.3 — Models-as-a-Service (MaaS)
**Duration:** 1 hour
**Topics:**
- MaaS (GA in 3.4): serving models as managed API endpoints
- Tier-based access control:
  - Defining tiers: Free, Premium, Enterprise
  - Rate limits and token quotas per tier
  - Self-service API keys: `POST /maas-api/v1/tokens`
- Built on Kuadrant (Authorino + Limitador):
  - Authorino: authentication and authorization
  - Limitador: rate limiting and quota enforcement
- Enterprise OIDC integration: Azure AD, Okta, Keycloak
- Showback dashboards (TP): consumption tracking per user/team
- Use case: platform team serving models to application teams with metered access

**Deliverables:**
- MaaS endpoint configured with 2 tiers (free/premium)
- Rate limiting in action
- Self-service API key generation workflow

---

### L3-1.4 — NeMo Guardrails for AI Safety
**Duration:** 1 hour
**Prerequisites:** Sub-tutorial: `tutorial_ai/nemo_guardrails/`
**Topics:**
- NeMo Guardrails on OpenShift AI (GA in 3.4)
- Guardrails Orchestrator: middleware between application and LLM
- Safety capabilities:
  - Content filtering (HAP detection, profanity, PII)
  - Jailbreak protection
  - Topic control (keep conversations on-topic)
  - Input/output validation
- Integration with TrustyAI and Llama Guard detectors
- Deploying guardrails for the Gemma4-e4b endpoint
- Testing: attempting jailbreak, off-topic, and harmful prompts
- Monitoring guardrail activations in Prometheus/Grafana

**Deliverables:**
- NeMo Guardrails protecting the model endpoint
- Demonstration: blocked harmful/off-topic requests
- Guardrail activation metrics in Grafana

---

### L3-1.5 — Software Supply Chain Security for AI
**Duration:** 30 min
**Topics:**
- AI-specific supply chain risks: model poisoning, data poisoning, dependency attacks
- OpenShift security tools for AI:
  - Trusted Artifact Signer: cryptographic signing of model containers
  - Trusted Profile Analyzer: vulnerability and license scanning
  - Quay: signed images with provenance history
- Security Context Constraints (SCC) for AI workloads:
  - `restricted-v2` (default, recommended)
  - `anyuid` (some ML images need root)
  - `privileged` (GPU drivers only)
- Secure model ingestion workflow: download → scan → sign → store → serve
- Model provenance tracking through the registry

**Deliverables:**
- Signed model container image
- Secure model ingestion pipeline

---

## L3-M2: Agent Evaluation and Benchmarking

### L3-2.1 — EvalHub: Centralized Evaluation Platform
**Duration:** 45 min
**Topics:**
- EvalHub on OpenShift AI (Technology Preview in 3.4, officially documented in 3.5)
  - Deployed as part of the `trustyai` DSC component (not a separate component)
  - Reference: https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5/html-single/evaluating_ai_systems/index
- Framework-agnostic evaluation control plane
- 167 built-in benchmarks across categories:
  - Language understanding (MMLU, HellaSwag, ARC)
  - Reasoning (GSM8K, MATH, BBH)
  - Code generation (HumanEval, MBPP)
  - Safety (ToxiGen, BBQ, CrowS-Pairs)
  - RAG-specific (faithfulness, relevance)
- Garak adversarial scanning: automated jailbreak and prompt injection testing
- Running evaluations via EvalHub vs LMEvalJob (comparison)
- Viewing and comparing results in dashboard

**Deliverables:**
- EvalHub evaluation run for the deployed model
- Garak adversarial scan results
- Comparison: EvalHub vs LMEvalJob approaches

---

### L3-2.2 — Custom Agent Evaluation Pipelines
**Duration:** 1.5 hours
**Topics:**
- Designing evaluation for AI agents (beyond model quality):
  - Task completion rate
  - Tool selection accuracy (precision/recall of tool choices)
  - Reasoning quality (coherence, relevance)
  - Response time and cost
  - Safety compliance (guardrail activation rate)
- Building evaluation datasets for agents:
  - Multi-turn conversation scenarios
  - Tool-calling scenarios with expected tool sequences
  - Edge cases and adversarial inputs
- Implementing evaluation with MLflow (reference: mlflow-tutorial L3-M1)
- Pipeline integration: automated evaluation in KFP pipelines
- Regression testing: comparing agent versions over time

**Deliverables:**
- Custom agent evaluation pipeline
- Evaluation dataset with 20+ test scenarios
- Regression test comparing 2 agent versions

---

### L3-2.3 — Agent Testing Methodologies
**Duration:** 1 hour
**Topics:**
- Testing layers for deployed agents:
  1. Unit: individual tool functions, prompt templates
  2. Integration: agent → model endpoint, agent → MCP server
  3. System: end-to-end conversation flows
  4. Load: concurrent users, throughput limits
  5. Adversarial: jailbreak, prompt injection, data exfiltration
- Testing in OpenShift:
  - Pipeline-based automated testing (KFP)
  - Pre-deployment gates: agent must pass evaluation before promotion
  - Canary testing: route small traffic to new agent version
- A/B testing agents via OpenShift Route traffic splitting
- Continuous evaluation: scheduled pipeline runs monitoring agent quality

**Deliverables:**
- Multi-layer agent test suite
- Pre-deployment evaluation gate in KFP pipeline
- A/B test configuration for agent versions

---

## L3-M3: Advanced Model Serving

### L3-3.1 — llm-d: Distributed LLM Inference
**Duration:** 1 hour
**Topics:**
- llm-d architecture: Kubernetes-native distributed inference (CNCF Sandbox)
- Core components:
  - Endpoint Picker (EPP): semantic router with cache-aware scheduling
  - Disaggregated prefill/decode: separate heavy prompt ingestion from token generation
  - KV-cache management: tiered offloading to CPU/disk, global indexing
  - UCCL: Unified Collective Communication Library for KV-cache transport
- `LLMInferenceService` CRD (replacing `InferenceService` for LLM workloads)
- Performance: sub-400ms latency, 87%+ cache hit rates, 90% GPU utilization
- When to use llm-d vs standard KServe:
  - llm-d: high-throughput, multi-GPU, production LLM serving
  - KServe: single-model, simpler setup, non-LLM models
- Deploying Gemma4-e4b on llm-d

**Deliverables:**
- Gemma4-e4b deployed on llm-d with disaggregated serving
- Performance comparison: llm-d vs standard KServe vLLM

---

### L3-3.2 — Model Quantization and Optimization
**Duration:** 45 min
**Topics:**
- LLM Compressor (GA in 2.25+): model quantization for deployment
- Quantization formats: FP8, INT8, INT4, GPTQ, AWQ
- Quantizing a fine-tuned model for optimal inference:
  - Trade-off: quality vs speed vs VRAM
- RedHatAI pre-quantized models on Hugging Face
- Deploying quantized models on vLLM
- Benchmarking: original vs quantized (quality and performance)

**Deliverables:**
- Fine-tuned model quantized to FP8
- Benchmark comparison: full precision vs quantized

---

### L3-3.3 — Multi-Model Serving Patterns
**Duration:** 45 min
**Topics:**
- Serving multiple models on the same cluster:
  - Separate InferenceServices (standard approach)
  - MLServer for classical ML models (new in 3.4)
  - Model routing: different models for different tasks
- Model fallback chains: primary → fallback if primary overloaded
- A/B testing models via Route traffic splitting
- GenAI Playground: side-by-side model comparison (TP)
- Resource optimization: GPU sharing across models

**Deliverables:**
- 3 models deployed: LLM (vLLM), embedding (vLLM), classical ML (MLServer)
- Route-based A/B test between 2 LLM versions

---

## L3-M4: Advanced Fine-Tuning

### L3-4.1 — InstructLab on OpenShift AI
**Duration:** 1.5 hours
**Prerequisites:** L1-M3 completed
**Topics:**
- InstructLab status: core repo archived (2026), refactored into SDG Hub + Training Hub
  - LAB method is niche — taxonomy-driven synthetic data generation
  - The `trainer` DSC component (Training Hub) supersedes InstructLab's training component
  - This lesson covers the LAB-tuning approach for specialized use cases
- LAB-tuning on OpenShift AI (Technology Preview)
- End-to-end workflow:
  1. Define taxonomy (skills + knowledge)
  2. Generate synthetic data (SDG)
  3. Multi-phase training (knowledge tuning → skill tuning)
  4. Evaluation
- `ilab-on-ocp` project for deployment
- Data Science Pipelines for orchestration
- Comparison: Training Hub LoRA (L1) vs InstructLab LAB-tuning (this lesson)
  - LoRA: quick, targeted fine-tuning with existing data
  - LAB: community-driven, synthetic data generation, broader knowledge injection

**Deliverables:**
- InstructLab taxonomy with custom knowledge and skills
- LAB-tuned model deployed and compared with LoRA fine-tuned version

---

### L3-4.2 — Feature Store with Feast
**Duration:** 45 min
**Topics:**
- Feast on OpenShift AI (GA in 3.4, v0.62.0)
- Feature store concepts: offline store (training), online store (inference)
- CRD: `FeatureStore`
- Setting up Feast:
  - Defining feature views and entities
  - Materializing features from offline to online store
  - Serving features at inference time
- Integration with training pipelines: feature retrieval as pipeline component
- Integration with serving: feature enrichment before model inference
- Web UI for feature exploration

**Deliverables:**
- Feast feature store deployed with sample features
- Feature retrieval integrated into a pipeline and serving workflow

---

### L3-4.3 — Continuous Learning Patterns
**Duration:** 1 hour
**Topics:**
- Continuous learning architecture on OpenShift AI:
  1. Collect feedback (user corrections, quality scores)
  2. Curate new training data from feedback
  3. Trigger re-training pipeline (scheduled or threshold-based)
  4. Evaluate new model against current production model
  5. Promote if better (automated or human-approved)
- Implementing the loop:
  - MLflow feedback collection (`log_assessment`)
  - KFP pipeline for scheduled retraining
  - Model Registry for version management
  - Automated promotion with evaluation gates
- Preventing catastrophic forgetting: replay buffers, OSFT
- Monitoring for quality drift over time

**Deliverables:**
- Continuous learning pipeline: feedback → retrain → evaluate → promote
- Drift detection monitoring

---

## L3-M5: Production Operations

### L3-5.1 — GitOps for AI Workloads
**Duration:** 1 hour
**Topics:**
- Applying GitOps (ArgoCD, reference: main tutorial L09) to AI workloads
- What to store in Git:
  - DataScienceCluster manifests
  - InferenceService / ServingRuntime manifests
  - Pipeline definitions
  - Model Registry configurations
  - Hardware Profiles
  - RBAC policies
- Kustomize overlays: dev → staging → production
- ArgoCD Application for AI infrastructure
- Drift detection: ArgoCD catches manual changes to model serving config
- Validated Pattern: "AI Generation with LLM and RAG" as GitOps template

**Deliverables:**
- ArgoCD Application managing the tutorial's AI workloads
- Kustomize overlays for dev and prod environments
- Drift detection demonstration

---

### L3-5.2 — CI/CD for AI Applications
**Duration:** 1 hour
**Topics:**
- CI/CD pipeline for AI (extending main tutorial L08):
  1. Code change (agent logic, prompt, model config)
  2. Build container image (Tekton or Pipelines)
  3. Run evaluation pipeline (KFP)
  4. Quality gate: pass benchmarks and agent tests
  5. Register model version
  6. Deploy to staging (ArgoCD sync)
  7. Canary testing in staging
  8. Promote to production
- Tekton pipeline for agent container builds
- KFP pipeline for automated evaluation
- Integration: Tekton triggers KFP which updates ArgoCD
- Rollback: automated rollback if production metrics degrade

**Deliverables:**
- End-to-end CI/CD pipeline for an AI agent
- Quality gate with automated evaluation
- Rollback demonstration

---

### L3-5.3 — Scaling and Performance Tuning
**Duration:** 45 min
**Topics:**
- GPU utilization optimization:
  - Right-sizing GPU allocations per model
  - MIG partitioning for multiple small models on one GPU
  - Dynamic Resource Allocation (DRA, GA in OpenShift 4.21)
- vLLM tuning:
  - `tensor-parallel-size` for multi-GPU inference
  - `max-model-len` for memory management
  - `gpu-memory-utilization` target
  - `max-num-seqs` for throughput vs latency trade-off
- Kueue tuning: queue priorities, preemption, borrowing policies
- Network tuning for distributed training:
  - SR-IOV NICs for high-performance networking
  - GPUDirect RDMA for GPU-to-GPU communication
- Cost optimization: spot/preemptible instances for training

**Deliverables:**
- Performance-tuned deployment configuration
- Cost analysis: optimized vs unoptimized GPU utilization

---

### L3-5.4 — Capstone: End-to-End AI Platform
**Duration:** 4-6 hours
**Topics:**
- Build a complete AI platform on OpenShift AI integrating everything learned:
  - **Model**: Gemma4-e4b fine-tuned on custom data, quantized, deployed on llm-d
  - **RAG**: Document ingestion pipeline, pgvector, retrieval-augmented responses
  - **Agents**: LangGraph agent with MCP tools (OpenShift resource management)
  - **MCP**: Custom MCP server + MCP Server for OpenShift, behind MCP Gateway
  - **Observability**: MLflow tracing, vLLM metrics, Grafana dashboards
  - **Governance**: Authorino auth, NeMo Guardrails, RBAC
  - **Evaluation**: Automated agent tests, LMEvalJob benchmarks, EvalHub scan
  - **CI/CD**: GitOps (ArgoCD) + Tekton + KFP evaluation pipeline
  - **Continuous learning**: Feedback → retrain → evaluate → promote loop
- Architecture documentation
- Operations runbook: common issues and resolution

**Deliverables:**
- Production-ready AI platform on OpenShift AI
- Architecture diagram
- Operations runbook
- Monitoring dashboard

---

### Level 3 Summary

| Module | Lessons | Estimated Time |
|--------|---------|---------------|
| M1: AI Agent Governance & Security | 5 lessons | ~4.25 hours |
| M2: Agent Evaluation & Benchmarking | 3 lessons | ~3.25 hours |
| M3: Advanced Model Serving | 3 lessons | ~2.5 hours |
| M4: Advanced Fine-Tuning | 3 lessons | ~3.25 hours |
| M5: Production Operations | 4 lessons | ~7-9 hours |
| **Total** | **18 lessons** | **~20-25 hours** |

### GOAL.md Coverage After Level 3 (Complete)

| Requirement | Status | Primary Lessons |
|-------------|--------|----------------|
| Model deployment/inference (Gemma4-e4b) | **Complete** | L1-M2, L3-M3 |
| Model fine-tuning (Gemma4-e4b) | **Complete** | L1-M3, L2-M6, L3-M4 |
| Fine-tuned model inference | **Complete** | L1-M3.3 |
| Model testing/benchmarking | **Complete** | L1-M5, L3-M2 |
| MCP servers deployments | **Complete** | L2-M2 |
| AI agents deployment | **Complete** | L2-M3 |
| AI agents observability | **Complete** | L2-M5 |
| AI agents evals/benchmarks | **Complete** | L3-M2 |
| AI agents governance | **Complete** | L3-M1 |
| RAG solution | **Complete** | L2-M1 |

---
---

# Complete Course Summary

| Level | Focus | Lessons | Time |
|-------|-------|---------|------|
| **Level 1 — Foundations** | Deploy, serve, fine-tune, benchmark, AutoML | 19 lessons | ~12-14 hours |
| **Level 2 — Practitioner** | RAG, AutoRAG, MCP, agents, pipelines, observability | 29 lessons | ~24-28 hours |
| **Level 3 — Expert** | Governance, evaluation, production ops | 18 lessons | ~20-25 hours |
| **Total** | | **66 lessons** | **~56-67 hours** |

---

## Project Structure

```
tutorial_ai/
├── GOAL.md                              # Original requirements
├── openshift_ai_docs.md                 # Reference links to official docs
├── openshift_ai/
│   ├── syllabus.md                      # This file — the master syllabus
│   ├── level_1/
│   │   ├── M1_platform_setup/
│   │   │   ├── 1_architecture_overview/
│   │   │   ├── 2_installing_openshift_ai/
│   │   │   ├── 3_dashboard_ai_hub_tour/
│   │   │   ├── 4_workbenches/
│   │   │   ├── 5_gpu_hardware_setup/
│   │   │   └── 6_genai_playground/
│   │   ├── M2_model_serving/
│   │   │   ├── 1_kserve_fundamentals/
│   │   │   ├── 2_deploying_gemma/
│   │   │   ├── 3_openai_compatible_api/
│   │   │   └── 4_autoscaling/
│   │   ├── M3_fine_tuning/
│   │   │   ├── 1_fine_tuning_concepts/
│   │   │   ├── 2_training_hub_lora/
│   │   │   └── 3_deploying_fine_tuned/
│   │   ├── M4_model_registry/
│   │   │   ├── 1_registry_setup/
│   │   │   └── 2_registering_models/
│   │   ├── M5_evaluation/
│   │   │   ├── 1_lmevaljob/
│   │   │   ├── 2_guidellm/
│   │   │   └── 3_serving_metrics_grafana/
│   │   └── M6_automl/
│   │       └── 1_automl_dashboard/
│   ├── level_2/
│   │   ├── M1_rag/
│   │   │   ├── 1_rag_architecture_ogx/
│   │   │   ├── 2_vector_database/
│   │   │   ├── 3_document_ingestion/
│   │   │   ├── 4_end_to_end_rag/
│   │   │   ├── 5_rag_evaluation/
│   │   │   └── 6_autorag_dashboard/
│   │   ├── M2_mcp_deployment/
│   │   │   ├── 1_mcp_overview/
│   │   │   ├── 2_lifecycle_operator/
│   │   │   ├── 3_openshift_mcp_server/
│   │   │   ├── 4_mcp_gateway/
│   │   │   └── 5_playground_testing/
│   │   ├── M3_agent_deployment/
│   │   │   ├── 1_deployment_patterns/
│   │   │   ├── 2_langchain_langgraph/
│   │   │   ├── 3_ogx_agents/
│   │   │   ├── 4_agents_mcp_tools/
│   │   │   └── 5_multi_agent_systems/
│   │   ├── M4_pipelines/
│   │   │   ├── 1_pipeline_setup/
│   │   │   ├── 2_kfp_sdk/
│   │   │   ├── 3_training_pipeline/
│   │   │   └── 4_rag_ingestion_pipeline/
│   │   ├── M5_observability/
│   │   │   ├── 1_mlflow_openshift_ai/
│   │   │   ├── 2_agent_tracing/
│   │   │   ├── 3_opentelemetry/
│   │   │   ├── 4_trustyai_monitoring/
│   │   │   └── 5_production_dashboards/
│   │   └── M6_distributed/
│   │       ├── 1_kuberay/
│   │       ├── 2_kueue/
│   │       ├── 3_distributed_training/
│   │       └── 4_spark/
│   └── level_3/
│       ├── M1_governance/
│       │   ├── 1_rbac/
│       │   ├── 2_authorino/
│       │   ├── 3_maas/
│       │   ├── 4_nemo_guardrails/
│       │   └── 5_supply_chain_security/
│       ├── M2_agent_evaluation/
│       │   ├── 1_evalhub/
│       │   ├── 2_custom_eval_pipelines/
│       │   └── 3_agent_testing/
│       ├── M3_advanced_serving/
│       │   ├── 1_llm_d/
│       │   ├── 2_quantization/
│       │   └── 3_multi_model/
│       ├── M4_advanced_fine_tuning/
│       │   ├── 1_instructlab/
│       │   ├── 2_feast/
│       │   └── 3_continuous_learning/
│       └── M5_production/
│           ├── 1_gitops/
│           ├── 2_cicd/
│           ├── 3_scaling_tuning/
│           └── 4_capstone/
├── redhat_ai/
│   └── syllabus.md                      # Red Hat AI Ecosystem tutorial (Podman AI Lab, RHEL AI, Granite)
├── ogx/
│   └── syllabus.md                      # OGX (Llama Stack) sub-tutorial
├── nemo_guardrails/
│   └── syllabus.md                      # NeMo Guardrails sub-tutorial
├── autorag/
│   └── syllabus.md                      # AutoRAG (standalone) sub-tutorial
└── evalhub/
    └── syllabus.md                      # EvalHub sub-tutorial
```

## OpenShift AI Feature Coverage Matrix

| Feature Area | Level 1 | Level 2 | Level 3 |
|---|---|---|---|
| Platform Setup | Install, Dashboard, Workbenches, GPU | — | — |
| GenAI Playground | Interactive testing, model comparison | MCP tool testing | — |
| KServe / Model Serving | Deploy, API, Autoscaling | — | llm-d, Quantization, Multi-model |
| vLLM | Basic deployment | — | Advanced tuning |
| Fine-Tuning | Training Hub LoRA/QLoRA | Distributed (Trainer v2) | InstructLab, Continuous learning |
| Model Registry | Setup, Register, Version | Pipeline integration | — |
| Evaluation | LMEvalJob, GuideLLM | RAG evaluation | EvalHub, Agent eval, Adversarial |
| Monitoring | Grafana dashboards | TrustyAI, MLflow, OTel | Production alerting |
| AutoML | Dashboard feature | — | — |
| AutoRAG | — | Dashboard feature | — |
| RAG | — | OGX, Vector DB, Ingestion, Eval | — |
| MCP | — | Lifecycle Op, Gateway, OpenShift MCP | — |
| Agents | — | LangGraph, OGX, MCP tools, Multi-agent | Evaluation, Testing |
| Pipelines | — | KFP setup, Training, RAG pipelines | CI/CD integration |
| Distributed | — | KubeRay, Kueue, Trainer v2, Spark | Performance tuning |
| Governance | — | — | RBAC, Network Policies, Authorino, MaaS, Guardrails, Supply chain |
| GitOps | — | — | ArgoCD for AI workloads |
| Feature Store | — | — | Feast |

## Key CRD Reference

| CRD | API Group | Level Introduced |
|-----|-----------|-----------------|
| DSCInitialization | `dscinitialization.opendatahub.io/v1` | L1-M1 |
| DataScienceCluster | `datasciencecluster.opendatahub.io/v2` | L1-M1 |
| Notebook | `kubeflow.org/v1` | L1-M1 |
| HardwareProfile | `infrastructure.opendatahub.io/v1` | L1-M1 |
| ServingRuntime | `serving.kserve.io/v1alpha1` | L1-M2 |
| InferenceService | `serving.kserve.io/v1beta1` | L1-M2 |
| ModelRegistry | `modelregistry.opendatahub.io/v1beta1` | L1-M4 |
| LMEvalJob | TrustyAI | L1-M5 |
| DataSciencePipelinesApplication | Kubeflow | L2-M4 |
| TrainJob | Kubeflow Trainer | L2-M6 |
| ClusterQueue / LocalQueue | Kueue | L2-M6 |
| RayCluster / RayJob | KubeRay | L2-M6 |
| TrustyAIService | `trustyai.opendatahub.io/v1` | L2-M5 |
| AuthConfig | `authorino.kuadrant.io/v1beta3` | L3-M1 |
| LLMInferenceService | `serving.kserve.io/v1alpha1` | L3-M3 |
| FeatureStore | Feast | L3-M4 |
