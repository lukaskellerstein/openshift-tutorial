"""
Traced Inference Client -- OpenTelemetry instrumented inference request

Sends an inference request to a vLLM endpoint (OpenAI-compatible API)
with full OpenTelemetry distributed tracing. Creates spans for each
phase of the request -- preparation, inference call, and response
parsing -- so the complete request lifecycle is visible in Jaeger.

Demonstrates:
    - Configuring the OpenTelemetry SDK (TracerProvider, OTLP exporter)
    - Creating manual spans with attributes and events
    - Propagating trace context via W3C traceparent headers
    - Correlating client-side and server-side traces

Usage:
    export INFERENCE_URL="https://my-model-my-project.apps.cluster.example.com"
    export OTEL_EXPORTER_OTLP_ENDPOINT="http://otel-collector:4317"
    python3 scripts/trace_inference.py

    # With a custom prompt:
    python3 scripts/trace_inference.py --prompt "Explain quantum computing in one paragraph."

    # With multiple requests for latency comparison:
    python3 scripts/trace_inference.py --requests 5

Environment variables:
    INFERENCE_URL                 -- vLLM inference endpoint base URL
                                    (default: http://localhost:8000)
    OTEL_EXPORTER_OTLP_ENDPOINT  -- OTel Collector OTLP gRPC endpoint
                                    (default: http://localhost:4317)
    MODEL_NAME                   -- Model name served by vLLM
                                    (default: granite-3.3-8b-instruct)
"""

import argparse
import json
import logging
import os
import sys
import time
from urllib.parse import urljoin

import requests
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

INFERENCE_URL = os.environ.get("INFERENCE_URL", "http://localhost:8000")
OTEL_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
MODEL_NAME = os.environ.get("MODEL_NAME", "granite-3.3-8b-instruct")

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OpenTelemetry SDK setup
# ---------------------------------------------------------------------------


def configure_tracer() -> trace.Tracer:
    """Configure the OpenTelemetry TracerProvider with OTLP export.

    Returns a Tracer instance named 'inference-client' that sends spans
    to the OTel Collector via gRPC.
    """
    resource = Resource.create(
        {
            "service.name": "inference-client",
            "service.version": "1.0.0",
            "deployment.environment": "tutorial",
        }
    )

    provider = TracerProvider(resource=resource)

    otlp_exporter = OTLPSpanExporter(
        endpoint=OTEL_ENDPOINT,
        insecure=True,
    )
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    trace.set_tracer_provider(provider)

    return trace.get_tracer("inference-client", "1.0.0")


# ---------------------------------------------------------------------------
# Inference with tracing
# ---------------------------------------------------------------------------


def traced_inference(
    tracer: trace.Tracer,
    prompt: str,
    request_number: int = 1,
) -> dict:
    """Send a single inference request with distributed tracing.

    Creates three child spans under a root 'inference-request' span:
        1. prepare-request  -- build the HTTP request payload
        2. call-inference   -- send the request and wait for response
        3. parse-response   -- extract and process the response body

    Args:
        tracer: OpenTelemetry Tracer instance.
        prompt: The user prompt to send to the model.
        request_number: Sequence number for multi-request runs.

    Returns:
        A dict with keys: trace_id, response_text, latency_ms,
        tokens_used, model.
    """
    with tracer.start_as_current_span(
        "inference-request",
        attributes={
            "request.number": request_number,
            "model.name": MODEL_NAME,
            "inference.endpoint": INFERENCE_URL,
        },
    ) as root_span:

        # -- Step 1: Prepare request ------------------------------------------
        with tracer.start_as_current_span(
            "prepare-request",
            attributes={"prompt.length": len(prompt)},
        ) as prep_span:
            payload = {
                "model": MODEL_NAME,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a helpful assistant. Be concise.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 256,
                "temperature": 0.7,
            }

            # Inject W3C trace context into HTTP headers so vLLM can
            # continue the same trace on the server side
            headers = {"Content-Type": "application/json"}
            inject(headers)

            prep_span.set_attribute("request.payload_size", len(json.dumps(payload)))
            prep_span.add_event("request-prepared")

        # -- Step 2: Call inference endpoint -----------------------------------
        with tracer.start_as_current_span("call-inference") as call_span:
            url = urljoin(INFERENCE_URL.rstrip("/") + "/", "v1/chat/completions")
            call_span.set_attribute("http.method", "POST")
            call_span.set_attribute("http.url", url)

            start_time = time.time()
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=120,
                    verify=False,
                )
                latency_ms = (time.time() - start_time) * 1000

                call_span.set_attribute("http.status_code", response.status_code)
                call_span.set_attribute("inference.latency_ms", round(latency_ms, 2))
                call_span.add_event(
                    "response-received",
                    attributes={"http.status_code": response.status_code},
                )

                response.raise_for_status()

            except requests.exceptions.RequestException as exc:
                call_span.set_attribute("error", True)
                call_span.set_attribute("error.message", str(exc))
                call_span.add_event("request-failed", attributes={"error": str(exc)})
                root_span.set_attribute("error", True)
                raise

        # -- Step 3: Parse response --------------------------------------------
        with tracer.start_as_current_span("parse-response") as parse_span:
            body = response.json()

            response_text = body["choices"][0]["message"]["content"]
            usage = body.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", 0)
            model_returned = body.get("model", MODEL_NAME)

            parse_span.set_attribute("response.length", len(response_text))
            parse_span.set_attribute("tokens.prompt", prompt_tokens)
            parse_span.set_attribute("tokens.completion", completion_tokens)
            parse_span.set_attribute("tokens.total", total_tokens)
            parse_span.add_event("response-parsed")

            # Record summary attributes on the root span for easy searching
            root_span.set_attribute("tokens.total", total_tokens)
            root_span.set_attribute("inference.latency_ms", round(latency_ms, 2))
            root_span.set_attribute("response.model", model_returned)

        # Extract trace ID for Jaeger lookup
        trace_id = format(root_span.get_span_context().trace_id, "032x")

        return {
            "trace_id": trace_id,
            "response_text": response_text,
            "latency_ms": round(latency_ms, 2),
            "tokens_used": total_tokens,
            "model": model_returned,
        }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Send traced inference requests to a vLLM endpoint"
    )
    parser.add_argument(
        "--prompt",
        default="What are the three main benefits of using OpenTelemetry for observability?",
        help="Prompt to send to the model",
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=1,
        help="Number of inference requests to send (default: 1)",
    )
    args = parser.parse_args()

    logger.info("Configuring OpenTelemetry...")
    logger.info("  OTLP endpoint: %s", OTEL_ENDPOINT)
    logger.info("  Inference URL: %s", INFERENCE_URL)
    logger.info("  Model:         %s", MODEL_NAME)
    logger.info("")

    tracer = configure_tracer()

    for i in range(1, args.requests + 1):
        logger.info("--- Request %d of %d ---", i, args.requests)
        logger.info("Prompt: %s", args.prompt)
        logger.info("")

        try:
            result = traced_inference(tracer, args.prompt, request_number=i)
        except Exception as exc:
            logger.error("Request %d failed: %s", i, exc)
            continue

        logger.info("Response: %s", result["response_text"][:200])
        if len(result["response_text"]) > 200:
            logger.info("  ... (truncated)")
        logger.info("")
        logger.info("  Trace ID:    %s", result["trace_id"])
        logger.info("  Latency:     %.2f ms", result["latency_ms"])
        logger.info("  Tokens used: %d", result["tokens_used"])
        logger.info("  Model:       %s", result["model"])
        logger.info("")

    # Flush spans before exiting
    provider = trace.get_tracer_provider()
    if hasattr(provider, "force_flush"):
        provider.force_flush(timeout_millis=10000)

    logger.info("All spans exported. Open Jaeger UI to view traces.")
    logger.info(
        "Search for service 'inference-client' to find the traces above."
    )


if __name__ == "__main__":
    main()
