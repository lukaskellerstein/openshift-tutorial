#!/usr/bin/env python3
"""
OGX Agents API -- Full Agent Lifecycle Demo

This script demonstrates the complete OGX / Llama Stack Agents API workflow:
  1. Create an agent with model, instructions, and tool definitions
  2. Create a session (conversation context)
  3. Execute turns (send user messages, receive responses with tool calling)
  4. Observe structured execution steps (inference, tool calls, results)
  5. Demonstrate session memory across multiple turns
  6. Clean up (delete the agent)

Prerequisites:
  - A LlamaStackApp deployed on OpenShift AI (from the OGX sub-tutorial)
  - MCP tool servers accessible from the LlamaStackApp pod
  - Environment variable OGX_ENDPOINT set to the LlamaStackApp route URL

Usage:
  export OGX_ENDPOINT="https://<llama-stack-route>"
  python3 ogx_agent.py
  python3 ogx_agent.py --query "List all pods in the current namespace"
  python3 ogx_agent.py --dry-run
"""

import argparse
import json
import os
import sys
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OGX_ENDPOINT = os.environ.get("OGX_ENDPOINT", "")
MODEL_NAME = os.environ.get("VLLM_MODEL_NAME", "granite-3.3-8b-instruct")
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://mcp-gateway:8080/sse")

# Default queries to demonstrate multi-turn conversation with memory
DEFAULT_QUERIES = [
    "What pods are running in the current namespace?",
    "Which of those pods has been running the longest?",
]

# System prompt for the agent
AGENT_INSTRUCTIONS = (
    "You are a helpful OpenShift operations assistant. "
    "You can query the OpenShift cluster using the available tools to answer "
    "questions about pods, deployments, services, routes, and other resources. "
    "Always provide clear, concise answers. When listing resources, format them "
    "as a readable list with relevant details (name, status, age, etc.)."
)

# ---------------------------------------------------------------------------
# HTTP client setup
# ---------------------------------------------------------------------------

# Timeout is generous because tool calls can take time
HTTP_TIMEOUT = httpx.Timeout(120.0, connect=10.0)


def get_client() -> httpx.Client:
    """Create an HTTP client configured for the OGX endpoint."""
    return httpx.Client(
        base_url=OGX_ENDPOINT,
        timeout=HTTP_TIMEOUT,
        # Accept self-signed certs on OpenShift routes (dev/sandbox environments)
        verify=False,
    )


# ---------------------------------------------------------------------------
# Agent lifecycle functions
# ---------------------------------------------------------------------------


def create_agent(client: httpx.Client) -> str:
    """
    Create an OGX agent with model, instructions, and tool definitions.

    The agent configuration tells the LlamaStackApp:
      - Which model to use for inference
      - What system prompt (instructions) to prepend to every turn
      - Which tools are available (MCP servers, built-in tools, etc.)
      - How many inference iterations to allow per turn (prevents loops)

    Returns the agent_id.
    """
    agent_config = {
        "agent_config": {
            "model": MODEL_NAME,
            "instructions": AGENT_INSTRUCTIONS,
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
    }

    print("=== Creating agent ===")
    print(f"Model: {MODEL_NAME}")
    print(f"MCP server: {MCP_SERVER_URL}")
    print(f"Config: {json.dumps(agent_config, indent=2)}")
    print()

    response = client.post("/v1alpha/agents", json=agent_config)
    response.raise_for_status()
    result = response.json()
    agent_id = result["agent_id"]
    print(f"Agent ID: {agent_id}")
    print()
    return agent_id


def create_session(client: httpx.Client, agent_id: str) -> str:
    """
    Create a session for the agent.

    A session is a conversation context. All turns within a session share
    memory -- the agent can reference earlier messages without the client
    re-sending them. Each session is independent; creating a new session
    starts a fresh conversation.

    Returns the session_id.
    """
    print("=== Creating session ===")

    response = client.post(
        f"/v1alpha/agents/{agent_id}/sessions",
        json={},
    )
    response.raise_for_status()
    result = response.json()
    session_id = result["session_id"]
    print(f"Session ID: {session_id}")
    print()
    return session_id


def execute_turn(
    client: httpx.Client,
    agent_id: str,
    session_id: str,
    user_message: str,
    turn_number: int,
) -> dict[str, Any]:
    """
    Execute a single turn in the agent session.

    A turn is one user message -> agent response cycle. The server handles
    the full reasoning loop internally:
      1. Send user message + conversation history to the LLM
      2. If the LLM requests a tool call, execute it via the configured
         tool runtime (MCP server)
      3. Feed the tool result back to the LLM
      4. Repeat steps 2-3 until the LLM produces a final text response
         (or max_infer_iters is reached)

    The response includes:
      - output_message: the agent's final text response
      - steps: array of structured execution steps showing the full chain

    Returns the full turn response dict.
    """
    print(f"=== Executing turn {turn_number} ===")
    print(f"User: {user_message}")
    print()

    payload = {
        "messages": [
            {
                "role": "user",
                "content": user_message,
            }
        ]
    }

    response = client.post(
        f"/v1alpha/agents/{agent_id}/sessions/{session_id}/turns",
        json=payload,
    )
    response.raise_for_status()
    result = response.json()

    # Display the execution steps
    display_turn_steps(result)

    return result


def display_turn_steps(turn_result: dict[str, Any]) -> None:
    """
    Display the structured execution steps from a turn response.

    Each turn response contains a 'steps' array showing exactly what
    happened during the agent's reasoning:
      - 'inference' steps show LLM calls (with or without tool_calls)
      - 'tool_execution' steps show tool invocations and results
      - 'shield_call' steps show safety filter evaluations
    """
    steps = turn_result.get("steps", [])

    for i, step in enumerate(steps, 1):
        step_type = step.get("step_type", "unknown")
        print(f"--- Step {i}: {step_type} ---")

        if step_type == "inference":
            model_response = step.get("model_response", {})
            tool_calls = model_response.get("tool_calls", [])

            if tool_calls:
                for tc in tool_calls:
                    tool_name = tc.get("tool_name", "unknown")
                    arguments = tc.get("arguments", {})
                    print(f"LLM decided to call tool: {tool_name}({json.dumps(arguments)})")
            else:
                content = model_response.get("content", "")
                if content:
                    # Truncate long responses for display
                    display = content[:500] + "..." if len(content) > 500 else content
                    print(f"LLM generated final response.")
                else:
                    print("LLM returned empty response.")

        elif step_type == "tool_execution":
            tool_calls = step.get("tool_calls", [])
            for tc in tool_calls:
                tool_name = tc.get("tool_name", "unknown")
                result_str = tc.get("result", "")
                # Truncate long tool results for display
                display = result_str[:300] + "..." if len(result_str) > 300 else result_str
                print(f"Tool: {tool_name}")
                print(f"Result: {display}")

        elif step_type == "shield_call":
            violation = step.get("violation", None)
            if violation:
                print(f"Safety shield triggered: {violation}")
            else:
                print("Safety shield passed.")

        print()

    # Display the final output message
    output = turn_result.get("output_message", {})
    content = output.get("content", "No response")
    print(f"Assistant response:")
    print(content)
    print()
    print("-" * 60)
    print()


def delete_agent(client: httpx.Client, agent_id: str) -> None:
    """
    Delete the agent and clean up server-side resources.

    Deleting an agent also removes all its sessions and conversation
    history. In production, you might keep agents alive across requests
    and only delete them during maintenance.
    """
    print("=== Cleaning up ===")
    response = client.delete(f"/v1alpha/agents/{agent_id}")
    response.raise_for_status()
    print(f"Deleted agent {agent_id}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OGX Agents API lifecycle demo",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Custom query to send to the agent (default: use built-in demo queries)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the agent config without executing any API calls",
    )
    args = parser.parse_args()

    # Validate environment
    if not OGX_ENDPOINT:
        print("ERROR: OGX_ENDPOINT environment variable is not set.", file=sys.stderr)
        print("Set it to the LlamaStackApp route URL, e.g.:", file=sys.stderr)
        print('  export OGX_ENDPOINT="https://llama-stack-agent-myproject.apps.sandbox.example.com"', file=sys.stderr)
        sys.exit(1)

    print(f"OGX Endpoint: {OGX_ENDPOINT}")
    print(f"Model: {MODEL_NAME}")
    print(f"MCP Server: {MCP_SERVER_URL}")
    print()

    # Dry run -- just show the config
    if args.dry_run:
        print("=== Dry run -- agent config ===")
        config = {
            "model": MODEL_NAME,
            "instructions": AGENT_INSTRUCTIONS,
            "tools": [{"type": "mcp", "server_url": MCP_SERVER_URL, "transport": "sse"}],
            "tool_choice": "auto",
            "max_infer_iters": 5,
        }
        print(json.dumps(config, indent=2))
        return

    # Determine queries to run
    if args.query:
        queries = [args.query]
    else:
        queries = DEFAULT_QUERIES

    # Run the full agent lifecycle
    with get_client() as client:
        # Phase 1: Setup
        agent_id = create_agent(client)
        session_id = create_session(client, agent_id)

        try:
            # Phase 2: Execute turns
            for i, query in enumerate(queries, 1):
                execute_turn(client, agent_id, session_id, query, turn_number=i)

        finally:
            # Phase 3: Cleanup (always runs, even on error)
            delete_agent(client, agent_id)

    print("Done.")


if __name__ == "__main__":
    main()
