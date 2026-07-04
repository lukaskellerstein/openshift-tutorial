"""
MaaS (Models-as-a-Service) test client for OpenShift AI.

Sends inference requests to a MaaS-governed model endpoint and demonstrates
tier-based rate limiting. The script sends a configurable burst of rapid
requests, prints the rate-limit headers from each response, and handles
429 Too Many Requests responses gracefully.

Usage:
    # Free tier (expect rate limiting after 10 requests):
    python3 maas_test_client.py \\
        --endpoint https://gemma-maas.apps.sandbox.example.com \\
        --api-key <your-free-tier-key> \\
        --tier free \\
        --burst 15

    # Premium tier (expect no rate limiting for 15 requests):
    python3 maas_test_client.py \\
        --endpoint https://gemma-maas.apps.sandbox.example.com \\
        --api-key <your-premium-tier-key> \\
        --tier premium \\
        --burst 15

    # Single request (default burst=1):
    python3 maas_test_client.py \\
        --endpoint https://gemma-maas.apps.sandbox.example.com \\
        --api-key <your-key>

Environment variables:
    MAAS_ENDPOINT  — base URL (used if --endpoint is not provided)
    MAAS_API_KEY   — API key (used if --api-key is not provided)

Requirements:
    pip install requests
"""

import argparse
import os
import sys
import time

import requests


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The chat completions path (OpenAI-compatible API served by vLLM)
CHAT_COMPLETIONS_PATH = "/v1/chat/completions"

# Model name as deployed in the InferenceService
MODEL_NAME = "gemma-4-e4b"

# A short prompt that produces a brief response — keeps each request fast
# so the burst test completes quickly.
DEFAULT_PROMPT = "Respond with exactly one word: hello."


def send_request(
    endpoint: str,
    api_key: str,
    prompt: str = DEFAULT_PROMPT,
    max_tokens: int = 20,
    timeout: int = 30,
) -> requests.Response:
    """Send a single chat completion request to the MaaS endpoint.

    Args:
        endpoint: Base URL of the MaaS gateway (e.g., https://gemma-maas.apps...).
        api_key: The MaaS API key (passed as Bearer token).
        prompt: The user message to send.
        max_tokens: Maximum tokens in the model response.
        timeout: HTTP request timeout in seconds.

    Returns:
        The raw requests.Response object (caller inspects status and headers).
    """
    url = f"{endpoint.rstrip('/')}{CHAT_COMPLETIONS_PATH}"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
    }

    return requests.post(url, json=payload, headers=headers, timeout=timeout)


def extract_rate_limit_headers(response: requests.Response) -> dict:
    """Extract rate-limit headers from the response.

    Kuadrant / Limitador adds these standard headers:
        X-RateLimit-Limit     — the maximum number of requests in the window
        X-RateLimit-Remaining — how many requests remain in the current window
        X-RateLimit-Reset     — seconds until the window resets
        Retry-After           — seconds to wait before retrying (on 429 only)

    Args:
        response: The HTTP response from the MaaS endpoint.

    Returns:
        A dict with the rate-limit header values (strings), or empty strings
        if a header is not present.
    """
    return {
        "limit": response.headers.get("X-RateLimit-Limit", ""),
        "remaining": response.headers.get("X-RateLimit-Remaining", ""),
        "reset": response.headers.get("X-RateLimit-Reset", ""),
        "retry_after": response.headers.get("Retry-After", ""),
    }


def format_rate_limit_info(rl: dict) -> str:
    """Format rate-limit header values into a human-readable string.

    Args:
        rl: Dict returned by extract_rate_limit_headers().

    Returns:
        A formatted string like "[Limit: 10, Remaining: 7, Reset: 45s]".
    """
    parts = []
    if rl["limit"]:
        parts.append(f"Limit: {rl['limit']}")
    if rl["remaining"]:
        parts.append(f"Remaining: {rl['remaining']}")
    if rl["reset"]:
        parts.append(f"Reset: {rl['reset']}s")
    if rl["retry_after"]:
        parts.append(f"Retry-After: {rl['retry_after']}s")

    return f"[{', '.join(parts)}]" if parts else "[no rate-limit headers]"


def run_burst_test(
    endpoint: str,
    api_key: str,
    tier: str,
    burst_count: int,
    delay: float,
) -> None:
    """Send a burst of requests and report the rate-limit behavior.

    Args:
        endpoint: Base URL of the MaaS gateway.
        api_key: The MaaS API key.
        tier: The tier name (for display purposes only).
        burst_count: Number of requests to send.
        delay: Seconds to wait between requests (0.5 default).
    """
    print("=" * 50)
    print("MaaS Rate Limit Test")
    print("=" * 50)
    print(f"Endpoint: {endpoint}")
    print(f"Tier:     {tier}")
    print(f"Burst:    {burst_count} requests")
    print(f"Delay:    {delay}s between requests")
    print()

    success_count = 0
    rate_limited_count = 0
    error_count = 0

    for i in range(1, burst_count + 1):
        try:
            response = send_request(endpoint, api_key)
            rl = extract_rate_limit_headers(response)
            rl_info = format_rate_limit_info(rl)

            if response.status_code == 200:
                success_count += 1
                print(f"Request {i:>3}/{burst_count}: 200 OK  {rl_info}")

            elif response.status_code == 429:
                rate_limited_count += 1
                retry_after = rl.get("retry_after", "unknown")
                print(
                    f"Request {i:>3}/{burst_count}: "
                    f"429 Too Many Requests  {rl_info}"
                )
                print(f"  --> Rate limit exceeded. Waiting before retry...")

            elif response.status_code == 401:
                error_count += 1
                print(
                    f"Request {i:>3}/{burst_count}: "
                    f"401 Unauthorized  -- invalid or expired API key"
                )
                # No point continuing with a bad key
                print("\nAborting: API key is not valid.")
                break

            elif response.status_code == 403:
                error_count += 1
                print(
                    f"Request {i:>3}/{burst_count}: "
                    f"403 Forbidden  -- key valid but not authorized"
                )

            else:
                error_count += 1
                print(
                    f"Request {i:>3}/{burst_count}: "
                    f"{response.status_code} {response.reason}  {rl_info}"
                )

        except requests.exceptions.ConnectionError:
            error_count += 1
            print(
                f"Request {i:>3}/{burst_count}: "
                f"CONNECTION ERROR  -- cannot reach {endpoint}"
            )
            break

        except requests.exceptions.Timeout:
            error_count += 1
            print(f"Request {i:>3}/{burst_count}: TIMEOUT  -- request timed out")

        except requests.exceptions.RequestException as e:
            error_count += 1
            print(f"Request {i:>3}/{burst_count}: ERROR  -- {e}")

        # Small delay between requests to avoid overwhelming the endpoint
        # while still being fast enough to hit the rate limit
        if i < burst_count:
            time.sleep(delay)

    # Print summary
    print()
    print("=" * 50)
    print("Summary")
    print("=" * 50)
    print(f"Successful:    {success_count:>3}")
    print(f"Rate limited:  {rate_limited_count:>3}")
    print(f"Errors:        {error_count:>3}")
    print(f"Total:         {burst_count:>3}")


def single_request(endpoint: str, api_key: str, prompt: str) -> None:
    """Send a single request and print the full response with rate-limit info.

    Args:
        endpoint: Base URL of the MaaS gateway.
        api_key: The MaaS API key.
        prompt: The user message to send.
    """
    print("=" * 50)
    print("MaaS Single Request")
    print("=" * 50)
    print(f"Endpoint: {endpoint}")
    print(f"Prompt:   {prompt}")
    print()

    try:
        response = send_request(endpoint, api_key, prompt=prompt, max_tokens=200)
        rl = extract_rate_limit_headers(response)

        print(f"Status: {response.status_code} {response.reason}")
        print(f"Rate Limit: {format_rate_limit_info(rl)}")
        print()

        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})

            print(f"Response: {content}")
            print()
            print("--- Token Usage ---")
            print(f"Prompt tokens:     {usage.get('prompt_tokens', 'N/A')}")
            print(f"Completion tokens: {usage.get('completion_tokens', 'N/A')}")
            print(f"Total tokens:      {usage.get('total_tokens', 'N/A')}")

        elif response.status_code == 429:
            print("Rate limit exceeded.")
            retry_after = rl.get("retry_after")
            if retry_after:
                print(f"Retry after {retry_after} seconds.")

        elif response.status_code == 401:
            print("Authentication failed. Check your API key.")

        else:
            print(f"Response body: {response.text[:500]}")

    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Parse arguments and run the selected test mode."""
    parser = argparse.ArgumentParser(
        description="MaaS test client — send inference requests with rate-limit tracking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Burst test with free-tier key (expect rate limiting):
  python3 maas_test_client.py --endpoint https://gemma-maas.apps.example.com \\
      --api-key <key> --tier free --burst 15

  # Single request with custom prompt:
  python3 maas_test_client.py --endpoint https://gemma-maas.apps.example.com \\
      --api-key <key> --prompt "Explain Kubernetes in one sentence"

  # Using environment variables:
  export MAAS_ENDPOINT="https://gemma-maas.apps.example.com"
  export MAAS_API_KEY="<key>"
  python3 maas_test_client.py --burst 20
        """,
    )

    parser.add_argument(
        "--endpoint",
        type=str,
        default=os.environ.get("MAAS_ENDPOINT", ""),
        help=(
            "Base URL of the MaaS gateway "
            "(default: MAAS_ENDPOINT env var)"
        ),
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.environ.get("MAAS_API_KEY", ""),
        help=(
            "MaaS API key for authentication "
            "(default: MAAS_API_KEY env var)"
        ),
    )
    parser.add_argument(
        "--tier",
        type=str,
        default="unknown",
        choices=["free", "premium", "enterprise", "unknown"],
        help="Tier name for display purposes (default: unknown)",
    )
    parser.add_argument(
        "--burst",
        type=int,
        default=1,
        help=(
            "Number of requests to send in rapid succession. "
            "Set to 1 for a single request with full output (default: 1)"
        ),
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help=(
            "Seconds to wait between burst requests (default: 0.5). "
            "Lower values hit the rate limit faster."
        ),
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default=DEFAULT_PROMPT,
        help=f'User message to send (default: "{DEFAULT_PROMPT}")',
    )

    args = parser.parse_args()

    # Validate required arguments
    if not args.endpoint:
        print(
            "Error: --endpoint is required (or set MAAS_ENDPOINT env var).",
            file=sys.stderr,
        )
        print(
            "Example: --endpoint https://gemma-maas.apps.sandbox.example.com",
            file=sys.stderr,
        )
        sys.exit(1)

    if not args.api_key:
        print(
            "Error: --api-key is required (or set MAAS_API_KEY env var).",
            file=sys.stderr,
        )
        print(
            "Retrieve a key with: oc get secret maas-key-free-user1 "
            "-n maas-config -o jsonpath='{.data.api_key}' | base64 -d",
            file=sys.stderr,
        )
        sys.exit(1)

    # Run the selected mode
    try:
        if args.burst > 1:
            run_burst_test(
                endpoint=args.endpoint,
                api_key=args.api_key,
                tier=args.tier,
                burst_count=args.burst,
                delay=args.delay,
            )
        else:
            single_request(
                endpoint=args.endpoint,
                api_key=args.api_key,
                prompt=args.prompt,
            )
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)


if __name__ == "__main__":
    main()
