"""
Supervisor Agent -- FastAPI Application

A FastAPI service implementing the Supervisor pattern for multi-agent
orchestration. The supervisor receives user requests, classifies the
task type (research, code, or both), routes to the appropriate
specialist agent(s) via HTTP, and aggregates the results.

Architecture:
    User -> Supervisor -> Specialist Research Agent (research tasks)
                       -> Specialist Code Agent    (code tasks)
                       -> Both                     (compound tasks)

Environment variables:
    VLLM_ENDPOINT          -- Base URL for the vLLM OpenAI-compatible API
                              (e.g. http://vllm-server:8000/v1)
    VLLM_MODEL_NAME        -- Model name served by vLLM
                              (e.g. granite-3.3-8b-instruct)
    SPECIALIST_RESEARCH_URL -- URL of the research specialist service
                              (e.g. http://specialist-research:8080)
    SPECIALIST_CODE_URL    -- URL of the code specialist service
                              (e.g. http://specialist-code:8080)
    LOG_LEVEL              -- Logging level (default: INFO)
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

VLLM_ENDPOINT = os.environ.get("VLLM_ENDPOINT", "http://vllm-server:8000/v1")
VLLM_MODEL_NAME = os.environ.get("VLLM_MODEL_NAME", "granite-3.3-8b-instruct")
SPECIALIST_RESEARCH_URL = os.environ.get(
    "SPECIALIST_RESEARCH_URL", "http://specialist-research:8080"
)
SPECIALIST_CODE_URL = os.environ.get(
    "SPECIALIST_CODE_URL", "http://specialist-code:8080"
)
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global state -- populated during lifespan startup
# ---------------------------------------------------------------------------

llm: Any = None
http_client: httpx.AsyncClient | None = None

# Maximum number of retries for specialist calls
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2.0
SPECIALIST_TIMEOUT_SECONDS = 120.0

# ---------------------------------------------------------------------------
# Classification prompt
# ---------------------------------------------------------------------------

CLASSIFICATION_PROMPT = """\
You are a task classifier for a multi-agent system. Given a user message, \
classify the task into exactly one of these categories:

- "research" -- The user wants information, explanations, summaries, \
  documentation lookups, cluster status, or troubleshooting help.
- "code" -- The user wants code generation, YAML manifests, scripts, \
  Dockerfiles, configuration files, or code review.
- "both" -- The user wants a compound task that requires both research \
  AND code generation (e.g. "explain how Routes work and write me one").

Respond with ONLY a JSON object: {{"category": "<research|code|both>"}}
Do not include any other text.

User message: {message}
"""

AGGREGATION_PROMPT = """\
You are a helpful assistant aggregating results from specialist agents. \
The user asked: "{question}"

{results_section}

Synthesize these results into a single coherent response. If both research \
and code results are present, integrate them naturally -- lead with the \
explanation and follow with the code. Preserve any code blocks exactly as \
provided by the specialists.
"""


# ---------------------------------------------------------------------------
# Lifespan -- initialise LLM and HTTP client
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global llm, http_client

    llm = ChatOpenAI(
        base_url=VLLM_ENDPOINT,
        api_key="EMPTY",
        model=VLLM_MODEL_NAME,
        temperature=0,
    )
    logger.info(
        "LLM configured: endpoint=%s  model=%s", VLLM_ENDPOINT, VLLM_MODEL_NAME
    )

    http_client = httpx.AsyncClient(timeout=SPECIALIST_TIMEOUT_SECONDS)
    logger.info(
        "Specialist endpoints: research=%s  code=%s",
        SPECIALIST_RESEARCH_URL,
        SPECIALIST_CODE_URL,
    )

    yield

    if http_client is not None:
        await http_client.aclose()
        logger.info("HTTP client closed")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Supervisor Agent",
    description=(
        "Multi-agent supervisor that classifies tasks and routes them "
        "to specialist agents (research and code)"
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class InvokeRequest(BaseModel):
    """Request body for the /invoke endpoint."""

    message: str = Field(..., description="User message to send to the supervisor")
    thread_id: str = Field(
        default="default",
        description="Conversation thread identifier",
    )


class SpecialistResult(BaseModel):
    """Result from a single specialist agent."""

    specialist: str = Field(..., description="Name of the specialist (research or code)")
    response: str = Field(..., description="Specialist's response text")
    status: str = Field(..., description="ok or error")


class InvokeResponse(BaseModel):
    """Response body from the /invoke endpoint."""

    response: str = Field(..., description="Aggregated final response")
    category: str = Field(
        ..., description="Classified category: research, code, or both"
    )
    specialist_results: list[SpecialistResult] = Field(
        default_factory=list,
        description="Individual results from each specialist",
    )


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


async def classify_task(message: str) -> str:
    """Use the LLM to classify a user message into research, code, or both."""
    prompt = CLASSIFICATION_PROMPT.format(message=message)
    try:
        result = await llm.ainvoke(prompt)
        content = result.content.strip()
        # Parse the JSON response
        parsed = json.loads(content)
        category = parsed.get("category", "research")
        if category not in ("research", "code", "both"):
            logger.warning(
                "LLM returned unexpected category '%s', defaulting to 'research'",
                category,
            )
            return "research"
        return category
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("Classification failed (%s), defaulting to 'research'", exc)
        return "research"


async def call_specialist(
    specialist_name: str,
    specialist_url: str,
    message: str,
) -> SpecialistResult:
    """Call a specialist agent with retry logic.

    Retries up to MAX_RETRIES times with exponential backoff if the
    specialist is unavailable or returns an error.
    """
    if http_client is None:
        return SpecialistResult(
            specialist=specialist_name,
            response="HTTP client not initialised",
            status="error",
        )

    last_error = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await http_client.post(
                f"{specialist_url}/invoke",
                json={"message": message},
            )
            resp.raise_for_status()
            data = resp.json()
            return SpecialistResult(
                specialist=specialist_name,
                response=data.get("response", ""),
                status="ok",
            )
        except httpx.ConnectError as exc:
            last_error = f"Connection failed: {exc}"
            logger.warning(
                "Specialist '%s' unreachable (attempt %d/%d): %s",
                specialist_name,
                attempt,
                MAX_RETRIES,
                exc,
            )
        except httpx.HTTPStatusError as exc:
            last_error = f"HTTP {exc.response.status_code}: {exc.response.text}"
            logger.warning(
                "Specialist '%s' returned error (attempt %d/%d): %s",
                specialist_name,
                attempt,
                MAX_RETRIES,
                last_error,
            )
        except Exception as exc:
            last_error = str(exc)
            logger.warning(
                "Specialist '%s' call failed (attempt %d/%d): %s",
                specialist_name,
                attempt,
                MAX_RETRIES,
                exc,
            )

        if attempt < MAX_RETRIES:
            await asyncio.sleep(RETRY_DELAY_SECONDS * attempt)

    return SpecialistResult(
        specialist=specialist_name,
        response=f"Specialist unavailable after {MAX_RETRIES} attempts: {last_error}",
        status="error",
    )


async def aggregate_results(
    question: str,
    results: list[SpecialistResult],
) -> str:
    """Use the LLM to aggregate results from multiple specialists."""
    # Build the results section for the prompt
    sections = []
    for r in results:
        if r.status == "ok":
            sections.append(f"### {r.specialist.title()} Specialist Result:\n{r.response}")
        else:
            sections.append(
                f"### {r.specialist.title()} Specialist: UNAVAILABLE\n({r.response})"
            )

    results_section = "\n\n".join(sections)
    prompt = AGGREGATION_PROMPT.format(
        question=question, results_section=results_section
    )

    try:
        result = await llm.ainvoke(prompt)
        return result.content
    except Exception as exc:
        logger.exception("Aggregation failed")
        # Fall back to concatenating raw results
        fallback = []
        for r in results:
            if r.status == "ok":
                fallback.append(f"**{r.specialist.title()} Specialist:**\n{r.response}")
        return "\n\n---\n\n".join(fallback) if fallback else f"Aggregation error: {exc}"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/healthz")
async def healthz():
    """Liveness probe -- returns 200 if the process is alive."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    """Readiness probe -- returns 200 only when the supervisor is ready."""
    if llm is None:
        raise HTTPException(status_code=503, detail="Supervisor not ready")

    # Optionally check specialist availability
    checks = {}
    if http_client is not None:
        for name, url in [
            ("research", SPECIALIST_RESEARCH_URL),
            ("code", SPECIALIST_CODE_URL),
        ]:
            try:
                resp = await http_client.get(f"{url}/healthz", timeout=5.0)
                checks[name] = resp.status_code == 200
            except Exception:
                checks[name] = False

    return {"status": "ready", "specialists": checks}


@app.post("/invoke", response_model=InvokeResponse)
async def invoke(request: InvokeRequest):
    """Classify the task, route to specialists, and aggregate results."""
    if llm is None:
        raise HTTPException(status_code=503, detail="Supervisor not initialised")

    # Step 1: Classify the task
    category = await classify_task(request.message)
    logger.info("Task classified as: %s", category)

    # Step 2: Route to specialist(s)
    results: list[SpecialistResult] = []

    if category == "research":
        result = await call_specialist(
            "research", SPECIALIST_RESEARCH_URL, request.message
        )
        results.append(result)

    elif category == "code":
        result = await call_specialist(
            "code", SPECIALIST_CODE_URL, request.message
        )
        results.append(result)

    elif category == "both":
        # Call both specialists in parallel
        research_task = call_specialist(
            "research", SPECIALIST_RESEARCH_URL, request.message
        )
        code_task = call_specialist(
            "code", SPECIALIST_CODE_URL, request.message
        )
        research_result, code_result = await asyncio.gather(
            research_task, code_task
        )
        results.extend([research_result, code_result])

    # Step 3: Aggregate results
    if len(results) == 1 and results[0].status == "ok":
        # Single specialist -- no need to aggregate
        final_response = results[0].response
    else:
        final_response = await aggregate_results(request.message, results)

    return InvokeResponse(
        response=final_response,
        category=category,
        specialist_results=results,
    )
