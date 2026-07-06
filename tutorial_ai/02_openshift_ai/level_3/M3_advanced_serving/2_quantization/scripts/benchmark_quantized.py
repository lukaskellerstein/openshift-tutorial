#!/usr/bin/env python3
"""
Benchmark original vs quantized model endpoints.

Measures:
- Latency: total response time (mean, p50, p95)
- Throughput: tokens per second
- Quality: response comparison on standardized prompts

Usage:
    python benchmark_quantized.py \
        --original-url https://original-model-endpoint.apps.example.com \
        --quantized-url https://quantized-model-endpoint.apps.example.com \
        --num-requests 20
"""

import argparse
import statistics
import time
from typing import Dict, List

import requests

BENCHMARK_PROMPTS = [
    "Explain the concept of containerization in three sentences.",
    "Write a Python function to calculate the Fibonacci sequence.",
    "What are the key differences between SQL and NoSQL databases?",
    "Summarize the benefits of microservices architecture.",
    "Explain Kubernetes pods to a junior developer.",
]


def send_request(
    url: str, model_name: str, prompt: str, max_tokens: int = 150
) -> Dict:
    """Send a single inference request and measure timing."""
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.1,  # low temp for reproducibility
    }

    start = time.time()
    resp = requests.post(
        f"{url}/v1/chat/completions",
        json=payload,
        headers={"Content-Type": "application/json"},
        verify=False,
        timeout=120,
    )
    elapsed = time.time() - start
    resp.raise_for_status()
    data = resp.json()

    completion_tokens = data["usage"]["completion_tokens"]
    content = data["choices"][0]["message"]["content"]

    return {
        "elapsed_s": elapsed,
        "prompt_tokens": data["usage"]["prompt_tokens"],
        "completion_tokens": completion_tokens,
        "tokens_per_second": completion_tokens / elapsed if elapsed > 0 else 0,
        "content": content,
    }


def run_benchmark(
    url: str, model_name: str, prompts: List[str], num_requests: int
) -> Dict:
    """Run benchmark suite against a model endpoint."""
    results = []
    all_prompts = (prompts * ((num_requests // len(prompts)) + 1))[:num_requests]

    for i, prompt in enumerate(all_prompts):
        print(f"  Request {i + 1}/{num_requests}...", end=" ", flush=True)
        result = send_request(url, model_name, prompt)
        results.append(result)
        print(f"{result['elapsed_s']:.2f}s, {result['tokens_per_second']:.1f} tok/s")

    latencies = [r["elapsed_s"] for r in results]
    tps = [r["tokens_per_second"] for r in results]

    return {
        "latency_mean": statistics.mean(latencies),
        "latency_p50": statistics.median(latencies),
        "latency_p95": sorted(latencies)[int(len(latencies) * 0.95)],
        "throughput_mean": statistics.mean(tps),
        "throughput_p50": statistics.median(tps),
        "total_tokens": sum(r["completion_tokens"] for r in results),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark original vs quantized model endpoints"
    )
    parser.add_argument(
        "--original-url",
        required=True,
        help="URL of the original (full-precision) model endpoint",
    )
    parser.add_argument(
        "--quantized-url",
        required=True,
        help="URL of the quantized model endpoint",
    )
    parser.add_argument(
        "--original-model",
        default="gemma-4-e4b",
        help="Model name for original endpoint (default: gemma-4-e4b)",
    )
    parser.add_argument(
        "--quantized-model",
        default="granite-3-3-8b-fp8",
        help="Model name for quantized endpoint (default: granite-3-3-8b-fp8)",
    )
    parser.add_argument(
        "--num-requests",
        type=int,
        default=20,
        help="Number of requests per endpoint (default: 20)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Model Quantization Benchmark")
    print("=" * 60)

    print(f"\n--- Original Model ({args.original_model}) ---")
    original = run_benchmark(
        args.original_url, args.original_model, BENCHMARK_PROMPTS, args.num_requests
    )

    print(f"\n--- Quantized Model ({args.quantized_model}) ---")
    quantized = run_benchmark(
        args.quantized_url, args.quantized_model, BENCHMARK_PROMPTS, args.num_requests
    )

    # Print comparison
    print("\n" + "=" * 60)
    print("RESULTS COMPARISON")
    print("=" * 60)
    print(f"{'Metric':<25} {'Original':>12} {'Quantized':>12} {'Change':>10}")
    print("-" * 60)

    def pct_change(orig: float, quant: float) -> str:
        if orig == 0:
            return "N/A"
        return f"{((quant - orig) / orig * 100):+.1f}%"

    metrics = [
        (
            "Latency (mean)",
            f"{original['latency_mean']:.2f}s",
            f"{quantized['latency_mean']:.2f}s",
            pct_change(original["latency_mean"], quantized["latency_mean"]),
        ),
        (
            "Latency (p50)",
            f"{original['latency_p50']:.2f}s",
            f"{quantized['latency_p50']:.2f}s",
            pct_change(original["latency_p50"], quantized["latency_p50"]),
        ),
        (
            "Latency (p95)",
            f"{original['latency_p95']:.2f}s",
            f"{quantized['latency_p95']:.2f}s",
            pct_change(original["latency_p95"], quantized["latency_p95"]),
        ),
        (
            "Throughput (mean)",
            f"{original['throughput_mean']:.1f} t/s",
            f"{quantized['throughput_mean']:.1f} t/s",
            pct_change(original["throughput_mean"], quantized["throughput_mean"]),
        ),
        (
            "Total tokens",
            f"{original['total_tokens']}",
            f"{quantized['total_tokens']}",
            "",
        ),
    ]

    for name, orig, quant, change in metrics:
        print(f"{name:<25} {orig:>12} {quant:>12} {change:>10}")

    # Quality comparison -- show side-by-side responses for first prompt
    print("\n" + "=" * 60)
    print("QUALITY COMPARISON (first prompt)")
    print("=" * 60)
    print(f"Prompt: {BENCHMARK_PROMPTS[0]}")
    print(f"\nOriginal:\n{original['results'][0]['content'][:500]}")
    print(f"\nQuantized:\n{quantized['results'][0]['content'][:500]}")


if __name__ == "__main__":
    main()
