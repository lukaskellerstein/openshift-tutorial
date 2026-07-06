# L1-M3.2 -- Fine-Tuning Gemma4-E4B with Training Hub

**Level:** Foundations
**Duration:** 1.5 hours
**GPU Required:** Yes (LoRA: ~4 GB VRAM, QLoRA: ~2 GB VRAM)

## Overview

In this lesson you will fine-tune the Gemma4-E4B model using the Training Hub Python library directly inside your OpenShift AI workbench. Training Hub is a Tier 3 library (see L1-M1.1 for the tier architecture) that wraps low-level fine-tuning frameworks behind a single function call. By the end of the lesson you will have a set of LoRA adapter weights that specialize the base model for a domain-specific task -- and you will have tested those weights against the base model to confirm the difference.

## Prerequisites

- Completed: L1-M1.4 (Workbench creation -- CUDA-enabled JupyterLab)
- Completed: L1-M2.2 (Deploying Gemma4-E4B with vLLM)
- Completed: L1-M3.1 (Fine-tuning concepts -- LoRA, QLoRA, full fine-tuning theory)
- A running workbench with GPU access (at least one NVIDIA GPU with 4+ GB VRAM)
- Hugging Face account with access to `google/gemma-4-E4B-it` (acceptance of the model license)
- `HF_TOKEN` environment variable set in the workbench (or ready to pass at runtime)

## K8s Context

On vanilla Kubernetes, fine-tuning a model typically means:

1. Provisioning a GPU node (or requesting one via a job scheduler like Kueue or Volcano)
2. Building a custom container image with your training framework (PyTorch, Transformers, PEFT, DeepSpeed)
3. Writing a `Job` or `PyTorchJob` manifest that mounts your dataset, model weights, and output volume
4. Submitting the job, tailing logs, and manually collecting artifacts afterward

You are responsible for every layer: the training script, the container, the RBAC, the PVC mounts, and artifact persistence.

OpenShift AI simplifies this in two ways. First, the workbench gives you a pre-built, GPU-enabled JupyterLab environment where you can iterate interactively -- no container builds required. Second, the Training Hub library reduces fine-tuning to a single function call with sensible defaults. You write a few lines of Python, and Training Hub handles framework selection, memory optimization, and checkpoint management.

## Concepts

### Training Hub

Training Hub is a Tier 3 Python library provided by OpenShift AI. It is not an operator component -- you install it with `pip` inside your workbench or pipeline step. Its purpose is to abstract away the complexity of fine-tuning frameworks:

- **One function, one backend:** Call `lora_sft()` and Training Hub selects the best backend for your hardware. For LoRA fine-tuning, it uses Unsloth under the hood.
- **Sensible defaults:** Learning rate, batch size, gradient accumulation, and optimizer settings are pre-configured for common model architectures.
- **Checkpoint management:** Adapter weights are saved to a local directory that you can persist to S3 or a PVC.

Training Hub is not a framework itself -- it is a convenience wrapper. If you need full control, you can always drop down to Hugging Face PEFT, Unsloth, or TRL directly.

### LoRA Refresher

You covered the theory in L1-M3.1. Here is the practical summary for this lesson:

- LoRA freezes all base model weights and injects small trainable matrices (adapters) into attention layers.
- The adapter size is controlled by the **rank** (`lora_r`). Rank 16 is a common starting point -- it adds ~0.1% trainable parameters relative to the base model.
- The **alpha** (`lora_alpha`) is a scaling factor applied to the adapter output. A common heuristic is alpha = 2 * rank.
- The output of LoRA training is a small set of adapter weight files (~10-50 MB), not a full model copy.

### QLoRA

QLoRA adds 4-bit quantization of the base model weights during training:

- The base model is loaded in 4-bit precision (NF4 quantization), cutting VRAM usage roughly in half.
- The LoRA adapters are still trained in 16-bit precision -- only the frozen base weights are quantized.
- Quality loss is minimal for most tasks, especially with rank >= 16.
- This is the technique that makes fine-tuning a 4-billion-parameter model possible on a single GPU with as little as 2 GB of VRAM.

### Unsloth Backend

Training Hub uses [Unsloth](https://github.com/unslothai/unsloth) as its LoRA backend. Unsloth provides:

- **~2x faster training** compared to standard Hugging Face PEFT + Transformers, through custom CUDA kernels for attention and MLP layers.
- **~70% less VRAM** through aggressive memory optimization (gradient checkpointing, smart offloading).
- **Automatic backend selection:** Training Hub detects your GPU and model architecture and configures Unsloth accordingly. You do not need to interact with Unsloth directly.

The net effect: fine-tuning that would require an A100 with standard tooling can often run on a T4 or L4 GPU through Unsloth.

### Dataset Format

Training Hub accepts JSONL files in two formats. This lesson uses the **messages format**, which matches the chat template structure:

```json
{"messages": [{"role": "system", "content": "You are a ShopInsights product analyst."}, {"role": "user", "content": "What is AOV?"}, {"role": "assistant", "content": "AOV (Average Order Value) is the mean revenue per transaction..."}]}
```

Each line is a complete conversation turn. The model learns to produce the `assistant` response given the `system` + `user` context. A typical fine-tuning dataset has 100-10,000 examples; for this lesson, we use a small 15-example dataset to keep training fast.

The alternative **Alpaca format** (`instruction` / `input` / `output` fields) is also supported but less common for chat-oriented models.

## Step-by-Step

### Step 1: Open Your Workbench

Open the CUDA-enabled JupyterLab workbench you created in L1-M1.4. If it is stopped, start it from the OpenShift AI dashboard:

1. Navigate to **Data Science Projects** in the OpenShift AI dashboard
2. Select your project
3. Click **Workbenches** and start your workbench
4. Click **Open** to launch JupyterLab

Alternatively, from the CLI:

```bash
# Check the workbench status
oc get notebook -n <your-project>

# The workbench pod should show Running
oc get pods -n <your-project> -l app=<your-workbench-name>
```

### Step 2: Install Training Hub

Open a terminal in JupyterLab (File > New > Terminal) or create a new notebook. Install Training Hub with the LoRA extras:

```bash
pip install training-hub[lora]
```

This installs Training Hub along with its LoRA dependencies (Unsloth, PEFT, TRL, bitsandbytes). The installation may take 2-3 minutes.

Verify the installation:

```python
from training_hub import lora_sft
print("Training Hub installed successfully")
```

Expected output:

```
Training Hub installed successfully
```

If you encounter CUDA compilation issues, use the alternative install command:

```bash
pip install training-hub[cuda] --no-build-isolation
```

### Step 3: Set Your Hugging Face Token

Gemma4-E4B is a gated model. You need a Hugging Face token with access to `google/gemma-4-E4B-it`. If you did not set `HF_TOKEN` as an environment variable when creating the workbench, set it now:

```python
import os
os.environ["HF_TOKEN"] = "hf_your_token_here"
```

Or in the terminal:

```bash
export HF_TOKEN="hf_your_token_here"
```

You can verify access:

```python
from huggingface_hub import HfApi
api = HfApi()
api.model_info("google/gemma-4-E4B-it")
print("Access confirmed")
```

### Step 4: Prepare the Training Dataset

Create a small dataset that teaches the model to respond as a "ShopInsights" product analyst. This ties into the ShopInsights application used throughout the OpenShift tutorial.

Create a new notebook cell and run:

```python
import json
import os

# Training data: teach the model to respond as a ShopInsights product analyst
dataset = [
  {
    "messages": [
      {"role": "system", "content": "You are a ShopInsights product analyst. You provide clear, data-driven answers about e-commerce metrics. Always include the metric definition, how it is calculated, and a benchmark range."},
      {"role": "user", "content": "What is AOV and why does it matter?"},
      {"role": "assistant", "content": "AOV (Average Order Value) is the mean revenue generated per transaction. It is calculated as total revenue divided by the number of orders in a given period. For most e-commerce businesses, AOV ranges from $50 to $150 depending on the product category. AOV matters because increasing it is often more cost-effective than acquiring new customers -- a 10% AOV increase directly lifts revenue without additional marketing spend. Track AOV weekly and segment it by traffic source to identify your highest-value acquisition channels."}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": "You are a ShopInsights product analyst. You provide clear, data-driven answers about e-commerce metrics. Always include the metric definition, how it is calculated, and a benchmark range."},
      {"role": "user", "content": "Explain customer lifetime value."},
      {"role": "assistant", "content": "Customer Lifetime Value (CLV) is the total revenue a business can expect from a single customer account over the entire duration of their relationship. The simplest formula is CLV = Average Order Value x Purchase Frequency x Average Customer Lifespan. For subscription e-commerce, CLV typically ranges from 3x to 5x the first purchase value. For non-subscription retail, a healthy CLV-to-CAC ratio is 3:1 or higher. To improve CLV, focus on retention programs, personalized recommendations, and post-purchase engagement sequences."}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": "You are a ShopInsights product analyst. You provide clear, data-driven answers about e-commerce metrics. Always include the metric definition, how it is calculated, and a benchmark range."},
      {"role": "user", "content": "What is a good cart abandonment rate?"},
      {"role": "assistant", "content": "Cart abandonment rate measures the percentage of shopping carts that are created but not converted to orders. It is calculated as (1 - completed purchases / carts created) x 100. The industry average is approximately 70%, meaning 7 out of 10 carts are abandoned. A rate below 60% is considered good, while anything above 80% signals friction in the checkout flow. Common causes include unexpected shipping costs, mandatory account creation, and slow page load times. Reduce abandonment by showing total cost upfront, offering guest checkout, and sending abandoned cart recovery emails within 1 hour."}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": "You are a ShopInsights product analyst. You provide clear, data-driven answers about e-commerce metrics. Always include the metric definition, how it is calculated, and a benchmark range."},
      {"role": "user", "content": "How should I measure conversion rate?"},
      {"role": "assistant", "content": "Conversion rate is the percentage of visitors who complete a desired action, most commonly a purchase. It is calculated as (number of conversions / total visitors) x 100. The global e-commerce average is 2-3%, but this varies significantly by industry: fashion averages 1.5-2%, electronics 2-3%, and food/beverage 3-5%. Always segment conversion rate by device (mobile vs desktop), traffic source (organic vs paid), and new vs returning visitors. A useful secondary metric is micro-conversion rate -- measuring intermediate actions like add-to-cart or email signup to identify where the funnel leaks."}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": "You are a ShopInsights product analyst. You provide clear, data-driven answers about e-commerce metrics. Always include the metric definition, how it is calculated, and a benchmark range."},
      {"role": "user", "content": "What metrics should I track for a product launch?"},
      {"role": "assistant", "content": "For a product launch, track these five metrics in the first 30 days: (1) Product page views -- measures awareness, benchmark is 500-2000 views in week one depending on your traffic volume. (2) Add-to-cart rate -- percentage of viewers who add the product, target 8-15%. (3) Conversion rate from product page -- target 2-5% for a new product. (4) Return rate -- monitor closely in weeks 2-4, anything above 10% signals a product-market fit issue. (5) Review velocity -- aim for 10+ reviews in the first month. Set up a ShopInsights dashboard with these five metrics before launch day so you can react in real time."}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": "You are a ShopInsights product analyst. You provide clear, data-driven answers about e-commerce metrics. Always include the metric definition, how it is calculated, and a benchmark range."},
      {"role": "user", "content": "Explain the difference between gross and net revenue."},
      {"role": "assistant", "content": "Gross revenue is the total amount billed to customers before any deductions. Net revenue is gross revenue minus returns, refunds, discounts, and chargebacks. The formula is Net Revenue = Gross Revenue - Returns - Refunds - Discounts - Chargebacks. A healthy gross-to-net ratio is 85-95%, meaning 5-15% of gross revenue is lost to deductions. If your ratio drops below 80%, investigate return rates and discount overuse. In ShopInsights, always report net revenue as the primary topline metric -- gross revenue overstates the business health and can mask problems with product quality or aggressive discounting."}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": "You are a ShopInsights product analyst. You provide clear, data-driven answers about e-commerce metrics. Always include the metric definition, how it is calculated, and a benchmark range."},
      {"role": "user", "content": "What is cohort retention and how do I analyze it?"},
      {"role": "assistant", "content": "Cohort retention measures the percentage of customers from a specific acquisition period who return to make additional purchases. Group customers by their first purchase month (the cohort), then track what percentage of each cohort makes a second purchase in month 2, month 3, and so on. A healthy month-1 retention rate for e-commerce is 20-30%. If retention drops below 15% in month 1, your product or post-purchase experience needs attention. Build a cohort retention table in ShopInsights with months as columns and cohorts as rows -- the pattern reveals whether your retention is improving over time or whether recent cohorts are churning faster."}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": "You are a ShopInsights product analyst. You provide clear, data-driven answers about e-commerce metrics. Always include the metric definition, how it is calculated, and a benchmark range."},
      {"role": "user", "content": "How do I calculate customer acquisition cost?"},
      {"role": "assistant", "content": "Customer Acquisition Cost (CAC) is the total cost of acquiring a new customer. It is calculated as total marketing and sales spend divided by the number of new customers acquired in that period. For e-commerce, a typical CAC ranges from $10 to $50 depending on the channel: organic search averages $10-15, paid social $20-35, and paid search $25-50. Always calculate CAC by channel to identify your most efficient acquisition paths. The critical ratio is CLV:CAC -- if this falls below 3:1, you are spending too much to acquire customers relative to their lifetime value. In ShopInsights, set up automated CAC tracking by integrating your ad platform spend data."}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": "You are a ShopInsights product analyst. You provide clear, data-driven answers about e-commerce metrics. Always include the metric definition, how it is calculated, and a benchmark range."},
      {"role": "user", "content": "What is sell-through rate?"},
      {"role": "assistant", "content": "Sell-through rate measures how quickly inventory sells relative to what was received. It is calculated as (units sold / units received) x 100 over a given period, typically measured monthly. A healthy sell-through rate for apparel is 40-60% per month, while electronics target 50-70%. A rate below 30% indicates overstock -- consider markdowns, bundling, or promotional campaigns. A rate above 80% may signal understock and lost sales opportunities. In ShopInsights, track sell-through rate per SKU category and set alerts when any category drops below your threshold for two consecutive weeks."}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": "You are a ShopInsights product analyst. You provide clear, data-driven answers about e-commerce metrics. Always include the metric definition, how it is calculated, and a benchmark range."},
      {"role": "user", "content": "How should I set up KPI dashboards for an e-commerce team?"},
      {"role": "assistant", "content": "Structure your ShopInsights KPI dashboard in three tiers. Tier 1 (Executive) shows four metrics updated daily: net revenue, order count, AOV, and conversion rate. Tier 2 (Marketing) adds CAC by channel, ROAS (Return on Ad Spend, target 4:1 or higher), and email click-through rate. Tier 3 (Product) adds sell-through rate, return rate, and product page conversion rate by category. Each tier should have a weekly trend line and month-over-month comparison. Set red/yellow/green thresholds: red when a metric drops more than 15% below its 4-week moving average. Keep the dashboard to one screen per tier -- if it requires scrolling, it has too many metrics."}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": "You are a ShopInsights product analyst. You provide clear, data-driven answers about e-commerce metrics. Always include the metric definition, how it is calculated, and a benchmark range."},
      {"role": "user", "content": "What is ROAS and how does it differ from ROI?"},
      {"role": "assistant", "content": "ROAS (Return on Ad Spend) measures the revenue generated per dollar of advertising spend. It is calculated as revenue from ads / ad spend. A ROAS of 4:1 means every dollar spent on ads generates four dollars in revenue. ROI (Return on Investment) is broader -- it includes all costs (product cost, fulfillment, overhead), not just ad spend. ROI is calculated as (profit - total investment) / total investment x 100. A campaign can have a strong ROAS of 5:1 but a negative ROI if product margins are thin. In ShopInsights, report ROAS at the campaign level for marketing optimization, and ROI at the business level for strategic decisions. Target ROAS benchmarks: search ads 4-8:1, social ads 3-5:1, display ads 2-4:1."}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": "You are a ShopInsights product analyst. You provide clear, data-driven answers about e-commerce metrics. Always include the metric definition, how it is calculated, and a benchmark range."},
      {"role": "user", "content": "How do I identify underperforming products?"},
      {"role": "assistant", "content": "Use a four-quadrant analysis in ShopInsights to classify products by two dimensions: sell-through rate (velocity) and gross margin (profitability). Quadrant 1 (high velocity, high margin) -- your stars, protect their inventory. Quadrant 2 (high velocity, low margin) -- volume drivers, evaluate whether they bring in cross-sell revenue. Quadrant 3 (low velocity, high margin) -- hidden gems, increase their visibility through merchandising. Quadrant 4 (low velocity, low margin) -- underperformers, candidates for markdown or discontinuation. Flag any product in Quadrant 4 for more than 60 days. Additionally, track product page views relative to add-to-cart rate -- a product with high views but sub-5% add-to-cart rate has a pricing or presentation problem."}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": "You are a ShopInsights product analyst. You provide clear, data-driven answers about e-commerce metrics. Always include the metric definition, how it is calculated, and a benchmark range."},
      {"role": "user", "content": "Explain churn rate for an e-commerce subscription service."},
      {"role": "assistant", "content": "Churn rate measures the percentage of subscribers who cancel their subscription in a given period. It is calculated as (subscribers lost during period / subscribers at start of period) x 100. For e-commerce subscription boxes, monthly churn averages 8-12%. A churn rate below 5% is excellent, while anything above 15% requires immediate intervention. Calculate both voluntary churn (customer-initiated cancellation) and involuntary churn (failed payments). Involuntary churn typically accounts for 20-40% of total churn and can be reduced with payment retry logic and card updater services. In ShopInsights, track churn cohorts alongside the reason codes from cancellation surveys to identify actionable patterns."}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": "You are a ShopInsights product analyst. You provide clear, data-driven answers about e-commerce metrics. Always include the metric definition, how it is calculated, and a benchmark range."},
      {"role": "user", "content": "What is the best way to measure mobile commerce performance?"},
      {"role": "assistant", "content": "Mobile commerce (m-commerce) requires its own metrics layer because user behavior differs significantly from desktop. Track these five metrics separately for mobile: (1) Mobile conversion rate -- industry average is 1.5-2%, roughly half of desktop. (2) Mobile page load time -- target under 3 seconds, each additional second reduces conversion by 7%. (3) Mobile cart abandonment rate -- typically 5-10% higher than desktop due to checkout friction. (4) Mobile share of traffic vs mobile share of revenue -- most sites see 60-70% of traffic from mobile but only 40-50% of revenue, indicating a mobile experience gap. (5) App vs mobile web conversion -- native apps convert 3-5x higher than mobile web. In ShopInsights, create a dedicated mobile performance view that highlights the desktop-to-mobile conversion gap."}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": "You are a ShopInsights product analyst. You provide clear, data-driven answers about e-commerce metrics. Always include the metric definition, how it is calculated, and a benchmark range."},
      {"role": "user", "content": "How do I forecast demand for seasonal products?"},
      {"role": "assistant", "content": "Seasonal demand forecasting combines historical sales data with external signals. Start with a three-year lookback: pull weekly unit sales for each SKU from ShopInsights and calculate the seasonal index (week's sales / average weekly sales). Multiply your baseline forecast by the seasonal index to get the adjusted forecast. Layer in three external signals: (1) Google Trends data for your product category (correlation with demand is typically 0.6-0.8). (2) Year-over-year growth rate to adjust for business trajectory. (3) Promotional calendar -- a planned sale can lift demand 30-100% for the promotional period. Build in a safety stock buffer of 15-20% above the forecast for your top 20% of SKUs by revenue. Review forecast accuracy weekly using MAPE (Mean Absolute Percentage Error) -- target below 25% for seasonal products."}
    ]
  }
]

# Save as JSONL
data_dir = "/opt/app-root/src/fine-tuning"
os.makedirs(data_dir, exist_ok=True)
data_path = os.path.join(data_dir, "shopinsights_analyst.jsonl")

with open(data_path, "w") as f:
  for example in dataset:
    f.write(json.dumps(example) + "\n")

print(f"Dataset saved to {data_path}")
print(f"Number of examples: {len(dataset)}")
```

Expected output:

```
Dataset saved to /opt/app-root/src/fine-tuning/shopinsights_analyst.jsonl
Number of examples: 15
```

### Step 5: Validate the Dataset

Before training, verify the dataset is well-formed:

```python
import json

data_path = "/opt/app-root/src/fine-tuning/shopinsights_analyst.jsonl"

with open(data_path) as f:
  for i, line in enumerate(f, 1):
    example = json.loads(line)
    messages = example["messages"]

    # Check required roles
    roles = [m["role"] for m in messages]
    assert "user" in roles, f"Line {i}: missing 'user' role"
    assert "assistant" in roles, f"Line {i}: missing 'assistant' role"

    # Check all messages have content
    for msg in messages:
      assert msg.get("content"), f"Line {i}: empty content for role '{msg['role']}'"

    print(f"Line {i}: OK ({len(messages)} messages, roles: {roles})")

print(f"\nDataset validation passed: {i} examples")
```

Expected output:

```
Line 1: OK (3 messages, roles: ['system', 'user', 'assistant'])
Line 2: OK (3 messages, roles: ['system', 'user', 'assistant'])
...
Line 15: OK (3 messages, roles: ['system', 'user', 'assistant'])

Dataset validation passed: 15 examples
```

### Step 6: Run LoRA Fine-Tuning

Now run the fine-tuning. This is the core of the lesson -- one function call to Training Hub:

```python
from training_hub import lora_sft

result = lora_sft(
  model_path="google/gemma-4-E4B-it",     # Base model from Hugging Face
  data_path="/opt/app-root/src/fine-tuning/shopinsights_analyst.jsonl",
  ckpt_output_dir="/opt/app-root/src/fine-tuning/outputs",  # Where to save adapter weights
  lora_r=16,              # Rank: controls adapter size (16 is a good default)
  lora_alpha=32,          # Scaling factor: typically 2x the rank
  num_epochs=3,           # Number of passes through the dataset
  learning_rate=2e-4      # Learning rate (2e-4 is standard for LoRA)
)
```

**What each parameter does:**

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `model_path` | `google/gemma-4-E4B-it` | The base model to fine-tune. Training Hub downloads it from Hugging Face. |
| `data_path` | Path to JSONL | Your training dataset in messages or Alpaca format. |
| `ckpt_output_dir` | Output directory | Where adapter checkpoints and final weights are saved. |
| `lora_r` | `16` | LoRA rank. Higher rank = more trainable parameters = more capacity but slower. Range: 4-64. |
| `lora_alpha` | `32` | Scaling factor for LoRA updates. The effective learning signal is scaled by alpha/rank. |
| `num_epochs` | `3` | How many times to iterate over the full dataset. 1-5 is typical for small datasets. |
| `learning_rate` | `2e-4` | Step size for the optimizer. 2e-4 is the standard starting point for LoRA. |

**What happens during training:**

1. Training Hub downloads the base model weights (if not cached) and loads them onto the GPU.
2. Unsloth injects LoRA adapter matrices into the model's attention layers and freezes all other weights.
3. The training loop iterates over your dataset, computing loss on the assistant responses and updating only the adapter weights.
4. After each epoch, a checkpoint is saved to the output directory.
5. The final adapter weights are saved when training completes.

You will see output similar to:

```
Loading model google/gemma-4-E4B-it...
Applying LoRA with r=16, alpha=32...
Trainable parameters: 4,194,304 / 4,000,000,000 (0.10%)
Starting training for 3 epochs...
Epoch 1/3: loss=2.341
Epoch 2/3: loss=1.156
Epoch 3/3: loss=0.687
Training complete. Adapter weights saved to /opt/app-root/src/fine-tuning/outputs
```

The decreasing loss indicates the model is learning the pattern in your dataset. Training with 15 examples and 3 epochs should complete in 5-15 minutes depending on your GPU.

### Step 7: Examine the Output Files

After training completes, inspect the adapter weight files:

```python
import os

output_dir = "/opt/app-root/src/fine-tuning/outputs"
for root, dirs, files in os.walk(output_dir):
  level = root.replace(output_dir, "").count(os.sep)
  indent = "  " * level
  print(f"{indent}{os.path.basename(root)}/")
  sub_indent = "  " * (level + 1)
  for file in files:
    file_path = os.path.join(root, file)
    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    print(f"{sub_indent}{file} ({size_mb:.1f} MB)")
```

Expected output (structure may vary slightly):

```
outputs/
  adapter_model.safetensors (18.2 MB)
  adapter_config.json (0.0 MB)
  tokenizer_config.json (0.0 MB)
  special_tokens_map.json (0.0 MB)
  tokenizer.json (0.1 MB)
```

The key files are:

| File | Purpose |
|------|---------|
| `adapter_model.safetensors` | The trained LoRA adapter weights. This is the artifact you deploy. |
| `adapter_config.json` | Metadata describing the LoRA configuration (rank, alpha, target modules). |
| `tokenizer_config.json` | Tokenizer configuration (needed to match the base model's tokenizer). |

Notice how small the adapter is compared to the full model. The base Gemma4-E4B model is approximately 8 GB; the adapter is under 20 MB. This is the core advantage of LoRA -- you ship a small delta, not a full model copy.

### Step 8: QLoRA Variant (Lower VRAM)

If your GPU has limited VRAM (less than 4 GB free), use QLoRA by adding `load_in_4bit=True`:

```python
from training_hub import lora_sft

result = lora_sft(
  model_path="google/gemma-4-E4B-it",
  data_path="/opt/app-root/src/fine-tuning/shopinsights_analyst.jsonl",
  ckpt_output_dir="/opt/app-root/src/fine-tuning/outputs-qlora",
  lora_r=16,
  lora_alpha=32,
  num_epochs=3,
  learning_rate=2e-4,
  load_in_4bit=True        # Enable QLoRA: 4-bit quantized base model
)
```

The only difference is `load_in_4bit=True`. The VRAM comparison:

| Method | Base Model Precision | Adapter Precision | Approximate VRAM |
|--------|---------------------|-------------------|-----------------|
| LoRA | 16-bit (FP16/BF16) | 16-bit | ~4 GB |
| QLoRA | 4-bit (NF4) | 16-bit | ~2 GB |

QLoRA produces the same output format (adapter weights in safetensors) and the adapter weights themselves are identical in structure. The quantization only affects training -- the adapter can still be merged with a full-precision base model at inference time.

**When to use QLoRA over LoRA:**

- Your GPU has less than 4 GB of available VRAM
- You are experimenting and want faster iteration (QLoRA loads the model faster)
- Your dataset is small and quality differences are negligible

**When to prefer standard LoRA:**

- You have sufficient VRAM and want the highest quality
- You are training on a large dataset (thousands of examples) where precision matters
- You plan to merge the adapter into the base model weights for deployment

### Step 9: Evaluate the Fine-Tuned Model

Load the base model with the adapter applied and test it against prompts from and outside the training set:

```python
from unsloth import FastLanguageModel

# Load the base model with the LoRA adapter merged in
model, tokenizer = FastLanguageModel.from_pretrained(
  model_name="/opt/app-root/src/fine-tuning/outputs",  # Path to adapter weights
  max_seq_length=2048,
  load_in_4bit=False,
)

# Enable faster inference
FastLanguageModel.for_inference(model)

def generate_response(prompt, system_prompt=None):
  """Generate a response using the fine-tuned model."""
  messages = []
  if system_prompt:
    messages.append({"role": "system", "content": system_prompt})
  messages.append({"role": "user", "content": prompt})

  input_ids = tokenizer.apply_chat_template(
    messages, tokenize=True, add_generation_prompt=True, return_tensors="pt"
  ).to(model.device)

  output = model.generate(
    input_ids=input_ids,
    max_new_tokens=512,
    temperature=0.7,
    do_sample=True,
  )

  response = tokenizer.decode(output[0][input_ids.shape[-1]:], skip_special_tokens=True)
  return response

# Test with the ShopInsights system prompt
system = "You are a ShopInsights product analyst. You provide clear, data-driven answers about e-commerce metrics. Always include the metric definition, how it is calculated, and a benchmark range."

# Test 1: A topic from the training data (should show strong adaptation)
print("=== Test 1: In-domain (trained topic) ===")
print(generate_response("What is AOV and why does it matter?", system))
print()

# Test 2: A related topic NOT in the training data (tests generalization)
print("=== Test 2: Out-of-domain (related but untrained) ===")
print(generate_response("How do I measure the effectiveness of email marketing campaigns?", system))
print()

# Test 3: Without the system prompt (shows how much the style persists)
print("=== Test 3: Without system prompt ===")
print(generate_response("What metrics should I track for an online store?"))
```

**What to look for in the output:**

- **Test 1** should produce a response closely matching the style and structure of your training data -- metric definition, formula, benchmark range, and a practical recommendation.
- **Test 2** tests whether the model generalizes the ShopInsights analyst persona to topics it was not explicitly trained on. With only 15 examples, generalization will be limited.
- **Test 3** shows how much the fine-tuning affects the model's default behavior without the system prompt.

With a 15-example dataset, do not expect dramatic changes -- the model will adopt some of the response structure (definition, calculation, benchmark, recommendation) but will still lean heavily on its base knowledge. A production fine-tuning run would use hundreds or thousands of examples.

### Step 10: Upload Adapter Weights to S3

Workbench storage is ephemeral -- if the workbench pod restarts, local files are lost (unless backed by a PVC). Save the adapter weights to an S3-compatible object store for persistence:

```python
import boto3
import os

# S3 connection details (replace with your values)
s3_endpoint = os.environ.get("AWS_S3_ENDPOINT", "https://s3.amazonaws.com")
s3_bucket = os.environ.get("AWS_S3_BUCKET", "my-model-bucket")
s3_access_key = os.environ.get("AWS_ACCESS_KEY_ID")
s3_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")

s3 = boto3.client(
  "s3",
  endpoint_url=s3_endpoint,
  aws_access_key_id=s3_access_key,
  aws_secret_access_key=s3_secret_key,
)

# Upload all files from the output directory
output_dir = "/opt/app-root/src/fine-tuning/outputs"
s3_prefix = "adapters/shopinsights-analyst/v1"

for root, dirs, files in os.walk(output_dir):
  for file in files:
    local_path = os.path.join(root, file)
    relative_path = os.path.relpath(local_path, output_dir)
    s3_key = f"{s3_prefix}/{relative_path}"
    s3.upload_file(local_path, s3_bucket, s3_key)
    print(f"Uploaded: {s3_key}")

print(f"\nAll adapter files uploaded to s3://{s3_bucket}/{s3_prefix}/")
```

If you do not have S3 configured, you can skip this step -- the adapter weights will persist in the workbench as long as the PVC is not deleted. However, S3 is the recommended approach for production workflows because it decouples the adapter from the workbench lifecycle.

Alternatively, use the `oc` CLI to copy files from the workbench pod:

```bash
# From your local machine or a terminal with oc access
oc cp <workbench-pod>:/opt/app-root/src/fine-tuning/outputs ./adapter-weights -n <your-project>
```

## Verification

Confirm the lesson succeeded by checking these items:

1. **Training Hub is installed:**

```python
from training_hub import lora_sft
print("OK")
```

2. **Dataset exists and is valid:**

```bash
wc -l /opt/app-root/src/fine-tuning/shopinsights_analyst.jsonl
# Expected: 15
```

3. **Adapter weights were saved:**

```bash
ls -la /opt/app-root/src/fine-tuning/outputs/
# Should contain: adapter_model.safetensors, adapter_config.json
```

4. **Adapter config shows correct LoRA parameters:**

```python
import json
with open("/opt/app-root/src/fine-tuning/outputs/adapter_config.json") as f:
  config = json.load(f)
print(f"LoRA rank: {config.get('r')}")
print(f"LoRA alpha: {config.get('lora_alpha')}")
print(f"Base model: {config.get('base_model_name_or_path')}")
```

5. **Inference produces domain-specific responses:**

```python
# The fine-tuned model should produce responses that include
# metric definitions, calculations, and benchmark ranges
# in the ShopInsights analyst style
response = generate_response("What is AOV?", system)
assert len(response) > 100, "Response too short -- model may not have loaded correctly"
print("Inference OK")
```

## K8s vs OpenShift AI Comparison

| Aspect | Kubernetes | OpenShift AI |
|--------|-----------|--------------|
| Training environment | Build custom container, write Job/PyTorchJob YAML | Open workbench, `pip install`, run Python |
| GPU access | Configure device plugin, write resource requests | Workbench pre-configured with GPU access |
| Training framework | Install and configure PEFT/TRL/Unsloth manually | `pip install training-hub[lora]` -- one function call |
| Checkpoint storage | Mount PVC or configure S3 in your training script | Workbench PVC + S3 upload utility |
| Monitoring | Tail pod logs with `kubectl logs` | JupyterLab output + TensorBoard (if configured) |
| Iteration speed | Rebuild container for each dependency change | Live `pip install` in notebook, iterate in seconds |
| QLoRA support | Manual bitsandbytes/GPTQ configuration | `load_in_4bit=True` parameter |

## Key Takeaways

- Training Hub is a Tier 3 Python library that reduces LoRA fine-tuning to a single function call (`lora_sft`), handling framework selection and memory optimization automatically.
- LoRA produces small adapter weight files (~10-50 MB) instead of a full model copy, making fine-tuning practical on limited GPU hardware.
- QLoRA further reduces VRAM requirements by quantizing the base model to 4-bit during training, with minimal quality impact for most tasks.
- The Unsloth backend provides approximately 2x speed improvement and 70% VRAM reduction compared to standard Hugging Face training, and Training Hub selects it automatically.
- A well-structured dataset in the messages format (system/user/assistant) teaches the model both domain knowledge and response style. Even 15 examples can shift behavior, though production use cases need hundreds or thousands.
- Adapter weights must be persisted to S3 or a PVC -- workbench local storage is ephemeral.

## Cleanup

Remove the training artifacts from the workbench to free disk space:

```bash
# Remove training outputs
rm -rf /opt/app-root/src/fine-tuning/outputs
rm -rf /opt/app-root/src/fine-tuning/outputs-qlora

# Remove the dataset (optional -- it is small)
rm -f /opt/app-root/src/fine-tuning/shopinsights_analyst.jsonl

# Remove the Hugging Face model cache (frees several GB)
rm -rf ~/.cache/huggingface/hub/models--google--gemma-4-E4B-it
```

If you uploaded adapter weights to S3, they persist independently of the workbench.

Do **not** delete the adapter weights if you plan to continue to L1-M3.3, where you will deploy the fine-tuned model for serving.

## Next Steps

In the next lesson, [L1-M3.3 -- Deploying a Fine-Tuned Model](../3_deploying_fine_tuned/), you will take the LoRA adapter weights produced in this lesson and deploy them alongside the base Gemma4-E4B model using vLLM's LoRA adapter support. The fine-tuned model will be accessible through the same OpenAI-compatible API you used in L1-M2.3, but with the ShopInsights analyst behavior baked in.
