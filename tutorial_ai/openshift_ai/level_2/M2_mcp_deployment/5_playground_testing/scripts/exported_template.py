"""
Exported Python code template from GenAI Playground

This is an example of the code template you get when clicking "View code"
in the GenAI Playground after configuring an MCP server connection.

Adapt this template for production use by:
1. Adding error handling
2. Configuring environment variables for URLs and tokens
3. Adding proper logging
4. Wrapping in a FastAPI/Flask endpoint if deploying as a service

This uses the openai SDK to call the vLLM endpoint (OpenAI-compatible API)
and the mcp SDK to call MCP tools.
"""

import asyncio
import json
import os
from openai import OpenAI
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession


# ---------------------------------------------------------------------------
# Configuration (update these for your environment)
# ---------------------------------------------------------------------------

# vLLM endpoint (the model serving endpoint from L1-M2)
VLLM_URL = os.environ.get("VLLM_URL", "https://gemma4-e4b-my-project.apps.cluster.example.com")
MODEL_NAME = os.environ.get("MODEL_NAME", "gemma4-e4b")

# MCP server endpoint (direct or via gateway)
MCP_URL = os.environ.get("MCP_URL", "http://shopinsights-mcp.mcp-servers.svc.cluster.local:8080/mcp")


# ---------------------------------------------------------------------------
# MCP tool discovery
# ---------------------------------------------------------------------------

async def get_mcp_tools(mcp_url: str) -> list[dict]:
    """Connect to MCP server and get available tools in OpenAI format."""
    async with streamablehttp_client(mcp_url) as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()
            tools_result = await session.list_tools()

            # Convert MCP tools to OpenAI function calling format
            openai_tools = []
            for tool in tools_result.tools:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.inputSchema,
                    }
                })
            return openai_tools


async def call_mcp_tool(mcp_url: str, tool_name: str, arguments: dict) -> str:
    """Call an MCP tool and return the result."""
    async with streamablehttp_client(mcp_url) as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return result.content[0].text


# ---------------------------------------------------------------------------
# Agent loop (LLM + tool calling)
# ---------------------------------------------------------------------------

async def chat_with_tools(user_message: str):
    """Send a message to the LLM with MCP tools available."""

    # 1. Get available tools from the MCP server
    tools = await get_mcp_tools(MCP_URL)
    print(f"Available tools: {[t['function']['name'] for t in tools]}")

    # 2. Create the OpenAI client pointing at vLLM
    client = OpenAI(
        base_url=f"{VLLM_URL}/v1",
        api_key="not-needed",  # vLLM doesn't require an API key by default
    )

    # 3. Send the user message with tools
    messages = [
        {"role": "system", "content": "You are a helpful assistant with access to ShopInsights tools. Use them to answer questions about products and orders."},
        {"role": "user", "content": user_message},
    ]

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        tools=tools,
        tool_choice="auto",
    )

    # 4. Handle tool calls (if any)
    assistant_message = response.choices[0].message

    if assistant_message.tool_calls:
        # Add the assistant's message (with tool calls) to the conversation
        messages.append(assistant_message.model_dump())

        # Execute each tool call via MCP
        for tool_call in assistant_message.tool_calls:
            print(f"\nTool call: {tool_call.function.name}({tool_call.function.arguments})")

            arguments = json.loads(tool_call.function.arguments)
            result = await call_mcp_tool(MCP_URL, tool_call.function.name, arguments)

            print(f"Tool result: {result[:200]}...")

            # Add the tool result to the conversation
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

        # 5. Get the final response with tool results
        final_response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
        )
        print(f"\nAssistant: {final_response.choices[0].message.content}")
    else:
        print(f"\nAssistant: {assistant_message.content}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Example queries that will trigger tool calls
    queries = [
        "What products do you have in the Electronics category?",
        "Give me an order summary for the last 7 days.",
        "Are there any products with low stock?",
    ]

    for query in queries:
        print(f"\n{'=' * 60}")
        print(f"User: {query}")
        print("-" * 60)
        asyncio.run(chat_with_tools(query))
