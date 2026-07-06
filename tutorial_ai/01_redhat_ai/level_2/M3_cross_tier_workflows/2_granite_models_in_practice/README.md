# L2-3.2 — Granite Models in Practice

**Level:** Practitioner
**Duration:** 45 min

## Overview

This lesson brings together everything you have learned about models throughout this tutorial and applies it to practical decision-making. You will learn how to choose the right Granite model for a given task, understand how quantization formats affect VRAM, quality, and throughput, see how model formats differ across the three Red Hat AI tiers, and compare Granite with community alternatives. By the end you will have a systematic framework for model selection that you can apply to any AI project on the Red Hat stack.

## Prerequisites

- Completed all prior lessons in this tutorial (L1-M1 through L2-3.1)
- Familiarity with the Granite model family (covered in [L1-1.2](../../../level_1/M1_ecosystem/2_model_strategy/))
- Familiarity with model formats across tiers: GGUF in Podman AI Lab, safetensors/native in RHEL AI, OCI/S3 in OpenShift AI
- Understanding of the cross-tier workflow (covered in [L2-3.1](../1_end_to_end/))

## Concepts

### Choosing the Right Granite Model for the Task

The Granite family is not a single model -- it is a collection of purpose-built models. Choosing the wrong one wastes resources or underdelivers on quality. The first decision is always: **what kind of task are you solving?**

#### Granite Language (Dense: 2B/3B/8B/14B/30B, MoE: 1B-3B/3B-8B)

General-purpose text generation. Use for chat interfaces, question answering, summarization, translation, and content generation. The 8B dense model is the default starting point for most enterprise applications -- it balances quality with resource efficiency. Move up to 14B or 30B when you need stronger reasoning or domain complexity. Move down to 2B or the MoE variants for edge deployment or when GPU memory is constrained.

**When to use:** Customer support bots, internal knowledge assistants, document summarization, email drafting, general-purpose Q&A.

#### Granite Code (3B/8B/20B/34B)

Optimized for software development: code generation, code completion, code review, bug detection, and refactoring. Trained on 116+ programming languages with strength in enterprise languages (Java, Python, Go, TypeScript) and infrastructure-as-code formats (YAML, Terraform, Ansible).

**When to use:** IDE code assistants, automated code review pipelines, documentation generation from code, test generation, migration tooling.

#### Granite Guardian

A safety classification model designed to run alongside a generation model. It evaluates both user inputs and model outputs for harmful content, social bias, jailbreak attempts, and hallucination (groundedness checking). Deploy it as a sidecar or gateway filter in front of your generation model.

**When to use:** Any user-facing application where you need content moderation, compliance filtering, or hallucination detection. Required in regulated industries (finance, healthcare, government).

#### Granite Embedding (30M/125M/278M)

Encoder models that convert text into dense vector representations for semantic search and retrieval. These are not generation models -- they produce embeddings, not text. The 125M variant is the default for most RAG applications. The 30M variant works for resource-constrained environments. The 278M variant provides the highest retrieval quality.

**When to use:** RAG pipelines (vector database population and query embedding), semantic search, document clustering, duplicate detection, recommendation systems.

#### Granite Speech

Multilingual automatic speech recognition and speech translation. Handles 30+ languages, speaker diarization, and cross-language translation.

**When to use:** Voice interfaces, call center transcription, meeting summarization, multilingual voice assistants, accessibility features.

#### Granite Vision

Multimodal models that process images alongside text. Handles document understanding, chart interpretation, visual question answering, and image captioning.

**When to use:** Document processing pipelines (invoices, forms, receipts), visual inspection, diagram interpretation, accessibility alt-text generation.

---

### Granite Model Selection Guide

The following table maps common AI tasks to the recommended Granite model and size:

| Task | Granite Model | Recommended Size | Why This Size |
|------|--------------|-----------------|---------------|
| General chat / Q&A | Language | 8B Dense | Best quality-to-resource ratio for most workloads |
| Complex reasoning / analysis | Language | 14B or 30B Dense | Larger models handle nuance and multi-step reasoning better |
| Edge / mobile / IoT | Language | 1B/3B MoE or 2B Dense | Fits in limited memory, still usable quality |
| Batch summarization | Language | 8B Dense | Good throughput at acceptable quality |
| Long-document processing | Language | 8B+ Dense (128K context) | Needs the full context window for large inputs |
| Code completion (IDE) | Code | 3B or 8B | Low latency matters more than peak quality |
| Code generation (pipeline) | Code | 20B or 34B | Quality matters more than latency in batch pipelines |
| Code review automation | Code | 8B or 20B | Needs enough capacity to reason about code quality |
| Content moderation | Guardian | (single size) | Purpose-built, no size choice needed |
| Hallucination detection | Guardian | (single size) | Evaluates groundedness of another model's output |
| RAG retrieval | Embedding | 125M | Best balance of retrieval quality and speed |
| Lightweight RAG | Embedding | 30M | When embedding speed or memory is constrained |
| High-precision retrieval | Embedding | 278M | When retrieval quality is the top priority |
| Voice interface | Speech | (single size) | Purpose-built for ASR and translation |
| Document scanning | Vision | (single size) | Purpose-built for image + text understanding |

**Decision shortcut:** If you are unsure, start with Granite 4.0 Small (8B Dense) for text generation, Granite Code 8B for code tasks, and Granite Embedding 125M for RAG. These are the default choices that work for most projects. Scale up only when evaluation shows the smaller model is insufficient.

---

### Quantization Variants and Trade-offs

In [L1-1.2](../../../level_1/M1_ecosystem/2_model_strategy/) you learned that RedHatAI on HuggingFace publishes pre-quantized models in multiple formats. Now we examine the practical trade-offs in depth.

Quantization reduces model precision from 16-bit floating point to lower bit widths. This trades a small amount of output quality for significant reductions in GPU memory usage and (in some cases) faster inference.

#### Quantization Formats Explained

**FP16 (Full Precision):** The baseline format. Every model weight is stored as a 16-bit floating-point number. This is the highest quality but requires the most VRAM. Use FP16 when you have ample GPU memory and need reference-quality output, or when evaluating whether a quantized variant introduces unacceptable quality loss.

**FP8 (RedHatAI Default):** Weights are stored as 8-bit floating-point numbers. This is the default quantization that Red Hat ships for most models on HuggingFace. FP8 cuts VRAM roughly in half compared to FP16 with minimal quality degradation -- most users cannot distinguish FP8 output from FP16 in blind tests. This is the recommended starting point for production.

**INT8:** Weights are stored as 8-bit integers. Similar VRAM savings to FP8 but uses integer arithmetic instead of floating point. Broadly supported across GPU generations. Quality impact is comparable to FP8.

**GPTQ (4-bit grouped):** Weights are quantized to 4 bits using a grouped quantization scheme. Reduces VRAM to roughly 25% of FP16. Some quality loss is measurable on benchmarks, especially for complex reasoning tasks. Use when you need to fit a larger model into limited GPU memory.

**AWQ (Activation-Aware 4-bit):** An improved 4-bit quantization that preserves the weights most important to model quality (identified by analyzing activation patterns). Generally better quality than GPTQ at the same bit width. This is the recommended 4-bit format when your GPU supports it.

**NVFP4 (NVIDIA FP4):** A 4-bit floating-point format specific to NVIDIA Hopper (H100) and Blackwell (B200) GPUs. Uses hardware-native FP4 computation for both reduced memory and higher throughput. Only available on recent NVIDIA hardware -- if you have Hopper or newer GPUs, this is the best 4-bit option.

**GGUF (Variable, CPU-optimized):** The format used by llama.cpp in Podman AI Lab. GGUF supports its own quantization levels (Q4_K_M, Q5_K_M, Q8_0, etc.) and is optimized for CPU inference. Not compatible with vLLM. Use exclusively in Podman AI Lab.

#### Quantization Trade-offs Table

| Format | Bits | VRAM vs FP16 | Quality vs FP16 | Inference Speed | GPU Compatibility | Best For |
|--------|------|-------------|----------------|-----------------|-------------------|----------|
| FP16 | 16 | 1.0x (baseline) | Baseline | Baseline | All modern GPUs | Reference quality, evaluation, ample VRAM |
| FP8 | 8 | ~0.5x | 99%+ | Same or faster | Ampere+ (A100, L40S, H100) | **Production default**, best quality/memory trade-off |
| INT8 | 8 | ~0.5x | 98-99% | Same or faster | All modern GPUs | Production, broad GPU support |
| GPTQ | 4 | ~0.25x | 93-97% | Faster | All modern GPUs | Fitting large models on smaller GPUs |
| AWQ | 4 | ~0.25x | 95-98% | Faster | Ampere+ | Best 4-bit quality, memory-constrained |
| NVFP4 | 4 | ~0.25x | 95-98% | Fastest (on supported HW) | Hopper/Blackwell only | NVIDIA H100/B200 deployments |
| GGUF | 4-8 | ~0.25-0.5x | 90-98% | CPU-optimized | CPU (any); GPU optional | Podman AI Lab, local experimentation |

#### Practical VRAM Examples

To help with capacity planning, here are approximate VRAM requirements for Granite Language models:

| Model | FP16 | FP8 | INT4/AWQ | GGUF (Q4_K_M) |
|-------|------|-----|----------|----------------|
| Granite 3B | ~6 GB | ~3 GB | ~2 GB | ~2 GB (CPU) |
| Granite 8B | ~16 GB | ~8 GB | ~4 GB | ~5 GB (CPU) |
| Granite 14B | ~28 GB | ~14 GB | ~7 GB | ~9 GB (CPU) |
| Granite 30B | ~60 GB | ~30 GB | ~15 GB | ~18 GB (CPU) |

> **Note:** These are approximate model weight sizes. Actual VRAM usage includes KV cache, activation memory, and runtime overhead. Budget 20-40% additional VRAM beyond model weight size for production workloads.

#### Choosing a Quantization Format

Use this decision tree:

1. **Do you have a GPU?**
   - No --> Use **GGUF** (CPU inference via llama.cpp in Podman AI Lab)
   - Yes --> Continue

2. **Is maximum quality critical?**
   - Yes --> Use **FP16** (or BF16)
   - No --> Continue

3. **Does the model fit in GPU memory at FP8?**
   - Yes --> Use **FP8** (RedHatAI default, best quality-to-efficiency ratio)
   - No --> Continue

4. **Do you have NVIDIA Hopper/Blackwell GPUs (H100/B200)?**
   - Yes --> Use **NVFP4** (hardware-optimized 4-bit)
   - No --> Use **AWQ** (best software-based 4-bit quality)

---

### Running Granite Models Across the Red Hat AI Stack

Each tier of the Red Hat AI stack uses different model formats and inference backends. Understanding which format goes where prevents confusion when moving models between tiers.

#### Model Format by Tier

| Tier | Tool | Model Format | Inference Backend | How Models Are Loaded |
|------|------|-------------|-------------------|----------------------|
| Desktop | Podman AI Lab | GGUF | llama.cpp | Downloaded from catalog or imported from file |
| Server | RHEL AI | Safetensors / native | vLLM | Downloaded via `ilab model download` or local path |
| Platform | OpenShift AI | Safetensors / native (in S3 or OCI image) | KServe + vLLM (Red Hat AI Inference Server) | StorageUri in InferenceService points to S3 bucket or OCI registry |

#### Key Differences by Tier

**Podman AI Lab** uses GGUF exclusively because it runs on llama.cpp, which is optimized for CPU inference. You cannot run safetensors models in Podman AI Lab. The catalog provides pre-quantized GGUF models (typically Q4_K_M quantization).

**RHEL AI** uses vLLM, which loads models in safetensors format. vLLM supports FP16, FP8, and AWQ/GPTQ quantization natively. Download models from HuggingFace (either `ibm-granite` for original models or `RedHatAI` for pre-quantized variants) using `ilab model download`.

**OpenShift AI** also uses vLLM (packaged as the Red Hat AI Inference Server) but loads models from S3-compatible storage or OCI registries rather than local disk. The ServingRuntime configuration specifies the model format, quantization, and vLLM parameters.

#### Cross-Tier Model Compatibility

```
Podman AI Lab (GGUF)  <--  No direct path  -->  RHEL AI / OpenShift AI (safetensors)
                                |
                    RHEL AI (safetensors) <--> OpenShift AI (safetensors)
                         Same format, same vLLM config
```

Models move freely between RHEL AI and OpenShift AI because both use vLLM with safetensors. Moving between Podman AI Lab and the other tiers requires format conversion (safetensors to GGUF using tools like `llama.cpp`'s `convert` scripts). In practice, you typically use Podman AI Lab for exploration with the catalog's GGUF models, then switch to the safetensors version of the same model on RHEL AI or OpenShift AI.

#### Format Conversion Reference

| From | To | Conversion | Tool |
|------|----|-----------|------|
| GGUF (Desktop) | Safetensors (Server/Platform) | Convert weights and metadata | `llama.cpp` convert scripts or HuggingFace `transformers` |
| Safetensors (Server) | GGUF (Desktop) | Quantize and package | `llama.cpp` `convert-hf-to-gguf.py` |
| Safetensors (Server) | Safetensors (Platform) | No conversion needed | Upload to S3 or push as OCI image |

In practice, you rarely need to convert manually. The typical workflow is:
1. Experiment with GGUF models in Podman AI Lab.
2. When ready for server or production, download the safetensors version of the same model from HuggingFace.
3. Fine-tune on RHEL AI (safetensors in, safetensors out).
4. Deploy the fine-tuned safetensors model to OpenShift AI.

---

### Granite vs Community Models

Red Hat's stack supports more than Granite. The validated model collections include Llama, Mistral, Qwen, Gemma, DeepSeek, and others. Understanding when to use Granite versus community models is a practical decision every team faces.

#### Granite vs Community Comparison Table

| Dimension | Granite | Llama (Meta) | Qwen (Alibaba) | Gemma (Google) | Mistral/Mixtral |
|-----------|---------|-------------|----------------|---------------|-----------------|
| **License** | Apache 2.0 | Llama Community License | Apache 2.0 (Qwen 2.5) | Gemma License (restricted) | Apache 2.0 (some); proprietary (others) |
| **IP Indemnification** | Yes (via IBM/Red Hat) | No | No | No | No |
| **Training Data Transparency** | Published composition | Partial | Limited | Limited | Limited |
| **Red Hat Support** | Full (model + platform) | Platform only | Platform only | Platform only | Platform only |
| **Size Range (Dense)** | 2B to 30B | 1B to 405B | 0.5B to 72B | 2B to 27B | 7B to 22B (MoE to 8x22B) |
| **Code Models** | Yes (3B to 34B) | Yes (Code Llama) | Yes (Qwen Coder) | Yes (CodeGemma) | Yes (Codestral) |
| **Embedding Models** | Yes (30M to 278M) | No (third-party) | Yes | Yes | Yes (Mistral Embed) |
| **Safety Models** | Yes (Guardian) | Yes (Llama Guard) | No | No | No |
| **Speech Models** | Yes | No | Yes (Qwen Audio) | No | No |
| **Vision Models** | Yes | Yes (Llama Vision) | Yes (Qwen VL) | Yes (PaliGemma) | Yes (Pixtral) |
| **InstructLab Fine-tuning** | First-class support | Supported | Community support | Community support | Community support |
| **vLLM Validated** | Yes (all sizes) | Yes (validated collections) | Yes (validated collections) | Yes (validated collections) | Yes (validated collections) |

#### When to Use Granite

- **Enterprise deployments in regulated industries.** The combination of Apache 2.0 licensing, training data transparency, and IP indemnification makes Granite the safest choice when legal and compliance teams are involved.
- **All-Granite stacks.** When you use Granite Language + Granite Embedding + Granite Guardian, everything is under one license with one support contract. This simplifies procurement and reduces license-tracking overhead.
- **InstructLab fine-tuning workflows.** Granite is the primary target for InstructLab's synthetic data generation and LAB-tuning pipeline. You will get the most predictable results fine-tuning Granite on RHEL AI.
- **When the 2B-30B range covers your needs.** If your task does not require a 70B+ model, Granite offers competitive quality with stronger legal protections.

#### When to Use Community Models

- **You need a model larger than 30B dense.** Granite's largest dense model is 30B. If your task requires 70B or 405B parameters (e.g., the most complex reasoning, multilingual generation, or research use cases), Llama 3.1 405B or DeepSeek-V3 671B (MoE) are your options.
- **Benchmark performance is the top priority.** On some benchmarks, the latest community models (especially at larger sizes) outperform Granite. If you are optimizing purely for task quality and license restrictions are acceptable, evaluate community alternatives.
- **You are already invested in a model ecosystem.** If your team has Llama fine-tunes, Llama-specific evaluation pipelines, or Llama-based applications in production, switching to Granite may not be worth the migration cost.
- **Specialized tasks where a community model excels.** Some community models are optimized for narrow tasks (e.g., math reasoning, specific languages) where they outperform general-purpose Granite models.

#### Mixing Granite and Community Models

In practice, many organizations mix models:

- **Granite for core enterprise workloads** (customer-facing chat, internal knowledge bases, document processing) -- where indemnification and support matter.
- **Community models for specialized tasks** (research exploration, maximum-quality code generation, niche language support) -- where you accept the license and support trade-offs.
- **Granite Guardian as a safety layer for any model** -- regardless of which model generates the response, Granite Guardian can evaluate it for safety.

This is a supported pattern. OpenShift AI can serve Granite and community models side by side on the same cluster, and your application can route requests to different models based on the task.

---

### RedHatAI Validated Model Collections

Every month, Red Hat publishes updated validated model collections on HuggingFace. Understanding what "validated" means helps you make informed deployment decisions.

#### What "Validated" Means

A validated model has passed the following checks:

1. **Compatibility testing** -- the model loads and serves correctly on the Red Hat AI Inference Server (vLLM-based).
2. **Serving configuration** -- tensor parallelism settings, quantization compatibility, and GPU memory requirements are documented.
3. **Performance benchmarks** -- throughput (tokens/second) and latency (time to first token) are measured on reference hardware.
4. **OpenShift AI certification** -- the model is tested on OpenShift AI with a specific ServingRuntime and documented configuration.

Validation is **not** the same as support. For non-Granite models, Red Hat supports the serving infrastructure (vLLM, KServe, OpenShift AI) but not the model itself. If a community model produces incorrect outputs, that is not a Red Hat support issue. If vLLM fails to serve the model correctly, it is.

#### What Validated Collections Include

Each monthly collection typically covers:

- All current Granite models (language, code, guardian, embedding) in multiple quantization formats
- Selected sizes of Llama, Mistral/Mixtral, Qwen, Gemma, and DeepSeek
- Recommended serving configurations (GPU type, tensor parallelism, max model length)
- Known issues or limitations for specific model/GPU combinations

#### Naming Convention on HuggingFace

RedHatAI model names follow a predictable pattern:

```
RedHatAI/<model-name>-<quantization>
```

Examples:
- `RedHatAI/granite-4.1-8b-instruct-FP8` -- Granite 4.1 8B in FP8
- `RedHatAI/granite-4.1-8b-instruct-AWQ` -- Granite 4.1 8B in AWQ
- `RedHatAI/Llama-4-Scout-17B-16E-Instruct-FP8` -- Llama 4 Scout in FP8
- `RedHatAI/Qwen3-8B-FP8` -- Qwen 3 8B in FP8

Browse the full collection at [huggingface.co/RedHatAI](https://huggingface.co/RedHatAI).

---

## Step-by-Step: Walkthrough Comparing Models

This walkthrough demonstrates how to apply the model selection framework to a concrete scenario. You will evaluate models for an enterprise knowledge assistant, compare their resource requirements under different quantization levels, and map the deployment to the appropriate Red Hat AI tier.

### Step 1: Define the Use Case Requirements

You are building a customer-facing knowledge assistant for a financial services company. The requirements are:

- Answer questions about financial products, policies, and procedures
- Process documents (PDFs, scanned forms) for information extraction
- Moderate all responses for compliance (no financial advice, no hallucinated numbers)
- Deploy to OpenShift AI with GPU constraints: 2x NVIDIA L4 GPUs (24 GB VRAM each)
- Enterprise indemnification is required (regulated industry)

### Step 2: Select Models for Each Task

Apply the model selection guide:

| Task | Selected Model | Reasoning |
|------|---------------|-----------|
| Knowledge Q&A | Granite 4.0 Small (8B) | Indemnification required, 8B fits L4 comfortably in FP8 |
| Document processing | Granite Vision | Handles scanned PDFs and forms, same license |
| Response moderation | Granite Guardian | Purpose-built for content safety, required for compliance |
| Document retrieval (RAG) | Granite Embedding 125M | Pairs with Granite Language for all-Granite RAG stack |

The indemnification requirement eliminates all community models for the core pipeline. This is a common outcome in regulated industries.

### Step 3: Choose Quantization Levels

With 2x L4 GPUs (24 GB each, 48 GB total), plan the memory budget:

| Model | Format | VRAM Required | GPU Assignment |
|-------|--------|--------------|----------------|
| Granite 4.0 Small (8B) | FP8 | ~8 GB | GPU 1 |
| Granite Guardian | FP8 | ~4 GB | GPU 1 |
| Granite Embedding 125M | FP16 | <1 GB | GPU 2 (or CPU) |
| Granite Vision | FP8 | ~8 GB | GPU 2 |

Total estimated VRAM: ~20 GB across 2 GPUs. This leaves headroom for KV cache and concurrent requests. FP8 is the right choice here -- the GPUs have enough memory, so there is no need to drop to 4-bit quantization.

If you only had 1x L4 (24 GB), you would need to:
- Drop Granite 4.0 Small to AWQ INT4 (~4 GB)
- Run Granite Guardian at AWQ INT4 (~2 GB)
- Run Granite Embedding on CPU
- Fit Granite Vision at AWQ INT4 (~4 GB)

This would work (~10 GB on one GPU) but with measurable quality loss on the generation model.

### Step 4: Map to Red Hat AI Tiers

The workflow across tiers for this project:

| Phase | Tier | Activity | Model Format |
|-------|------|----------|-------------|
| Prototype | Podman AI Lab | Test Granite 8B GGUF in Playground, build RAG recipe with sample documents | GGUF |
| Evaluate | Podman AI Lab | Compare Granite 8B vs 3B quality on domain questions, test system prompts | GGUF |
| Fine-tune (if needed) | RHEL AI | Create taxonomy for financial domain knowledge, run InstructLab pipeline | Safetensors |
| Deploy | OpenShift AI | Push models to S3, create InferenceService for each model, configure Routes | Safetensors |
| Monitor | OpenShift AI | vLLM metrics, Granite Guardian rejection rates, latency dashboards | N/A |

### Step 5: Verify the Selection

Before committing to production, validate your choices:

1. **Quality check:** Run 50-100 domain-specific prompts through Granite 8B FP8 and compare outputs against Granite 8B FP16. If the quality difference is unacceptable, either use FP16 (requiring more VRAM) or move to a larger model.

2. **Throughput check:** Estimate concurrent users and required tokens/second. A single Granite 8B FP8 on an L4 GPU typically serves 5-15 concurrent users at interactive speeds. If you need more, add replicas or GPUs.

3. **Guardian coverage check:** Test Granite Guardian with adversarial prompts specific to your domain (requests for financial advice, attempts to extract confidential data, prompt injection). Verify it catches what your compliance team requires.

4. **RAG quality check:** Evaluate Granite Embedding 125M retrieval accuracy on your actual document corpus. If retrieval quality is poor, try the 278M variant before adding more documents or changing chunking strategies.

---

## Key Takeaways

- **Start model selection from the task, not the model.** Map your requirements to a Granite sub-family (Language, Code, Guardian, Embedding, Speech, Vision) first, then choose the size based on your hardware constraints and quality needs.
- **FP8 is the production default.** It cuts VRAM in half with minimal quality loss. Drop to 4-bit (AWQ or NVFP4) only when GPU memory forces it, and always evaluate quality after quantizing.
- **Model formats differ by tier but the API is the same.** GGUF for Podman AI Lab (llama.cpp), safetensors for RHEL AI and OpenShift AI (vLLM). The OpenAI-compatible API works everywhere -- your application code does not change between tiers.
- **Granite's advantage is legal and operational, not just technical.** Apache 2.0 licensing, IP indemnification, and training data transparency matter most in regulated industries and enterprise procurement. When those are not concerns, community models are a valid and supported choice.
- **RedHatAI validated collections de-risk community model deployment.** "Validated" means tested on vLLM and certified for OpenShift AI -- not that Red Hat supports the model itself. Use the published serving configurations as your starting point.

---

## What's Next: Tutorial Complete

You have reached the end of the **Red Hat AI Ecosystem tutorial**.

### What You Covered

**Level 1 -- Foundations** (9 lessons) gave you the conceptual framework and hands-on introduction to each tier:

- **M1 -- Ecosystem:** The three-tier deployment model (Desktop, Server, Platform), Red Hat's AI strategy, and the Granite model family with its licensing, training data transparency, and IP indemnification story.
- **M2 -- Podman AI Lab:** Installing and exploring the desktop AI tool, running pre-built recipes (chatbot, RAG, code generation), and understanding how local prototypes export to production tiers.
- **M3 -- RHEL AI:** The bootable container image architecture, the InstructLab workflow (serve, chat, fine-tune), and how RHEL AI models and workflows feed into OpenShift AI.
- **M4 -- Validated Patterns:** GitOps-based reference architectures for production AI deployments using ArgoCD and validated patterns.

**Level 2 -- Practitioner** (6 lessons) built on those foundations with production-grade workflows:

- **M1 -- Advanced Podman AI Lab:** Custom models and catalogs, building full application stacks with the OpenAI-compatible API and Podman Compose, integrating with developer tools.
- **M2 -- Model Customization:** Modular model customization with Docling, SDG Hub, and Training Hub; model optimization with LLM Compressor and Speculators; production deployment with systemd, TLS, multi-model serving, and monitoring.
- **M3 -- Cross-Tier Workflows:** The end-to-end seven-step pipeline from desktop to cluster (L2-3.1), and this lesson on practical model selection, quantization trade-offs, and Granite vs community models (L2-3.2).

### Where to Go from Here

This tutorial covered the Red Hat AI ecosystem -- the tools, models, and workflows that surround the platform. For deep coverage of the platform itself, continue to the **OpenShift AI tutorial** at [`../../../openshift_ai/`](../../../openshift_ai/), which covers:

- OpenShift AI installation and configuration
- Data Science Projects and Workbenches (JupyterHub)
- Model serving with KServe and the Red Hat AI Inference Server
- Training Hub for distributed fine-tuning on Kubernetes
- Model monitoring, drift detection, and bias tracking
- Multi-tenant GPU scheduling and resource quotas
- Integration with the MLOps lifecycle (experiment tracking, model registry, CI/CD)

The ecosystem knowledge from this tutorial -- understanding Granite models, quantization trade-offs, InstructLab workflows, and cross-tier architecture -- will make the OpenShift AI tutorial significantly more productive. You already know the "why" and the "what." OpenShift AI teaches the "how at scale."
