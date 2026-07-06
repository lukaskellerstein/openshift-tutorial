# L2-2.2 — Model Optimization for Production

**Level:** Practitioner
**Duration:** 45 min

## Overview

Serving full-precision models at scale requires expensive GPU hardware. Model optimization techniques — quantization, sparsity, and speculative decoding — reduce resource requirements while preserving quality. This lesson covers the Red Hat AI Model Optimization Toolkit (based on LLM Compressor) for quantization and sparsity, and the Speculators library for speculative decoding. By the end, you will have quantized a Granite model to FP8, served it with vLLM, and measured the VRAM savings.

## Prerequisites

- Completed L2-2.1 (Modular Model Customization with InstructLab)
- RHEL AI instance with GPU (NVIDIA Ampere or newer recommended — AMD ROCm does NOT include the Optimization Toolkit)
- Python 3.10+ with pip access
- Sufficient disk space for model weights (~16 GB for an 8B model)

## Concepts

### Red Hat AI Model Optimization Toolkit

The Model Optimization Toolkit is part of Red Hat AI Inference, available on RHEL AI. It is based on the upstream LLM Compressor project (v0.10.0) and carries **Technology Preview** status — it is functional but does not carry a production SLA.

The toolkit saves optimized models in the **compressed-tensors** format, a Safetensors extension that vLLM natively understands. This means you can quantize a model and serve it with vLLM without any format conversion step.

### Quantization Methods

Quantization reduces the precision of model weights (and optionally activations) to shrink memory footprint and increase inference speed. The toolkit supports several methods:

| Method | Type | Description | GPU Support |
|--------|------|-------------|-------------|
| FP8 (W8A8) | Dynamic per-token | 8-bit floating point, best quality/compression tradeoff | NVIDIA Ampere+, AMD MI300X |
| GPTQ (W4A16) | Weight-only INT4 | Post-training quantization with calibration data | NVIDIA Ampere+, AMD |
| AWQ (W4A16) | Weight-only INT4 | Activation-aware weight quantization | NVIDIA Ampere+ |
| MXFP4 (W4A16) | Microscale FP4 | Experimental, dense models only | NVIDIA Ampere+ |
| NVFP4 | NVIDIA 4-bit FP | Blackwell architecture exclusive | NVIDIA Blackwell only |
| INT8 (W8A8) | SmoothQuant | For older NVIDIA GPUs without FP8 support | NVIDIA Turing, Ampere |

Important compatibility notes:

- NVIDIA Blackwell GPUs do **not** support INT8 in vLLM — use FP8 or NVFP4 instead.
- NVFP4 is Blackwell-exclusive and will not work on Ampere or Hopper.
- Pre-quantized models published under the [RedHatAI](https://huggingface.co/RedHatAI) HuggingFace organization recover >99% of baseline accuracy, saving you the quantization step entirely.

### Sparsity

Sparsity reduces computation by zeroing out weight values that contribute least to model output. The toolkit uses **SparseGPT** for unstructured sparsity, which can be combined with quantization for maximum compression. Sparse models require vLLM's sparse kernel support for inference speedup.

### Speculators Library

[Speculators](https://huggingface.co/vllm-project) (Apache 2.0, v0.5.0) implements speculative decoding: a small "draft" model predicts several tokens ahead, and the large "target" model verifies them in a single forward pass. When the draft model predicts correctly, you get multiple tokens for the cost of one target-model inference.

Key characteristics:

- **2-2.7x latency reduction** for interactive workloads (chat, code completion)
- **No quality loss** — the output is mathematically equivalent to the target model alone
- Published under the `vllm-project` organization on HuggingFace
- Best suited for latency-sensitive use cases; throughput-bound batch workloads see less benefit

### When to Use What

| Goal | Technique | Tradeoff |
|------|-----------|----------|
| Default optimization (Ampere/Hopper) | FP8 quantization | Minimal quality loss, ~2x VRAM reduction |
| Fit on smaller GPUs | GPTQ or AWQ (INT4) | More quality loss, ~4x VRAM reduction |
| Reduce latency for interactive use | Speculative decoding | Extra GPU memory for draft model |
| Maximum compression | Sparsity + quantization | Requires sparse kernel support in vLLM |

## Step-by-Step

### Step 1: Install the Optimization Toolkit

Install LLM Compressor on your RHEL AI instance.

```bash
pip install llmcompressor
```

Verify the installation:

```bash
python3 -c "import llmcompressor; print(llmcompressor.__version__)"
```

### Step 2: Quantize a Model to FP8

FP8 dynamic quantization is the recommended default. It requires no calibration data and preserves >99% of baseline accuracy.

Create a file `quantize_fp8.py`:

```python
from llmcompressor import oneshot
from llmcompressor.modifiers.quantization import QuantizationModifier

model_id = "RedHatAI/granite-4.1-8b-instruct"
output_dir = "./granite-4.1-8b-instruct-FP8"

recipe = QuantizationModifier(
    targets="Linear",
    scheme="FP8_DYNAMIC",
)

oneshot(
    model=model_id,
    recipe=recipe,
    output_dir=output_dir,
)

print(f"Quantized model saved to {output_dir}")
```

Run the quantization:

```bash
python3 quantize_fp8.py
```

This downloads the full-precision model, quantizes all linear layers to FP8, and saves the result in compressed-tensors format. On an A100 GPU, this takes approximately 5-10 minutes for an 8B model.

### Step 3: Quantize with GPTQ INT4 (Alternative)

When you need to fit a model on a GPU with less VRAM, INT4 quantization provides ~4x compression at the cost of slightly more quality degradation. GPTQ requires calibration data.

Create a file `quantize_gptq.py`:

```python
from llmcompressor import oneshot
from llmcompressor.modifiers.quantization import GPTQModifier

model_id = "RedHatAI/granite-4.1-8b-instruct"
output_dir = "./granite-4.1-8b-instruct-GPTQ-INT4"

recipe = GPTQModifier(
    targets="Linear",
    scheme="W4A16",
    ignore=["lm_head"],
)

oneshot(
    model=model_id,
    dataset="ultrachat_200k",
    recipe=recipe,
    output_dir=output_dir,
    num_calibration_samples=512,
)

print(f"Quantized model saved to {output_dir}")
```

```bash
python3 quantize_gptq.py
```

The `ignore=["lm_head"]` parameter keeps the output projection layer in full precision, which improves generation quality. The `num_calibration_samples=512` parameter controls how much calibration data GPTQ uses to determine optimal quantization scales.

### Step 4: Serve and Benchmark the Quantized Model

Serve both the original and FP8-quantized models with vLLM to compare VRAM usage and throughput.

Serve the FP8 model:

```bash
python3 -m vllm.entrypoints.openai.api_server \
  --model ./granite-4.1-8b-instruct-FP8 \
  --port 8000 \
  --max-model-len 4096
```

In a separate terminal, query the model:

```bash
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "./granite-4.1-8b-instruct-FP8",
    "messages": [{"role": "user", "content": "Explain Kubernetes pods in two sentences."}],
    "max_tokens": 100
  }' | python3 -m json.tool
```

Check VRAM usage while the model is loaded:

```bash
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
```

Compare these numbers against the full-precision model. You should see roughly 2x VRAM reduction with FP8 (e.g., ~8 GB for FP8 vs ~16 GB for FP16 on an 8B model).

### Step 5: Set Up Speculative Decoding

Install the Speculators library and configure vLLM to use a draft model for speculative decoding.

```bash
pip install speculators
```

Serve with speculative decoding enabled:

```bash
python3 -m vllm.entrypoints.openai.api_server \
  --model RedHatAI/granite-4.1-8b-instruct \
  --speculative-model vllm-project/granite-4.1-8b-instruct-speculators \
  --num-speculative-tokens 5 \
  --port 8001 \
  --max-model-len 4096
```

The `--num-speculative-tokens 5` parameter tells vLLM to have the draft model predict 5 tokens ahead before the target model verifies them. Higher values increase potential speedup but also increase the chance of rejection.

Measure latency by timing a request:

```bash
time curl -s http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "RedHatAI/granite-4.1-8b-instruct",
    "messages": [{"role": "user", "content": "Write a Python function that merges two sorted lists."}],
    "max_tokens": 200
  }' > /dev/null
```

Compare this against the same request without speculative decoding (port 8000). For interactive workloads, you should see 2-2.7x latency reduction.

## Verification

Confirm each optimization step produced the expected result:

| Check | Command | Expected Result |
|-------|---------|-----------------|
| FP8 model exists | `ls ./granite-4.1-8b-instruct-FP8/` | Model files in compressed-tensors format |
| FP8 model serves | `curl localhost:8000/v1/models` | Model listed and responding |
| VRAM reduced | `nvidia-smi` | ~8 GB for FP8 vs ~16 GB for FP16 (8B model) |
| Quality preserved | Query both models with the same prompt | Comparable response quality |
| Speculative decoding works | `curl localhost:8001/v1/chat/completions` | Responses with lower latency |

## Key Takeaways

- **FP8 is the recommended default quantization** for NVIDIA Ampere and Hopper GPUs. It requires no calibration data and achieves ~2x VRAM reduction with minimal quality loss (>99% accuracy retention).
- **INT4 (GPTQ/AWQ) cuts VRAM further** (~4x reduction) but introduces more quality tradeoff and requires calibration data. Use it when FP8 models still do not fit your target GPU.
- **Pre-quantized models on the RedHatAI HuggingFace** save you the quantization step entirely. Check for your target model before running quantization yourself.
- **Speculative decoding with Speculators** provides 2-2.7x latency reduction with mathematically equivalent output. It benefits interactive workloads (chat, code completion) more than batch processing.
- **Cross-reference:** The OpenShift AI track lesson L3-3.2 covers deploying these same optimization techniques on OpenShift AI with KServe and vLLM at cluster scale.

## Cleanup

```bash
# Remove quantized model directories
rm -rf ./granite-4.1-8b-instruct-FP8
rm -rf ./granite-4.1-8b-instruct-GPTQ-INT4

# Stop any running vLLM servers
pkill -f "vllm.entrypoints"

# Uninstall packages (optional)
pip uninstall llmcompressor speculators -y
```

## Next Steps

Continue to [L2-2.3 — RHEL AI Production Deployment](../3_production_deployment/) to learn how to configure RHEL AI for production use with systemd services, TLS, multi-model serving, and monitoring.
