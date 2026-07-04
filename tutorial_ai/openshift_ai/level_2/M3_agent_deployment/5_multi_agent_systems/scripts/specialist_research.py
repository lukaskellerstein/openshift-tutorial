"""
Research Specialist Agent -- FastAPI Application

A FastAPI service implementing a specialist agent focused on information
gathering and research tasks. Uses a LangGraph ReAct agent with MCP tools
to search for information, query cluster resources, and browse documentation.

This agent is called by the Supervisor agent when a task is classified as
a research task. It can also be invoked directly for testing.

Environment variables:
    VLLM_ENDPOINT   -- Base URL for the vLLM OpenAI-compatible API
                       (e.g. http://vllm-server:8000/v1)
    VLLM_MODEL_NAME -- Model name served by vLLM
                       (e.g. granite-3.3-8b-instruct)
    MCP_SERVERS     -- JSON array of MCP server connection objects
                       (e.g. [{"url": "http://mcp-openshift:8080/mcp", "transport": "streamable_http"}])
    LOG_LEVEL       -- Logging level (default: INFO)
"""

import json
import logging
import os
from contextlib import asynccontextmanager
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

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global state -- populated during lifespan startup
# ---------------------------------------------------------------------------

mcp_client: MultiServerMCPClient | None = None
agent_executor: Any = None

# ---------------------------------------------------------------------------
# Research-specific system prompt
# ---------------------------------------------------------------------------

RESEARCH_SYSTEM_PROMPT = """\
You are a Research Specialist agent. Your expertise is in gathering \
information, searching documentation, querying cluster resources, and \
providing thorough, well-structured answers.

When given a task:
1. Use your available tools to gather relevant information.
2. Synthesize the information into a clear, well-organized response.
3. Cite specific resources, commands, or documentation where applicable.
4. If you cannot find the information, say so clearly -- do not fabricate.

You have access to MCP tools that may include:
- OpenShift cluster resource queries (pods, deployments, services, routes)
- Documentation search
- Web browsing

Always structure your response with clear headings and bullet points \
when the answer is complex.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_mcp_servers() -> dict[str, dict]:
    """Parse MCP_SERVERS env var into the dict format expected by
    MultiServerMCPClient.

    Input JSON is a list of objects:
        [{"url": "http://host:port/mcp", "transport": "streamable_http"}]

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
        api_key="EMPTY",
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
        logger.info("No MCP servers configured -- research agent will run without tools")

    # -- Agent ----------------------------------------------------------------
    agent_executor = create_react_agent(
        llm,
        tools,
        prompt=RESEARCH_SYSTEM_PROMPT,
    )
    logger.info("Research specialist agent ready (tools=%d)", len(tools))

    yield

    # -- Shutdown -------------------------------------------------------------
    if mcp_client is not None:
        await mcp_client.__aexit__(None, None, None)
        logger.info("MCP clients disconnected")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Research Specialist Agent",
    description=(
        "Specialist agent for information gathering, documentation search, "
        "and cluster resource queries via MCP tools"
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class InvokeRequest(BaseModel):
    """Request body for the /invoke endpoint."""

    message: str = Field(..., description="Research task to perform")
    thread_id: str = Field(
        default="default",
        description="Conversation thread identifier",
    )


class InvokeResponse(BaseModel):
    """Response body from the /invoke endpoint."""

    response: str = Field(..., description="Research specialist's response")
    tools_used: list[str] = Field(
        default_factory=list,
        description="Names of MCP tools used during research",
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
        raise HTTPException(status_code=503, detail="Research agent not ready")
    return {"status": "ready", "specialist": "research"}


@app.post("/invoke", response_model=InvokeResponse)
async def invoke(request: InvokeRequest):
    """Invoke the research specialist agent."""
    if agent_executor is None:
        raise HTTPException(status_code=503, detail="Research agent not initialised")

    try:
        result = await agent_executor.ainvoke(
            {"messages": [("user", request.message)]},
            config={"configurable": {"thread_id": request.thread_id}},
        )
    except Exception as exc:
        logger.exception("Research agent invocation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Extract the final AI message and tool usage
    messages = result.get("messages", [])
    final_message = ""
    tools_used: list[str] = []

    for msg in messages:
        if hasattr(msg, "content") and hasattr(msg, "type"):
            if msg.type == "ai" and msg.content:
                final_message = msg.content
            if msg.type == "tool":
                tools_used.append(msg.name)

    return InvokeResponse(response=final_message, tools_used=tools_used)
