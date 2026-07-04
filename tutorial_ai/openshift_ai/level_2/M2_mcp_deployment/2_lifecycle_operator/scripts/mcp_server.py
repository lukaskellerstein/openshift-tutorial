"""
Custom MCP Server: ShopInsights Tools

A simple MCP server that provides product and order analytics tools.
This is deployed on OpenShift AI via the MCP Lifecycle Operator.

Transport: Streamable HTTP (for Kubernetes server-to-server communication)
"""

import json
import os
import contextlib
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
import random

import uvicorn
from mcp.server.lowlevel import Server
import mcp.types as types
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send


# ---------------------------------------------------------------------------
# Simulated data (in production, these would query a database or API)
# ---------------------------------------------------------------------------

PRODUCTS = {
    "PROD-001": {"name": "Wireless Headphones", "category": "Electronics", "price": 79.99, "stock": 142},
    "PROD-002": {"name": "Running Shoes", "category": "Footwear", "price": 129.99, "stock": 67},
    "PROD-003": {"name": "Coffee Maker", "category": "Kitchen", "price": 49.99, "stock": 203},
    "PROD-004": {"name": "Backpack", "category": "Accessories", "price": 59.99, "stock": 91},
    "PROD-005": {"name": "Smart Watch", "category": "Electronics", "price": 199.99, "stock": 38},
}

ORDERS = [
    {"order_id": "ORD-1001", "product_id": "PROD-001", "quantity": 2, "status": "delivered", "date": "2026-07-01"},
    {"order_id": "ORD-1002", "product_id": "PROD-003", "quantity": 1, "status": "shipped", "date": "2026-07-02"},
    {"order_id": "ORD-1003", "product_id": "PROD-005", "quantity": 1, "status": "processing", "date": "2026-07-03"},
    {"order_id": "ORD-1004", "product_id": "PROD-002", "quantity": 3, "status": "delivered", "date": "2026-06-28"},
    {"order_id": "ORD-1005", "product_id": "PROD-004", "quantity": 1, "status": "shipped", "date": "2026-07-03"},
    {"order_id": "ORD-1006", "product_id": "PROD-001", "quantity": 1, "status": "delivered", "date": "2026-06-30"},
    {"order_id": "ORD-1007", "product_id": "PROD-003", "quantity": 2, "status": "processing", "date": "2026-07-04"},
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def get_product_info(product_id: str) -> dict:
    """Get detailed information about a product."""
    product = PRODUCTS.get(product_id)
    if not product:
        return {"error": f"Product {product_id} not found"}
    return {"product_id": product_id, **product}


def list_products(category: str | None = None) -> list[dict]:
    """List all products, optionally filtered by category."""
    results = []
    for pid, product in PRODUCTS.items():
        if category and product["category"].lower() != category.lower():
            continue
        results.append({"product_id": pid, **product})
    return results


def get_order_summary(days: int = 7) -> dict:
    """Get order summary for the last N days."""
    cutoff = datetime.now() - timedelta(days=days)
    recent_orders = [
        o for o in ORDERS
        if datetime.strptime(o["date"], "%Y-%m-%d") >= cutoff
    ]

    total_revenue = 0.0
    for order in recent_orders:
        product = PRODUCTS.get(order["product_id"], {})
        total_revenue += product.get("price", 0) * order["quantity"]

    status_counts = {}
    for order in recent_orders:
        status = order["status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "period_days": days,
        "total_orders": len(recent_orders),
        "total_revenue": round(total_revenue, 2),
        "status_breakdown": status_counts,
        "orders": recent_orders,
    }


def get_low_stock_alerts(threshold: int = 50) -> list[dict]:
    """Get products with stock below the threshold."""
    alerts = []
    for pid, product in PRODUCTS.items():
        if product["stock"] < threshold:
            alerts.append({
                "product_id": pid,
                "name": product["name"],
                "current_stock": product["stock"],
                "threshold": threshold,
            })
    return alerts


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

def serve():
    server = Server("shopinsights-tools")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="get_product_info",
                description="Get detailed information about a product including name, category, price, and stock level.",
                inputSchema={
                    "type": "object",
                    "required": ["product_id"],
                    "properties": {
                        "product_id": {
                            "type": "string",
                            "description": "The product ID (e.g., PROD-001)",
                        }
                    },
                },
            ),
            types.Tool(
                name="list_products",
                description="List all products in the catalog. Optionally filter by category (Electronics, Footwear, Kitchen, Accessories).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "Optional category filter",
                        }
                    },
                },
            ),
            types.Tool(
                name="get_order_summary",
                description="Get a summary of orders for the last N days, including total revenue and status breakdown.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "Number of days to look back (default: 7)",
                            "default": 7,
                        }
                    },
                },
            ),
            types.Tool(
                name="get_low_stock_alerts",
                description="Get products with stock levels below a specified threshold.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "threshold": {
                            "type": "integer",
                            "description": "Stock threshold for alerts (default: 50)",
                            "default": 50,
                        }
                    },
                },
            ),
        ]

    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: dict
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:

        if name == "get_product_info":
            result = get_product_info(arguments["product_id"])
        elif name == "list_products":
            result = list_products(arguments.get("category"))
        elif name == "get_order_summary":
            result = get_order_summary(arguments.get("days", 7))
        elif name == "get_low_stock_alerts":
            result = get_low_stock_alerts(arguments.get("threshold", 50))
        else:
            result = {"error": f"Unknown tool: {name}"}

        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    # ------------------------------------------------------------------
    # Streamable HTTP transport (required for Kubernetes deployment)
    # ------------------------------------------------------------------

    session_manager = StreamableHTTPSessionManager(
        app=server,
        json_response=True,
        event_store=None,   # No resumability needed for stateless tools
        stateless=True,
    )

    async def handle_streamable_http(
        scope: Scope, receive: Receive, send: Send
    ) -> None:
        await session_manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            print("ShopInsights MCP Server started (Streamable HTTP)")
            try:
                yield
            finally:
                print("ShopInsights MCP Server shutting down...")

    starlette_app = Starlette(
        debug=False,
        routes=[
            Mount("/mcp", app=handle_streamable_http),
        ],
        lifespan=lifespan,
    )

    port = int(os.environ.get("MCP_PORT", "8080"))
    uvicorn.run(starlette_app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    serve()
