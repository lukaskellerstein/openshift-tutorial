"""
Test client for the MCP Gateway

Connects to the MCP Gateway and tests tool calls that are routed
to the appropriate backend MCP server.

The gateway federates multiple MCP servers behind a single endpoint,
so this client sees tools from ALL registered servers.

Usage:
    # With OAuth2 token
    python test_gateway.py https://mcp-gateway-mcp-servers.apps.cluster.example.com/mcp --token <token>

    # Without auth (if auth is disabled for testing)
    python test_gateway.py http://mcp-gateway.mcp-servers.svc.cluster.local:8443/mcp
"""

import asyncio
import json
import sys

from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession


async def test_gateway(gateway_url: str, token: str | None = None):
    """Connect to the MCP Gateway and test tools from multiple servers."""

    print(f"Connecting to MCP Gateway at: {gateway_url}")
    if token:
        print("Using OAuth2 token for authentication")
    print("=" * 60)

    # Configure headers for authentication
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with streamablehttp_client(gateway_url, headers=headers) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # -----------------------------------------------------------
            # 1. List ALL available tools (from all registered servers)
            # -----------------------------------------------------------
            print("\n--- All Available Tools (federated) ---")
            tools_result = await session.list_tools()
            for tool in tools_result.tools:
                print(f"  - {tool.name}: {tool.description[:70]}...")
            print(f"\n  Total tools: {len(tools_result.tools)}")

            # -----------------------------------------------------------
            # 2. Call a ShopInsights tool (routed to shopinsights-mcp)
            # -----------------------------------------------------------
            print("\n--- ShopInsights: list_products ---")
            try:
                result = await session.call_tool("list_products", {"category": "Electronics"})
                for content in result.content:
                    data = json.loads(content.text)
                    for p in data:
                        print(f"  {p['product_id']}: {p['name']} (${p['price']})")
            except Exception as e:
                print(f"  Error: {e}")

            # -----------------------------------------------------------
            # 3. Call an OpenShift tool (routed to openshift-mcp-server)
            # -----------------------------------------------------------
            print("\n--- OpenShift: projects_list ---")
            try:
                result = await session.call_tool("projects_list", {})
                for content in result.content:
                    print(f"  {content.text[:300]}")
            except Exception as e:
                print(f"  Error: {e}")

            # -----------------------------------------------------------
            # 4. Call another ShopInsights tool
            # -----------------------------------------------------------
            print("\n--- ShopInsights: get_order_summary ---")
            try:
                result = await session.call_tool("get_order_summary", {"days": 7})
                for content in result.content:
                    summary = json.loads(content.text)
                    print(f"  Orders: {summary.get('total_orders', 'N/A')}")
                    print(f"  Revenue: ${summary.get('total_revenue', 'N/A')}")
            except Exception as e:
                print(f"  Error: {e}")

            # -----------------------------------------------------------
            # 5. Call an OpenShift tool for pods
            # -----------------------------------------------------------
            print("\n--- OpenShift: pods_list_in_namespace (mcp-servers) ---")
            try:
                result = await session.call_tool("pods_list_in_namespace", {"namespace": "mcp-servers"})
                for content in result.content:
                    print(f"  {content.text[:300]}")
            except Exception as e:
                print(f"  Error: {e}")

    print("\n" + "=" * 60)
    print("Gateway test complete. Tools from multiple servers are accessible via a single endpoint.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_gateway.py <gateway-url> [--token <token>]")
        print("Example: python test_gateway.py https://mcp-gateway.apps.cluster.example.com/mcp --token eyJ...")
        sys.exit(1)

    gateway_url = sys.argv[1]
    token = None
    if "--token" in sys.argv:
        token_idx = sys.argv.index("--token") + 1
        if token_idx < len(sys.argv):
            token = sys.argv[token_idx]

    asyncio.run(test_gateway(gateway_url, token))
