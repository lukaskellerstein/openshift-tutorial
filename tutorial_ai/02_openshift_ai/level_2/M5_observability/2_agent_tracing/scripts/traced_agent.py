"""
Traced LangGraph Agent -- MLflow Tracing Example

Demonstrates MLflow tracing capabilities with a LangGraph ReAct agent:
  1. Auto-tracing via mlflow.langchain.autolog()
  2. Manual tracing with the @mlflow.trace decorator
  3. Span-level tracing with mlflow.start_span() for RAG decomposition
  4. MCP tool call wrapping with custom spans

The agent has two tools:
  - search_products  -- simulated product catalog search (returns canned data)
  - calculate_metric -- simple arithmetic for business metrics

A simulated/mock mode is available for environments without a live LLM
endpoint. Set MOCK_LLM=true to use canned agent responses instead of
calling a real model.

Environment variables:
    MLFLOW_TRACKING_URI  -- MLflow tracking server URL
                            (e.g. https://mlflow-tracking-ai-tutorial.apps.<cluster>)
    MLFLOW_EXPERIMENT_NAME -- Experiment name (default: agent-tracing-demo)
    VLLM_ENDPOINT        -- Base URL for the vLLM OpenAI-compatible API
                            (e.g. http://vllm-server:8000/v1)
    VLLM_MODEL_NAME      -- Model name served by vLLM
                            (e.g. granite-3.3-8b-instruct)
    MOCK_LLM             -- Set to "true" to use simulated responses
                            (default: false)

Usage:
    # With a live vLLM endpoint and MLflow server:
    export MLFLOW_TRACKING_URI="https://mlflow-tracking-ai-tutorial.apps.<cluster>"
    export VLLM_ENDPOINT="http://vllm-server:8000/v1"
    export VLLM_MODEL_NAME="granite-3.3-8b-instruct"
    python3 traced_agent.py

    # With mock mode (no LLM required):
    export MLFLOW_TRACKING_URI="https://mlflow-tracking-ai-tutorial.apps.<cluster>"
    export MOCK_LLM=true
    python3 traced_agent.py

Requirements:
    pip install mlflow langchain-openai langgraph
"""

import os
import sys
import time
import json

try:
    import mlflow
    import mlflow.langchain
except ImportError:
    print("Error: mlflow is not installed.", file=sys.stderr)
    print("Install with: pip install mlflow", file=sys.stderr)
    sys.exit(1)

try:
    from langchain_openai import ChatOpenAI
    from langchain_core.tools import tool
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
except ImportError:
    print("Error: langchain packages not installed.", file=sys.stderr)
    print("Install with: pip install langchain-openai langgraph", file=sys.stderr)
    sys.exit(1)

try:
    from langgraph.prebuilt import create_react_agent
except ImportError:
    print("Error: langgraph is not installed.", file=sys.stderr)
    print("Install with: pip install langgraph", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MLFLOW_TRACKING_URI = os.environ.get(
    "MLFLOW_TRACKING_URI", "http://localhost:5000"
)
MLFLOW_EXPERIMENT_NAME = os.environ.get(
    "MLFLOW_EXPERIMENT_NAME", "agent-tracing-demo"
)
VLLM_ENDPOINT = os.environ.get("VLLM_ENDPOINT", "http://vllm-server:8000/v1")
VLLM_MODEL_NAME = os.environ.get("VLLM_MODEL_NAME", "granite-3.3-8b-instruct")
MOCK_LLM = os.environ.get("MOCK_LLM", "false").lower() == "true"


# ---------------------------------------------------------------------------
# Simulated data -- product catalog for the search tool
# ---------------------------------------------------------------------------

PRODUCT_CATALOG = {
    "laptop": [
        {"name": "ThinkPad X1 Carbon", "price": 1299.99, "stock": 42, "category": "electronics"},
        {"name": "MacBook Air M3", "price": 1099.00, "stock": 28, "category": "electronics"},
    ],
    "headphones": [
        {"name": "Sony WH-1000XM5", "price": 349.99, "stock": 156, "category": "electronics"},
        {"name": "AirPods Pro 2", "price": 249.00, "stock": 89, "category": "electronics"},
    ],
    "keyboard": [
        {"name": "Keychron Q1 Pro", "price": 199.00, "stock": 73, "category": "peripherals"},
    ],
    "default": [
        {"name": "Generic Widget", "price": 9.99, "stock": 500, "category": "misc"},
    ],
}

# Simulated document corpus for RAG demonstration
DOCUMENT_CORPUS = [
    {
        "id": "doc-001",
        "title": "Q2 Sales Report",
        "content": "Total revenue for Q2 was $2.4M, up 15% from Q1. "
                   "Laptop sales grew 22% driven by back-to-school demand. "
                   "Headphone category maintained steady growth at 8%.",
        "embedding_time_ms": 12,
    },
    {
        "id": "doc-002",
        "title": "Inventory Policy Update",
        "content": "Minimum stock threshold raised to 50 units for electronics. "
                   "Reorder triggers updated for seasonal demand forecasting. "
                   "New supplier onboarding reduced lead time to 5 days.",
        "embedding_time_ms": 9,
    },
    {
        "id": "doc-003",
        "title": "Customer Satisfaction Survey",
        "content": "NPS score improved to 72 from 65 last quarter. "
                   "Primary drivers: faster shipping (2-day average) and "
                   "improved product recommendation accuracy (up 18%).",
        "embedding_time_ms": 11,
    },
]


# ---------------------------------------------------------------------------
# Tools -- these are the agent's callable functions
# ---------------------------------------------------------------------------

@tool
def search_products(query: str) -> str:
    """Search the product catalog for items matching the query.

    Args:
        query: Search term (e.g. 'laptop', 'headphones', 'keyboard')

    Returns:
        JSON string with matching products and their details.
    """
    # Simulate a small latency for realism
    time.sleep(0.1)

    query_lower = query.lower()
    results = None
    for key in PRODUCT_CATALOG:
        if key in query_lower:
            results = PRODUCT_CATALOG[key]
            break

    if results is None:
        results = PRODUCT_CATALOG["default"]

    return json.dumps({
        "query": query,
        "results": results,
        "total_found": len(results),
    })


@tool
def calculate_metric(expression: str) -> str:
    """Calculate a simple arithmetic expression for business metrics.

    Supports basic operations: +, -, *, /, and parentheses.

    Args:
        expression: Math expression to evaluate (e.g. '1299.99 * 42')

    Returns:
        The result of the calculation as a string.
    """
    # Simulate computation time
    time.sleep(0.05)

    # Restrict to safe arithmetic operations only
    allowed_chars = set("0123456789.+-*/() ")
    if not all(c in allowed_chars for c in expression):
        return json.dumps({"error": "Invalid characters in expression. Only numbers and +-*/() are allowed."})

    try:
        result = eval(expression)  # Safe: input is restricted to digits and operators
        return json.dumps({"expression": expression, "result": round(result, 2)})
    except Exception as e:
        return json.dumps({"error": f"Calculation failed: {str(e)}"})


# ---------------------------------------------------------------------------
# Manual tracing examples
# ---------------------------------------------------------------------------

@mlflow.trace(name="custom_data_preprocessing", span_type="FUNCTION")
def preprocess_query(raw_query: str) -> dict:
    """Preprocess a user query before sending it to the agent.

    This function is decorated with @mlflow.trace to demonstrate manual
    tracing of custom logic that autolog does not capture automatically.
    """
    # Simulate preprocessing steps
    time.sleep(0.02)

    cleaned = raw_query.strip().lower()
    tokens = cleaned.split()
    keywords = [t for t in tokens if len(t) > 3]

    result = {
        "original": raw_query,
        "cleaned": cleaned,
        "token_count": len(tokens),
        "keywords": keywords,
        "timestamp": time.time(),
    }

    # Log attributes to the current span
    mlflow.update_current_trace(
        tags={"query.token_count": str(len(tokens))},
    )

    return result


def rag_pipeline(query: str) -> dict:
    """Simulate a RAG pipeline with separate retrieval and generation spans.

    Uses mlflow.start_span() to create explicit child spans for the
    retrieval and generation phases, making it easy to see latency
    breakdown in the MLflow trace viewer.
    """
    with mlflow.start_span(name="rag_pipeline", span_type="CHAIN") as parent_span:
        parent_span.set_inputs({"query": query})

        # -- Retrieval phase --------------------------------------------------
        with mlflow.start_span(name="retrieval", span_type="RETRIEVER") as retrieval_span:
            retrieval_span.set_inputs({"query": query, "top_k": 3})
            retrieval_start = time.time()

            # Simulate embedding the query
            time.sleep(0.015)  # ~15ms for query embedding

            # Simulate vector similarity search
            time.sleep(0.025)  # ~25ms for search

            # Return matching documents (simulated)
            retrieved_docs = []
            query_lower = query.lower()
            for doc in DOCUMENT_CORPUS:
                # Simple keyword matching as a stand-in for vector similarity
                if any(word in doc["content"].lower() for word in query_lower.split()):
                    retrieved_docs.append(doc)

            if not retrieved_docs:
                retrieved_docs = DOCUMENT_CORPUS[:2]  # Fallback: return first two docs

            retrieval_time_ms = (time.time() - retrieval_start) * 1000

            retrieval_span.set_outputs({
                "num_documents": len(retrieved_docs),
                "document_ids": [d["id"] for d in retrieved_docs],
                "retrieval_time_ms": round(retrieval_time_ms, 2),
            })

        # -- Generation phase -------------------------------------------------
        with mlflow.start_span(name="generation", span_type="LLM") as generation_span:
            # Build the augmented prompt from retrieved context
            context = "\n\n".join(
                f"[{doc['title']}]: {doc['content']}" for doc in retrieved_docs
            )
            augmented_prompt = (
                f"Based on the following context, answer the question.\n\n"
                f"Context:\n{context}\n\n"
                f"Question: {query}\n\n"
                f"Answer:"
            )

            generation_span.set_inputs({
                "prompt_length": len(augmented_prompt),
                "context_documents": len(retrieved_docs),
            })

            generation_start = time.time()

            # Simulate LLM generation (or call real LLM if available)
            time.sleep(0.1)  # Simulated generation latency
            generated_answer = (
                f"Based on the available data: "
                f"{retrieved_docs[0]['content'][:100]}... "
                f"(Synthesized from {len(retrieved_docs)} retrieved documents.)"
            )

            generation_time_ms = (time.time() - generation_start) * 1000

            generation_span.set_outputs({
                "answer_length": len(generated_answer),
                "generation_time_ms": round(generation_time_ms, 2),
                "simulated_token_count": len(generated_answer.split()),
            })

        # -- Assemble result --------------------------------------------------
        result = {
            "query": query,
            "answer": generated_answer,
            "sources": [{"id": d["id"], "title": d["title"]} for d in retrieved_docs],
            "retrieval_time_ms": round(retrieval_time_ms, 2),
            "generation_time_ms": round(generation_time_ms, 2),
            "total_time_ms": round(retrieval_time_ms + generation_time_ms, 2),
        }

        parent_span.set_outputs(result)
        return result


def trace_mcp_tool_call(tool_name: str, tool_input: dict) -> dict:
    """Wrap an MCP tool call with an MLflow span.

    Demonstrates how to trace external MCP tool invocations that are
    not automatically captured by LangChain autologging.
    """
    with mlflow.start_span(name=f"mcp_tool_call:{tool_name}", span_type="TOOL") as span:
        span.set_inputs({"tool_name": tool_name, "tool_input": tool_input})

        call_start = time.time()

        # Simulate calling an MCP server over HTTP
        time.sleep(0.08)  # Simulated network + execution latency

        # Simulated response from the MCP tool server
        mock_response = {
            "status": "success",
            "tool": tool_name,
            "result": f"Processed {tool_input} via MCP server",
            "server_processing_time_ms": 45,
        }

        call_duration_ms = (time.time() - call_start) * 1000

        span.set_outputs({
            "response": mock_response,
            "call_duration_ms": round(call_duration_ms, 2),
        })

        return mock_response


# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------

def run_agent_demo(agent_executor) -> str:
    """Run the agent with a sample query and return the trace ID."""
    print("\n" + "=" * 70)
    print("DEMO 1: Agent with auto-tracing (mlflow.langchain.autolog)")
    print("=" * 70)

    query = "Search for laptops in stock and calculate the total inventory value"
    print(f"\nQuery: {query}")

    result = agent_executor.invoke(
        {"messages": [HumanMessage(content=query)]},
    )

    # Print the agent's response
    messages = result.get("messages", [])
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.content:
            print(f"\nAgent response:\n  {msg.content[:300]}")

    # Get the active trace ID
    trace = mlflow.get_last_active_trace()
    trace_id = trace.info.request_id if trace else "unknown"
    print(f"\nTrace ID: {trace_id}")

    return trace_id


def run_manual_tracing_demo() -> str:
    """Demonstrate manual tracing with @mlflow.trace decorator."""
    print("\n" + "=" * 70)
    print("DEMO 2: Manual tracing with @mlflow.trace decorator")
    print("=" * 70)

    query = "What are the best-selling headphones in Q2?"
    print(f"\nQuery: {query}")

    result = preprocess_query(query)
    print(f"\nPreprocessed query:")
    print(f"  Original:    {result['original']}")
    print(f"  Cleaned:     {result['cleaned']}")
    print(f"  Token count: {result['token_count']}")
    print(f"  Keywords:    {result['keywords']}")

    trace = mlflow.get_last_active_trace()
    trace_id = trace.info.request_id if trace else "unknown"
    print(f"\nTrace ID: {trace_id}")

    return trace_id


def run_rag_tracing_demo() -> str:
    """Demonstrate span-level tracing for RAG retrieval vs generation."""
    print("\n" + "=" * 70)
    print("DEMO 3: RAG pipeline with retrieval/generation span decomposition")
    print("=" * 70)

    query = "What was the revenue growth in Q2?"
    print(f"\nQuery: {query}")

    result = rag_pipeline(query)
    print(f"\nAnswer: {result['answer']}")
    print(f"\nSources:")
    for src in result["sources"]:
        print(f"  - {src['title']} ({src['id']})")
    print(f"\nLatency breakdown:")
    print(f"  Retrieval:  {result['retrieval_time_ms']:.1f} ms")
    print(f"  Generation: {result['generation_time_ms']:.1f} ms")
    print(f"  Total:      {result['total_time_ms']:.1f} ms")

    trace = mlflow.get_last_active_trace()
    trace_id = trace.info.request_id if trace else "unknown"
    print(f"\nTrace ID: {trace_id}")

    return trace_id


def run_mcp_tracing_demo() -> str:
    """Demonstrate tracing MCP tool calls with explicit spans."""
    print("\n" + "=" * 70)
    print("DEMO 4: MCP tool call tracing with mlflow.start_span()")
    print("=" * 70)

    # Simulate an agent calling multiple MCP tools
    tools_to_call = [
        ("inventory_lookup", {"product_id": "SKU-001", "warehouse": "us-east"}),
        ("price_check", {"product_id": "SKU-001", "currency": "USD"}),
    ]

    with mlflow.start_span(name="agent_tool_calling_loop", span_type="CHAIN") as parent:
        parent.set_inputs({"num_tools": len(tools_to_call)})

        results = []
        for tool_name, tool_input in tools_to_call:
            print(f"\n  Calling MCP tool: {tool_name}")
            print(f"    Input: {tool_input}")
            result = trace_mcp_tool_call(tool_name, tool_input)
            print(f"    Status: {result['status']}")
            print(f"    Duration: {result['call_duration_ms']:.1f} ms")
            results.append(result)

        parent.set_outputs({"num_results": len(results), "all_succeeded": True})

    trace = mlflow.get_last_active_trace()
    trace_id = trace.info.request_id if trace else "unknown"
    print(f"\nTrace ID: {trace_id}")

    return trace_id


def print_summary(trace_ids: dict, tracking_uri: str) -> None:
    """Print a summary of all trace IDs and MLflow UI URLs."""
    print("\n" + "=" * 70)
    print("TRACE SUMMARY")
    print("=" * 70)
    print(f"\nMLflow Tracking URI: {tracking_uri}")
    print(f"Experiment: {MLFLOW_EXPERIMENT_NAME}")
    print(f"\nTraces generated:")

    for demo_name, trace_id in trace_ids.items():
        print(f"\n  {demo_name}:")
        print(f"    Trace ID: {trace_id}")
        print(f"    View in UI: {tracking_uri}/#/experiments/1/traces/{trace_id}")

    print(f"\nTo view all traces, open the MLflow UI:")
    print(f"  {tracking_uri}/#/experiments")
    print(f"\nNavigate to the '{MLFLOW_EXPERIMENT_NAME}' experiment and click")
    print(f"the 'Traces' tab to see the full list of traces.\n")


def main() -> None:
    # -- Configure MLflow -----------------------------------------------------
    print("Configuring MLflow...")
    print(f"  Tracking URI:    {MLFLOW_TRACKING_URI}")
    print(f"  Experiment:      {MLFLOW_EXPERIMENT_NAME}")
    print(f"  Mock LLM mode:   {MOCK_LLM}")

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)

    # -- Enable LangChain auto-tracing ----------------------------------------
    # This single call instruments all LangChain/LangGraph components:
    # LLM calls, tool invocations, chain steps, and agent loops are
    # automatically captured as spans within a trace.
    mlflow.langchain.autolog(
        log_models=False,      # Do not log serialized model artifacts
        log_input_examples=True,
        log_model_signatures=True,
    )
    print("  LangChain autolog enabled")

    # -- Build the agent ------------------------------------------------------
    if MOCK_LLM:
        print("\n  Using MOCK LLM -- agent responses are simulated")
        # In mock mode we skip the real agent invocation and demonstrate
        # only the manual tracing features (demos 2-4).
        agent_executor = None
    else:
        print(f"\n  Connecting to vLLM: {VLLM_ENDPOINT}")
        print(f"  Model: {VLLM_MODEL_NAME}")

        llm = ChatOpenAI(
            base_url=VLLM_ENDPOINT,
            api_key="EMPTY",
            model=VLLM_MODEL_NAME,
            temperature=0,
        )

        agent_executor = create_react_agent(
            llm,
            tools=[search_products, calculate_metric],
        )
        print("  ReAct agent created with tools: search_products, calculate_metric")

    # -- Run demos ------------------------------------------------------------
    trace_ids = {}

    # Demo 1: Agent auto-tracing (requires live LLM)
    if agent_executor is not None:
        try:
            trace_id = run_agent_demo(agent_executor)
            trace_ids["Demo 1: Agent auto-tracing"] = trace_id
        except Exception as e:
            print(f"\n  Demo 1 failed (LLM may be unavailable): {e}")
            print("  Continuing with manual tracing demos...")
    else:
        print("\n  Skipping Demo 1 (agent auto-tracing) -- MOCK_LLM is enabled.")
        print("  To run Demo 1, set MOCK_LLM=false and provide VLLM_ENDPOINT.")

    # Demo 2: Manual tracing with @mlflow.trace
    trace_id = run_manual_tracing_demo()
    trace_ids["Demo 2: @mlflow.trace decorator"] = trace_id

    # Demo 3: RAG pipeline with span decomposition
    trace_id = run_rag_tracing_demo()
    trace_ids["Demo 3: RAG span decomposition"] = trace_id

    # Demo 4: MCP tool call tracing
    trace_id = run_mcp_tracing_demo()
    trace_ids["Demo 4: MCP tool call tracing"] = trace_id

    # -- Summary --------------------------------------------------------------
    print_summary(trace_ids, MLFLOW_TRACKING_URI)


if __name__ == "__main__":
    main()
