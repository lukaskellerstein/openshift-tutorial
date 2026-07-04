"""
Test client for the OpenShift MCP Server

Connects to the deployed OpenShift MCP Server and demonstrates
querying Kubernetes/OpenShift resources via MCP tools.

Usage:
    # Within the cluster (using Service DNS)
    python test_openshift_mcp.py http://openshift-mcp-server.mcp-servers.svc.cluster.local:8080/mcp

    # Via external Route
    python test_openshift_mcp.py https://openshift-mcp-server-mcp-servers.apps.cluster.example.com/mcp
"""

import asyncio
import json
import sys

from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession


async def test_openshift_mcp(server_url: str):
    """Connect to the OpenShift MCP Server and test cluster resource tools."""

    print(f"Connecting to OpenShift MCP Server at: {server_url}")
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
                print(f"  - {tool.name}")
            print(f"\n  Total: {len(tools_result.tools)} tools")

            # -----------------------------------------------------------
            # 2. List namespaces / projects
            # -----------------------------------------------------------
            print("\n--- List Projects ---")
            result = await session.call_tool("projects_list", {})
            for content in result.content:
                data = json.loads(content.text) if content.text.startswith("[") or content.text.startswith("{") else content.text
                if isinstance(data, list):
                    for project in data[:5]:
                        name = project.get("name", project) if isinstance(project, dict) else project
                        print(f"  - {name}")
                    if len(data) > 5:
                        print(f"  ... and {len(data) - 5} more")
                else:
                    print(f"  {str(data)[:200]}")

            # -----------------------------------------------------------
            # 3. List pods in a namespace
            # -----------------------------------------------------------
            print("\n--- List Pods (mcp-servers namespace) ---")
            try:
                result = await session.call_tool("pods_list_in_namespace", {"namespace": "mcp-servers"})
                for content in result.content:
                    print(f"  {content.text[:300]}")
            except Exception as e:
                print(f"  (Could not list pods: {e})")

            # -----------------------------------------------------------
            # 4. List events
            # -----------------------------------------------------------
            print("\n--- Recent Events (mcp-servers namespace) ---")
            try:
                result = await session.call_tool("events_list", {"namespace": "mcp-servers"})
                for content in result.content:
                    print(f"  {content.text[:300]}")
            except Exception as e:
                print(f"  (Could not list events: {e})")

            # -----------------------------------------------------------
            # 5. Get a specific resource
            # -----------------------------------------------------------
            print("\n--- Get Deployment (openshift-mcp-server) ---")
            try:
                result = await session.call_tool("resources_get", {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "name": "openshift-mcp-server",
                    "namespace": "mcp-servers",
                })
                for content in result.content:
                    print(f"  {content.text[:300]}")
            except Exception as e:
                print(f"  (Could not get deployment: {e})")

    print("\n" + "=" * 60)
    print("OpenShift MCP Server test complete.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_openshift_mcp.py <server-url>")
        print("Example: python test_openshift_mcp.py http://openshift-mcp-server.mcp-servers.svc.cluster.local:8080/mcp")
        sys.exit(1)

    server_url = sys.argv[1]
    asyncio.run(test_openshift_mcp(server_url))
