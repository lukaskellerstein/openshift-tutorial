# L1-3.3 — Fine-Tuning with the ilab CLI

**Level:** Foundations
**Duration:** 45 min

## Overview

When the base Granite model needs domain-specific knowledge or capabilities, you can fine-tune it using InstructLab's taxonomy-driven workflow on RHEL AI. This lesson walks through the complete `ilab` fine-tuning pipeline: building a taxonomy, generating synthetic data, training the model, and evaluating results.

## Prerequisites

- Completed: [L1-3.2 — Serving and Chatting with RHEL AI](../2_serving_and_chatting/)
- RHEL AI instance with GPU (40+ GB VRAM recommended for fine-tuning)
- Model served and working from L1-3.2

## Concepts

### The InstructLab Workflow

InstructLab uses a five-stage pipeline to fine-tune models from minimal hand-written data:

```
taxonomy --> SDG --> train --> evaluate --> serve
```

1. **Taxonomy**: hierarchical YAML files encoding knowledge and skills. You define *what* the model should learn as structured seed examples.
2. **Synthetic Data Generation (SDG)**: a teacher model reads your taxonomy and generates hundreds or thousands of training examples automatically.
3. **Training**: multi-phase fine-tuning using the LAB (Large-scale Alignment for chatBots) method — knowledge tuning, skills tuning, then alignment.
4. **Evaluation**: benchmark the fine-tuned model against standard benchmarks (MMLU, MT-Bench) and compare with the base model.
5. **Serve**: deploy the fine-tuned model using the same `ilab model serve` workflow from L1-3.2.

### Knowledge vs Skills

Taxonomy contributions fall into two categories:

| Aspect | Knowledge | Skills |
|--------|-----------|--------|
| **Purpose** | Teach factual information | Teach behavioral capabilities |
| **Input** | `qna.yaml` with a `document` field pointing to source material | `qna.yaml` with a `task_description` field |
| **Example** | "OpenShift Routes support three TLS termination modes" | "Summarize a Kubernetes manifest in plain English" |
| **Seed examples** | Minimum 5 question-answer pairs grounded in the source document | Minimum 5 input-output demonstration pairs |

### Background Process Management

Long-running tasks like data generation and training can run in detached mode (Developer Preview):

- **`-dt` flag**: detach the process so it runs in the background
- **`ilab process list`**: list all background processes and their status
- **`ilab process attach --latest`**: reattach to the most recent background process

## Step-by-Step

### Step 1: Create a Taxonomy Directory

The taxonomy is a directory tree under `~/.local/share/instructlab/taxonomy/`. Knowledge contributions go under `taxonomy/knowledge/`, skills under `taxonomy/compositional_skills/`.

```bash
cd ~/.local/share/instructlab
mkdir -p taxonomy/knowledge/technology/cloud/openshift_routes
```

### Step 2: Write a Source Document

For knowledge contributions, create a markdown file containing the factual content you want the model to learn. Place it alongside the `qna.yaml`.

```bash
cat > taxonomy/knowledge/technology/cloud/openshift_routes/document.md << 'EOF'
# OpenShift Routes

OpenShift Routes expose Services to external traffic. Unlike Kubernetes
Ingress, Routes are a first-class OpenShift resource managed by the
built-in HAProxy-based router.

Routes support three TLS termination modes: edge (TLS terminates at
the router), passthrough (TLS passed directly to the pod), and
re-encrypt (TLS terminates at the router, new TLS connection to pod).

OpenShift supports wildcard routes using the *.example.com pattern,
useful for multi-tenant applications.
EOF
```

### Step 3: Write the qna.yaml File

The `qna.yaml` file defines seed examples that teach the model what to learn from the source document. You need at least 5 question-answer pairs.

```yaml
# taxonomy/knowledge/technology/cloud/openshift_routes/qna.yaml
created_by: tutorial-user
version: 3
domain: technology
seed_examples:
  - context: >
      OpenShift Routes expose Services to external traffic. Unlike
      Kubernetes Ingress, Routes are a first-class OpenShift resource
      managed by the built-in HAProxy-based router.
    question: What is the difference between OpenShift Routes and Kubernetes Ingress?
    answer: >
      OpenShift Routes are a first-class OpenShift resource that expose
      Services to external traffic, managed by a built-in HAProxy-based
      router. Kubernetes Ingress requires installing a separate ingress
      controller, while OpenShift's router is pre-installed.
  - context: >
      Edge: TLS terminates at the router. Traffic between the router
      and the pod is unencrypted. This is the simplest and most common mode.
    question: What happens to TLS traffic in edge termination mode?
    answer: >
      In edge termination mode, TLS terminates at the router. Traffic
      between the router and the backend pod is unencrypted. This is
      the simplest and most common TLS termination mode.
  - context: >
      Passthrough: TLS is passed directly to the pod. The pod must
      handle TLS termination itself.
    question: When should you use passthrough TLS termination?
    answer: >
      Use passthrough TLS termination when you need end-to-end encryption.
      In this mode, the router passes TLS traffic directly to the pod,
      and the pod must handle TLS termination itself.
  - context: >
      Re-encrypt: TLS terminates at the router, then a new TLS
      connection is established to the pod.
    question: How does re-encrypt TLS termination work?
    answer: >
      In re-encrypt mode, TLS terminates at the router, then a new TLS
      connection is established to the pod. This provides two separate
      TLS segments and is used when the pod has its own certificate but
      you also want the router to inspect traffic.
  - context: >
      OpenShift supports wildcard routes using the *.example.com pattern.
      Wildcard routes match any subdomain and are useful for multi-tenant
      applications.
    question: What are wildcard routes in OpenShift?
    answer: >
      Wildcard routes in OpenShift use the *.example.com pattern to match
      any subdomain. They are useful for multi-tenant applications where
      each tenant gets a unique subdomain under the same domain.
document:
  repo: https://github.com/your-org/your-taxonomy-repo
  commit: abc123
  patterns:
    - document.md
```

### Step 4: Validate the Taxonomy

Before generating data, verify the taxonomy is well-formed:

```bash
ilab taxonomy diff
```

Expected output:

```
Taxonomy in /home/user/.local/share/instructlab/taxonomy/ is valid :)
---
knowledge/technology/cloud/openshift_routes/qna.yaml
  Additions:
    - openshift_routes
```

If validation fails, check for YAML syntax errors and ensure you have at least 5 seed examples.

### Step 5: Generate Synthetic Data

Use the teacher model to generate training examples from your taxonomy:

```bash
# Quick generation for testing (simple pipeline, fewer examples)
ilab data generate --pipeline simple --num-instructions 100

# Full generation for production fine-tuning
ilab data generate --pipeline full --num-instructions 250
```

For long-running generation, use detached mode:

```bash
ilab data generate --pipeline full --num-instructions 250 -dt
ilab process list
ilab process attach --latest
```

Generated data is saved to `~/.local/share/instructlab/datasets/`.

### Step 6: Review Generated Data

Inspect the quality of generated examples before training:

```python
import json, glob

files = sorted(glob.glob("/home/user/.local/share/instructlab/datasets/*.jsonl"))
with open(files[-1]) as f:
    for i, line in enumerate(f):
        if i >= 5:
            break
        ex = json.loads(line)
        print(f"Q: {ex.get('instruction', '')[:100]}")
        print(f"A: {ex.get('output', '')[:100]}\n")
```

Look for: accurate answers, diverse question phrasing, no hallucinated facts. If quality is poor, improve your seed examples and regenerate.

### Step 7: Train the Model

Run multi-phase training on the generated data:

```bash
ilab model train
```

Training runs three phases:

1. **Knowledge tuning**: the model learns factual content from knowledge contributions
2. **Skills tuning**: the model learns behavioral patterns from skill contributions
3. **Alignment**: final alignment pass to maintain helpfulness and safety

Expect 30 minutes to several hours depending on hardware and dataset size. The trained model is saved to `~/.local/share/instructlab/checkpoints/`.

### Step 8: Evaluate the Model

Benchmark the fine-tuned model against standard benchmarks:

```bash
# General knowledge benchmark
ilab model evaluate --benchmark mmlu

# Multi-turn conversation quality
ilab model evaluate --benchmark mt_bench
```

Compare scores against the base model to verify improvement in your target domain without regression in general capabilities.

### Step 9: Serve and Test the Fine-Tuned Model

Serve the fine-tuned model and verify it learned your domain knowledge:

```bash
ls ~/.local/share/instructlab/checkpoints/
ilab model serve --model-path ~/.local/share/instructlab/checkpoints/<your-model>
ilab model chat --model <your-model>
```

Test with domain questions like "What TLS termination modes does an OpenShift Route support?" The fine-tuned model should answer accurately based on your taxonomy, while the base model would give generic or incomplete answers.

## LAB-Tuning vs LoRA/QLoRA

| Aspect | LAB (InstructLab) | LoRA / QLoRA |
|--------|-------------------|--------------|
| **Data source** | Generates its own data from taxonomy | Requires an existing dataset |
| **Data effort** | Write 5+ seed examples, SDG does the rest | Curate hundreds/thousands of examples |
| **Tuning method** | Full fine-tuning (multi-phase) | Parameter-efficient (adapter weights only) |
| **VRAM requirement** | Higher (full model weights) | Lower (only adapter weights in memory) |
| **Best for** | Adding domain knowledge with minimal data | Adapting behavior with existing datasets |
| **Output** | Complete fine-tuned model | Adapter weights (merged or separate) |

In Level 2 ([L2-2.1](../../../level_2/M2_model_customization/1_modular_customization/)), you will use the modular Python libraries (SDG Hub, Training Hub) for LoRA/QLoRA and more granular control over each step of the pipeline.

## Verification

| Check | Command | Expected Result |
|-------|---------|-----------------|
| Taxonomy valid | `ilab taxonomy diff` | "Taxonomy is valid" with your additions listed |
| Data generated | `ls ~/.local/share/instructlab/datasets/` | New `.jsonl` file with generated examples |
| Model trained | `ls ~/.local/share/instructlab/checkpoints/` | New model checkpoint directory |
| Evaluation ran | `ilab model evaluate --benchmark mmlu` | Scores printed, comparable to base model |
| Fine-tuned model responds | `ilab model chat --model <your-model>` | Accurate answers to domain-specific questions |

## Key Takeaways

- InstructLab's workflow (taxonomy, SDG, train, evaluate) lets you fine-tune with minimal hand-written data -- just 5+ seed examples per topic.
- Knowledge contributions need source documents; skill contributions need demonstration examples.
- The `-dt` detach flag and `ilab process list/attach` help manage long-running generation and training tasks.
- Always evaluate after training to check for improvement in your domain without regression in general capabilities.
- In Level 2, you will use the modular Python libraries (Docling, SDG Hub, Training Hub) for more control over each step.

## Cleanup

```bash
# Remove generated datasets (optional, to free disk space)
rm -rf ~/.local/share/instructlab/datasets/*

# Remove trained checkpoints (if you don't need them)
rm -rf ~/.local/share/instructlab/checkpoints/*

# Remove taxonomy additions
rm -rf ~/.local/share/instructlab/taxonomy/knowledge/technology/cloud/openshift_routes
```

## Next Steps

Continue to [L1-4.1 — From RHEL AI to OpenShift AI](../../M4_scaling_to_openshift_ai/1_from_rhel_ai_to_openshift_ai/) to learn when and how to scale from a single RHEL AI server to the OpenShift AI platform.
