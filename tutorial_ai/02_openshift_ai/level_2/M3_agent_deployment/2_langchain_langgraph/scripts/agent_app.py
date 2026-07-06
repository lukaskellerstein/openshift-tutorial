"""
LangGraph ReAct Agent -- FastAPI Application

A FastAPI service wrapping a LangGraph ReAct agent that connects to a
vLLM inference endpoint (OpenAI-compatible API) and integrates MCP
servers for tool calling.

Environment variables:
    VLLM_ENDPOINT   -- Base URL for the vLLM OpenAI-compatible API
                       (e.g. http://vllm-server:8000/v1)
    VLLM_MODEL_NAME -- Model name served by vLLM
                       (e.g. granite-3.3-8b-instruct)
    MCP_SERVERS     -- JSON array of MCP server connection objects
                       (e.g. [{"url": "http://mcp-gateway:8080/sse", "transport": "sse"}])
    LOG_LEVEL       -- Logging level (default: INFO)
"""

import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
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

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global state -- populated during lifespan startup
# ---------------------------------------------------------------------------

mcp_client: MultiServerMCPClient | None = None
agent_executor: Any = None


def _parse_mcp_servers() -> dict[str, dict]:
    """Parse MCP_SERVERS env var into the dict format expected by
    MultiServerMCPClient.

    Input JSON is a list of objects:
        [{"url": "http://host:port/sse", "transport": "sse"}]

    Output is a dict keyed by a generated server name:
        {"server_0": {"url": "http://host:port/sse", "transport": "sse"}}
    """
    try:
        servers = json.loads(MCP_SERVERS_RAW)
    except json.JSONDecodeError:
        logger.warning("Failed to parse MCP_SERVERS -- no MCP tools will be available")
        return {}

    if not isinstance(servers, list):
        logger.warning("MCP_SERVERS is not a JSON array -- no MCP tools will be available")
        return {}

    return {f"server_{i}": srv for i, srv in enumerate(servers)}


# ---------------------------------------------------------------------------
# Lifespan -- connect MCP clients and build the agent graph
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler.

    On startup:
        1. Connect to MCP servers and discover tools.
        2. Build the LangGraph ReAct agent with the discovered tools.

    On shutdown:
        1. Disconnect MCP clients.
    """
    global mcp_client, agent_executor

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
        mcp_client = MultiServerMCPClient(server_params)
        await mcp_client.__aenter__()
        tools = mcp_client.get_tools()
        logger.info("MCP tools loaded: %s", [t.name for t in tools])
    else:
        logger.info("No MCP servers configured -- agent will run without tools")

    # -- Agent ----------------------------------------------------------------
    agent_executor = create_react_agent(llm, tools)
    logger.info("ReAct agent ready")

    yield

    # -- Shutdown -------------------------------------------------------------
    if mcp_client is not None:
        await mcp_client.__aexit__(None, None, None)
        logger.info("MCP clients disconnected")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="LangGraph Agent",
    description="ReAct agent backed by vLLM with MCP tool integration",
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


class InvokeResponse(BaseModel):
    """Response body from the /invoke endpoint."""

    response: str = Field(..., description="Agent's final response")
    tool_calls: list[dict] = Field(
        default_factory=list,
        description="List of tool calls made during this invocation",
    )


class StreamRequest(BaseModel):
    """Request body for the /stream endpoint."""

    message: str = Field(..., description="User message to send to the agent")
    thread_id: str = Field(
        default="default",
        description="Conversation thread identifier for multi-turn sessions",
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
    return {"status": "ready"}


@app.post("/invoke", response_model=InvokeResponse)
async def invoke(request: InvokeRequest):
    """Invoke the agent synchronously and return the final response."""
    if agent_executor is None:
        raise HTTPException(status_code=503, detail="Agent not initialised")

    try:
        result = await agent_executor.ainvoke(
            {"messages": [("user", request.message)]},
            config={"configurable": {"thread_id": request.thread_id}},
        )
    except Exception as exc:
        logger.exception("Agent invocation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Extract the final AI message
    messages = result.get("messages", [])
    final_message = ""
    tool_calls_log: list[dict] = []

    for msg in messages:
        if hasattr(msg, "content") and hasattr(msg, "type"):
            if msg.type == "ai" and msg.content:
                final_message = msg.content
            if msg.type == "tool":
                tool_calls_log.append(
                    {"tool": msg.name, "content": msg.content}
                )

    return InvokeResponse(response=final_message, tool_calls=tool_calls_log)


@app.post("/stream")
async def stream(request: StreamRequest):
    """Stream agent events as Server-Sent Events (SSE)."""
    if agent_executor is None:
        raise HTTPException(status_code=503, detail="Agent not initialised")

    async def event_generator():
        try:
            async for event in agent_executor.astream_events(
                {"messages": [("user", request.message)]},
                config={"configurable": {"thread_id": request.thread_id}},
                version="v2",
            ):
                kind = event.get("event", "")
                if kind == "on_chat_model_stream":
                    content = event["data"]["chunk"].content
                    if content:
                        yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
                elif kind == "on_tool_start":
                    yield f"data: {json.dumps({'type': 'tool_start', 'name': event['name']})}\n\n"
                elif kind == "on_tool_end":
                    yield f"data: {json.dumps({'type': 'tool_end', 'name': event['name'], 'output': str(event['data'].get('output', ''))})}\n\n"
        except Exception as exc:
            logger.exception("Streaming failed")
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
