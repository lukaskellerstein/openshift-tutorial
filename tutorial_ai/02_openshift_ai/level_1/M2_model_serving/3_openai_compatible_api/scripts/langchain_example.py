"""
LangChain integration example using ChatOpenAI with a self-hosted vLLM model.

Demonstrates:
- Using ChatOpenAI with a self-hosted OpenAI-compatible endpoint
- Simple chain example with prompt templates
- How existing LangChain code works without modification (just change base_url)

Usage:
    export INFERENCE_URL="https://<your-route-host>"
    python3 langchain_example.py
    python3 langchain_example.py --topic "service mesh"

Requirements:
    pip install langchain-openai
"""

import argparse
import os
import sys

try:
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser
except ImportError:
    print("Error: Required packages not installed.", file=sys.stderr)
    print("Install with: pip install langchain-openai", file=sys.stderr)
    sys.exit(1)


def get_llm(base_url: str, model: str, temperature: float, max_tokens: int) -> ChatOpenAI:
    """Create a ChatOpenAI instance pointed at the vLLM endpoint."""
    return ChatOpenAI(
        base_url=f"{base_url}/v1",
        api_key="not-needed",  # Auth is disabled on the endpoint
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def simple_invoke(llm: ChatOpenAI) -> None:
    """Simplest possible usage -- invoke with a string."""
    print("=" * 60)
    print("Simple invoke")
    print("=" * 60)

    response = llm.invoke("What is a Pod in Kubernetes?")
    print(f"\nResponse:\n{response.content}")
    print(f"\nMetadata: {response.response_metadata.get('token_usage', {})}")


def chain_example(llm: ChatOpenAI, topic: str) -> None:
    """Demonstrate a LangChain chain with a prompt template."""
    print("\n" + "=" * 60)
    print("Chain with prompt template")
    print("=" * 60)

    # Define a prompt template
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a Kubernetes expert writing concise explanations for developers."),
        ("user", "Explain {topic} in exactly 3 bullet points. Keep each bullet to one sentence."),
    ])

    # Build a chain: prompt -> LLM -> output parser
    chain = prompt | llm | StrOutputParser()

    # Invoke the chain
    print(f"\nTopic: {topic}")
    result = chain.invoke({"topic": topic})
    print(f"\nResult:\n{result}")


def batch_example(llm: ChatOpenAI) -> None:
    """Demonstrate batch processing with LangChain."""
    print("\n" + "=" * 60)
    print("Batch processing")
    print("=" * 60)

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a concise technical writer."),
        ("user", "Define '{term}' in one sentence."),
    ])

    chain = prompt | llm | StrOutputParser()

    terms = [
        {"term": "Deployment"},
        {"term": "Service"},
        {"term": "ConfigMap"},
    ]

    print("\nProcessing batch of terms...")
    results = chain.batch(terms)

    for term_dict, result in zip(terms, results):
        print(f"\n  {term_dict['term']}: {result.strip()}")


def streaming_example(llm: ChatOpenAI, topic: str) -> None:
    """Demonstrate streaming with LangChain."""
    print("\n" + "=" * 60)
    print("Streaming with LangChain")
    print("=" * 60)

    prompt = ChatPromptTemplate.from_messages([
        ("user", "Give a brief overview of {topic} in OpenShift."),
    ])

    chain = prompt | llm | StrOutputParser()

    print(f"\nTopic: {topic}")
    print("Response: ", end="", flush=True)

    for token in chain.stream({"topic": topic}):
        print(token, end="", flush=True)

    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="LangChain example with vLLM")
    parser.add_argument(
        "--topic",
        type=str,
        default="container orchestration",
        help="Topic for the chain example (default: container orchestration)",
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

    llm = get_llm(inference_url, args.model, args.temperature, args.max_tokens)

    try:
        simple_invoke(llm)
        chain_example(llm, args.topic)
        batch_example(llm)
        streaming_example(llm, args.topic)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)


if __name__ == "__main__":
    main()
