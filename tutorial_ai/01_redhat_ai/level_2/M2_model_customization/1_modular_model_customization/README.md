# L2-2.1 — Modular Model Customization: Docling, SDG Hub, and Training Hub

**Level:** Practitioner
**Duration:** 1 hour

## Overview

In Level 1 you used the `ilab` CLI for a guided, end-to-end model customization workflow: create a taxonomy, generate synthetic data, train, evaluate. That CLI wraps everything into a single tool, which is great for getting started but limits your control over each step.

This lesson introduces the modular Python libraries that replaced the InstructLab monolith. You will use **Docling** for document processing, **SDG Hub** for synthetic data generation pipelines, and **Training Hub** for fine-tuning -- each as a standalone, composable library that you can integrate into Jupyter notebooks, CI/CD pipelines, and production workflows.

## Prerequisites

- Completed Level 1 (L1-M3 especially -- you understand the `ilab` CLI workflow)
- RHEL AI instance with GPU access, or a Python 3.10+ environment with pip access
- Jupyter notebook environment (optional but recommended for interactive exploration)
- A vLLM-compatible model available for teacher inference (SDG Hub step)

## Concepts

### The Evolution: ilab CLI to Modular Libraries

InstructLab's upstream GitHub repository was archived in April 2026. The functionality it provided -- document processing, synthetic data generation, and model training -- was broken into modular, composable Python libraries maintained by the Red Hat AI Innovation Team.

The `ilab` CLI still ships with RHEL AI as the getting-started interface. Under the hood, it now delegates to these same libraries. The difference is control: the CLI makes decisions for you (pipeline configuration, teacher model selection, training hyperparameters), while the libraries expose every knob.

**When to use the ilab CLI:**
- Quick exploration and one-off customization
- Getting started with model adaptation
- Following the guided workflow without needing to tune parameters

**When to use the Python libraries:**
- Production customization pipelines
- CI/CD integration (Tekton, GitHub Actions)
- Custom workflows in Jupyter notebooks
- Fine-grained control over each step (document chunking strategy, SDG pipeline composition, training hyperparameters)

### Docling

[Docling](https://github.com/docling-project/docling) is a document intelligence library that converts enterprise documents into structured data. It handles PDFs, HTML, images, DOCX, and other formats, extracting text, tables, and figures with layout awareness.

```bash
pip install docling
```

In the `ilab` CLI workflow, you manually wrote a Markdown source document for your taxonomy. Docling automates this: point it at your existing PDFs, product manuals, or internal documentation, and it produces clean Markdown or structured JSON ready for downstream processing.

**Cross-reference:** The OpenShift AI tutorial covers Docling in RAG pipelines (L2-1.3), where it preprocesses documents for vector embedding. Here we use it to prepare source material for synthetic data generation.

### SDG Hub

[SDG Hub](https://github.com/Red-Hat-AI-Innovation-Team/sdg_hub) provides modular synthetic data generation using composable "blocks" and "flows."

```bash
pip install sdg-hub
# Optional extras:
pip install sdg-hub[vllm]       # vLLM integration for teacher models
pip install sdg-hub[examples]   # Example pipelines and notebooks
```

SDG Hub requires Python 3.10+ and was published on PyPI in January 2026.

Key concepts:
- **Blocks** are individual SDG operations: generation, filtering, deduplication, validation, formatting.
- **Flows** are pipelines that chain blocks together. A flow defines the full journey from seed examples to a training-ready dataset.
- **Teacher models**: any vLLM-compatible model can serve as the teacher that generates synthetic data from your seed examples.

This replaces the `ilab data generate` command, giving you control over every stage of the pipeline.

### Training Hub

[Training Hub](https://github.com/Red-Hat-AI-Innovation-Team/training_hub) simplifies fine-tuning of foundation models with support for multiple training strategies.

```bash
pip install training-hub
# Optional extras:
pip install training-hub[cuda]   # CUDA support for GPU training
pip install training-hub[grpo]   # Group Relative Policy Optimization
```

**Important:** When combining `[grpo]` with `[cuda]`, install them sequentially to avoid dependency conflicts. Install `[cuda]` first with `--no-build-isolation`, then install `[grpo]`.

Supported training methods:
- **SFT** (Supervised Fine-Tuning) -- full-parameter training on your synthetic dataset
- **LoRA/QLoRA** via Unsloth -- parameter-efficient fine-tuning with reduced VRAM requirements
- **Continual learning** -- incrementally train on new data without catastrophic forgetting

This replaces `ilab model train`, giving you direct control over training configuration, hyperparameters, and the training loop.

**Cross-reference:** The OpenShift AI tutorial covers Training Hub running on OpenShift AI with Kubernetes-native training jobs (L1-M3).

### Red Hat AI Python Index

Red Hat provides an enterprise-grade Python package index with hardened, tested versions of these libraries built with Fromager. The index is:

- Pre-configured in OpenShift AI workbench base images (no setup needed there)
- Available to RHEL AI and standalone environments via `pip install --index-url`
- Documented at [access.redhat.com/articles/7137881](https://access.redhat.com/articles/7137881) (requires Red Hat Customer Portal access)

For this lesson, installing from PyPI is sufficient. In production, use the Red Hat AI Python Index for version compatibility guarantees and security patches.

## Step-by-Step

### Step 1: Install the Libraries

```bash
pip install docling sdg-hub training-hub
```

For GPU training, install CUDA support separately:

```bash
pip install training-hub[cuda] --no-build-isolation
```

Verify the installation:

```python
import docling
import sdg_hub
import training_hub

print(f"Docling: {docling.__version__}")
print(f"SDG Hub: {sdg_hub.__version__}")
print(f"Training Hub: {training_hub.__version__}")
```

### Step 2: Process Documents with Docling

Convert a source document (PDF, HTML, or DOCX) into structured data that can feed SDG.

```python
from docling.document_converter import DocumentConverter

converter = DocumentConverter()

# Convert a PDF — replace with your actual document path
result = converter.convert("product-manual.pdf")

# Export as Markdown (clean, structured text)
markdown_output = result.document.export_to_markdown()
print(markdown_output[:500])

# Export as structured dictionary (preserves tables, headings, sections)
structured_doc = result.document.export_to_dict()
print(f"Document has {len(structured_doc.get('texts', []))} text elements")
```

For batch processing of multiple documents:

```python
source_docs = ["manual-v1.pdf", "faq.html", "release-notes.pdf"]

processed_docs = []
for doc_path in source_docs:
    result = converter.convert(doc_path)
    processed_docs.append({
        "source": doc_path,
        "markdown": result.document.export_to_markdown(),
        "structured": result.document.export_to_dict()
    })

print(f"Processed {len(processed_docs)} documents")
```

Docling handles the heavy lifting that you would otherwise do manually: extracting text from complex layouts, parsing tables into structured data, and producing clean Markdown from messy enterprise documents.

### Step 3: Build an SDG Pipeline with SDG Hub

Use the processed documents to generate synthetic training data. SDG Hub organizes this into blocks (individual operations) and flows (pipelines of blocks).

```python
from sdg_hub.blocks import GenerateBlock, FilterBlock
from sdg_hub.flows import Flow

# Define seed examples grounded in your processed documents
seed_examples = [
    {
        "question": "What networking model does OpenShift use?",
        "answer": "OpenShift uses software-defined networking based on OVN-Kubernetes.",
        "context": markdown_output[:1000]  # From Docling output
    },
    # Add at least 4 more seed examples...
]

# Create an SDG flow with generation and filtering blocks
generate_block = GenerateBlock(
    model="granite-3.1-8b-instruct",  # Teacher model
    num_samples=100
)

filter_block = FilterBlock(
    min_quality_score=0.7
)

flow = Flow(blocks=[generate_block, filter_block])

# Run the pipeline
synthetic_dataset = flow.run(seed_examples)
print(f"Generated {len(synthetic_dataset)} synthetic examples")
```

**Note:** SDG Hub's API is evolving. Check the [SDG Hub GitHub repository](https://github.com/Red-Hat-AI-Innovation-Team/sdg_hub) for the latest block types, flow configuration options, and example notebooks. The `[examples]` extra installs reference pipelines you can adapt.

Review a sample of the generated data before proceeding to training:

```python
for i, example in enumerate(synthetic_dataset[:3]):
    print(f"--- Example {i+1} ---")
    print(f"Q: {example.get('question', 'N/A')[:200]}")
    print(f"A: {example.get('answer', 'N/A')[:200]}")
    print()
```

Look for diversity (varied question phrasing), accuracy (answers grounded in your source documents), and relevance (stays on topic). If quality is poor, improve your seed examples or adjust the filter block threshold.

### Step 4: Fine-Tune with Training Hub

Use the synthetic dataset from Step 3 to fine-tune a Granite model.

```python
from training_hub import TrainingConfig, Trainer

# Configure SFT (Supervised Fine-Tuning)
config = TrainingConfig(
    model_name="ibm-granite/granite-3.1-8b-instruct",
    training_method="sft",
    dataset=synthetic_dataset,        # From SDG Hub output
    output_dir="./fine-tuned-model",
    num_epochs=3,
    batch_size=4,
    learning_rate=2e-5
)

trainer = Trainer(config)
trainer.train()
```

For parameter-efficient fine-tuning with LoRA (requires less VRAM):

```python
config = TrainingConfig(
    model_name="ibm-granite/granite-3.1-8b-instruct",
    training_method="lora",
    dataset=synthetic_dataset,
    output_dir="./fine-tuned-model-lora",
    lora_rank=16,
    lora_alpha=32,
    num_epochs=3
)

trainer = Trainer(config)
trainer.train()
```

**Note:** Training Hub's configuration API may evolve. Check the [Training Hub GitHub repository](https://github.com/Red-Hat-AI-Innovation-Team/training_hub) for the current `TrainingConfig` parameters and supported training methods.

### Step 5: End-to-End Pipeline

Here is the complete flow connecting all three libraries. This is the pattern you would use in a Jupyter notebook or a CI/CD pipeline.

```python
from docling.document_converter import DocumentConverter
from sdg_hub.blocks import GenerateBlock, FilterBlock
from sdg_hub.flows import Flow
from training_hub import TrainingConfig, Trainer

# 1. Document processing
converter = DocumentConverter()
result = converter.convert("domain-knowledge.pdf")
source_text = result.document.export_to_markdown()

# 2. Prepare seed examples from the processed document
seed_examples = [
    {"question": "...", "answer": "...", "context": source_text[:1000]},
    # ... more seed examples grounded in the document
]

# 3. Synthetic data generation
flow = Flow(blocks=[
    GenerateBlock(model="granite-3.1-8b-instruct", num_samples=200),
    FilterBlock(min_quality_score=0.7)
])
synthetic_data = flow.run(seed_examples)
print(f"Generated {len(synthetic_data)} training examples from {len(seed_examples)} seeds")

# 4. Fine-tuning
config = TrainingConfig(
    model_name="ibm-granite/granite-3.1-8b-instruct",
    training_method="sft",
    dataset=synthetic_data,
    output_dir="./customized-model",
    num_epochs=3
)
trainer = Trainer(config)
trainer.train()

print("Pipeline complete: document -> synthetic data -> fine-tuned model")
```

Compare this with the `ilab` CLI equivalent:

| Step | ilab CLI | Python Libraries |
|------|----------|-----------------|
| Document processing | Manual Markdown file | `docling.DocumentConverter` |
| Seed examples | `qna.yaml` in taxonomy directory | Python data structures |
| Synthetic data generation | `ilab data generate` | `sdg_hub.flows.Flow` with configurable blocks |
| Training | `ilab model train` | `training_hub.Trainer` with explicit config |
| Control level | Preset pipelines, limited parameters | Full control over every step |

## Verification

Your lesson is complete when:

1. **Libraries installed successfully:**
   ```bash
   pip list | grep -E "docling|sdg-hub|training-hub"
   ```

2. **Docling processed a document:**
   - Markdown or JSON output produced from a source document
   - Text, tables, and structure extracted correctly

3. **SDG Hub generated synthetic data:**
   - Training examples generated from seed examples
   - Quality filtering applied, poor examples removed

4. **Training Hub ran fine-tuning** (requires GPU):
   - Fine-tuned model saved to output directory
   - Training loss decreased across epochs

5. **End-to-end pipeline runs without errors** in a notebook or script

## Key Takeaways

- The `ilab` CLI is the getting-started interface, but production model customization uses the modular Python libraries: **Docling** (document processing), **SDG Hub** (synthetic data pipelines), and **Training Hub** (fine-tuning).
- **Docling** automates document intelligence -- converting PDFs, HTML, and other formats into clean structured data -- replacing the manual Markdown authoring step from the `ilab` workflow.
- **SDG Hub** provides composable blocks and flows for synthetic data generation, giving you control over teacher model selection, generation parameters, and quality filtering.
- **Training Hub** supports SFT, LoRA/QLoRA (via Unsloth), and continual learning, letting you choose the right training strategy for your VRAM budget and use case.
- All three libraries can run locally on RHEL AI or at scale on OpenShift AI. The OpenShift AI tutorial covers Training Hub on Kubernetes (L1-M3) and Docling in RAG pipelines (L2-1.3).
- These libraries are actively evolving. Always check the GitHub repositories for the latest API details and example notebooks.

## Cleanup

If you installed the libraries in a virtual environment:

```bash
deactivate
rm -rf ./venv
```

Remove any generated artifacts:

```bash
rm -rf ./fine-tuned-model ./fine-tuned-model-lora ./customized-model
```

## Next Steps

Continue to [L2-2.2 — Model Optimization for Production](../2_model_optimization/) to learn how to reduce model size and inference cost using the Red Hat AI Model Optimization Toolkit (LLM Compressor) with quantization, sparsity, and speculative decoding.
