"""
MCP Client for testing the ShopInsights MCP Server

Connects to the MCP server via Streamable HTTP and calls each tool.
Use this to verify the server is working after deployment on OpenShift.

Usage:
    # Local testing
    python mcp_client.py http://localhost:8080/mcp

    # Testing against OpenShift Route
    python mcp_client.py https://shopinsights-mcp-my-project.apps.cluster.example.com/mcp
"""

import asyncio
import json
import sys

from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession


async def test_mcp_server(server_url: str):
    """Connect to the MCP server and test each tool."""

    print(f"Connecting to MCP server at: {server_url}")
    print("=" * 60)

    async with streamablehttp_client(server_url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # -----------------------------------------------------------
            # 1. List available tools
            # -----------------------------------------------------------
            print("\n--- Available Tools ---")
            tools_result = await session.list_tools()
            for tool in tools_result.tools:
                print(f"  - {tool.name}: {tool.description[:80]}...")

            # -----------------------------------------------------------
            # 2. Test: get_product_info
            # -----------------------------------------------------------
            print("\n--- Test: get_product_info ---")
            result = await session.call_tool("get_product_info", {"product_id": "PROD-001"})
            for content in result.content:
                data = json.loads(content.text)
                print(f"  Product: {data.get('name')} | Price: ${data.get('price')} | Stock: {data.get('stock')}")

            # -----------------------------------------------------------
            # 3. Test: list_products (filtered by category)
            # -----------------------------------------------------------
            print("\n--- Test: list_products (category=Electronics) ---")
            result = await session.call_tool("list_products", {"category": "Electronics"})
            for content in result.content:
                products = json.loads(content.text)
                for p in products:
                    print(f"  {p['product_id']}: {p['name']} (${p['price']})")

            # -----------------------------------------------------------
            # 4. Test: get_order_summary
            # -----------------------------------------------------------
            print("\n--- Test: get_order_summary (last 7 days) ---")
            result = await session.call_tool("get_order_summary", {"days": 7})
            for content in result.content:
                summary = json.loads(content.text)
                print(f"  Total orders: {summary['total_orders']}")
                print(f"  Total revenue: ${summary['total_revenue']}")
                print(f"  Status breakdown: {summary['status_breakdown']}")

            # -----------------------------------------------------------
            # 5. Test: get_low_stock_alerts
            # -----------------------------------------------------------
            print("\n--- Test: get_low_stock_alerts (threshold=50) ---")
            result = await session.call_tool("get_low_stock_alerts", {"threshold": 50})
            for content in result.content:
                alerts = json.loads(content.text)
                if alerts:
                    for alert in alerts:
                        print(f"  WARNING: {alert['name']} - stock: {alert['current_stock']} (threshold: {alert['threshold']})")
                else:
                    print("  No low stock alerts.")

    print("\n" + "=" * 60)
    print("All tests passed.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python mcp_client.py <server-url>")
        print("Example: python mcp_client.py http://localhost:8080/mcp")
        sys.exit(1)

    server_url = sys.argv[1]
    asyncio.run(test_mcp_server(server_url))
