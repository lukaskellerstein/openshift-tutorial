# Red Hat AI Ecosystem Tutorial

Learn the full Red Hat AI ecosystem — from local desktop experimentation to enterprise-scale deployment. This tutorial covers the three-tier journey that Red Hat provides for AI adoption: **Podman AI Lab** (desktop), **RHEL AI** (server/bare-metal), and how they connect to **OpenShift AI** (platform/cluster). It also covers the Granite model family and Red Hat Validated Patterns for production-ready reference architectures.

## Why This Tutorial?

The [OpenShift AI tutorial](../openshift_ai/) covers the platform in depth, but Red Hat's AI story is broader. Developers and architects need to understand the full journey:

1. **Prototyping locally** with Podman AI Lab
2. **Running single-server AI workloads** with RHEL AI
3. **Scaling to clusters** with OpenShift AI

This tutorial provides the ecosystem context and hands-on experience with the tools that sit outside (or below) the OpenShift AI platform.

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
├── README.md                                          ← you are here
├── level_1/                                           # Foundations (~6-8 hours)
│   ├── M1_ecosystem/
│   │   ├── 1_vision_and_architecture/README.md        # L1-1.1: Three-tier model, strategy
│   │   └── 2_model_strategy/README.md                 # L1-1.2: Granite, RedHatAI HuggingFace
│   ├── M2_podman_ai_lab/
│   │   ├── 1_installing_and_exploring/README.md       # L1-2.1: Install, catalog, playground
│   │   ├── 2_recipes_catalog/README.md                # L1-2.2: Chatbot, RAG, code gen
│   │   └── 3_to_production/README.md                  # L1-2.3: Export to RHEL AI / OCP AI
│   ├── M3_rhel_ai/
│   │   ├── 1_architecture_and_concepts/README.md      # L1-3.1: Bootable image, InstructLab
│   │   ├── 2_workflow_serve_chat_finetune/README.md   # L1-3.2: ilab CLI workflow
│   │   └── 3_openshift_ai_onramp/README.md            # L1-3.3: Scaling to OpenShift AI
│   └── M4_validated_patterns/
│       └── 1_validated_patterns_for_ai/README.md      # L1-4.1: GitOps RAG pattern
└── level_2/                                           # Practitioner (~5-7 hours)
    ├── M1_advanced_podman_ai_lab/
    │   ├── 1_custom_models_and_catalogs/README.md     # L2-1.1: Custom GGUF, catalogs
    │   └── 2_building_applications/README.md          # L2-1.2: OpenAI SDK, Compose stacks
    ├── M2_rhel_ai_deep_dive/
    │   ├── 1_instructlab_taxonomy_and_sdg/README.md   # L2-2.1: Taxonomy, SDG, LAB-tuning
    │   └── 2_production_deployment/README.md          # L2-2.2: Systemd, multi-model
    └── M3_cross_tier_workflows/
        ├── 1_end_to_end/README.md                     # L2-3.1: Desktop → server → cluster
        └── 2_granite_models_in_practice/README.md     # L2-3.2: Model selection, quantization
```

## Course Summary

| Level | Focus | Lessons | Time |
|-------|-------|---------|------|
| **Level 1 — Foundations** | Ecosystem overview, Podman AI Lab, RHEL AI, Granite, Validated Patterns | 9 lessons | ~6-8 hours |
| **Level 2 — Practitioner** | Custom catalogs, InstructLab deep dive, cross-tier workflows, Granite in practice | 6 lessons | ~5-7 hours |
| **Total** | | **15 lessons** | **~11-15 hours** |

## Technical Stack

- **Podman AI Lab**: Latest extension for Podman Desktop
- **Podman Desktop**: 1.10.3+ with Podman 5.0.1+
- **RHEL AI**: 1.5 (bootable container image, InstructLab, vLLM)
- **Models**: IBM Granite 4.x family (Apache 2.0 licensed)
- **RedHatAI HuggingFace**: Pre-quantized models (FP8, INT8, GPTQ, AWQ)
- **Validated Patterns**: GitOps reference architectures (ArgoCD-based)
- **Container Runtime**: Podman (not Docker)

## Getting Started

Start with [L1-1.1 — Red Hat AI Vision and Architecture](level_1/M1_ecosystem/1_vision_and_architecture/) to understand the three-tier deployment model, then work through the lessons sequentially.

## Reference Sources

- [Red Hat AI Learning Hub](https://docs.redhat.com/en/learn/ai)
- [Podman AI Lab Documentation](https://podman-desktop.io/docs/ai-lab)
- [RHEL AI Documentation 1.5](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux_ai/1.5)
- [RedHatAI on HuggingFace](https://huggingface.co/RedHatAI)
- [IBM Granite Models](https://huggingface.co/ibm-granite)
- [Validated Patterns](https://validatedpatterns.io/)
- [AI on OpenShift Community](https://ai-on-openshift.io/)
