"""
LangGraph ReAct Agent with MCP Tool Calling -- FastAPI Application

A FastAPI service wrapping a LangGraph ReAct agent that connects to a
vLLM inference endpoint (OpenAI-compatible API) and uses MCP servers
for tool calling. Designed for managing OpenShift cluster resources
via the MCP Server for OpenShift.

Environment variables:
    VLLM_ENDPOINT        -- Base URL for the vLLM OpenAI-compatible API
                            (e.g. http://vllm-server:8000/v1)
    VLLM_MODEL_NAME      -- Model name served by vLLM
                            (e.g. granite-3.3-8b-instruct)
    MCP_SERVERS           -- JSON array of MCP server connection objects
                            (e.g. [{"url": "http://mcp-server:8080/mcp",
                                     "transport": "streamable_http"}])
    AGENT_SYSTEM_PROMPT   -- System prompt for the agent (optional)
    LOG_LEVEL             -- Logging level (default: INFO)
"""

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

VLLM_ENDPOINT = os.environ.get("VLLM_ENDPOINT", "http://vllm-server:8000/v1")
VLLM_MODEL_NAME = os.environ.get("VLLM_MODEL_NAME", "granite-3.3-8b-instruct")
MCP_SERVERS_RAW = os.environ.get("MCP_SERVERS", "[]")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

SYSTEM_PROMPT = os.environ.get("AGENT_SYSTEM_PROMPT", """You are an OpenShift cluster management assistant. You have access to tools
that let you inspect and manage Kubernetes and OpenShift resources.

When a user asks about cluster resources, use the available tools to get
real-time information. Always report what you find accurately.

If a tool call fails, explain the error to the user and suggest what
permissions might be needed.

Always be concise and format your responses clearly.""")

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global state -- populated during lifespan startup
# ---------------------------------------------------------------------------

mcp_client: MultiServerMCPClient | None = None
agent_executor: Any = None
tools_loaded: list[str] = []


def _parse_mcp_servers() -> dict[str, dict]:
    """Parse MCP_SERVERS env var into the dict format expected by
    MultiServerMCPClient.

    Input JSON is a list of objects:
        [{"url": "http://host:port/mcp", "transport": "streamable_http"}]

    Supported transports:
        - "streamable_http"  -- Direct connection to MCP server (preferred)
        - "sse"              -- Connection via MCP Gateway

    Output is a dict keyed by a generated server name:
        {"server_0": {"url": "http://host:port/mcp", "transport": "streamable_http"}}
    """
    try:
        servers = json.loads(MCP_SERVERS_RAW)
    except json.JSONDecodeError:
        logger.warning("Failed to parse MCP_SERVERS -- no MCP tools will be available")
        return {}

    if not isinstance(servers, list):
        logger.warning("MCP_SERVERS is not a JSON array -- no MCP tools will be available")
        return {}

    if not servers:
        logger.info("MCP_SERVERS is empty -- agent will run without tools")
        return {}

    parsed = {}
    for i, srv in enumerate(servers):
        if "url" not in srv:
            logger.warning("MCP server entry %d missing 'url' -- skipping", i)
            continue
        if "transport" not in srv:
            logger.warning("MCP server entry %d missing 'transport' -- defaulting to streamable_http", i)
            srv["transport"] = "streamable_http"
        parsed[f"server_{i}"] = srv
        logger.info("MCP server configured: %s (%s)", srv["url"], srv["transport"])

    return parsed


# ---------------------------------------------------------------------------
# Lifespan -- connect MCP clients and build the agent graph
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler.

    On startup:
        1. Initialize the LLM client (vLLM via OpenAI-compatible API).
        2. Connect to MCP servers and discover available tools.
        3. Build the LangGraph ReAct agent with discovered tools.

    On shutdown:
        1. Disconnect MCP clients gracefully.
    """
    global mcp_client, agent_executor, tools_loaded

    # -- LLM -----------------------------------------------------------------
    llm = ChatOpenAI(
        base_url=VLLM_ENDPOINT,
        api_key="EMPTY",  # vLLM does not require a real key
        model=VLLM_MODEL_NAME,
        temperature=0,
    )
    logger.info("LLM configured: endpoint=%s  model=%s", VLLM_ENDPOINT, VLLM_MODEL_NAME)

    # -- MCP tools ------------------------------------------------------------
    server_params = _parse_mcp_servers()
    tools: list = []

    if server_params:
        try:
            mcp_client = MultiServerMCPClient(server_params)
            await mcp_client.__aenter__()
            tools = mcp_client.get_tools()
            tools_loaded = [t.name for t in tools]
            logger.info(
                "MCP tools loaded (%d tools): %s",
                len(tools_loaded),
                tools_loaded,
            )
        except Exception as exc:
            logger.error("Failed to connect to MCP servers: %s", exc)
            logger.warning("Agent will run without MCP tools")
            tools = []
            tools_loaded = []
    else:
        logger.info("No MCP servers configured -- agent will run without tools")

    # -- Agent ----------------------------------------------------------------
    agent_executor = create_react_agent(
        llm,
        tools,
        prompt=SYSTEM_PROMPT,
    )
    logger.info("ReAct agent ready (%d tools available)", len(tools))

    yield

    # -- Shutdown -------------------------------------------------------------
    if mcp_client is not None:
        try:
            await mcp_client.__aexit__(None, None, None)
            logger.info("MCP clients disconnected")
        except Exception as exc:
            logger.warning("Error disconnecting MCP clients: %s", exc)


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="LangGraph Agent with MCP Tools",
    description=(
        "ReAct agent backed by vLLM with MCP tool integration for "
        "OpenShift cluster management"
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class InvokeRequest(BaseModel):
    """Request body for the /invoke endpoint."""

    message: str = Field(..., description="User message to send to the agent")
    thread_id: str = Field(
        default="default",
        description="Conversation thread identifier for multi-turn sessions",
    )


class ToolCallRecord(BaseModel):
    """Record of a single tool call made during agent invocation."""

    tool: str = Field(..., description="Name of the MCP tool that was called")
    content: str | None = Field(
        None, description="Tool result content (may be truncated)"
    )
    timestamp: str = Field(..., description="ISO 8601 timestamp of the tool call")


class InvokeResponse(BaseModel):
    """Response body from the /invoke endpoint."""

    response: str = Field(..., description="Agent's final response")
    tool_calls: list[ToolCallRecord] = Field(
        default_factory=list,
        description="Ordered list of tool calls made during this invocation",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/healthz")
async def healthz():
    """Liveness probe -- returns 200 if the process is alive."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    """Readiness probe -- returns 200 only when the agent is fully initialised."""
    if agent_executor is None:
        raise HTTPException(status_code=503, detail="Agent not ready")
    return {"status": "ready", "tools_loaded": len(tools_loaded)}


@app.post("/invoke", response_model=InvokeResponse)
async def invoke(request: InvokeRequest):
    """Invoke the agent synchronously and return the final response.

    The agent will:
    1. Send the user message to the LLM along with available tool schemas.
    2. If the LLM decides to call a tool, execute the MCP tool call.
    3. Feed the tool result back to the LLM.
    4. Repeat steps 2-3 until the LLM produces a final text response.
    5. Return the response along with a log of all tool calls made.
    """
    if agent_executor is None:
        raise HTTPException(status_code=503, detail="Agent not initialised")

    logger.info('POST /invoke - message: "%s"', request.message[:100])

    try:
        result = await agent_executor.ainvoke(
            {"messages": [("user", request.message)]},
            config={"configurable": {"thread_id": request.thread_id}},
        )
    except Exception as exc:
        logger.exception("Agent invocation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # -- Extract final response and tool call log ----------------------------
    messages = result.get("messages", [])
    final_message = ""
    tool_calls_log: list[ToolCallRecord] = []
    tool_call_count = 0

    for msg in messages:
        if not hasattr(msg, "type"):
            continue

        # Capture the last AI message with content as the final response
        if msg.type == "ai" and getattr(msg, "content", None):
            final_message = msg.content

        # Log each tool call with timestamp
        if msg.type == "tool":
            tool_call_count += 1
            content_preview = msg.content[:500] if msg.content else None
            timestamp = datetime.now(timezone.utc).isoformat()

            tool_calls_log.append(
                ToolCallRecord(
                    tool=msg.name,
                    content=content_preview,
                    timestamp=timestamp,
                )
            )
            logger.info(
                "Tool call #%d: %s -> %s",
                tool_call_count,
                msg.name,
                msg.content[:100] if msg.content else "(empty)",
            )

    logger.info(
        "Agent response generated (%d tool calls)",
        tool_call_count,
    )

    return InvokeResponse(response=final_message, tool_calls=tool_calls_log)
