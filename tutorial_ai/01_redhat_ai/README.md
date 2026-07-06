# Red Hat AI Ecosystem Tutorial

Learn the full Red Hat AI ecosystem — from local desktop experimentation to enterprise-scale deployment. This tutorial covers the three-tier journey that Red Hat provides for AI adoption: **Podman AI Lab** (desktop), **RHEL AI** (server/bare-metal), and how they connect to **OpenShift AI** (platform/cluster). It also covers the Granite model family, model optimization, and Red Hat Validated Patterns for production-ready reference architectures.

## Why This Tutorial?

The [OpenShift AI tutorial](../openshift_ai/) covers the platform in depth, but Red Hat's AI story is broader. Developers and architects need to understand the full journey:

1. **Prototyping locally** with Podman AI Lab
2. **Running single-server AI workloads** with RHEL AI (inference and model customization)
3. **Scaling to clusters** with OpenShift AI

This tutorial provides the ecosystem context and hands-on experience with the tools that sit outside (or below) the OpenShift AI platform. It targets **Red Hat AI 3.4** — the unified "metal-to-agent" platform that bundles Red Hat AI Inference, RHEL AI, and OpenShift AI.

## Target Audience

- Developers evaluating Red Hat's AI stack who want the big picture
- Teams deciding where to run AI workloads (laptop vs server vs cluster)
- Anyone starting the OpenShift AI tutorial who wants ecosystem context first
- IT architects designing an AI platform strategy on Red Hat infrastructure

## Prerequisites

### Required

- Podman Desktop installed (for Podman AI Lab lessons)
- Basic understanding of containers and Podman
- Familiarity with LLM concepts (inference, fine-tuning, embeddings)

### Recommended

- OpenShift knowledge (for understanding the RHEL AI → OpenShift AI progression)
- GPU hardware for RHEL AI lessons (NVIDIA, AMD, or Intel — CPU fallback for exploration)

## Structure

```
redhat_ai/
├── syllabus.md
├── README.md                                              ← you are here
├── level_1/                                               # Foundations (~7-9 hours)
│   ├── M1_ecosystem/
│   │   ├── 1_vision_and_architecture/README.md            # L1-1.1: Red Hat AI portfolio
│   │   └── 2_model_strategy/README.md                     # L1-1.2: Granite, Model Catalog
│   ├── M2_podman_ai_lab/
│   │   ├── 1_installing_and_exploring/README.md           # L1-2.1: Install, catalog, playground
│   │   ├── 2_recipes_catalog/README.md                    # L1-2.2: Chatbot, RAG, code gen
│   │   └── 3_to_production/README.md                      # L1-2.3: Export to RHEL AI / OCP AI
│   ├── M3_rhel_ai/
│   │   ├── 1_architecture_and_concepts/README.md          # L1-3.1: Inference + adaptation platform
│   │   ├── 2_serving_and_chatting/README.md               # L1-3.2: Model serving with ilab CLI
│   │   └── 3_fine_tuning_with_ilab/README.md              # L1-3.3: Fine-tuning workflow
│   └── M4_scaling_to_openshift_ai/
│       ├── 1_from_rhel_ai_to_openshift_ai/README.md       # L1-4.1: Scaling to OpenShift AI
│       └── 2_validated_patterns_for_ai/README.md           # L1-4.2: GitOps RAG pattern
└── level_2/                                               # Practitioner (~7-9 hours)
    ├── M1_advanced_podman_ai_lab/
    │   ├── 1_custom_models_and_catalogs/README.md         # L2-1.1: Custom GGUF, catalogs
    │   └── 2_building_applications/README.md              # L2-1.2: OpenAI SDK, Compose stacks
    ├── M2_model_customization/
    │   ├── 1_modular_model_customization/README.md        # L2-2.1: Docling, SDG Hub, Training Hub
    │   ├── 2_model_optimization/README.md                 # L2-2.2: LLM Compressor, quantization
    │   └── 3_production_deployment/README.md              # L2-2.3: Systemd, multi-model
    └── M3_cross_tier_workflows/
        ├── 1_end_to_end/README.md                         # L2-3.1: Desktop → server → cluster
        └── 2_granite_models_in_practice/README.md         # L2-3.2: Model selection, quantization
```

## Course Summary

| Level | Focus | Lessons | Time |
|-------|-------|---------|------|
| **Level 1 — Foundations** | Red Hat AI portfolio, Podman AI Lab, RHEL AI (inference + fine-tuning), Validated Patterns | 10 lessons | ~7-9 hours |
| **Level 2 — Practitioner** | Custom catalogs, modular model customization, model optimization, cross-tier workflows | 7 lessons | ~7-9 hours |
| **Total** | | **17 lessons** | **~14-18 hours** |

## Technical Stack

- **Podman AI Lab**: Latest extension for Podman Desktop
- **Podman Desktop**: 1.28+ with Podman 6.0+
- **RHEL AI**: 3.4 (bootable container image, Red Hat AI Inference Server, Model Optimization Toolkit, ilab CLI)
- **Red Hat AI Inference**: Standalone vLLM-based inference server (v3.3.0)
- **Model Customization**: Docling, SDG Hub, Training Hub (modular Python libraries)
- **Models**: IBM Granite 4.x family (Apache 2.0 licensed)
- **RedHatAI HuggingFace**: Pre-quantized models (FP8, INT4, GPTQ, AWQ, MXFP4)
- **Validated Patterns**: GitOps reference architectures (ArgoCD-based)
- **Container Runtime**: Podman (not Docker)

## Getting Started

Start with [L1-1.1 — Red Hat AI Vision, Architecture, and Portfolio](level_1/M1_ecosystem/1_vision_and_architecture/) to understand the Red Hat AI platform and three-tier deployment model, then work through the lessons sequentially.

## Reference Sources

- [Red Hat AI Learning Hub](https://docs.redhat.com/en/learn/ai)
- [Red Hat AI 3 Documentation](https://docs.redhat.com/en/documentation/red_hat_ai/3)
- [RHEL AI 3.4 Documentation](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux_ai/3.4)
- [Red Hat AI Inference 3.4](https://docs.redhat.com/en/documentation/red_hat_ai_inference/3.4)
- [Podman AI Lab Documentation](https://podman-desktop.io/docs/ai-lab)
- [RedHatAI on HuggingFace](https://huggingface.co/RedHatAI)
- [IBM Granite Models](https://huggingface.co/ibm-granite)
- [Validated Patterns](https://validatedpatterns.io/)
- [AI on OpenShift Community](https://ai-on-openshift.io/)
