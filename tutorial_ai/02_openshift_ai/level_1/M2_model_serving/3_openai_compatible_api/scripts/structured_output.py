"""
Structured output (JSON mode) example using the OpenAI Python SDK with a self-hosted vLLM model.

Demonstrates:
- Requesting JSON output via response_format
- Parsing and validating the structured response
- Using JSON mode for data extraction tasks

Usage:
    export INFERENCE_URL="https://<your-route-host>"
    python3 structured_output.py
    python3 structured_output.py --task extract
"""

import argparse
import json
import os
import sys

from openai import OpenAI, OpenAIError


def get_client(base_url: str) -> OpenAI:
    """Create an OpenAI client pointed at the vLLM endpoint."""
    return OpenAI(
        base_url=f"{base_url}/v1",
        api_key="not-needed",  # Auth is disabled on the endpoint
    )


def json_list(client: OpenAI, model: str, max_tokens: int) -> None:
    """Request a structured JSON list from the model."""
    print("=" * 60)
    print("Task: Generate a structured JSON list")
    print("=" * 60)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": (
                    "List 3 benefits of Kubernetes. "
                    "Return a JSON object with a key 'benefits' containing an array. "
                    "Each item should have keys: 'benefit' (short name) and 'description' (one sentence)."
                ),
            }
        ],
        response_format={"type": "json_object"},
        max_tokens=max_tokens,
        temperature=0.3,  # Lower temperature for more consistent structure
    )

    raw_content = response.choices[0].message.content
    print(f"\nRaw response:\n{raw_content}")

    # Parse and validate
    try:
        data = json.loads(raw_content)
        print(f"\nParsed successfully. Type: {type(data).__name__}")
        print(f"Formatted output:\n{json.dumps(data, indent=2)}")

        # Validate expected structure
        if "benefits" in data and isinstance(data["benefits"], list):
            print(f"\nValidation: Found {len(data['benefits'])} benefits")
            for i, item in enumerate(data["benefits"], 1):
                benefit = item.get("benefit", "(missing)")
                description = item.get("description", "(missing)")
                print(f"  {i}. {benefit}: {description}")
        else:
            print("\nValidation: Response is valid JSON but does not match expected schema.")
            print("This is expected -- JSON mode guarantees valid JSON, not schema conformance.")
    except json.JSONDecodeError as e:
        print(f"\nFailed to parse JSON: {e}")
        print("This should not happen in JSON mode, but always handle it defensively.")

    print(f"\nTokens used: {response.usage.total_tokens}")


def data_extraction(client: OpenAI, model: str, max_tokens: int) -> None:
    """Use JSON mode for structured data extraction from unstructured text."""
    print("\n" + "=" * 60)
    print("Task: Extract structured data from unstructured text")
    print("=" * 60)

    source_text = (
        "Our e-commerce platform runs on OpenShift 4.14. We have 3 microservices: "
        "the product catalog (Python, 2 replicas), the order processor (Java, 4 replicas), "
        "and the payment gateway (Go, 2 replicas). The cluster has 12 worker nodes "
        "with 64GB RAM each. We process about 50,000 orders per day."
    )

    print(f"\nSource text:\n  {source_text}")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a data extraction assistant. Extract structured information "
                    "from the user's text and return it as JSON."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Extract the following from this text and return as JSON:\n"
                    f"- platform (string)\n"
                    f"- platform_version (string)\n"
                    f"- microservices (array of objects with: name, language, replicas)\n"
                    f"- infrastructure (object with: worker_nodes, ram_per_node)\n"
                    f"- daily_orders (number)\n\n"
                    f"Text: {source_text}"
                ),
            },
        ],
        response_format={"type": "json_object"},
        max_tokens=max_tokens,
        temperature=0.0,  # Deterministic for extraction tasks
    )

    raw_content = response.choices[0].message.content

    try:
        data = json.loads(raw_content)
        print(f"\nExtracted data:\n{json.dumps(data, indent=2)}")

        # Validate specific fields
        checks = [
            ("platform" in data, "platform field present"),
            ("microservices" in data, "microservices field present"),
        ]
        print("\nValidation:")
        for passed, description in checks:
            status = "PASS" if passed else "FAIL"
            print(f"  [{status}] {description}")

    except json.JSONDecodeError as e:
        print(f"\nFailed to parse JSON: {e}")

    print(f"\nTokens used: {response.usage.total_tokens}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Structured output example with vLLM")
    parser.add_argument(
        "--task",
        type=str,
        choices=["list", "extract", "all"],
        default="all",
        help="Which task to run (default: all)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=400,
        help="Maximum tokens in the response (default: 400)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gemma-4-e4b",
        help="Model name (default: gemma-4-e4b)",
    )
    args = parser.parse_args()

    inference_url = os.environ.get("INFERENCE_URL")
    if not inference_url:
        print("Error: INFERENCE_URL environment variable is not set.", file=sys.stderr)
        print("Set it with:", file=sys.stderr)
        print('  export INFERENCE_URL="https://$(oc get route -l serving.kserve.io/inferenceservice=gemma-4-e4b -n gemma-model -o jsonpath=\'{.items[0].spec.host}\')"', file=sys.stderr)
        sys.exit(1)

    client = get_client(inference_url)

    try:
        if args.task in ("list", "all"):
            json_list(client, args.model, args.max_tokens)
        if args.task in ("extract", "all"):
            data_extraction(client, args.model, args.max_tokens)
    except OpenAIError as e:
        print(f"\nAPI error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)


if __name__ == "__main__":
    main()
