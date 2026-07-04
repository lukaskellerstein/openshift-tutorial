# L3-M4.1 -- InstructLab on OpenShift AI

**Level:** Expert
**Duration:** 1.5 hours

## Overview

In [L1-M3.2](../../../level_1/M3_fine_tuning/2_training_hub_lora/) you fine-tuned a model using Training Hub's `lora_sft()` -- you curated a dataset, called one function, and got adapter weights. That workflow assumes you already have a high-quality training dataset. InstructLab takes a different approach: instead of curating data manually, you define a **taxonomy** of knowledge and skills, a teacher model generates synthetic training data from that taxonomy, and a multi-phase training process (the LAB methodology) fine-tunes the student model.

The original `instructlab` CLI repository was archived in early 2026 and its components were refactored into two pieces that ship with OpenShift AI: **SDG Hub** (synthetic data generation) and **Training Hub** (the `trainer` DSC component). The LAB methodology -- Large-scale Alignment for chatBots -- remains available on OpenShift AI as a **Technology Preview**. This lesson walks through the end-to-end LAB-tuning workflow: taxonomy definition, synthetic data generation, multi-phase training, and evaluation.

LAB-tuning is not a replacement for standard LoRA fine-tuning. It is a complementary approach suited to scenarios where you need to inject broad domain knowledge or teach new reasoning patterns, and you do not have a curated dataset to start from.

## Prerequisites

- Completed: [L1-M3.1 -- Fine-Tuning Concepts](../../../level_1/M3_fine_tuning/1_fine_tuning_concepts/) (LoRA, QLoRA, full fine-tuning theory)
- Completed: [L1-M3.2 -- Training Hub LoRA](../../../level_1/M3_fine_tuning/2_training_hub_lora/) (hands-on LoRA fine-tuning)
- Completed: [L1-M3.3 -- Deploying Fine-Tuned Models](../../../level_1/M3_fine_tuning/3_deploying_fine_tuned/) (serving adapter weights)
- OpenShift AI cluster with the `trainer` DSC component enabled (Technology Preview)
- GPU access: at least one NVIDIA GPU with 16+ GB VRAM (teacher + student models must fit in memory during SDG)
- A running workbench with CUDA support
- Hugging Face token with access to the base model (e.g., `google/gemma-4-E4B-it`)
- Data Science Pipelines (DSPA) configured in your project (see [L2-M4.1](../../../level_2/M4_pipelines/1_pipeline_setup/))

## Concepts

### What Is the LAB Methodology?

LAB (Large-scale Alignment for chatBots) is a fine-tuning methodology developed by IBM Research and adopted by the InstructLab project. The core idea is that humans are better at writing **facts and specifications** than they are at writing **training examples**. Instead of asking subject-matter experts to create hundreds of question-answer pairs, you ask them to write taxonomy entries -- structured descriptions of what the model should know or be able to do -- and let a teacher model generate the training data.

The LAB workflow has four stages:

```
Taxonomy          SDG              Multi-Phase          Evaluation
Definition   -->  (Synthetic Data  -->  Training    -->  (vs. base
(human)           Generation)           (knowledge       model)
                  (teacher model)       then skills)
```

This contrasts with standard LoRA fine-tuning where the workflow is:

```
Dataset           Single-Phase         Evaluation
Curation     -->  Training        -->  (vs. base
(human)           (LoRA SFT)           model)
```

The LAB approach shifts the human effort from **data curation** to **taxonomy design**, and compensates with automated data generation and multi-phase training.

### Taxonomy Structure

A taxonomy is a YAML file that organizes what the model should learn into two categories:

**Knowledge entries** teach the model facts. Each entry includes:
- A domain and topic identifier
- Seed examples: a few question-answer pairs that demonstrate the kind of knowledge
- Context: a passage of text containing the facts (optional but improves SDG quality)

**Skill entries** teach the model reasoning patterns or output formats. Each entry includes:
- A domain and topic identifier
- Seed examples: input-output pairs that demonstrate the skill
- No context block -- skills are about patterns, not facts

The teacher model uses seed examples as a template. If you provide three seed examples about product documentation, the teacher generates dozens or hundreds of similar examples, varying the questions and extracting different facts from the context.

### Synthetic Data Generation (SDG)

SDG is the process where a large teacher model reads your taxonomy entries and generates synthetic training data. The teacher model (typically a larger, more capable model than the student being fine-tuned) does the following:

1. Reads each taxonomy entry's seed examples
2. Generates new question-answer pairs that follow the same pattern
3. For knowledge entries: extracts facts from the context and creates diverse questions
4. For skill entries: creates new inputs and generates outputs following the demonstrated pattern
5. Applies filtering to remove low-quality or duplicate examples

The output is a JSONL dataset in the messages format, ready for training.

SDG quality depends on two factors:
- **Taxonomy quality**: Well-written seed examples with diverse question styles produce better synthetic data. Three to five seed examples per entry is the recommended range.
- **Teacher model capability**: Larger teacher models generate higher-quality synthetic data. Using a 70B+ parameter teacher for SDG that trains a 4B student is a common configuration.

### Multi-Phase Training

Unlike standard LoRA fine-tuning (single pass over the dataset), LAB-tuning runs in two phases:

**Phase 1 -- Knowledge tuning:** The student model is fine-tuned on the knowledge portion of the synthetic data. This injects factual information from the taxonomy's knowledge entries.

**Phase 2 -- Skills tuning:** The knowledge-tuned model is then fine-tuned on the skills portion. This teaches the model how to reason about and present the knowledge in the formats defined by the skill entries.

The rationale for two phases is that knowledge and skills interact: the model first needs to internalize the facts before it can learn to reason about them in structured ways. Training both simultaneously can lead to interference where the model learns the output format but fills it with hallucinated facts.

### Architecture: InstructLab Components on OpenShift AI

```
+------------------------------------------------------------------+
|                    OpenShift AI Cluster                           |
|                                                                  |
|  +-------------------+    +-------------------+                  |
|  |    SDG Hub         |    |   Training Hub    |                  |
|  |    (Tier 3 lib)    |    |   (Tier 3 lib /   |                  |
|  |                    |    |    trainer DSC)    |                  |
|  |  - Load taxonomy   |    |                   |                  |
|  |  - Connect to      |    |  - Knowledge      |                  |
|  |    teacher model   |    |    tuning phase   |                  |
|  |  - Generate        |    |  - Skills tuning  |                  |
|  |    synthetic data  |    |    phase          |                  |
|  +--------+-----------+    +--------+----------+                  |
|           |                         |                             |
|           v                         v                             |
|  +-------------------+    +-------------------+                  |
|  |  Teacher Model     |    |  Student Model    |                  |
|  |  (vLLM endpoint)   |    |  (base weights +  |                  |
|  |  e.g. 70B+         |    |   LoRA adapters)  |                  |
|  +-------------------+    +-------------------+                  |
|                                                                  |
|  +------------------------------------------------------+       |
|  |         Data Science Pipeline (KFP v2)                |       |
|  |  taxonomy --> SDG --> knowledge tune --> skill tune    |       |
|  |    --> evaluate --> register model                     |       |
|  +------------------------------------------------------+       |
|                                                                  |
|  +-------------------+    +-------------------+                  |
|  |  Model Registry    |    |  S3 / PVC Storage |                  |
|  |  (versioned        |    |  (taxonomy, SDG   |                  |
|  |   model tracking)  |    |   data, weights)  |                  |
|  +-------------------+    +-------------------+                  |
+------------------------------------------------------------------+
```

### InstructLab, SDG Hub, Training Hub: How They Relate

| Component | Role | Status |
|-----------|------|--------|
| `instructlab` CLI | Original all-in-one tool for taxonomy, SDG, training, and serving | Archived (2026) |
| SDG Hub | Tier 3 Python library for synthetic data generation from taxonomy | Available on OpenShift AI |
| Training Hub | Tier 3 Python library for LoRA/QLoRA/LAB fine-tuning | Available on OpenShift AI |
| `trainer` DSC component | Tier 1 DSC component managing distributed training jobs via CRDs | Technology Preview |
| `ilab-on-ocp` | Community project for deploying InstructLab workflow on OpenShift | Reference architecture |

In practice, you use SDG Hub and Training Hub as Python libraries inside a workbench or pipeline step. The `trainer` DSC component is relevant for distributed multi-GPU training at scale (beyond this lesson's scope).

## Step-by-Step

### Step 1: Verify Prerequisites

Confirm that the `trainer` DSC component is enabled and that your project has a GPU-enabled workbench.

```bash
# Check the DataScienceCluster for trainer component status
oc get datasciencecluster default-dsc -o jsonpath='{.spec.components.trainer.managementState}'
```

Expected output:

```
Managed
```

If the output is `Removed`, the trainer component is not enabled. Ask your cluster administrator to enable it, or enable it yourself if you have admin access:

```bash
oc patch datasciencecluster default-dsc --type merge \
  -p '{"spec":{"components":{"trainer":{"managementState":"Managed"}}}}'
```

Expected output:

```
datasciencecluster.datasciencecluster.opendatahub.io/default-dsc patched
```

Verify your workbench is running with GPU access:

```bash
oc get notebook -n <your-project>
```

Expected output:

```
NAME              AGE   STATUS
my-workbench      5d    Running
```

```bash
# Confirm the workbench pod has a GPU allocated
oc get pod -l app=<your-workbench-name> -n <your-project> \
  -o jsonpath='{.items[0].spec.containers[0].resources.limits}'
```

Expected output:

```
{"cpu":"4","memory":"16Gi","nvidia.com/gpu":"1"}
```

### Step 2: Install SDG Hub and Training Hub

Open a terminal in your workbench and install both libraries:

```bash
pip install sdg-hub training-hub[lora]
```

Expected output:

```
Successfully installed sdg-hub-x.x.x training-hub-x.x.x ...
```

Verify the installation:

```python
from sdg_hub import TaxonomyLoader, SDGPipeline
from training_hub import lora_sft
print("SDG Hub and Training Hub installed successfully")
```

Expected output:

```
SDG Hub and Training Hub installed successfully
```

### Step 3: Create the Taxonomy

The taxonomy is the human-authored input to the LAB workflow. You define what the model should know (knowledge) and what it should be able to do (skills). See `scripts/taxonomy_example.yaml` for the full file.

Create the taxonomy file in your workbench:

```python
import yaml
import os

# Load the taxonomy from the lesson's scripts directory,
# or create it inline. Here we show the inline version.

taxonomy = {
    "version": 3,
    "created_by": "tutorial-user",
    "domain": "e-commerce",
    "document_outline": "Product catalog and analytics knowledge for Acme Corp's ShopInsights platform.",
    "seed_examples": [],
    "knowledge": [
        {
            "task_description": "Answer questions about Acme Corp product catalog and policies.",
            "domain": "e-commerce",
            "topic": "acme_corp_products",
            "created_by": "tutorial-user",
            "context": (
                "Acme Corp is an e-commerce company specializing in outdoor equipment. "
                "Their flagship products include the TrailBlazer 3000 hiking boot (SKU: TB-3000, "
                "price: $189.99, waterproof rating: IPX7, available sizes: 6-14 US), the "
                "SummitPack 45L backpack (SKU: SP-45L, price: $249.99, weight: 1.2kg, "
                "capacity: 45 liters, material: ripstop nylon), and the AlpineShield rain "
                "jacket (SKU: AS-RJ, price: $159.99, waterproof rating: 20,000mm, breathability: "
                "15,000g/m2/24h). Acme Corp offers free shipping on orders over $100, a 30-day "
                "return policy with free return labels, and a lifetime warranty on all hiking "
                "boots. Their loyalty program, Peak Rewards, gives 1 point per dollar spent, "
                "with 500 points redeemable for a $25 discount."
            ),
            "seed_examples": [
                {
                    "question": "What is the price of the TrailBlazer 3000?",
                    "answer": (
                        "The TrailBlazer 3000 hiking boot (SKU: TB-3000) is priced at $189.99. "
                        "It features an IPX7 waterproof rating and is available in US sizes 6-14. "
                        "Acme Corp offers a lifetime warranty on all hiking boots."
                    ),
                },
                {
                    "question": "What is Acme Corp's return policy?",
                    "answer": (
                        "Acme Corp offers a 30-day return policy with free return shipping labels. "
                        "Products must be in their original condition. For hiking boots specifically, "
                        "Acme Corp also provides a lifetime warranty covering manufacturing defects."
                    ),
                },
                {
                    "question": "How does the Peak Rewards loyalty program work?",
                    "answer": (
                        "Peak Rewards is Acme Corp's loyalty program. Members earn 1 point per "
                        "dollar spent on any purchase. Points can be redeemed at a rate of 500 "
                        "points for a $25 discount on future orders. Combined with free shipping "
                        "on orders over $100, this provides significant savings for repeat customers."
                    ),
                },
            ],
        }
    ],
    "skills": [
        {
            "task_description": "Generate structured product comparison tables for e-commerce items.",
            "domain": "e-commerce",
            "topic": "product_comparison",
            "created_by": "tutorial-user",
            "seed_examples": [
                {
                    "question": "Compare the TrailBlazer 3000 and SummitPack 45L.",
                    "answer": (
                        "| Feature | TrailBlazer 3000 | SummitPack 45L |\n"
                        "|---------|------------------|----------------|\n"
                        "| Category | Hiking Boot | Backpack |\n"
                        "| Price | $189.99 | $249.99 |\n"
                        "| SKU | TB-3000 | SP-45L |\n"
                        "| Key Spec | IPX7 waterproof | 45L capacity |\n"
                        "| Weight | N/A | 1.2kg |\n"
                        "| Warranty | Lifetime | Standard 30-day |"
                    ),
                },
                {
                    "question": "Create a comparison between the AlpineShield rain jacket and a competitor's jacket priced at $199.99 with a 15,000mm waterproof rating.",
                    "answer": (
                        "| Feature | AlpineShield | Competitor |\n"
                        "|---------|-------------|------------|\n"
                        "| Price | $159.99 | $199.99 |\n"
                        "| Waterproof Rating | 20,000mm | 15,000mm |\n"
                        "| Breathability | 15,000g/m2/24h | Not specified |\n"
                        "| Return Policy | 30-day free returns | Varies |\n"
                        "| Value | Better specs, lower price | Higher price |"
                    ),
                },
                {
                    "question": "Summarize the outdoor equipment product line in a table.",
                    "answer": (
                        "| Product | SKU | Price | Category | Key Feature |\n"
                        "|---------|-----|-------|----------|-------------|\n"
                        "| TrailBlazer 3000 | TB-3000 | $189.99 | Footwear | IPX7 waterproof |\n"
                        "| SummitPack 45L | SP-45L | $249.99 | Bags | 45L, 1.2kg |\n"
                        "| AlpineShield RJ | AS-RJ | $159.99 | Jackets | 20,000mm waterproof |"
                    ),
                },
            ],
        }
    ],
}

# Save taxonomy
taxonomy_dir = "/opt/app-root/src/lab-tuning"
os.makedirs(taxonomy_dir, exist_ok=True)
taxonomy_path = os.path.join(taxonomy_dir, "taxonomy.yaml")

with open(taxonomy_path, "w") as f:
    yaml.dump(taxonomy, f, default_flow_style=False, sort_keys=False, width=120)

print(f"Taxonomy saved to {taxonomy_path}")
print(f"Knowledge entries: {len(taxonomy['knowledge'])}")
print(f"Skill entries: {len(taxonomy['skills'])}")
```

Expected output:

```
Taxonomy saved to /opt/app-root/src/lab-tuning/taxonomy.yaml
Knowledge entries: 1
Skill entries: 1
```

**Taxonomy design guidelines for production:**

| Guideline | Recommendation |
|-----------|---------------|
| Seed examples per entry | 3-5 (fewer gives the teacher too little signal; more is diminishing returns) |
| Context length | 200-1000 words per knowledge entry (enough facts for diverse questions) |
| Skill diversity | Each seed example should demonstrate a different variation of the skill |
| Topic granularity | One entry per narrow topic (not "everything about products") |
| Entries per taxonomy | 5-50 for a focused domain; 50+ for broad knowledge injection |

### Step 4: Generate Synthetic Data (SDG)

SDG uses a teacher model to generate training examples from your taxonomy. The teacher model must be accessible via an OpenAI-compatible API endpoint -- typically a large model served via vLLM on your cluster.

First, confirm you have a teacher model endpoint. If you deployed a model in [L1-M2.2](../../../level_1/M2_model_serving/2_deploying_gemma/), you can use that endpoint, or any vLLM-served model accessible from the workbench.

```bash
# Find the model serving endpoint in your namespace
oc get inferenceservice -n <your-project> -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.url}{"\n"}{end}'
```

Expected output:

```
gemma-4-e4b    https://gemma-4-e4b-your-project.apps.cluster.example.com
```

Run SDG using the script at `scripts/generate_sdg.py`, or execute inline:

```python
import json
import os
import yaml
from openai import OpenAI

# Configuration
TAXONOMY_PATH = "/opt/app-root/src/lab-tuning/taxonomy.yaml"
OUTPUT_PATH = "/opt/app-root/src/lab-tuning/sdg_output.jsonl"
TEACHER_ENDPOINT = os.environ.get(
    "TEACHER_ENDPOINT",
    "https://gemma-4-e4b-your-project.apps.cluster.example.com/v1"
)
TEACHER_MODEL = os.environ.get("TEACHER_MODEL", "gemma-4-e4b")
NUM_EXAMPLES_PER_SEED = 5  # How many synthetic examples to generate per seed

# Load taxonomy
with open(TAXONOMY_PATH) as f:
    taxonomy = yaml.safe_load(f)

client = OpenAI(base_url=TEACHER_ENDPOINT, api_key="unused")

generated = []

# Generate from knowledge entries
for entry in taxonomy.get("knowledge", []):
    context = entry.get("context", "")
    for seed in entry["seed_examples"]:
        prompt = (
            f"You are a training data generator. Given this context:\n\n"
            f"{context}\n\n"
            f"And this example question-answer pair:\n"
            f"Q: {seed['question']}\n"
            f"A: {seed['answer']}\n\n"
            f"Generate {NUM_EXAMPLES_PER_SEED} new, diverse question-answer pairs "
            f"based on the same context. Each answer should be detailed and factual, "
            f"citing specific data from the context. Return as JSON array with "
            f"'question' and 'answer' keys."
        )

        response = client.chat.completions.create(
            model=TEACHER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=2048,
        )

        try:
            content = response.choices[0].message.content
            # Parse the JSON array from the response
            pairs = json.loads(content)
            for pair in pairs:
                generated.append({
                    "messages": [
                        {"role": "system", "content": entry["task_description"]},
                        {"role": "user", "content": pair["question"]},
                        {"role": "assistant", "content": pair["answer"]},
                    ],
                    "source": "sdg-knowledge",
                    "taxonomy_topic": entry["topic"],
                })
            print(f"  Knowledge seed generated {len(pairs)} examples")
        except (json.JSONDecodeError, KeyError) as e:
            print(f"  Warning: failed to parse teacher output: {e}")

# Generate from skill entries
for entry in taxonomy.get("skills", []):
    for seed in entry["seed_examples"]:
        prompt = (
            f"You are a training data generator. Given this example of a skill:\n"
            f"Input: {seed['question']}\n"
            f"Output: {seed['answer']}\n\n"
            f"Generate {NUM_EXAMPLES_PER_SEED} new input-output pairs that demonstrate "
            f"the same skill pattern (structured comparison tables). Each output should "
            f"use markdown table format. Vary the products and attributes. Return as "
            f"JSON array with 'question' and 'answer' keys."
        )

        response = client.chat.completions.create(
            model=TEACHER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=2048,
        )

        try:
            content = response.choices[0].message.content
            pairs = json.loads(content)
            for pair in pairs:
                generated.append({
                    "messages": [
                        {"role": "system", "content": entry["task_description"]},
                        {"role": "user", "content": pair["question"]},
                        {"role": "assistant", "content": pair["answer"]},
                    ],
                    "source": "sdg-skill",
                    "taxonomy_topic": entry["topic"],
                })
            print(f"  Skill seed generated {len(pairs)} examples")
        except (json.JSONDecodeError, KeyError) as e:
            print(f"  Warning: failed to parse teacher output: {e}")

# Save generated data
with open(OUTPUT_PATH, "w") as f:
    for example in generated:
        f.write(json.dumps(example) + "\n")

print(f"\nSDG complete: {len(generated)} examples saved to {OUTPUT_PATH}")

# Show breakdown
knowledge_count = sum(1 for e in generated if e["source"] == "sdg-knowledge")
skill_count = sum(1 for e in generated if e["source"] == "sdg-skill")
print(f"  Knowledge examples: {knowledge_count}")
print(f"  Skill examples: {skill_count}")
```

Expected output:

```
  Knowledge seed generated 5 examples
  Knowledge seed generated 5 examples
  Knowledge seed generated 5 examples
  Skill seed generated 5 examples
  Skill seed generated 5 examples
  Skill seed generated 5 examples

SDG complete: 30 examples saved to /opt/app-root/src/lab-tuning/sdg_output.jsonl
  Knowledge examples: 15
  Skill examples: 15
```

The exact number depends on how many examples the teacher produces per seed. With 3 knowledge seeds and 3 skill seeds, each generating 5 examples, you get approximately 30 total training examples.

**SDG quality checks:**

After generation, inspect a few examples to verify quality:

```python
import json

with open("/opt/app-root/src/lab-tuning/sdg_output.jsonl") as f:
    examples = [json.loads(line) for line in f]

# Show first knowledge example
print("=== Sample Knowledge Example ===")
k_example = next(e for e in examples if e["source"] == "sdg-knowledge")
for msg in k_example["messages"]:
    print(f"  [{msg['role']}]: {msg['content'][:100]}...")

print()

# Show first skill example
print("=== Sample Skill Example ===")
s_example = next(e for e in examples if e["source"] == "sdg-skill")
for msg in s_example["messages"]:
    print(f"  [{msg['role']}]: {msg['content'][:100]}...")
```

Expected output:

```
=== Sample Knowledge Example ===
  [system]: Answer questions about Acme Corp product catalog and policies....
  [user]: What waterproof rating does the TrailBlazer 3000 have and what does it mean for outdoor use?...
  [assistant]: The TrailBlazer 3000 has an IPX7 waterproof rating, which means it can withstand submers...

=== Sample Skill Example ===
  [system]: Generate structured product comparison tables for e-commerce items....
  [user]: Compare a hiking backpack priced at $199 with 50L capacity against a daypack at $89 with 25L...
  [assistant]: | Feature | Hiking Backpack | Daypack |...
```

If the examples look low quality (hallucinated facts, broken table formatting), consider:
- Using a larger teacher model
- Improving the seed examples in your taxonomy
- Reducing `temperature` to 0.6 for more faithful generation

### Step 5: Split Data for Multi-Phase Training

LAB-tuning requires separate datasets for the knowledge phase and skills phase:

```python
import json

INPUT_PATH = "/opt/app-root/src/lab-tuning/sdg_output.jsonl"
KNOWLEDGE_PATH = "/opt/app-root/src/lab-tuning/knowledge_train.jsonl"
SKILLS_PATH = "/opt/app-root/src/lab-tuning/skills_train.jsonl"

knowledge_data = []
skills_data = []

with open(INPUT_PATH) as f:
    for line in f:
        example = json.loads(line)
        # Remove metadata fields -- Training Hub expects only 'messages'
        train_example = {"messages": example["messages"]}
        if example["source"] == "sdg-knowledge":
            knowledge_data.append(train_example)
        else:
            skills_data.append(train_example)

for path, data, name in [
    (KNOWLEDGE_PATH, knowledge_data, "knowledge"),
    (SKILLS_PATH, skills_data, "skills"),
]:
    with open(path, "w") as f:
        for example in data:
            f.write(json.dumps(example) + "\n")
    print(f"{name}: {len(data)} examples saved to {path}")
```

Expected output:

```
knowledge: 15 examples saved to /opt/app-root/src/lab-tuning/knowledge_train.jsonl
skills: 15 examples saved to /opt/app-root/src/lab-tuning/skills_train.jsonl
```

### Step 6: Phase 1 -- Knowledge Tuning

Run the first training phase on the knowledge data. This injects factual knowledge into the student model:

```python
from training_hub import lora_sft

print("=== Phase 1: Knowledge Tuning ===")
knowledge_result = lora_sft(
    model_path="google/gemma-4-E4B-it",
    data_path="/opt/app-root/src/lab-tuning/knowledge_train.jsonl",
    ckpt_output_dir="/opt/app-root/src/lab-tuning/phase1_knowledge",
    lora_r=16,
    lora_alpha=32,
    num_epochs=3,
    learning_rate=2e-4,
)
print("Phase 1 complete. Knowledge adapter saved.")
```

Expected output:

```
=== Phase 1: Knowledge Tuning ===
Loading model google/gemma-4-E4B-it...
Applying LoRA with r=16, alpha=32...
Trainable parameters: 4,194,304 / 4,000,000,000 (0.10%)
Starting training for 3 epochs...
Epoch 1/3: loss=2.456
Epoch 2/3: loss=1.287
Epoch 3/3: loss=0.743
Training complete. Adapter weights saved to /opt/app-root/src/lab-tuning/phase1_knowledge
Phase 1 complete. Knowledge adapter saved.
```

### Step 7: Phase 2 -- Skills Tuning

Load the Phase 1 adapter and continue training on the skills data. This teaches the model how to present knowledge in structured formats:

```python
from training_hub import lora_sft

print("=== Phase 2: Skills Tuning ===")
skills_result = lora_sft(
    model_path="/opt/app-root/src/lab-tuning/phase1_knowledge",  # Start from Phase 1 output
    data_path="/opt/app-root/src/lab-tuning/skills_train.jsonl",
    ckpt_output_dir="/opt/app-root/src/lab-tuning/phase2_skills",
    lora_r=16,
    lora_alpha=32,
    num_epochs=3,
    learning_rate=1e-4,  # Lower learning rate for Phase 2 to avoid catastrophic forgetting
)
print("Phase 2 complete. LAB-tuned adapter saved.")
```

Expected output:

```
=== Phase 2: Skills Tuning ===
Loading model from /opt/app-root/src/lab-tuning/phase1_knowledge...
Applying LoRA with r=16, alpha=32...
Starting training for 3 epochs...
Epoch 1/3: loss=1.823
Epoch 2/3: loss=0.956
Epoch 3/3: loss=0.512
Training complete. Adapter weights saved to /opt/app-root/src/lab-tuning/phase2_skills
Phase 2 complete. LAB-tuned adapter saved.
```

**Why a lower learning rate in Phase 2:** Phase 2 starts from a model that already has knowledge-tuned weights. Using the same learning rate as Phase 1 risks overwriting the knowledge learned in Phase 1 -- a problem called catastrophic forgetting. Halving the learning rate (2e-4 to 1e-4) reduces this risk while still allowing the model to learn the skill patterns.

### Step 8: Evaluate the LAB-Tuned Model

Compare the LAB-tuned model against the base model on both knowledge and skill tasks:

```python
from unsloth import FastLanguageModel

# Load the LAB-tuned model (Phase 2 output)
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="/opt/app-root/src/lab-tuning/phase2_skills",
    max_seq_length=2048,
    load_in_4bit=False,
)
FastLanguageModel.for_inference(model)

def generate(prompt, system_prompt=None, max_tokens=512):
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    input_ids = tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True, return_tensors="pt"
    ).to(model.device)

    output = model.generate(
        input_ids=input_ids, max_new_tokens=max_tokens,
        temperature=0.7, do_sample=True,
    )
    return tokenizer.decode(output[0][input_ids.shape[-1]:], skip_special_tokens=True)

# Test knowledge retention
print("=== Knowledge Test (should cite Acme Corp specifics) ===")
print(generate(
    "What are Acme Corp's flagship products and their prices?",
    system_prompt="Answer questions about Acme Corp product catalog and policies."
))
print()

# Test skill acquisition
print("=== Skill Test (should produce a markdown table) ===")
print(generate(
    "Compare the TrailBlazer 3000 boot with the SummitPack 45L backpack in a table.",
    system_prompt="Generate structured product comparison tables for e-commerce items."
))
print()

# Test generalization
print("=== Generalization Test (new product, should use learned table skill) ===")
print(generate(
    "Create a comparison table for a tent ($299, 2-person, 3.5kg) and a sleeping bag ($149, rated to -10C, 1.2kg).",
    system_prompt="Generate structured product comparison tables for e-commerce items."
))
```

Expected output (will vary based on model and training):

```
=== Knowledge Test (should cite Acme Corp specifics) ===
Acme Corp's flagship products include the TrailBlazer 3000 hiking boot
(SKU: TB-3000, $189.99), the SummitPack 45L backpack (SKU: SP-45L,
$249.99), and the AlpineShield rain jacket (SKU: AS-RJ, $159.99)...

=== Skill Test (should produce a markdown table) ===
| Feature | TrailBlazer 3000 | SummitPack 45L |
|---------|------------------|----------------|
| Category | Hiking Boot | Backpack |
| Price | $189.99 | $249.99 |
...

=== Generalization Test (new product, should use learned table skill) ===
| Feature | Tent | Sleeping Bag |
|---------|------|--------------|
| Price | $299 | $149 |
| Capacity | 2-person | 1-person |
| Weight | 3.5kg | 1.2kg |
...
```

**What to look for:**
- The knowledge test should produce specific Acme Corp details (SKUs, prices) from the taxonomy context.
- The skill test should output a properly formatted markdown table.
- The generalization test should apply the table formatting skill to products not in the training data.

### Step 9: Orchestrate with a Data Science Pipeline

For production use, the LAB-tuning workflow should run as a KFP pipeline rather than manual notebook cells. See `scripts/lab_training_pipeline.py` for the full pipeline definition.

Compile and submit the pipeline:

```bash
cd /opt/app-root/src
python lab_training_pipeline.py --compile-only --output lab-pipeline.yaml
```

Expected output:

```
Pipeline compiled to lab-pipeline.yaml
```

Upload the pipeline via the OpenShift AI dashboard:

1. Navigate to **Data Science Pipelines** > **Pipelines**
2. Click **Import pipeline**
3. Upload `lab-pipeline.yaml`
4. Create a run with your parameters (taxonomy path, teacher endpoint, base model)

Or submit programmatically:

```python
import subprocess
from kfp.client import Client

route = subprocess.check_output(
    ["oc", "get", "route", "ds-pipeline-dspa", "-n", "<your-project>",
     "-o", "jsonpath={.spec.host}"],
).decode().strip()

token = subprocess.check_output(["oc", "whoami", "-t"]).decode().strip()

client = Client(host=f"https://{route}", existing_token=token)

run = client.create_run_from_pipeline_package(
    pipeline_file="lab-pipeline.yaml",
    arguments={
        "taxonomy_path": "/opt/app-root/src/lab-tuning/taxonomy.yaml",
        "teacher_endpoint": "https://gemma-4-e4b-your-project.apps.cluster.example.com/v1",
        "teacher_model": "gemma-4-e4b",
        "base_model": "google/gemma-4-E4B-it",
        "num_sdg_examples": 5,
        "knowledge_epochs": 3,
        "skills_epochs": 3,
    },
    run_name="lab-tuning-run",
    experiment_name="instructlab-experiments",
)
print(f"Run submitted: {run.run_id}")
```

Expected output:

```
Run submitted: a1b2c3d4-e5f6-...
```

### Step 10: Deploy and Compare

Deploy the LAB-tuned model using the same pattern from [L1-M3.3](../../../level_1/M3_fine_tuning/3_deploying_fine_tuned/). Upload the Phase 2 adapter weights to S3 and create an InferenceService pointing to the merged model.

To compare LAB-tuning versus standard LoRA, query both endpoints with the same prompts:

```python
from openai import OpenAI

# Endpoint for the standard LoRA fine-tuned model (from L1-M3.3)
lora_client = OpenAI(
    base_url="https://gemma-4-e4b-finetuned-your-project.apps.cluster.example.com/v1",
    api_key="unused",
)

# Endpoint for the LAB-tuned model
lab_client = OpenAI(
    base_url="https://gemma-4-e4b-lab-tuned-your-project.apps.cluster.example.com/v1",
    api_key="unused",
)

test_prompts = [
    ("What is the SKU for the SummitPack 45L?", "Knowledge recall"),
    ("Compare the TrailBlazer 3000 and AlpineShield jacket in a table.", "Skill application"),
    ("What are the warranty terms for Acme Corp hiking boots?", "Knowledge + detail"),
]

for prompt, category in test_prompts:
    print(f"\n=== {category} ===")
    print(f"Prompt: {prompt}\n")

    lora_resp = lora_client.chat.completions.create(
        model="gemma-4-e4b-finetuned",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
    )
    print(f"[LoRA]: {lora_resp.choices[0].message.content[:200]}...")

    lab_resp = lab_client.chat.completions.create(
        model="gemma-4-e4b-lab-tuned",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
    )
    print(f"[LAB]:  {lab_resp.choices[0].message.content[:200]}...")
```

Expected output:

```
=== Knowledge recall ===
Prompt: What is the SKU for the SummitPack 45L?

[LoRA]: The SummitPack 45L is a popular backpack option. I don't have specific SKU information...
[LAB]:  The SummitPack 45L backpack has SKU: SP-45L. It is priced at $249.99, weighs 1.2kg...

=== Skill application ===
Prompt: Compare the TrailBlazer 3000 and AlpineShield jacket in a table.

[LoRA]: The TrailBlazer 3000 is a hiking boot priced at $189.99 and the AlpineShield...
[LAB]:  | Feature | TrailBlazer 3000 | AlpineShield RJ |
        |---------|------------------|-----------------|...
```

The LAB-tuned model should outperform the standard LoRA model on:
- **Knowledge recall**: citing specific facts from the taxonomy context (SKUs, prices, policies)
- **Skill application**: producing structured table output when asked for comparisons

The standard LoRA model may outperform on tasks that were well-represented in its curated training dataset but that were not covered by the taxonomy.

## Verification

Confirm the lesson succeeded by checking these items:

1. **Taxonomy was created and is valid:**

```bash
python -c "import yaml; t = yaml.safe_load(open('/opt/app-root/src/lab-tuning/taxonomy.yaml')); print(f'Knowledge: {len(t[\"knowledge\"])}, Skills: {len(t[\"skills\"])}')"
```

Expected output:

```
Knowledge: 1, Skills: 1
```

2. **SDG generated training examples:**

```bash
wc -l /opt/app-root/src/lab-tuning/sdg_output.jsonl
```

Expected output:

```
30 /opt/app-root/src/lab-tuning/sdg_output.jsonl
```

3. **Phase 1 (knowledge) adapter weights exist:**

```bash
ls -la /opt/app-root/src/lab-tuning/phase1_knowledge/adapter_model.safetensors
```

Expected output:

```
-rw-r--r-- 1 user user 18874368 ... adapter_model.safetensors
```

4. **Phase 2 (skills) adapter weights exist:**

```bash
ls -la /opt/app-root/src/lab-tuning/phase2_skills/adapter_model.safetensors
```

Expected output:

```
-rw-r--r-- 1 user user 18874368 ... adapter_model.safetensors
```

5. **LAB-tuned model produces knowledge-aware, structured responses:**

```python
response = generate(
    "What is the price of the TrailBlazer 3000?",
    system_prompt="Answer questions about Acme Corp product catalog and policies."
)
assert "$189.99" in response, "Model did not recall the correct price"
print("Knowledge verification passed")
```

Expected output:

```
Knowledge verification passed
```

## Training Hub LoRA vs LAB-Tuning Comparison

| Aspect | Training Hub LoRA (L1-M3.2) | InstructLab LAB-Tuning |
|--------|----------------------------|------------------------|
| Data requirement | Curated dataset needed (JSONL with messages) | Taxonomy entries (knowledge + skills YAML) |
| Data generation | Manual -- human writes every training example | Automated -- teacher model generates from taxonomy |
| Training phases | Single phase (one `lora_sft()` call) | Multi-phase (knowledge tuning then skills tuning) |
| Best for | Targeted behavior/style changes with known examples | Broad knowledge injection when curated data is unavailable |
| Human effort | Writing training examples (high volume) | Writing taxonomy entries (low volume, high precision) |
| Setup complexity | Simple (install Training Hub, call one function) | Complex (taxonomy + SDG + multi-phase + evaluation) |
| Maturity on OpenShift AI | GA (Training Hub) | Technology Preview |
| GPU requirements | Moderate (single GPU, student model only) | Higher (teacher model for SDG + student for training) |
| Reproducibility | Deterministic (same data, same result) | Variable (SDG output depends on teacher model sampling) |
| Iteration cycle | Change dataset, retrain | Change taxonomy, re-run SDG, retrain both phases |

**When to use which:**

- Use **Training Hub LoRA** when you have a curated dataset of examples, when you need predictable results, or when you are making targeted behavioral adjustments (response style, specific task performance).
- Use **LAB-tuning** when you need to inject domain knowledge from documents, when subject-matter experts can describe what the model should know but cannot write hundreds of training examples, or when you need both knowledge recall and structured output formatting.
- Both approaches produce LoRA adapter weights that can be served by vLLM with the same deployment pattern (see [L1-M3.3](../../../level_1/M3_fine_tuning/3_deploying_fine_tuned/)).

## Key Takeaways

- The LAB methodology shifts human effort from data curation to taxonomy design. Subject-matter experts describe knowledge and skills, and a teacher model generates the training data automatically.
- LAB-tuning uses two training phases: knowledge tuning (inject facts) followed by skills tuning (teach reasoning and formatting patterns). This separation prevents the model from learning formats without grounding them in facts.
- SDG quality is the single biggest factor in LAB-tuning success. Invest in well-written taxonomy entries with diverse seed examples and use the largest available teacher model.
- The original `instructlab` CLI was archived and refactored into SDG Hub and Training Hub -- both are available as Tier 3 Python libraries on OpenShift AI. The LAB-tuning workflow is a Technology Preview.
- For production, orchestrate the LAB-tuning workflow as a KFP pipeline (taxonomy validation, SDG, Phase 1, Phase 2, evaluation, model registration) rather than running steps manually in a notebook.
- LAB-tuning complements, rather than replaces, standard LoRA fine-tuning. The right choice depends on whether your bottleneck is data availability (use LAB) or data quality control (use standard LoRA).

## Troubleshooting

| Problem | Likely Cause | Solution |
|---------|-------------|----------|
| SDG produces low-quality examples | Teacher model too small or temperature too high | Use a larger teacher model; reduce temperature to 0.6 |
| Phase 2 degrades Phase 1 knowledge | Learning rate too high in Phase 2 | Lower Phase 2 learning rate (try 5e-5) or reduce epochs |
| Teacher model returns unparseable JSON | Model not following the generation prompt format | Add few-shot examples to the SDG prompt; use a more instruction-following teacher |
| `trainer` DSC component not available | Component not enabled or OpenShift AI version too old | Verify DSC config; requires OpenShift AI 2.x with Technology Preview features |
| Out of GPU memory during SDG | Teacher and student both loaded simultaneously | Run SDG and training sequentially, not in the same process; or use a separate GPU for the teacher |
| Pipeline fails at knowledge tuning | PVC storage full or model download fails | Check PVC capacity; ensure `HF_TOKEN` is set in the pipeline environment |

## Cleanup

Remove all LAB-tuning artifacts from the workbench:

```bash
# Remove all training outputs and generated data
rm -rf /opt/app-root/src/lab-tuning

# Remove the Hugging Face model cache (frees several GB)
rm -rf ~/.cache/huggingface/hub/models--google--gemma-4-E4B-it

# Remove compiled pipeline YAML (if created)
rm -f /opt/app-root/src/lab-pipeline.yaml
```

If you created a PVC for LAB-tuning storage (see `manifests/lab-tuning-pvc.yaml`), delete it:

```bash
oc delete pvc lab-tuning-storage -n <your-project>
```

Expected output:

```
persistentvolumeclaim "lab-tuning-storage" deleted
```

## Next Steps

In the next lesson, [L3-M4.2 -- Feast Feature Store](../2_feast/), you will set up a feature store on OpenShift AI for managing and serving features used in training and inference pipelines. Feature stores complement fine-tuning workflows by providing consistent, versioned access to the features that feed into model training and real-time predictions.
