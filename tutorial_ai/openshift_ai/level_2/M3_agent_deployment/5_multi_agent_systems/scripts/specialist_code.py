"""
Code Specialist Agent -- FastAPI Application

A FastAPI service implementing a specialist agent focused on code
generation tasks. Uses a LangGraph agent optimised for generating
YAML manifests, Python scripts, shell commands, Dockerfiles, and
other code artefacts.

This agent is called by the Supervisor agent when a task is classified
as a code generation task. It can also be invoked directly for testing.

Environment variables:
    VLLM_ENDPOINT   -- Base URL for the vLLM OpenAI-compatible API
                       (e.g. http://vllm-server:8000/v1)
    VLLM_MODEL_NAME -- Model name served by vLLM
                       (e.g. granite-3.3-8b-instruct)
    LOG_LEVEL       -- Logging level (default: INFO)
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

VLLM_ENDPOINT = os.environ.get("VLLM_ENDPOINT", "http://vllm-server:8000/v1")
VLLM_MODEL_NAME = os.environ.get("VLLM_MODEL_NAME", "granite-3.3-8b-instruct")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global state -- populated during lifespan startup
# ---------------------------------------------------------------------------

agent_executor: Any = None

# ---------------------------------------------------------------------------
# Code-specific system prompt
# ---------------------------------------------------------------------------

CODE_SYSTEM_PROMPT = """\
You are a Code Specialist agent. Your expertise is in generating \
high-quality code, configuration files, and technical artefacts for \
Kubernetes and OpenShift environments.

When given a task:
1. Understand the requirements precisely before generating code.
2. Generate clean, well-commented, production-quality code.
3. Always include the language identifier in code blocks (e.g. ```yaml, ```python, ```bash).
4. Explain key decisions and configuration choices.
5. Follow best practices for the target platform (OpenShift security defaults, \
   resource limits, proper labels).

You can generate:
- **YAML manifests**: Deployments, Services, Routes, BuildConfigs, ConfigMaps, etc.
- **Python scripts**: FastAPI apps, LangChain/LangGraph agents, data processing
- **Shell scripts**: Setup, teardown, debugging, deployment automation
- **Dockerfiles / Containerfiles**: Multi-stage builds, UBI-based images
- **Helm charts**: values.yaml, templates

Always structure your response as:
1. Brief explanation of what the code does
2. The code itself in properly fenced code blocks
3. Usage instructions (how to apply/run the code)
"""


# ---------------------------------------------------------------------------
# Lifespan -- build the agent graph
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler.

    On startup:
        1. Build the LangGraph agent with the code-focused system prompt.

    The code specialist does not use MCP tools -- it relies on the LLM's
    code generation capabilities directly.
    """
    global agent_executor

    # -- LLM -----------------------------------------------------------------
    llm = ChatOpenAI(
        base_url=VLLM_ENDPOINT,
        api_key="EMPTY",
        model=VLLM_MODEL_NAME,
        temperature=0,
    )
    logger.info("LLM configured: endpoint=%s  model=%s", VLLM_ENDPOINT, VLLM_MODEL_NAME)

    # -- Agent ----------------------------------------------------------------
    # The code specialist uses no external tools -- it generates code
    # using the LLM's built-in knowledge. Tools could be added later
    # (e.g. a linter, a schema validator) if needed.
    agent_executor = create_react_agent(
        llm,
        tools=[],
        prompt=CODE_SYSTEM_PROMPT,
    )
    logger.info("Code specialist agent ready")

    yield


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Code Specialist Agent",
    description=(
        "Specialist agent for code generation: YAML manifests, Python scripts, "
        "shell commands, Dockerfiles, and other technical artefacts"
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class InvokeRequest(BaseModel):
    """Request body for the /invoke endpoint."""

    message: str = Field(..., description="Code generation task to perform")
    thread_id: str = Field(
        default="default",
        description="Conversation thread identifier",
    )


class CodeBlock(BaseModel):
    """A single generated code block."""

    language: str = Field(..., description="Language identifier (yaml, python, bash, etc.)")
    code: str = Field(..., description="The generated code")
    filename: str = Field(
        default="",
        description="Suggested filename for the code (optional)",
    )


class InvokeResponse(BaseModel):
    """Response body from the /invoke endpoint."""

    response: str = Field(
        ..., description="Full response including explanation and code"
    )
    code_blocks: list[CodeBlock] = Field(
        default_factory=list,
        description="Extracted code blocks from the response",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_code_blocks(text: str) -> list[CodeBlock]:
    """Extract fenced code blocks from the response text.

    Parses markdown-style code fences:
        ```language
        code here
        ```
    """
    blocks: list[CodeBlock] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```") and line.strip() != "```":
            # Opening fence with language
            language = line.strip().removeprefix("```").strip()
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            blocks.append(
                CodeBlock(
                    language=language,
                    code="\n".join(code_lines),
                )
            )
        i += 1
    return blocks


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
        raise HTTPException(status_code=503, detail="Code agent not ready")
    return {"status": "ready", "specialist": "code"}


@app.post("/invoke", response_model=InvokeResponse)
async def invoke(request: InvokeRequest):
    """Invoke the code specialist agent."""
    if agent_executor is None:
        raise HTTPException(status_code=503, detail="Code agent not initialised")

    try:
        result = await agent_executor.ainvoke(
            {"messages": [("user", request.message)]},
            config={"configurable": {"thread_id": request.thread_id}},
        )
    except Exception as exc:
        logger.exception("Code agent invocation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Extract the final AI message
    messages = result.get("messages", [])
    final_message = ""

    for msg in messages:
        if hasattr(msg, "content") and hasattr(msg, "type"):
            if msg.type == "ai" and msg.content:
                final_message = msg.content

    # Extract code blocks from the response
    code_blocks = _extract_code_blocks(final_message)

    return InvokeResponse(response=final_message, code_blocks=code_blocks)
