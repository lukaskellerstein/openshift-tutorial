#!/usr/bin/env python3
"""
OGX vs LangGraph -- Side-by-Side Comparison

This script runs the same task using both the OGX Agents API and a LangGraph
ReAct agent, then compares the results. The goal is to demonstrate the
tradeoffs between the two approaches:

  OGX Agents API:
    - Minimal client code (~30 lines of actual logic)
    - Server handles tool calling, memory, safety
    - Standardized REST API -- not tied to a Python framework

  LangGraph:
    - More client code (~80 lines of actual logic)
    - Full control over the agent loop and state
    - Rich ecosystem (LangChain adapters, vector stores, etc.)

Prerequisites:
  - LlamaStackApp deployed on OpenShift AI (for OGX approach)
  - vLLM model serving deployed (for LangGraph approach)
  - MCP tool servers deployed and accessible
  - Environment variables:
      OGX_ENDPOINT   -- LlamaStackApp route URL
      VLLM_ENDPOINT  -- vLLM OpenAI-compatible API URL
      VLLM_MODEL_NAME -- Model name served by vLLM
      MCP_SERVER_URL  -- MCP server SSE endpoint URL

Usage:
  export OGX_ENDPOINT="https://<llama-stack-route>"
  export VLLM_ENDPOINT="http://vllm-server:8000/v1"
  export VLLM_MODEL_NAME="granite-3.3-8b-instruct"
  export MCP_SERVER_URL="http://mcp-gateway:8080/sse"
  python3 ogx_vs_langgraph_comparison.py
"""

import json
import os
import sys
import time
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OGX_ENDPOINT = os.environ.get("OGX_ENDPOINT", "")
VLLM_ENDPOINT = os.environ.get("VLLM_ENDPOINT", "http://vllm-server:8000/v1")
VLLM_MODEL_NAME = os.environ.get("VLLM_MODEL_NAME", "granite-3.3-8b-instruct")
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://mcp-gateway:8080/sse")

# The task both agents will perform
TASK = "What pods are running in the current namespace? List their names and statuses."

SYSTEM_PROMPT = (
    "You are a helpful OpenShift operations assistant. "
    "Use the available tools to query the cluster and provide clear, "
    "concise answers about cluster resources."
)


# ---------------------------------------------------------------------------
# Approach 1: OGX Agents API
# ---------------------------------------------------------------------------


def run_ogx_agent(task: str) -> dict[str, Any]:
    """
    Run a task using the OGX Agents API.

    This demonstrates the minimal code needed to use OGX:
      1. Create agent (POST /v1alpha/agents)
      2. Create session (POST /agents/{id}/sessions)
      3. Execute turn (POST /agents/{id}/sessions/{sid}/turns)
      4. Delete agent (DELETE /agents/{id})

    Total API-interaction code: ~30 lines.
    """
    import httpx

    print("=" * 60)
    print("APPROACH 1: OGX Agents API")
    print("=" * 60)
    print()

    start_time = time.time()

    client = httpx.Client(
        base_url=OGX_ENDPOINT,
        timeout=httpx.Timeout(120.0, connect=10.0),
        verify=False,
    )

    try:
        # Step 1: Create agent
        response = client.post(
            "/v1alpha/agents",
            json={
                "agent_config": {
                    "model": VLLM_MODEL_NAME,
                    "instructions": SYSTEM_PROMPT,
                    "tools": [
                        {
                            "type": "mcp",
                            "server_url": MCP_SERVER_URL,
                            "transport": "sse",
                        }
                    ],
                    "tool_choice": "auto",
                    "max_infer_iters": 5,
                    "enable_session_persistence": True,
                }
            },
        )
        response.raise_for_status()
        agent_id = response.json()["agent_id"]
        print(f"  Created agent: {agent_id}")

        # Step 2: Create session
        response = client.post(
            f"/v1alpha/agents/{agent_id}/sessions",
            json={},
        )
        response.raise_for_status()
        session_id = response.json()["session_id"]
        print(f"  Created session: {session_id}")

        # Step 3: Execute turn
        response = client.post(
            f"/v1alpha/agents/{agent_id}/sessions/{session_id}/turns",
            json={
                "messages": [{"role": "user", "content": task}],
            },
        )
        response.raise_for_status()
        turn_result = response.json()

        elapsed = time.time() - start_time

        # Extract results
        output_message = turn_result.get("output_message", {}).get("content", "")
        steps = turn_result.get("steps", [])
        tool_calls_made = sum(
            len(s.get("tool_calls", []))
            for s in steps
            if s.get("step_type") == "tool_execution"
        )

        print(f"  Turn completed in {elapsed:.1f}s")
        print(f"  Steps: {len(steps)}")
        print(f"  Tool calls: {tool_calls_made}")
        print()
        print("  Response:")
        print(f"  {output_message}")
        print()

        # Step 4: Cleanup
        client.delete(f"/v1alpha/agents/{agent_id}")
        print(f"  Deleted agent: {agent_id}")

        return {
            "approach": "OGX Agents API",
            "response": output_message,
            "elapsed_seconds": elapsed,
            "steps": len(steps),
            "tool_calls": tool_calls_made,
            "lines_of_code": 30,
        }

    finally:
        client.close()


# ---------------------------------------------------------------------------
# Approach 2: LangGraph ReAct Agent
# ---------------------------------------------------------------------------


def run_langgraph_agent(task: str) -> dict[str, Any]:
    """
    Run the same task using a LangGraph ReAct agent.

    This demonstrates the LangGraph approach:
      1. Create ChatOpenAI pointed at vLLM
      2. Load tools from MCP server via langchain-mcp-adapters
      3. Build a ReAct agent with create_react_agent
      4. Invoke the agent with the task
      5. Extract the response

    Total orchestration code: ~80 lines (more with error handling).
    """
    from langchain_openai import ChatOpenAI
    from langgraph.prebuilt import create_react_agent

    # langchain-mcp-adapters provides MCP tool loading for LangChain
    from langchain_mcp_adapters.client import MultiServerMCPClient

    print("=" * 60)
    print("APPROACH 2: LangGraph ReAct Agent")
    print("=" * 60)
    print()

    start_time = time.time()

    # Step 1: Create the LLM client pointed at vLLM
    llm = ChatOpenAI(
        base_url=VLLM_ENDPOINT,
        api_key="not-needed",  # vLLM does not require an API key
        model=VLLM_MODEL_NAME,
        temperature=0,
    )
    print(f"  LLM: {VLLM_MODEL_NAME} at {VLLM_ENDPOINT}")

    # Step 2: Load tools from MCP server
    # The MCP adapter connects to the SSE endpoint and discovers available tools
    mcp_client = MultiServerMCPClient(
        connections={
            "openshift": {
                "url": MCP_SERVER_URL,
                "transport": "sse",
            }
        }
    )

    # We need to run the async MCP client in a sync context
    import asyncio

    async def _run_agent():
        async with mcp_client:
            tools = mcp_client.get_tools()
            print(f"  Loaded {len(tools)} tools from MCP server")

            # Step 3: Build the ReAct agent
            agent = create_react_agent(
                model=llm,
                tools=tools,
                prompt=SYSTEM_PROMPT,
            )
            print("  Created ReAct agent")

            # Step 4: Invoke the agent
            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": task}]}
            )

            return result

    result = asyncio.run(_run_agent())
    elapsed = time.time() - start_time

    # Step 5: Extract the response
    # LangGraph returns a dict with 'messages' -- the last message is the response
    messages = result.get("messages", [])
    final_message = messages[-1] if messages else None
    response_text = final_message.content if final_message else "No response"

    # Count tool calls from the message history
    tool_calls_made = sum(
        1 for m in messages
        if hasattr(m, "type") and m.type == "tool"
    )

    print(f"  Completed in {elapsed:.1f}s")
    print(f"  Messages in chain: {len(messages)}")
    print(f"  Tool calls: {tool_calls_made}")
    print()
    print("  Response:")
    print(f"  {response_text}")
    print()

    return {
        "approach": "LangGraph ReAct Agent",
        "response": response_text,
        "elapsed_seconds": elapsed,
        "steps": len(messages),
        "tool_calls": tool_calls_made,
        "lines_of_code": 80,
    }


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def print_comparison(ogx_result: dict[str, Any], langgraph_result: dict[str, Any]) -> None:
    """Print a side-by-side comparison table."""
    print()
    print("=" * 60)
    print("COMPARISON")
    print("=" * 60)
    print()
    print(f"{'Metric':<30} {'OGX Agents API':<25} {'LangGraph':<25}")
    print("-" * 80)
    print(f"{'Elapsed time':<30} {ogx_result['elapsed_seconds']:<25.1f} {langgraph_result['elapsed_seconds']:<25.1f}")
    print(f"{'Execution steps':<30} {ogx_result['steps']:<25} {langgraph_result['steps']:<25}")
    print(f"{'Tool calls made':<30} {ogx_result['tool_calls']:<25} {langgraph_result['tool_calls']:<25}")
    print(f"{'Approx. lines of code':<30} {ogx_result['lines_of_code']:<25} {langgraph_result['lines_of_code']:<25}")
    print()
    print("Key differences:")
    print("  - OGX: agent loop runs server-side, client sends HTTP requests")
    print("  - LangGraph: agent loop runs client-side, you control every step")
    print("  - OGX: memory is automatic (session persistence)")
    print("  - LangGraph: memory requires a checkpointer (you configure it)")
    print("  - OGX: safety shields are built-in (if configured on LlamaStackApp)")
    print("  - LangGraph: safety requires custom middleware or guardrails library")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    # Validate environment
    missing = []
    if not OGX_ENDPOINT:
        missing.append("OGX_ENDPOINT")
    if not VLLM_ENDPOINT:
        missing.append("VLLM_ENDPOINT")

    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}", file=sys.stderr)
        print("Set them before running this script. Example:", file=sys.stderr)
        print('  export OGX_ENDPOINT="https://llama-stack-agent-myproject.apps.sandbox.example.com"', file=sys.stderr)
        print('  export VLLM_ENDPOINT="http://vllm-server:8000/v1"', file=sys.stderr)
        sys.exit(1)

    print(f"Task: {TASK}")
    print(f"Model: {VLLM_MODEL_NAME}")
    print(f"MCP Server: {MCP_SERVER_URL}")
    print()

    # Check that required packages are available
    try:
        import httpx  # noqa: F401
    except ImportError:
        print("ERROR: httpx is required. Install with: pip install httpx", file=sys.stderr)
        sys.exit(1)

    ogx_result = None
    langgraph_result = None

    # Run OGX approach
    try:
        ogx_result = run_ogx_agent(TASK)
    except Exception as e:
        print(f"  OGX approach failed: {e}")
        print()
        ogx_result = {
            "approach": "OGX Agents API",
            "response": f"FAILED: {e}",
            "elapsed_seconds": 0,
            "steps": 0,
            "tool_calls": 0,
            "lines_of_code": 30,
        }

    # Run LangGraph approach
    try:
        # Check for LangGraph dependencies
        import langchain_openai  # noqa: F401
        import langgraph  # noqa: F401
        langgraph_result = run_langgraph_agent(TASK)
    except ImportError as e:
        print(f"  LangGraph approach skipped -- missing dependency: {e}")
        print("  Install with: pip install langchain langchain-openai langgraph langchain-mcp-adapters")
        print()
        langgraph_result = {
            "approach": "LangGraph ReAct Agent",
            "response": f"SKIPPED: missing {e.name}",
            "elapsed_seconds": 0,
            "steps": 0,
            "tool_calls": 0,
            "lines_of_code": 80,
        }
    except Exception as e:
        print(f"  LangGraph approach failed: {e}")
        print()
        langgraph_result = {
            "approach": "LangGraph ReAct Agent",
            "response": f"FAILED: {e}",
            "elapsed_seconds": 0,
            "steps": 0,
            "tool_calls": 0,
            "lines_of_code": 80,
        }

    # Print comparison
    print_comparison(ogx_result, langgraph_result)

    print("Done.")


if __name__ == "__main__":
    main()
