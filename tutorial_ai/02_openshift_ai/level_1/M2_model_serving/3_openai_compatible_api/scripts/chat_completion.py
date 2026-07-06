"""
Chat completion example using the OpenAI Python SDK with a self-hosted vLLM model.

Demonstrates:
- Connecting to a vLLM endpoint using the openai SDK
- Multi-turn conversation (system + user + assistant + user)
- Token usage tracking
- Error handling

Usage:
    export INFERENCE_URL="https://<your-route-host>"
    python3 chat_completion.py
    python3 chat_completion.py --temperature 0.0 --max-tokens 100
"""

import argparse
import os
import sys

from openai import OpenAI, OpenAIError


def get_client(base_url: str) -> OpenAI:
    """Create an OpenAI client pointed at the vLLM endpoint."""
    return OpenAI(
        base_url=f"{base_url}/v1",
        api_key="not-needed",  # Auth is disabled on the endpoint
    )


def single_turn(client: OpenAI, model: str, temperature: float, max_tokens: int) -> None:
    """Send a single chat completion request and print the result."""
    print("=" * 60)
    print("Single-turn chat completion")
    print("=" * 60)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a helpful assistant specializing in cloud-native technologies."},
            {"role": "user", "content": "What is OpenShift AI and how does it relate to Kubernetes?"},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )

    print(f"\nAssistant: {response.choices[0].message.content}")
    print(f"\n--- Token Usage ---")
    print(f"Prompt tokens:     {response.usage.prompt_tokens}")
    print(f"Completion tokens: {response.usage.completion_tokens}")
    print(f"Total tokens:      {response.usage.total_tokens}")


def multi_turn(client: OpenAI, model: str, temperature: float, max_tokens: int) -> None:
    """Demonstrate a multi-turn conversation with context carried across turns."""
    print("\n" + "=" * 60)
    print("Multi-turn conversation")
    print("=" * 60)

    messages = [
        {"role": "system", "content": "You are a helpful assistant. Keep answers concise."},
        {"role": "user", "content": "What is a Kubernetes Pod?"},
    ]

    # Turn 1
    print(f"\nUser: {messages[-1]['content']}")
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    assistant_msg = response.choices[0].message.content
    print(f"Assistant: {assistant_msg}")
    print(f"  (tokens: {response.usage.total_tokens})")

    # Add the assistant's response to the conversation history
    messages.append({"role": "assistant", "content": assistant_msg})

    # Turn 2 -- follow-up question that relies on context
    follow_up = "How is that different from a Deployment?"
    messages.append({"role": "user", "content": follow_up})

    print(f"\nUser: {follow_up}")
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    assistant_msg = response.choices[0].message.content
    print(f"Assistant: {assistant_msg}")
    print(f"  (tokens: {response.usage.total_tokens})")

    # Turn 3 -- another follow-up
    messages.append({"role": "assistant", "content": assistant_msg})
    follow_up = "When would I use a StatefulSet instead?"
    messages.append({"role": "user", "content": follow_up})

    print(f"\nUser: {follow_up}")
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    assistant_msg = response.choices[0].message.content
    print(f"Assistant: {assistant_msg}")
    print(f"  (tokens: {response.usage.total_tokens})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat completion example with vLLM")
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.7,
        help="Sampling temperature (0.0-2.0, default: 0.7)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=200,
        help="Maximum tokens in the response (default: 200)",
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
        single_turn(client, args.model, args.temperature, args.max_tokens)
        multi_turn(client, args.model, args.temperature, args.max_tokens)
    except OpenAIError as e:
        print(f"\nAPI error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)


if __name__ == "__main__":
    main()
