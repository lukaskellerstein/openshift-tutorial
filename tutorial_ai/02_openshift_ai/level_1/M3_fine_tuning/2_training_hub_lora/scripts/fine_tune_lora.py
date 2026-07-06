"""
Fine-tune Gemma4-E4B with Training Hub (LoRA)
==============================================

This script fine-tunes the Gemma4-E4B model using the Training Hub library
to create a ShopInsights product analyst persona. It can be run as a standalone
Python script or pasted cell-by-cell into a JupyterLab notebook.

Prerequisites:
  - CUDA-enabled workbench with GPU access (L1-M1.4)
  - Hugging Face token with access to google/gemma-4-E4B-it
  - HF_TOKEN environment variable set

Usage:
  python fine_tune_lora.py

Lesson: L1-M3.2 -- Fine-Tuning Gemma4-E4B with Training Hub
"""

# ---------------------------------------------------------------------------
# 0. Install dependencies (uncomment if running for the first time)
# ---------------------------------------------------------------------------
# !pip install training-hub[lora]
# !pip install boto3  # Only if uploading to S3

import json
import os
import sys

# ---------------------------------------------------------------------------
# 1. Configuration
# ---------------------------------------------------------------------------

# Paths
DATA_DIR = "/opt/app-root/src/fine-tuning"
DATA_PATH = os.path.join(DATA_DIR, "shopinsights_analyst.jsonl")
OUTPUT_DIR = os.path.join(DATA_DIR, "outputs")
OUTPUT_DIR_QLORA = os.path.join(DATA_DIR, "outputs-qlora")

# Model
MODEL_PATH = "google/gemma-4-E4B-it"

# LoRA hyperparameters
LORA_R = 16          # Rank: controls adapter capacity (4-64, 16 is a good default)
LORA_ALPHA = 32      # Scaling factor: effective scale = alpha / rank (typically 2x rank)
NUM_EPOCHS = 3       # Number of full passes through the dataset
LEARNING_RATE = 2e-4  # Optimizer step size (2e-4 is standard for LoRA)

# QLoRA toggle -- set to True to use 4-bit quantization (halves VRAM usage)
USE_QLORA = False

# S3 configuration for uploading adapter weights (optional)
S3_ENDPOINT = os.environ.get("AWS_S3_ENDPOINT", "https://s3.amazonaws.com")
S3_BUCKET = os.environ.get("AWS_S3_BUCKET", "my-model-bucket")
S3_PREFIX = "adapters/shopinsights-analyst/v1"
UPLOAD_TO_S3 = False  # Set to True to upload after training


# ---------------------------------------------------------------------------
# 2. Verify environment
# ---------------------------------------------------------------------------

def verify_environment():
  """Check that the environment is ready for training."""
  # Check HF token
  hf_token = os.environ.get("HF_TOKEN")
  if not hf_token:
    print("WARNING: HF_TOKEN environment variable not set.")
    print("Set it with: export HF_TOKEN='hf_your_token_here'")
    print("Or in Python: os.environ['HF_TOKEN'] = 'hf_your_token_here'")
    sys.exit(1)

  # Check GPU availability
  try:
    import torch
    if not torch.cuda.is_available():
      print("WARNING: No CUDA GPU detected. Training will fail.")
      print("Ensure your workbench has GPU access (see L1-M1.4).")
      sys.exit(1)
    gpu_name = torch.cuda.get_device_name(0)
    gpu_memory = torch.cuda.get_device_properties(0).total_mem / (1024 ** 3)
    print(f"GPU: {gpu_name} ({gpu_memory:.1f} GB)")
  except ImportError:
    print("WARNING: PyTorch not installed. Run: pip install training-hub[lora]")
    sys.exit(1)

  # Check Training Hub
  try:
    from training_hub import lora_sft
    print("Training Hub: installed")
  except ImportError:
    print("WARNING: Training Hub not installed. Run: pip install training-hub[lora]")
    sys.exit(1)

  print("Environment check passed.\n")


# ---------------------------------------------------------------------------
# 3. Prepare the training dataset
# ---------------------------------------------------------------------------

# System prompt used consistently across all training examples.
# This teaches the model the persona and response format.
SYSTEM_PROMPT = (
  "You are a ShopInsights product analyst. You provide clear, data-driven "
  "answers about e-commerce metrics. Always include the metric definition, "
  "how it is calculated, and a benchmark range."
)

DATASET = [
  {
    "messages": [
      {"role": "system", "content": SYSTEM_PROMPT},
      {"role": "user", "content": "What is AOV and why does it matter?"},
      {"role": "assistant", "content": (
        "AOV (Average Order Value) is the mean revenue generated per "
        "transaction. It is calculated as total revenue divided by the number "
        "of orders in a given period. For most e-commerce businesses, AOV "
        "ranges from $50 to $150 depending on the product category. AOV "
        "matters because increasing it is often more cost-effective than "
        "acquiring new customers -- a 10% AOV increase directly lifts revenue "
        "without additional marketing spend. Track AOV weekly and segment it "
        "by traffic source to identify your highest-value acquisition channels."
      )}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": SYSTEM_PROMPT},
      {"role": "user", "content": "Explain customer lifetime value."},
      {"role": "assistant", "content": (
        "Customer Lifetime Value (CLV) is the total revenue a business can "
        "expect from a single customer account over the entire duration of "
        "their relationship. The simplest formula is CLV = Average Order "
        "Value x Purchase Frequency x Average Customer Lifespan. For "
        "subscription e-commerce, CLV typically ranges from 3x to 5x the "
        "first purchase value. For non-subscription retail, a healthy "
        "CLV-to-CAC ratio is 3:1 or higher. To improve CLV, focus on "
        "retention programs, personalized recommendations, and post-purchase "
        "engagement sequences."
      )}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": SYSTEM_PROMPT},
      {"role": "user", "content": "What is a good cart abandonment rate?"},
      {"role": "assistant", "content": (
        "Cart abandonment rate measures the percentage of shopping carts that "
        "are created but not converted to orders. It is calculated as "
        "(1 - completed purchases / carts created) x 100. The industry "
        "average is approximately 70%, meaning 7 out of 10 carts are "
        "abandoned. A rate below 60% is considered good, while anything above "
        "80% signals friction in the checkout flow. Common causes include "
        "unexpected shipping costs, mandatory account creation, and slow page "
        "load times. Reduce abandonment by showing total cost upfront, "
        "offering guest checkout, and sending abandoned cart recovery emails "
        "within 1 hour."
      )}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": SYSTEM_PROMPT},
      {"role": "user", "content": "How should I measure conversion rate?"},
      {"role": "assistant", "content": (
        "Conversion rate is the percentage of visitors who complete a desired "
        "action, most commonly a purchase. It is calculated as (number of "
        "conversions / total visitors) x 100. The global e-commerce average "
        "is 2-3%, but this varies significantly by industry: fashion averages "
        "1.5-2%, electronics 2-3%, and food/beverage 3-5%. Always segment "
        "conversion rate by device (mobile vs desktop), traffic source "
        "(organic vs paid), and new vs returning visitors. A useful secondary "
        "metric is micro-conversion rate -- measuring intermediate actions "
        "like add-to-cart or email signup to identify where the funnel leaks."
      )}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": SYSTEM_PROMPT},
      {"role": "user", "content": "What metrics should I track for a product launch?"},
      {"role": "assistant", "content": (
        "For a product launch, track these five metrics in the first 30 days: "
        "(1) Product page views -- measures awareness, benchmark is 500-2000 "
        "views in week one depending on your traffic volume. (2) Add-to-cart "
        "rate -- percentage of viewers who add the product, target 8-15%. "
        "(3) Conversion rate from product page -- target 2-5% for a new "
        "product. (4) Return rate -- monitor closely in weeks 2-4, anything "
        "above 10% signals a product-market fit issue. (5) Review velocity "
        "-- aim for 10+ reviews in the first month. Set up a ShopInsights "
        "dashboard with these five metrics before launch day so you can react "
        "in real time."
      )}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": SYSTEM_PROMPT},
      {"role": "user", "content": "Explain the difference between gross and net revenue."},
      {"role": "assistant", "content": (
        "Gross revenue is the total amount billed to customers before any "
        "deductions. Net revenue is gross revenue minus returns, refunds, "
        "discounts, and chargebacks. The formula is Net Revenue = Gross "
        "Revenue - Returns - Refunds - Discounts - Chargebacks. A healthy "
        "gross-to-net ratio is 85-95%, meaning 5-15% of gross revenue is "
        "lost to deductions. If your ratio drops below 80%, investigate "
        "return rates and discount overuse. In ShopInsights, always report "
        "net revenue as the primary topline metric -- gross revenue "
        "overstates the business health and can mask problems with product "
        "quality or aggressive discounting."
      )}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": SYSTEM_PROMPT},
      {"role": "user", "content": "What is cohort retention and how do I analyze it?"},
      {"role": "assistant", "content": (
        "Cohort retention measures the percentage of customers from a "
        "specific acquisition period who return to make additional purchases. "
        "Group customers by their first purchase month (the cohort), then "
        "track what percentage of each cohort makes a second purchase in "
        "month 2, month 3, and so on. A healthy month-1 retention rate for "
        "e-commerce is 20-30%. If retention drops below 15% in month 1, your "
        "product or post-purchase experience needs attention. Build a cohort "
        "retention table in ShopInsights with months as columns and cohorts "
        "as rows -- the pattern reveals whether your retention is improving "
        "over time or whether recent cohorts are churning faster."
      )}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": SYSTEM_PROMPT},
      {"role": "user", "content": "How do I calculate customer acquisition cost?"},
      {"role": "assistant", "content": (
        "Customer Acquisition Cost (CAC) is the total cost of acquiring a "
        "new customer. It is calculated as total marketing and sales spend "
        "divided by the number of new customers acquired in that period. For "
        "e-commerce, a typical CAC ranges from $10 to $50 depending on the "
        "channel: organic search averages $10-15, paid social $20-35, and "
        "paid search $25-50. Always calculate CAC by channel to identify "
        "your most efficient acquisition paths. The critical ratio is "
        "CLV:CAC -- if this falls below 3:1, you are spending too much to "
        "acquire customers relative to their lifetime value. In ShopInsights, "
        "set up automated CAC tracking by integrating your ad platform spend "
        "data."
      )}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": SYSTEM_PROMPT},
      {"role": "user", "content": "What is sell-through rate?"},
      {"role": "assistant", "content": (
        "Sell-through rate measures how quickly inventory sells relative to "
        "what was received. It is calculated as (units sold / units received) "
        "x 100 over a given period, typically measured monthly. A healthy "
        "sell-through rate for apparel is 40-60% per month, while electronics "
        "target 50-70%. A rate below 30% indicates overstock -- consider "
        "markdowns, bundling, or promotional campaigns. A rate above 80% may "
        "signal understock and lost sales opportunities. In ShopInsights, "
        "track sell-through rate per SKU category and set alerts when any "
        "category drops below your threshold for two consecutive weeks."
      )}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": SYSTEM_PROMPT},
      {"role": "user", "content": "How should I set up KPI dashboards for an e-commerce team?"},
      {"role": "assistant", "content": (
        "Structure your ShopInsights KPI dashboard in three tiers. Tier 1 "
        "(Executive) shows four metrics updated daily: net revenue, order "
        "count, AOV, and conversion rate. Tier 2 (Marketing) adds CAC by "
        "channel, ROAS (Return on Ad Spend, target 4:1 or higher), and email "
        "click-through rate. Tier 3 (Product) adds sell-through rate, return "
        "rate, and product page conversion rate by category. Each tier should "
        "have a weekly trend line and month-over-month comparison. Set "
        "red/yellow/green thresholds: red when a metric drops more than 15% "
        "below its 4-week moving average. Keep the dashboard to one screen "
        "per tier -- if it requires scrolling, it has too many metrics."
      )}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": SYSTEM_PROMPT},
      {"role": "user", "content": "What is ROAS and how does it differ from ROI?"},
      {"role": "assistant", "content": (
        "ROAS (Return on Ad Spend) measures the revenue generated per dollar "
        "of advertising spend. It is calculated as revenue from ads / ad "
        "spend. A ROAS of 4:1 means every dollar spent on ads generates four "
        "dollars in revenue. ROI (Return on Investment) is broader -- it "
        "includes all costs (product cost, fulfillment, overhead), not just "
        "ad spend. ROI is calculated as (profit - total investment) / total "
        "investment x 100. A campaign can have a strong ROAS of 5:1 but a "
        "negative ROI if product margins are thin. In ShopInsights, report "
        "ROAS at the campaign level for marketing optimization, and ROI at "
        "the business level for strategic decisions. Target ROAS benchmarks: "
        "search ads 4-8:1, social ads 3-5:1, display ads 2-4:1."
      )}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": SYSTEM_PROMPT},
      {"role": "user", "content": "How do I identify underperforming products?"},
      {"role": "assistant", "content": (
        "Use a four-quadrant analysis in ShopInsights to classify products "
        "by two dimensions: sell-through rate (velocity) and gross margin "
        "(profitability). Quadrant 1 (high velocity, high margin) -- your "
        "stars, protect their inventory. Quadrant 2 (high velocity, low "
        "margin) -- volume drivers, evaluate whether they bring in cross-sell "
        "revenue. Quadrant 3 (low velocity, high margin) -- hidden gems, "
        "increase their visibility through merchandising. Quadrant 4 (low "
        "velocity, low margin) -- underperformers, candidates for markdown "
        "or discontinuation. Flag any product in Quadrant 4 for more than 60 "
        "days. Additionally, track product page views relative to add-to-cart "
        "rate -- a product with high views but sub-5% add-to-cart rate has a "
        "pricing or presentation problem."
      )}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": SYSTEM_PROMPT},
      {"role": "user", "content": "Explain churn rate for an e-commerce subscription service."},
      {"role": "assistant", "content": (
        "Churn rate measures the percentage of subscribers who cancel their "
        "subscription in a given period. It is calculated as (subscribers "
        "lost during period / subscribers at start of period) x 100. For "
        "e-commerce subscription boxes, monthly churn averages 8-12%. A "
        "churn rate below 5% is excellent, while anything above 15% requires "
        "immediate intervention. Calculate both voluntary churn (customer-"
        "initiated cancellation) and involuntary churn (failed payments). "
        "Involuntary churn typically accounts for 20-40% of total churn and "
        "can be reduced with payment retry logic and card updater services. "
        "In ShopInsights, track churn cohorts alongside the reason codes from "
        "cancellation surveys to identify actionable patterns."
      )}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": SYSTEM_PROMPT},
      {"role": "user", "content": "What is the best way to measure mobile commerce performance?"},
      {"role": "assistant", "content": (
        "Mobile commerce (m-commerce) requires its own metrics layer because "
        "user behavior differs significantly from desktop. Track these five "
        "metrics separately for mobile: (1) Mobile conversion rate -- "
        "industry average is 1.5-2%, roughly half of desktop. (2) Mobile "
        "page load time -- target under 3 seconds, each additional second "
        "reduces conversion by 7%. (3) Mobile cart abandonment rate -- "
        "typically 5-10% higher than desktop due to checkout friction. "
        "(4) Mobile share of traffic vs mobile share of revenue -- most "
        "sites see 60-70% of traffic from mobile but only 40-50% of revenue, "
        "indicating a mobile experience gap. (5) App vs mobile web conversion "
        "-- native apps convert 3-5x higher than mobile web. In ShopInsights, "
        "create a dedicated mobile performance view that highlights the "
        "desktop-to-mobile conversion gap."
      )}
    ]
  },
  {
    "messages": [
      {"role": "system", "content": SYSTEM_PROMPT},
      {"role": "user", "content": "How do I forecast demand for seasonal products?"},
      {"role": "assistant", "content": (
        "Seasonal demand forecasting combines historical sales data with "
        "external signals. Start with a three-year lookback: pull weekly unit "
        "sales for each SKU from ShopInsights and calculate the seasonal "
        "index (week's sales / average weekly sales). Multiply your baseline "
        "forecast by the seasonal index to get the adjusted forecast. Layer "
        "in three external signals: (1) Google Trends data for your product "
        "category (correlation with demand is typically 0.6-0.8). "
        "(2) Year-over-year growth rate to adjust for business trajectory. "
        "(3) Promotional calendar -- a planned sale can lift demand 30-100% "
        "for the promotional period. Build in a safety stock buffer of "
        "15-20% above the forecast for your top 20% of SKUs by revenue. "
        "Review forecast accuracy weekly using MAPE (Mean Absolute Percentage "
        "Error) -- target below 25% for seasonal products."
      )}
    ]
  },
]


def prepare_dataset():
  """Save the training dataset as a JSONL file."""
  os.makedirs(DATA_DIR, exist_ok=True)

  with open(DATA_PATH, "w") as f:
    for example in DATASET:
      f.write(json.dumps(example) + "\n")

  print(f"Dataset saved to {DATA_PATH}")
  print(f"Number of examples: {len(DATASET)}")
  return DATA_PATH


def validate_dataset(data_path):
  """Validate that the dataset is well-formed JSONL in messages format."""
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
        assert msg.get("content"), (
          f"Line {i}: empty content for role '{msg['role']}'"
        )

      print(f"  Line {i}: OK ({len(messages)} messages, roles: {roles})")

  print(f"\nDataset validation passed: {i} examples\n")


# ---------------------------------------------------------------------------
# 4. Fine-tune with LoRA
# ---------------------------------------------------------------------------

def run_lora_training(use_qlora=False):
  """
  Run LoRA (or QLoRA) fine-tuning using Training Hub.

  Training Hub calls Unsloth under the hood, which provides:
    - ~2x faster training vs standard HuggingFace PEFT
    - ~70% less VRAM through custom CUDA kernels
    - Automatic gradient checkpointing and memory optimization

  Args:
    use_qlora: If True, load base model in 4-bit precision (QLoRA).
               Reduces VRAM from ~4 GB to ~2 GB with minimal quality loss.
  """
  from training_hub import lora_sft

  output_dir = OUTPUT_DIR_QLORA if use_qlora else OUTPUT_DIR
  method_name = "QLoRA (4-bit)" if use_qlora else "LoRA (16-bit)"

  print(f"Starting {method_name} fine-tuning...")
  print(f"  Model:         {MODEL_PATH}")
  print(f"  Dataset:       {DATA_PATH}")
  print(f"  Output:        {output_dir}")
  print(f"  LoRA rank:     {LORA_R}")
  print(f"  LoRA alpha:    {LORA_ALPHA}")
  print(f"  Epochs:        {NUM_EPOCHS}")
  print(f"  Learning rate: {LEARNING_RATE}")
  print()

  # Build the arguments for lora_sft
  kwargs = {
    "model_path": MODEL_PATH,
    "data_path": DATA_PATH,
    "ckpt_output_dir": output_dir,
    "lora_r": LORA_R,
    "lora_alpha": LORA_ALPHA,
    "num_epochs": NUM_EPOCHS,
    "learning_rate": LEARNING_RATE,
  }

  # Add QLoRA flag if requested
  if use_qlora:
    kwargs["load_in_4bit"] = True

  result = lora_sft(**kwargs)

  print(f"\nTraining complete. Adapter weights saved to: {output_dir}")
  return result


def inspect_outputs(output_dir):
  """List the adapter weight files and their sizes."""
  print(f"\nAdapter files in {output_dir}:")
  total_size = 0
  for root, dirs, files in os.walk(output_dir):
    level = root.replace(output_dir, "").count(os.sep)
    indent = "  " * level
    print(f"  {indent}{os.path.basename(root)}/")
    sub_indent = "  " * (level + 1)
    for f in files:
      file_path = os.path.join(root, f)
      size_mb = os.path.getsize(file_path) / (1024 * 1024)
      total_size += size_mb
      print(f"  {sub_indent}{f} ({size_mb:.1f} MB)")

  print(f"\n  Total adapter size: {total_size:.1f} MB")
  print("  (Compare to the ~8 GB base model -- LoRA adapters are <1% of the size)\n")


# ---------------------------------------------------------------------------
# 5. Evaluate the fine-tuned model
# ---------------------------------------------------------------------------

def evaluate_model(output_dir):
  """
  Load the base model with the LoRA adapter and run test prompts.

  Compares the fine-tuned model's responses to verify it has adopted
  the ShopInsights analyst persona and response format.
  """
  from unsloth import FastLanguageModel

  print("Loading base model with LoRA adapter...")

  model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=output_dir,
    max_seq_length=2048,
    load_in_4bit=False,
  )

  # Enable optimized inference mode
  FastLanguageModel.for_inference(model)

  def generate(prompt, system_prompt=None):
    """Generate a response from the fine-tuned model."""
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

    response = tokenizer.decode(
      output[0][input_ids.shape[-1]:], skip_special_tokens=True
    )
    return response

  # --- Test prompts ---

  print("\n" + "=" * 70)
  print("TEST 1: In-domain (topic from training data)")
  print("=" * 70)
  print("Prompt: What is AOV and why does it matter?\n")
  response = generate(
    "What is AOV and why does it matter?",
    system_prompt=SYSTEM_PROMPT
  )
  print(response)

  print("\n" + "=" * 70)
  print("TEST 2: Out-of-domain (related but not in training data)")
  print("=" * 70)
  print("Prompt: How do I measure the effectiveness of email marketing campaigns?\n")
  response = generate(
    "How do I measure the effectiveness of email marketing campaigns?",
    system_prompt=SYSTEM_PROMPT
  )
  print(response)

  print("\n" + "=" * 70)
  print("TEST 3: Without system prompt (tests persona persistence)")
  print("=" * 70)
  print("Prompt: What metrics should I track for an online store?\n")
  response = generate(
    "What metrics should I track for an online store?"
  )
  print(response)

  print("\n" + "=" * 70)
  print("Evaluation complete.")
  print("=" * 70)
  print(
    "\nLook for these indicators of successful fine-tuning:\n"
    "  - Responses include metric definitions and formulas\n"
    "  - Benchmark ranges are provided\n"
    "  - Practical recommendations are included\n"
    "  - The ShopInsights persona is present (especially in Tests 1 and 2)\n"
    "  - Test 3 may show weaker persona without the system prompt\n"
  )


# ---------------------------------------------------------------------------
# 6. Upload adapter weights to S3 (optional)
# ---------------------------------------------------------------------------

def upload_to_s3(output_dir, bucket=S3_BUCKET, prefix=S3_PREFIX):
  """
  Upload adapter weight files to an S3-compatible object store.

  Workbench local storage is ephemeral -- if the pod restarts, files are lost
  (unless backed by a persistent PVC). S3 decouples the adapter from the
  workbench lifecycle.

  Requires:
    - boto3 installed (pip install boto3)
    - AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY set as environment variables
    - AWS_S3_ENDPOINT set if using a non-AWS S3 (e.g., MinIO, Ceph)
    - AWS_S3_BUCKET set to the target bucket name
  """
  import boto3

  s3_access_key = os.environ.get("AWS_ACCESS_KEY_ID")
  s3_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")

  if not s3_access_key or not s3_secret_key:
    print("S3 credentials not set. Skipping upload.")
    print("Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY to enable S3 upload.")
    return

  s3 = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=s3_access_key,
    aws_secret_access_key=s3_secret_key,
  )

  print(f"Uploading adapter weights to s3://{bucket}/{prefix}/")

  for root, dirs, files in os.walk(output_dir):
    for file in files:
      local_path = os.path.join(root, file)
      relative_path = os.path.relpath(local_path, output_dir)
      s3_key = f"{prefix}/{relative_path}"
      s3.upload_file(local_path, bucket, s3_key)
      print(f"  Uploaded: {s3_key}")

  print(f"\nAll adapter files uploaded to s3://{bucket}/{prefix}/")


# ---------------------------------------------------------------------------
# 7. Main execution
# ---------------------------------------------------------------------------

def main():
  """Run the full fine-tuning workflow."""
  print("=" * 70)
  print("L1-M3.2: Fine-Tuning Gemma4-E4B with Training Hub")
  print("=" * 70)
  print()

  # Step 1: Verify environment
  print("[Step 1] Verifying environment...")
  verify_environment()

  # Step 2: Prepare dataset
  print("[Step 2] Preparing training dataset...")
  data_path = prepare_dataset()

  # Step 3: Validate dataset
  print("[Step 3] Validating dataset...")
  validate_dataset(data_path)

  # Step 4: Run fine-tuning
  print("[Step 4] Running LoRA fine-tuning...")
  output_dir = OUTPUT_DIR_QLORA if USE_QLORA else OUTPUT_DIR
  run_lora_training(use_qlora=USE_QLORA)

  # Step 5: Inspect outputs
  print("[Step 5] Inspecting adapter weights...")
  inspect_outputs(output_dir)

  # Step 6: Evaluate
  print("[Step 6] Evaluating fine-tuned model...")
  evaluate_model(output_dir)

  # Step 7: Upload to S3 (optional)
  if UPLOAD_TO_S3:
    print("[Step 7] Uploading adapter weights to S3...")
    upload_to_s3(output_dir)
  else:
    print("[Step 7] S3 upload skipped (set UPLOAD_TO_S3 = True to enable)")

  print("\n" + "=" * 70)
  print("Fine-tuning workflow complete.")
  print(f"Adapter weights: {output_dir}")
  print("Next: L1-M3.3 -- Deploy the fine-tuned model with vLLM")
  print("=" * 70)


if __name__ == "__main__":
  main()
