# L1-M3.1 -- Fine-Tuning Concepts on OpenShift AI

**Level:** Foundations
**Duration:** 30 min

## Overview

Fine-tuning adapts a pre-trained model to your specific domain, style, or task -- and OpenShift AI provides multiple paths to do it, from a single notebook cell to distributed multi-GPU training across nodes. If you have fine-tuned models on vanilla Kubernetes (managing PyTorch jobs, GPU scheduling, and storage manually), OpenShift AI replaces that manual orchestration with integrated tooling at every scale.

This conceptual lesson maps the fine-tuning landscape, explains when to fine-tune versus using prompt engineering or RAG, and introduces the three fine-tuning approaches available on OpenShift AI.

## Prerequisites

- Completed: [L1-M2.4 -- Autoscaling](../../M2_model_serving/4_autoscaling/)
- Familiarity with LLM concepts (parameters, tokens, inference)
- Basic understanding of model training (loss functions, epochs, learning rate)
- No cluster required -- this is a conceptual lesson

## K8s Context

On vanilla Kubernetes, fine-tuning a model means assembling the infrastructure yourself: writing a `PyTorchJob` or a custom `Job`, mounting dataset PVCs, configuring GPU resource requests, managing NCCL environment variables for multi-GPU communication, and building container images with the right CUDA/PyTorch versions. If you want distributed training, you also need to set up the Training Operator, configure `torchrun` arguments, and coordinate worker pods manually.

OpenShift AI replaces this patchwork with three integrated approaches at different scales -- from a Tier 3 Python library you call in a notebook, to a Tier 1 DSC component that manages distributed training through CRDs.

## Concepts

### The Fine-Tuning Landscape

Fine-tuning modifies a pre-trained model's weights so it performs better on a specific task. There are several approaches, each trading off VRAM usage, training speed, and output quality.

#### SFT (Supervised Fine-Tuning)

Full-parameter fine-tuning updates every weight in the model using labeled input-output pairs. This produces the highest-quality adaptation because the entire model capacity is available for learning.

The cost is significant: you need enough GPU memory to hold the full model weights, gradients, and optimizer states simultaneously. For a 7B parameter model in mixed precision, that is roughly 28-56 GB of VRAM -- often requiring multiple GPUs even for a single training run.

**Use when:** You have ample GPU resources and need maximum quality. Common for training foundation models from a strong base checkpoint.

#### LoRA (Low-Rank Adaptation)

Instead of updating all model weights, LoRA freezes the pre-trained model and injects small trainable "adapter" matrices into each transformer layer. These adapters learn task-specific modifications while the original weights remain unchanged.

The key insight is that the weight updates during fine-tuning have low intrinsic rank -- they can be approximated by much smaller matrices without meaningful quality loss. In practice, LoRA trains roughly 0.1-1% of the total parameters.

Benefits:
- ~70% less VRAM than full SFT
- Training is 2-3x faster
- Adapter weights are small (typically 10-100 MB) and can be swapped at serving time
- Multiple adapters can share the same base model

**Use when:** You want efficient fine-tuning with near-SFT quality. This is the default recommendation for most use cases.

#### QLoRA (Quantized LoRA)

QLoRA combines LoRA with 4-bit quantization of the base model. The pre-trained weights are loaded in 4-bit NormalFloat (NF4) format, while the LoRA adapter matrices train in full precision (bfloat16). A technique called "double quantization" further reduces the memory footprint of the quantization constants.

This makes it possible to fine-tune a 7B model on a single consumer GPU with 8 GB of VRAM -- something that would be impossible with full SFT or even standard LoRA.

The tradeoff is speed: quantized matrix operations are slower than their full-precision equivalents, so QLoRA training takes longer per step than LoRA. Final quality is typically within 1-2% of full LoRA.

**Use when:** You have limited GPU memory and need to fine-tune a model that would not fit otherwise.

#### OSFT (Orthogonal Subspace Fine-Tuning)

OSFT constrains the fine-tuning updates to lie in the orthogonal complement of the subspace spanned by the original weight matrices. In simpler terms: it learns new behaviors without overwriting existing ones.

Standard fine-tuning (including LoRA) can cause "catastrophic forgetting" -- the model gets better at your task but loses general capabilities it had before. OSFT mitigates this by mathematically ensuring the adaptation does not interfere with the pre-trained knowledge.

**Use when:** Preserving the model's existing capabilities is critical -- for example, fine-tuning a general-purpose model on domain-specific data without degrading its general reasoning.

### SFT vs LoRA vs QLoRA Comparison

| Aspect | SFT (Full) | LoRA | QLoRA |
|--------|-----------|------|-------|
| Parameters trained | 100% | ~0.1-1% | ~0.1-1% |
| VRAM usage | Very high | ~30% of SFT | ~15% of SFT |
| Training speed | Baseline | 2-3x faster | 1.5-2x faster (quant overhead) |
| Quality | Best | Near-SFT | Within 1-2% of LoRA |
| Adapter size | Full model copy | 10-100 MB | 10-100 MB |
| Multi-adapter serving | No (separate models) | Yes (swap adapters) | Yes (swap adapters) |
| Min GPUs for 7B model | 2-4 GPUs | 1 GPU (16 GB) | 1 GPU (8 GB) |

### When to Fine-Tune vs. Prompt Engineering vs. RAG

Before reaching for fine-tuning, consider whether a simpler approach solves your problem. Each technique addresses a different kind of gap between what a model can do out of the box and what you need it to do.

#### Decision Tree

```
Start here: Does the base model understand your task?
|
+-- YES, but output format/style is wrong
|   |
|   +-- Can you fix it with a system prompt or few-shot examples?
|       |
|       +-- YES --> Prompt Engineering (cheapest, fastest iteration)
|       +-- NO  --> Fine-Tuning (teaches new behavior patterns)
|
+-- YES, but it lacks specific factual knowledge
|   |
|   +-- Is the knowledge static or slowly changing?
|       |
|       +-- Dynamic / frequently updated --> RAG (retrieval at inference time)
|       +-- Static / stable domain --> RAG or Fine-Tuning (either works)
|
+-- NO, it fundamentally cannot do the task
    |
    +-- Is it a reasoning/format issue or a knowledge issue?
        |
        +-- Reasoning / format --> Fine-Tuning
        +-- Knowledge --> RAG + possibly Fine-Tuning
```

#### Comparison

| Approach | What It Changes | Training Needed | Cost | Best For |
|----------|----------------|-----------------|------|----------|
| Prompt Engineering | Input context only | None | Lowest | Format tweaks, persona, simple instructions |
| RAG | Adds external knowledge at inference | None (but needs retrieval pipeline) | Medium | Current/dynamic data, document Q&A |
| Fine-Tuning | Model weights | Yes (GPU hours) | Highest | New behaviors, domain-specific style, structured output |

**In practice, these approaches combine.** A common production pattern is: fine-tune a model on your domain's style and terminology, then use RAG to inject current data at inference time. Prompt engineering is always the first step.

### OpenShift AI Fine-Tuning Options

OpenShift AI provides three approaches to fine-tuning, organized by complexity and scale. They correspond to the three-tier architecture you learned in [L1-M1.1](../../M1_platform_setup/1_architecture_overview/).

#### Option 1: Training Hub (Tier 3 Python Library)

Training Hub is a Python library that provides simple, high-level functions for fine-tuning directly from a notebook:

```python
pip install training-hub

from training_hub import lora_sft, qlora_sft, sft, osft

# LoRA fine-tuning in one function call
lora_sft(
    model="google/gemma-3-4b-it",
    dataset="my-dataset",
    output_dir="./fine-tuned-adapter",
)
```

Available functions:
- `sft()` -- full supervised fine-tuning
- `lora_sft()` -- LoRA fine-tuning
- `qlora_sft()` -- QLoRA fine-tuning
- `osft()` -- orthogonal subspace fine-tuning

Under the hood, Training Hub uses the [Unsloth](https://github.com/unslothai/unsloth) backend for LoRA-based methods. Unsloth provides custom CUDA kernels that make LoRA training approximately 2x faster and use 70% less memory compared to standard HuggingFace implementations.

**When to use:** Exploratory fine-tuning, prototyping, small models, single-GPU jobs. This is the starting point for most fine-tuning work and what we will use in [L1-M3.2](../2_training_hub_lora/).

**Scale:** Single GPU, single node. The training runs inside your notebook pod or as a single-pod job.

#### Option 2: Kubeflow Trainer v2 (Tier 1 DSC Component)

For production-grade distributed training, OpenShift AI provides the `trainer` component in the DataScienceCluster. This is a Tier 1 component that installs the Kubeflow Trainer v2 controller.

The key CRDs:

```yaml
# ClusterTrainingRuntime -- defines a reusable training template
apiVersion: kubeflow.org/v2alpha1
kind: ClusterTrainingRuntime
metadata:
  name: torch-distributed-lora
spec:
  template:
    spec:
      replicatedJobs:
        - name: worker
          replicas: 4
          template:
            spec:
              containers:
                - name: trainer
                  resources:
                    limits:
                      nvidia.com/gpu: 1
```

```yaml
# TrainJob -- submits a training job using a runtime template
apiVersion: kubeflow.org/v2alpha1
kind: TrainJob
metadata:
  name: gemma-lora-finetune
spec:
  runtimeRef:
    name: torch-distributed-lora
  datasetConfig:
    storageUri: pvc://training-data/dataset
  modelConfig:
    storageUri: pvc://models/gemma-3-4b
```

The `ClusterTrainingRuntime` defines reusable training templates (think of them as training "profiles"), while `TrainJob` references a runtime and provides job-specific parameters (dataset, model, hyperparameters).

Under the hood, Trainer v2 uses PyTorch FSDP (Fully Sharded Data Parallel) for distributed training, automatically sharding model parameters, gradients, and optimizer states across multiple GPUs and nodes.

**When to use:** Production fine-tuning, large models, multi-GPU or multi-node training, repeatable training pipelines.

**Scale:** Multi-GPU, multi-node. Requires the `trainer` DSC component to be enabled and the JobSet operator to be installed.

This approach is covered in detail in L2-M6.3 (Distributed Training).

#### Option 3: InstructLab / LAB-Tuning

InstructLab is Red Hat's approach to taxonomy-driven fine-tuning. Instead of curating a dataset manually, you define a taxonomy (a tree of skills and knowledge) and InstructLab uses a teacher model to generate synthetic training data from your taxonomy entries.

The workflow:
1. Define a taxonomy: structured descriptions of knowledge or skills you want the model to learn
2. InstructLab generates synthetic question-answer pairs from your taxonomy
3. The model is fine-tuned on the generated data using LAB (Large-scale Alignment for chatBots) methodology

**When to use:** When you want to add knowledge or skills to a model without manually curating a large dataset. Particularly useful for organizational knowledge bases.

**Scale:** Varies. The synthetic data generation requires a capable teacher model. Training can be single-node or distributed.

This is the most specialized approach and is covered in L3-M4.1 (InstructLab).

### OpenShift AI Fine-Tuning Options Comparison

| Aspect | Training Hub | Kubeflow Trainer v2 | InstructLab |
|--------|-------------|--------------------:|-------------|
| Tier | 3 (Python library) | 1 (DSC component) | Specialized workflow |
| Installation | `pip install training-hub` | Enable `trainer` in DSC | Separate tooling |
| Interface | Python functions | CRDs (`TrainJob`) | CLI + taxonomy files |
| Methods | SFT, LoRA, QLoRA, OSFT | SFT, LoRA (via runtimes) | LAB methodology |
| Scale | Single GPU | Multi-GPU, multi-node | Varies |
| Backend | Unsloth | PyTorch FSDP | InstructLab |
| Best for | Prototyping, small models | Production, large models | Knowledge injection |
| Tutorial lesson | L1-M3.2 | L2-M6.3 | L3-M4.1 |

### Progressive Scaling Path

Fine-tuning on OpenShift AI follows a natural progression from experimentation to production:

```
Notebook (Training Hub)          Simplest. One function call. Single GPU.
        |                        Good for: prototyping, small models, exploring
        v                        hyperparameters.
Single-Node TrainJob             One pod, one or more GPUs. CRD-based, reproducible.
        |                        Good for: models that fit on one node, automated
        v                        retraining.
Distributed Multi-GPU TrainJob   Multiple pods, PyTorch FSDP. Scales to large models.
        |                        Good for: 13B+ models, production fine-tuning.
        v
Automated Pipeline               KFP pipeline triggers training, evaluation, and
                                 registry upload. Full MLOps.
                                 Good for: continuous fine-tuning, CI/CD for models.
```

Each step up adds infrastructure complexity but enables larger models and more reliable workflows. Start with Training Hub in a notebook; graduate to Trainer v2 when you need reproducibility, scale, or automation.

### Hardware Requirements

The GPU memory required depends on the fine-tuning method and model size. This table provides approximate VRAM requirements for common scenarios:

| Scenario | Method | GPUs | Approx. VRAM per GPU |
|----------|--------|------|---------------------|
| Small model (1-4B params) | QLoRA | 1 | ~2-4 GB |
| Small model (1-4B params) | LoRA | 1 | ~4-8 GB |
| Small model (1-4B params) | Full SFT | 1 | ~16 GB |
| Medium model (7-13B params) | QLoRA | 1 | ~6-10 GB |
| Medium model (7-13B params) | LoRA | 1 | ~16-24 GB |
| Medium model (7-13B params) | Full SFT | 2-4 | ~24-40 GB each |
| Large model (30-70B params) | QLoRA | 1-2 | ~24-48 GB each |
| Large model (30-70B params) | LoRA | 4+ | ~40-80 GB each |
| Large model (30-70B params) | Full SFT | 8+ | ~80 GB each |

Notes:
- VRAM estimates include model weights, adapter weights, gradients, optimizer states, and activation memory.
- Batch size significantly affects VRAM. The estimates above assume small batch sizes (1-4). Gradient accumulation can simulate larger batches without additional VRAM.
- Unsloth (used by Training Hub) reduces LoRA/QLoRA VRAM usage by roughly 70% compared to standard HuggingFace, so actual requirements with Training Hub will be at the lower end of these ranges.
- On the Red Hat Developer Sandbox, you typically have access to a single GPU with 16-24 GB VRAM, making QLoRA and LoRA on small-to-medium models the practical options.

### Key CRDs (Preview)

These CRDs become available when the `trainer` component is enabled in the DataScienceCluster. You will work with them in later lessons:

| CRD | API Group | Purpose |
|-----|-----------|---------|
| `TrainJob` | `kubeflow.org/v2alpha1` | Defines a single training job -- specifies model, dataset, hyperparameters, and references a runtime |
| `ClusterTrainingRuntime` | `kubeflow.org/v2alpha1` | Cluster-wide training runtime templates -- defines infrastructure (replicas, GPUs, containers) reusable across jobs |

These CRDs follow the same pattern as KServe's `InferenceService` and `ServingRuntime`: one CRD defines the infrastructure template, the other references it and adds job-specific parameters.

## Step-by-Step

This is a conceptual lesson -- no cluster is required. The steps below walk through the key decisions you will face when fine-tuning on OpenShift AI.

### Step 1: Choose Your Approach -- Fine-Tuning, RAG, or Prompt Engineering

Before writing any training code, decide whether fine-tuning is the right tool for your problem.

Consider a scenario: you have a customer support chatbot using Gemma 4B, and it does not follow your company's response format (greeting, summary, action items, closing).

- **Try prompt engineering first.** Add a system prompt with the format specification and a few examples. If the model follows the format consistently, you are done. Cost: zero GPU hours.
- **If prompt engineering is inconsistent,** the model "knows" the format from the prompt but drifts in longer conversations. This is a signal that fine-tuning can help -- the behavior needs to be baked into the weights, not just the context window.
- **If the model needs current data** (product catalog, knowledge base), use RAG. Fine-tuning is not the right tool for injecting facts that change.

### Step 2: Select the Fine-Tuning Method

Once you have decided to fine-tune, choose the method based on your GPU budget:

1. **Start with QLoRA** if you have limited GPU memory (under 16 GB). It lets you fine-tune models that would not otherwise fit.
2. **Use LoRA** if you have a 16+ GB GPU. It is faster than QLoRA (no quantization overhead) and produces slightly better results.
3. **Use full SFT** only if you have multiple high-end GPUs and need maximum quality. In most cases, LoRA produces results within 1-2% of full SFT at a fraction of the cost.
4. **Consider OSFT** if your fine-tuning dataset is narrow and you are concerned about catastrophic forgetting of the model's general capabilities.

### Step 3: Pick the Right OpenShift AI Tool

Match the tool to your stage:

| Stage | Tool | Why |
|-------|------|-----|
| Exploring / prototyping | Training Hub in a notebook | Fastest iteration, minimal setup |
| Single production job | Training Hub or TrainJob | Reproducible, can be scheduled |
| Recurring production training | TrainJob + KFP pipeline | Automated, version-tracked |
| Multi-node large model | Distributed TrainJob | PyTorch FSDP, multi-GPU |
| Knowledge injection | InstructLab | Taxonomy-driven, synthetic data |

For this tutorial's hands-on lesson (L1-M3.2), we will use Training Hub in a notebook to fine-tune Gemma with LoRA. This is the fastest path from zero to a fine-tuned model.

### Step 4: Understand the Data Requirements

Fine-tuning quality depends heavily on data. Regardless of method, you need:

- **Labeled examples** in the format your model should produce. For instruction-tuned models, this means prompt-response pairs.
- **Hundreds to low thousands** of examples for LoRA/QLoRA (not millions -- the base model already knows language).
- **Consistent quality** -- a small, high-quality dataset outperforms a large, noisy one.
- **Proper formatting** -- the data must match the model's chat template (e.g., Gemma's `<start_of_turn>` / `<end_of_turn>` tokens).

Common dataset formats:
```json
{"instruction": "Summarize this ticket", "input": "Customer reports...", "output": "Summary: ..."}
```

```json
{"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
```

HuggingFace Datasets is the standard way to load and prepare training data. Training Hub accepts HuggingFace dataset references directly.

## Key Takeaways

- Fine-tuning changes model weights to learn new behaviors; prompt engineering and RAG change what the model sees at inference time. Try the cheaper options first.
- LoRA and QLoRA make fine-tuning practical on limited hardware by training only small adapter matrices instead of the full model. QLoRA adds 4-bit quantization to reduce VRAM further.
- OpenShift AI offers three fine-tuning paths: Training Hub (notebook, Tier 3), Kubeflow Trainer v2 (CRD-based, Tier 1), and InstructLab (taxonomy-driven). Start with Training Hub and scale up as needed.
- Training Hub uses Unsloth under the hood, providing 2x speed and 70% memory savings for LoRA-based methods compared to standard implementations.
- The natural progression is: notebook prototyping with Training Hub, then single-node TrainJob, then distributed multi-GPU TrainJob, then automated pipelines.

## Cleanup

No resources to clean up -- this was a conceptual lesson.

## Next Steps

In the next lesson, [L1-M3.2 -- Training Hub LoRA](../2_training_hub_lora/), you will fine-tune Gemma using LoRA in an OpenShift AI notebook. You will prepare a dataset, run `lora_sft()` from Training Hub, and verify the adapter weights are produced -- all on a single GPU.
