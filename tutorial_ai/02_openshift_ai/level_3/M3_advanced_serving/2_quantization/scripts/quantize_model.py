#!/usr/bin/env python3
"""
Quantize a Hugging Face model to FP8 using LLM Compressor.

This script demonstrates the oneshot quantization workflow:
1. Load a pretrained model
2. Define a quantization recipe (FP8 W8A8)
3. Run oneshot compression with calibration data
4. Save the compressed model

Usage:
    python quantize_model.py \
        --model google/gemma-4-E4B-it \
        --output ./gemma-4-e4b-fp8 \
        --num-samples 512
"""

import argparse

from datasets import load_dataset
from llmcompressor import oneshot
from llmcompressor.modifiers.quantization import QuantizationModifier
from transformers import AutoModelForCausalLM, AutoTokenizer


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Quantize a model to FP8 using LLM Compressor"
    )
    parser.add_argument(
        "--model",
        default="google/gemma-4-E4B-it",
        help="Hugging Face model ID or local path (default: google/gemma-4-E4B-it)",
    )
    parser.add_argument(
        "--output",
        default="./gemma-4-e4b-fp8",
        help="Output directory for the quantized model (default: ./gemma-4-e4b-fp8)",
    )
    parser.add_argument(
        "--num-samples",
        type=int,
        default=512,
        help="Number of calibration samples (default: 512)",
    )
    parser.add_argument(
        "--max-seq-len",
        type=int,
        default=2048,
        help="Maximum sequence length for calibration data (default: 2048)",
    )
    args = parser.parse_args()

    # Load model and tokenizer
    print(f"Loading model: {args.model}")
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        torch_dtype="auto",
        device_map="auto",
    )
    tokenizer = AutoTokenizer.from_pretrained(args.model)

    # Load calibration dataset
    # FineWeb-Edu is a curated web text dataset suitable for general-purpose calibration.
    # For domain-specific models, replace with a dataset that matches your deployment domain.
    print(f"Loading calibration data ({args.num_samples} samples)...")
    ds = load_dataset("HuggingFaceFW/fineweb-edu", name="sample-10BT", split="train")
    ds = ds.shuffle(seed=42).select(range(args.num_samples))

    def preprocess(example):
        return tokenizer(
            example["text"], truncation=True, max_length=args.max_seq_len
        )

    ds = ds.map(preprocess, remove_columns=ds.column_names)

    # Define FP8 quantization recipe
    # - targets="Linear": quantize all Linear layers
    # - scheme="FP8_DYNAMIC": use FP8 with dynamically computed scale factors
    # - ignore=["lm_head"]: keep the output projection at full precision to preserve quality
    recipe = QuantizationModifier(
        targets="Linear",
        scheme="FP8_DYNAMIC",
        ignore=["lm_head"],
    )

    # Run oneshot quantization
    # This makes a single pass over the calibration data to compute scale factors,
    # then quantizes all targeted layers.
    print("Running FP8 quantization...")
    oneshot(
        model=model,
        dataset=ds,
        recipe=recipe,
        max_seq_length=args.max_seq_len,
        num_calibration_data=args.num_samples,
    )

    # Save compressed model
    # save_compressed=True writes the weights in the compressed-tensors format
    # that vLLM auto-detects at load time.
    print(f"Saving quantized model to: {args.output}")
    model.save_pretrained(args.output, save_compressed=True)
    tokenizer.save_pretrained(args.output)

    print("Done! Model is ready for vLLM deployment.")


if __name__ == "__main__":
    main()
