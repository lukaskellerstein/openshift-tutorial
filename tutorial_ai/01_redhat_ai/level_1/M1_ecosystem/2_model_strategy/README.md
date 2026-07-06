# L1-1.2 — Red Hat AI Model Strategy: Granite and Beyond

**Level:** Foundations
**Duration:** 30 min

## Overview

This lesson covers the IBM Granite model family and Red Hat's broader model strategy. You will learn why Red Hat bets on Apache 2.0 licensed models, how the Granite family covers language, code, vision, speech, and safety use cases, and how Red Hat's validated model collections on HuggingFace extend support beyond Granite to include Llama, Mistral, DeepSeek, and other community models.

## Prerequisites

- Completed [L1-1.1 — Red Hat AI Vision and Architecture](../1_vision_and_architecture/)
- Basic understanding of LLM concepts (parameters, context window, quantization)
- No cluster or software installation required — this is a conceptual lesson

## Concepts

### Why Models Matter for Platform Strategy

When choosing an AI platform, the model layer is often overlooked — but it determines your long-term flexibility. Key questions include:

- **Can you inspect the training data?** (For compliance and bias auditing)
- **Can you fine-tune and redistribute the model?** (For customization without legal risk)
- **Can you run it on your own infrastructure?** (For data sovereignty)
- **Is the model indemnified?** (For enterprise legal protection)

Red Hat's model strategy answers all four with the IBM Granite family and supplements it with validated community models for use cases where Granite is not the best fit.

---

### The IBM Granite Model Family

Granite is IBM's open-source model family, licensed under **Apache 2.0**. This is the most permissive license commonly used for LLMs — it allows commercial use, modification, fine-tuning, and redistribution with no royalties and no restrictions on output ownership.

Granite is not a single model. It is a family of models purpose-built for different AI tasks:

```mermaid
graph TB
    G[IBM Granite Family<br/>Apache 2.0 Licensed]

    G --> GL[Granite Language]
    G --> GC[Granite Code]
    G --> GG[Granite Guardian]
    G --> GE[Granite Embedding R2]
    G --> GS[Granite Speech]
    G --> GV[Granite Vision]
    G --> GT[Granite Time Series]
    G --> GD[Granite Docling]

    GL --> GL1["Granite 4.1 Dense: 3B, 8B, 30B<br/>Granite 4.1 MoE: 1B/3B, 3B/8B"]
    GC --> GC1["Code Gen & Understanding<br/>Multi-language"]
    GG --> GG1["Safety & moderation<br/>Content filtering"]
    GE --> GE1["Text embeddings (R2)<br/>RAG retrieval"]
    GS --> GS1["Speech-to-text<br/>Text-to-speech"]
    GV --> GV1["Vision-language<br/>Image understanding"]
    GT --> GT1["Forecasting<br/>Time series analysis"]
    GD --> GD1["Document-specialized<br/>Docling library integration"]

    style G fill:#cc0000,color:#fff
    style GL fill:#4a90d9,color:#fff
    style GC fill:#6aa84f,color:#fff
    style GG fill:#e06666,color:#fff
    style GE fill:#f6b26b,color:#000
    style GS fill:#8e7cc3,color:#fff
    style GV fill:#c27ba0,color:#fff
    style GT fill:#45818e,color:#fff
    style GD fill:#a64d79,color:#fff
```

#### Granite Language Models (Granite 4.1 — Latest)

The core text generation models and the headline of the Granite family. **Granite 4.1** (released May 2026) is the latest generation, with three dense models (3B, 8B, 30B) optimized for chat and instruction following, plus two MoE variants for efficiency-sensitive deployments. Granite 4.0 models remain available for users who need the specific size variants (2B, 14B).

| Model | Parameters | Architecture | Context Window | Key Strengths |
|-------|-----------|-------------|----------------|---------------|
| **Granite 4.1 3B** | 3B | Dense | 128K | Lightweight chat, fast inference |
| **Granite 4.1 8B** | 8B | Dense | 128K | Best balance of quality and resources (headline model) |
| **Granite 4.1 30B** | 30B | Dense | 128K | Highest quality for demanding tasks |
| Granite 4.1 Tiny | 1B (active) / 3B (total) | MoE | 128K | Ultra-lightweight, edge deployment |
| Granite 4.1 Small | 3B (active) / 8B (total) | MoE | 128K | Efficient for chat and simple tasks |
| Granite 4.0 Compact | 2B | Dense | 128K | Smallest dense model, resource-constrained environments |
| Granite 4.0 Tiny | 3B | Dense | 128K | Small footprint, good general performance |
| Granite 4.0 Small | 8B | Dense | 128K | General-purpose, broad compatibility |
| Granite 4.0 Medium | 14B | Dense | 128K | Higher quality for complex reasoning |
| Granite 4.0 Large | 30B | Dense | 128K | Previous-gen large model |

**Dense vs MoE (Mixture of Experts):** Dense models activate all parameters for every token. MoE models have more total parameters but only activate a subset (the "active" count) for each token, making them faster and more memory-efficient at inference time. For example, Granite 4.1 Small has 8B total parameters but only uses 3B for any given token — giving you 8B-quality output at closer to 3B inference cost. The Granite 4.1 dense models (3B, 8B, 30B) are the primary recommended models for most use cases.

**Context window:** All Granite 4.x models support 128K tokens, with some configurations extending to 512K. This is important for RAG use cases where you need to fit many retrieved documents into the context.

#### Granite Code Models

Purpose-built for software development tasks: code generation, code completion, code explanation, and bug fixing. These models are trained on a curated code corpus covering 116+ programming languages.

| Model | Parameters | Optimized For |
|-------|-----------|--------------|
| Granite Code 3B | 3B | Code completion, inline suggestions |
| Granite Code 8B | 8B | Code generation, explanation, refactoring |
| Granite Code 20B | 20B | Complex code generation, multi-file reasoning |
| Granite Code 34B | 34B | Highest quality code generation, architecture-level tasks |

Granite Code models are particularly strong in enterprise languages (Java, Python, Go, JavaScript/TypeScript) and understand infrastructure-as-code formats (YAML, Terraform, Ansible).

#### Granite Guardian

A specialized model for AI safety. Granite Guardian evaluates LLM inputs and outputs for risks including:

- **Harmful content** — violence, hate speech, self-harm
- **Social bias** — gender, racial, and other biases in generated text
- **Jailbreak detection** — attempts to bypass safety guardrails
- **Groundedness** — whether the model's response is grounded in provided context (hallucination detection)
- **Relevance** — whether the response addresses the actual question

Granite Guardian is designed to run alongside a generation model as a safety layer. In production, you deploy both: the generation model answers the user's question, and Granite Guardian evaluates whether the response is safe to return.

#### Granite Embedding R2

Text embedding models optimized for retrieval-augmented generation (RAG). The **R2 (Revision 2)** models are the improved second generation, with better retrieval accuracy and broader language support. These models convert text into dense vector representations that can be stored in a vector database and searched by semantic similarity.

| Model | Dimensions | Max Tokens | Use Case |
|-------|-----------|------------|----------|
| Granite Embedding 30M | 384 | 512 | Lightweight RAG, resource-constrained |
| Granite Embedding 125M | 768 | 512 | General-purpose RAG, good quality/speed balance |
| Granite Embedding 278M | 1024 | 512 | Highest quality retrieval |

Using Granite Embedding R2 with Granite Language creates an all-Granite RAG stack — same license, same vendor, same support contract.

#### Granite Speech

Multilingual automatic speech recognition (ASR) and speech translation. Granite Speech models handle:

- Speech-to-text transcription in 30+ languages
- Cross-language speech translation
- Speaker diarization (identifying who said what)

#### Granite Vision

Multimodal models that process both images and text. Use cases include:

- Document understanding (extracting information from scanned documents, forms, receipts)
- Image captioning and visual question answering
- Chart and diagram interpretation

#### Granite Time Series

A new addition to the Granite family, purpose-built for time series forecasting and analysis. These models handle:

- Multi-horizon forecasting (predicting future values across multiple time steps)
- Anomaly detection in temporal data
- Pattern recognition across seasonal and cyclical data

Time series models are particularly relevant for enterprise use cases like demand forecasting, infrastructure capacity planning, and financial trend analysis.

#### Granite Docling

Document-specialized models designed to work with the [Docling](https://github.com/DS4SD/docling) library. Docling is an open-source document processing toolkit that converts PDFs, DOCX, PPTX, and other formats into structured data. Granite Docling models are optimized for:

- Extracting structured content from complex document layouts (tables, headers, lists)
- Understanding document hierarchy and relationships between sections
- Processing scanned and digital documents with mixed content types

The combination of Docling (for document parsing) and Granite Docling models (for understanding) creates an end-to-end document intelligence pipeline under Apache 2.0.

---

### Why Red Hat Bets on Granite

Red Hat's strategic alignment with Granite is not arbitrary. Several properties make Granite uniquely suitable for an enterprise open-source platform:

**Apache 2.0 licensing.** Unlike Meta's Llama (custom license with usage restrictions above 700M monthly users) or Mistral's models (Apache 2.0 for some, proprietary for others), every Granite model uses Apache 2.0. This means:
- No usage restrictions at any scale
- You can fine-tune, modify, and redistribute without restrictions
- You own the outputs — no license claims on generated content
- No "phone home" requirements or usage reporting

**Training data transparency.** IBM publishes information about Granite's training data composition. This is critical for enterprises in regulated industries (finance, healthcare, government) that need to demonstrate their AI models were not trained on problematic data.

**Enterprise indemnification.** IBM and Red Hat provide intellectual property indemnification for Granite models — if a legal challenge arises regarding the model's training data, IBM assumes the legal risk, not the customer. This is a significant differentiator for risk-averse enterprises.

**Optimized for Red Hat's stack.** Granite models are the primary test target for vLLM optimizations in the Red Hat AI Inference Server, InstructLab fine-tuning workflows, and OpenShift AI model serving. They receive the most testing and performance tuning across the Red Hat AI stack.

---

### RedHatAI on HuggingFace

Red Hat maintains an organization on HuggingFace at [huggingface.co/RedHatAI](https://huggingface.co/RedHatAI) that serves two purposes:

1. **Pre-quantized Granite models** — ready to download and serve with vLLM
2. **Validated model collections** — community models that Red Hat has tested and certified for use with vLLM and OpenShift AI

#### Pre-quantized Models

Quantization reduces a model's memory footprint by storing weights in lower-precision formats. The RedHatAI HuggingFace organization provides Granite models pre-quantized in multiple formats:

| Quantization Format | Precision | Memory Savings | Quality Impact | Best For |
|--------------------|-----------|---------------|----------------|----------|
| FP16 (baseline) | 16-bit float | None (baseline) | None | Reference quality, ample GPU memory |
| FP8 (W8A8) | 8-bit float | ~50% vs FP16 | Minimal | Production serving with good quality |
| INT8 | 8-bit integer | ~50% vs FP16 | Low | Production serving, broad GPU support |
| GPTQ (INT4) | 4-bit (grouped) | ~75% vs FP16 | Moderate | Memory-constrained GPUs |
| AWQ (INT4) | 4-bit (activation-aware) | ~75% vs FP16 | Low-moderate | Best 4-bit quality, less memory |
| MXFP4 | 4-bit (Microscaling) | ~75% vs FP16 | Low-moderate | Experimental, next-gen 4-bit format |
| NVFP4 | 4-bit (NVIDIA) | ~75% vs FP16 | Low-moderate | NVIDIA Blackwell GPUs with FP4 support |

Why this matters: a 30B parameter model in FP16 requires ~60 GB of GPU memory. In FP8, it fits in ~30 GB. In AWQ 4-bit, it fits in ~15 GB. Pre-quantized models save you the time and expertise of running quantization yourself. RedHatAI pre-quantized models recover >99% of baseline accuracy across all quantization formats.

The naming convention on HuggingFace follows a predictable pattern:
```
RedHatAI/granite-4.1-8b-instruct-FP8
RedHatAI/granite-4.1-8b-instruct-GPTQ-INT4
RedHatAI/granite-4.1-30b-instruct-AWQ-INT4
RedHatAI/granite-4.1-8b-instruct-MXFP4
```

#### Validated Model Collections

Every month, Red Hat publishes **validated model collections** — curated sets of models that have been tested against vLLM on OpenShift AI. These collections are not limited to Granite. Red Hat tests and validates models from across the open-source community:

| Model Family | Provider | License | Validated Sizes |
|-------------|----------|---------|-----------------|
| Granite | IBM | Apache 2.0 | 2B to 30B |
| Llama | Meta | Llama Community License | 3B to 405B |
| Mistral / Mixtral | Mistral AI | Apache 2.0 (some models) | 7B to 8x22B |
| DeepSeek | DeepSeek | MIT | 7B to 671B (MoE) |
| Qwen | Alibaba | Apache 2.0 (Qwen 2.5) | 0.5B to 72B |
| Gemma | Google | Gemma License | 2B to 27B |

**What "validated" means in practice:**
1. The model is tested for compatibility with the Red Hat AI Inference Server (vLLM-based)
2. Serving configurations (tensor parallelism, quantization settings) are verified
3. Performance benchmarks are recorded on reference hardware
4. The model is certified for use on OpenShift AI with a supported configuration

This does not mean Red Hat provides support for the model itself (only Granite gets full support), but it means you can deploy these models on OpenShift AI with confidence that the serving infrastructure works correctly.

---

### Model Optimization Toolkit

The **Red Hat Model Optimization Toolkit** is a Technology Preview tool for quantizing, compressing, and optimizing models for efficient serving. It is based on the upstream **LLM Compressor** (v0.10.0) project.

#### Quantization Methods

The toolkit supports several quantization approaches, each with different tradeoffs:

| Method | Format | Description | Status |
|--------|--------|-------------|--------|
| FP8 | W8A8 | 8-bit weights and activations | Production-ready |
| GPTQ | W4A16 (INT4) | 4-bit weights, 16-bit activations | Production-ready |
| AWQ | W4A16 (INT4) | Activation-aware 4-bit weights | Production-ready |
| MXFP4 | Microscaling FP4 | Next-gen 4-bit with microscaling | Experimental |
| NVFP4 | NVIDIA FP4 | 4-bit for NVIDIA Blackwell GPUs only | Hardware-specific |

**W8A8 (FP8)** is the recommended starting point for most production workloads — it halves memory requirements with minimal quality loss. **W4A16 (INT4)** via GPTQ or AWQ is for memory-constrained deployments where you need a large model to fit on fewer GPUs.

#### Sparsity

The toolkit also supports **SparseGPT** — a structured sparsity method that prunes model weights to reduce computation. Sparse models can be combined with quantization (e.g., sparse + FP8) for compounding efficiency gains.

#### Speculative Decoding with Speculators

The **Speculators** library (published under the `vllm-project` GitHub organization, Apache 2.0 licensed) enables **speculative decoding** — a technique where a small "draft" model generates candidate tokens that a larger "target" model verifies in parallel. This reduces latency by **2-2.7x** without changing the output quality (the target model's output distribution is preserved exactly).

Speculative decoding is particularly effective for:
- Interactive chat applications where latency matters more than throughput
- Scenarios where you are already serving a large model and have spare compute for the draft model
- Time-to-first-token optimization in streaming use cases

#### Status and Availability

The Model Optimization Toolkit is currently in **Technology Preview** — it is functional and tested but does not yet carry a production SLA. The pre-quantized models on RedHatAI's HuggingFace organization are produced using this toolkit and recover >99% of baseline accuracy, so the quantization quality is well-validated even if the toolkit itself is still pre-GA.

---

### Model Selection Guidance

Choosing a model depends on your requirements across four dimensions:

```mermaid
graph TD
    START["What are your requirements?"] --> LICENSE{"Need IP<br/>indemnification?"}

    LICENSE -- "Yes" --> GRANITE["Use Granite<br/>(Apache 2.0 + indemnified)"]
    LICENSE -- "No" --> PERF{"Need highest<br/>benchmark scores?"}

    PERF -- "Yes" --> COMMUNITY["Evaluate community models<br/>(Llama, Mistral, DeepSeek, Qwen)"]
    PERF -- "No" --> SIZE{"Resource<br/>constraints?"}

    SIZE -- "Tight (< 16GB VRAM)" --> SMALL["Granite 4.1 3B<br/>or Granite 4.1 Tiny (1B/3B MoE)"]
    SIZE -- "Moderate (16-48GB)" --> MEDIUM["Granite 4.1 8B<br/>(headline model)"]
    SIZE -- "Ample (48GB+)" --> LARGE["Granite 4.1 30B<br/>or community 70B+"]

    style GRANITE fill:#cc0000,color:#fff
    style COMMUNITY fill:#4a90d9,color:#fff
    style SMALL fill:#6aa84f,color:#fff
    style MEDIUM fill:#f6b26b,color:#000
    style LARGE fill:#8e7cc3,color:#fff
```

**Use Granite when:**
- You need enterprise indemnification (regulated industries, risk-averse organizations)
- You want a single vendor for model + platform support (IBM/Red Hat)
- Training data transparency is a compliance requirement
- You prefer Apache 2.0 with no usage restrictions at any scale

**Use community models when:**
- You need the highest possible benchmark performance for a specific task
- You need a model size not available in the Granite family (e.g., 70B+ dense models)
- You are already invested in a specific model ecosystem (e.g., Llama fine-tunes)
- License restrictions are acceptable for your use case

**Practical guidance for common scenarios:**

| Scenario | Recommended Model | Why |
|----------|------------------|-----|
| General enterprise chatbot | Granite 4.1 8B | Best balance of quality and resources (headline model) |
| RAG application | Granite Embedding R2 + Granite 4.1 8B | All-Granite stack, same license and support |
| Code assistant | Granite Code | Strong enterprise language support |
| Content moderation layer | Granite Guardian | Purpose-built safety model |
| Maximum quality, cost no object | Llama 3.1 405B or DeepSeek-V3 | Highest benchmarks, but need significant GPU resources |
| Edge/mobile deployment | Granite 4.1 Tiny (1B/3B MoE) | Smallest footprint, MoE efficiency |
| Document processing | Granite Docling + Docling library | End-to-end document intelligence pipeline |
| Image understanding | Granite Vision | Multimodal, handles scanned documents and VQA |
| Multilingual voice interface | Granite Speech + Granite 4.1 8B | End-to-end speech pipeline |
| Time series forecasting | Granite Time Series | Purpose-built for temporal data analysis |

---

### Granite Model Family Reference Table

A comprehensive reference of the Granite model family. **Granite 4.1** (May 2026) is the latest generation.

| Model | Family | Parameters | Architecture | Context | License | Primary Use Case |
|-------|--------|-----------|-------------|---------|---------|-----------------|
| **Granite 4.1 3B** | Language | 3B | Dense | 128K | Apache 2.0 | Lightweight chat, fast inference |
| **Granite 4.1 8B** | Language | 8B | Dense | 128K | Apache 2.0 | General-purpose, headline model |
| **Granite 4.1 30B** | Language | 30B | Dense | 128K | Apache 2.0 | Demanding tasks, highest quality |
| Granite 4.1 Tiny | Language | 1B/3B | MoE | 128K | Apache 2.0 | Edge, ultra-lightweight inference |
| Granite 4.1 Small | Language | 3B/8B | MoE | 128K | Apache 2.0 | Efficient chat and instruction following |
| Granite 4.0 Compact | Language | 2B | Dense | 128K | Apache 2.0 | Resource-constrained environments |
| Granite 4.0 Tiny | Language | 3B | Dense | 128K | Apache 2.0 | Small footprint general use |
| Granite 4.0 Small | Language | 8B | Dense | 128K | Apache 2.0 | General-purpose (previous gen) |
| Granite 4.0 Medium | Language | 14B | Dense | 128K | Apache 2.0 | Complex reasoning, higher quality |
| Granite 4.0 Large | Language | 30B | Dense | 128K | Apache 2.0 | Large model (previous gen) |
| Granite Code | Code | varies | Dense | 128K | Apache 2.0 | Code generation and understanding |
| Granite Guardian | Safety | varies | Dense | varies | Apache 2.0 | Content moderation, safety filtering |
| Granite Embedding R2 30M | Embedding | 30M | Encoder | 512 | Apache 2.0 | Lightweight RAG retrieval |
| Granite Embedding R2 125M | Embedding | 125M | Encoder | 512 | Apache 2.0 | General-purpose RAG |
| Granite Embedding R2 278M | Embedding | 278M | Encoder | 512 | Apache 2.0 | High-quality retrieval |
| Granite Speech | Speech | varies | Encoder-Decoder | varies | Apache 2.0 | Speech-to-text, text-to-speech |
| Granite Vision | Vision | varies | Vision-Language | varies | Apache 2.0 | Document understanding, VQA |
| Granite Time Series | Time Series | varies | varies | varies | Apache 2.0 | Forecasting, temporal analysis |
| Granite Docling | Document | varies | varies | varies | Apache 2.0 | Document intelligence with Docling |

## Key Takeaways

- The **IBM Granite** model family (latest: **Granite 4.1**, May 2026) is Apache 2.0 licensed with no usage restrictions, covering language, code, vision, speech, embeddings, safety, time series, and document intelligence — a complete model ecosystem under a single permissive license.
- Red Hat bets on Granite for three reasons: **Apache 2.0 licensing** (no restrictions at any scale), **training data transparency** (auditable for compliance), and **enterprise indemnification** (IBM assumes legal risk).
- The **Model Optimization Toolkit** (Technology Preview, based on LLM Compressor) provides quantization (FP8, INT4 via GPTQ/AWQ, MXFP4, NVFP4), sparsity (SparseGPT), and speculative decoding (Speculators library, 2-2.7x latency reduction).
- **RedHatAI on HuggingFace** provides pre-quantized models (FP8, INT4, GPTQ, AWQ, MXFP4, NVFP4) recovering >99% baseline accuracy, plus monthly validated collections that extend beyond Granite to include Llama, Mistral, DeepSeek, Qwen, and Gemma.
- "Validated" means Red Hat has tested a model on vLLM and certified it for OpenShift AI — not that Red Hat provides full support for non-Granite models.
- Choose **Granite for enterprise use cases** where indemnification and transparency matter. Choose **community models** when you need maximum benchmark performance or model sizes outside the Granite range.

## Next Steps

Continue to [L1-2.1 — Installing and Exploring Podman AI Lab](../../M2_podman_ai_lab/1_installing_and_exploring/) to get hands-on with the first tier of Red Hat's AI stack: downloading models, chatting with them locally, and running pre-built AI application recipes on your desktop.
