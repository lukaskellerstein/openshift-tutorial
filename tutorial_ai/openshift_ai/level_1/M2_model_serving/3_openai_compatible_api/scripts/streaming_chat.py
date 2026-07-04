"""
Streaming chat completion example using the OpenAI Python SDK with a self-hosted vLLM model.

Demonstrates:
- Streaming tokens as they arrive (Server-Sent Events)
- Collecting the full response while streaming
- Usage tracking after stream completes

Usage:
    export INFERENCE_URL="https://<your-route-host>"
    python3 streaming_chat.py
    python3 streaming_chat.py --prompt "Explain container networking"
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


def stream_chat(
    client: OpenAI,
    model: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
) -> None:
    """Stream a chat completion and print tokens as they arrive."""
    print(f"User: {prompt}")
    print(f"Assistant: ", end="", flush=True)

    # Collect the full response while streaming
    collected_content = []
    finish_reason = None

    stream = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
        stream_options={"include_usage": True},  # Request usage stats in stream
    )

    usage = None
    for chunk in stream:
        # The final chunk may contain usage information
        if chunk.usage is not None:
            usage = chunk.usage

        if not chunk.choices:
            continue

        delta = chunk.choices[0].delta
        if delta.content:
            print(delta.content, end="", flush=True)
            collected_content.append(delta.content)

        if chunk.choices[0].finish_reason:
            finish_reason = chunk.choices[0].finish_reason

    print()  # Newline after streaming completes

    # Print summary
    full_response = "".join(collected_content)
    print(f"\n--- Stream Summary ---")
    print(f"Finish reason: {finish_reason}")
    print(f"Response length: {len(full_response)} characters")
    if usage:
        print(f"Prompt tokens:     {usage.prompt_tokens}")
        print(f"Completion tokens: {usage.completion_tokens}")
        print(f"Total tokens:      {usage.total_tokens}")
    else:
        print("(Usage stats not available in stream -- use non-streaming for token counts)")


def interactive_mode(client: OpenAI, model: str, temperature: float, max_tokens: int) -> None:
    """Run an interactive streaming chat session."""
    print("=" * 60)
    print("Interactive Streaming Chat (type 'quit' to exit)")
    print("=" * 60)

    messages = [
        {"role": "system", "content": "You are a helpful assistant specializing in Kubernetes and OpenShift."},
    ]

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except EOFError:
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            break

        messages.append({"role": "user", "content": user_input})

        print("Assistant: ", end="", flush=True)
        collected = []

        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                print(delta.content, end="", flush=True)
                collected.append(delta.content)

        print()
        full_response = "".join(collected)
        messages.append({"role": "assistant", "content": full_response})


def main() -> None:
    parser = argparse.ArgumentParser(description="Streaming chat example with vLLM")
    parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        help="Single prompt to stream (omit for interactive mode)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.7,
        help="Sampling temperature (0.0-2.0, default: 0.7)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=300,
        help="Maximum tokens in the response (default: 300)",
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
        if args.prompt:
            stream_chat(client, args.model, args.prompt, args.temperature, args.max_tokens)
        else:
            interactive_mode(client, args.model, args.temperature, args.max_tokens)
    except OpenAIError as e:
        print(f"\nAPI error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)


if __name__ == "__main__":
    main()
