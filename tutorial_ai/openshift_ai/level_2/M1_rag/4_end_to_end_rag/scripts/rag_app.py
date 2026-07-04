"""
RAG Application -- FastAPI service implementing the complete
Retrieval-Augmented Generation pipeline.

Connects to:
  - An embedding model on vLLM (/v1/embeddings)
  - pgvector for similarity search
  - An LLM on vLLM (/v1/chat/completions)

Requirements (pip install):
  fastapi==0.115.0
  uvicorn==0.30.0
  psycopg2-binary==2.9.9
  httpx==0.27.0
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Configuration -- all values come from environment variables
# ---------------------------------------------------------------------------

EMBEDDING_URL = os.getenv("EMBEDDING_URL", "http://embedding-model:8080")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

LLM_URL = os.getenv("LLM_URL", "http://gemma-4-e4b:8080")
LLM_MODEL = os.getenv("LLM_MODEL", "gemma-4-e4b")

DB_HOST = os.getenv("DB_HOST", "pgvector")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "vectordb")
DB_USER = os.getenv("DB_USER", "vectordb")
DB_PASSWORD = os.getenv("DB_PASSWORD", "vectordb")

TOP_K = int(os.getenv("TOP_K", "5"))
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.7"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rag_app")

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_TEMPLATE = """\
You are a helpful assistant. Answer the user's question based ONLY on \
the provided context. If the context does not contain enough information \
to answer the question, say "I don't have enough information to answer \
that question based on the available documents."

When you use information from the context, cite the source using \
[Source: filename] format.

Context:
{context}
"""

# ---------------------------------------------------------------------------
# HTTP client (shared across requests)
# ---------------------------------------------------------------------------

http_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the shared HTTP client lifecycle."""
    global http_client
    http_client = httpx.AsyncClient(timeout=120.0)
    logger.info("RAG application started")
    yield
    await http_client.aclose()
    logger.info("RAG application stopped")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="RAG Application",
    description="Retrieval-Augmented Generation service using vLLM + pgvector",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class AskRequest(BaseModel):
    question: str


class SourceInfo(BaseModel):
    source: str
    chunk_index: int
    similarity: float
    content_preview: str


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceInfo]
    chunks_retrieved: int


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def get_db_connection():
    """Create a connection to the pgvector database."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def search_similar_chunks(
    embedding: list[float],
    top_k: int = TOP_K,
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[dict[str, Any]]:
    """
    Query pgvector for the most similar document chunks.

    Uses cosine distance (<=> operator). Returns chunks that exceed
    the similarity threshold, ordered by similarity descending.
    """
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Convert the Python list to a pgvector-compatible string
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

            cur.execute(
                """
                SELECT
                    id,
                    content,
                    source,
                    chunk_index,
                    1 - (embedding <=> %s::vector) AS similarity
                FROM documents
                WHERE 1 - (embedding <=> %s::vector) > %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
                """,
                (embedding_str, embedding_str, threshold, embedding_str, top_k),
            )

            rows = cur.fetchall()
            return [dict(row) for row in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Embedding helper
# ---------------------------------------------------------------------------


async def get_query_embedding(question: str) -> list[float]:
    """
    Call the embedding model's /v1/embeddings endpoint to convert
    the question into a vector.
    """
    url = f"{EMBEDDING_URL}/v1/embeddings"
    payload = {
        "input": question,
        "model": EMBEDDING_MODEL,
    }

    response = await http_client.post(url, json=payload)

    if response.status_code != 200:
        logger.error(
            "Embedding request failed: %d %s", response.status_code, response.text
        )
        raise HTTPException(
            status_code=502,
            detail=f"Embedding model returned {response.status_code}",
        )

    data = response.json()
    return data["data"][0]["embedding"]


# ---------------------------------------------------------------------------
# LLM generation helper
# ---------------------------------------------------------------------------


async def generate_answer(
    question: str,
    context_chunks: list[dict[str, Any]],
) -> str:
    """
    Construct the augmented prompt with retrieved context and call
    the LLM's /v1/chat/completions endpoint.
    """
    # Build the context block from retrieved chunks
    if context_chunks:
        context_parts = []
        for chunk in context_chunks:
            source = chunk.get("source", "unknown")
            chunk_idx = chunk.get("chunk_index", 0)
            content = chunk.get("content", "")
            context_parts.append(
                f"---\n[Source: {source}, Chunk {chunk_idx}]\n{content}"
            )
        context_text = "\n".join(context_parts) + "\n---"
    else:
        context_text = "(No relevant context found in the documents.)"

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(context=context_text)

    url = f"{LLM_URL}/v1/chat/completions"
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        "temperature": 0.3,
        "max_tokens": 1024,
    }

    response = await http_client.post(url, json=payload)

    if response.status_code != 200:
        logger.error(
            "LLM request failed: %d %s", response.status_code, response.text
        )
        raise HTTPException(
            status_code=502,
            detail=f"LLM returned {response.status_code}",
        )

    data = response.json()
    return data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


@app.post("/api/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    """
    Full RAG pipeline:
    1. Embed the question
    2. Search for similar chunks in pgvector
    3. Construct augmented prompt with context
    4. Generate answer with the LLM
    5. Return answer + sources
    """
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    logger.info("Received question: %s", question[:100])

    # Step 1: Embed the question
    logger.info("Embedding the question...")
    query_embedding = await get_query_embedding(question)

    # Step 2: Retrieve similar chunks from pgvector
    logger.info("Searching for similar chunks (top_k=%d, threshold=%.2f)...", TOP_K, SIMILARITY_THRESHOLD)
    chunks = search_similar_chunks(query_embedding, top_k=TOP_K, threshold=SIMILARITY_THRESHOLD)
    logger.info("Retrieved %d chunks", len(chunks))

    # Step 3 + 4: Generate answer with augmented prompt
    logger.info("Generating answer with LLM...")
    answer = await generate_answer(question, chunks)

    # Step 5: Format response with sources
    sources = [
        SourceInfo(
            source=chunk.get("source", "unknown"),
            chunk_index=chunk.get("chunk_index", 0),
            similarity=round(float(chunk.get("similarity", 0)), 4),
            content_preview=chunk.get("content", "")[:200],
        )
        for chunk in chunks
    ]

    return AskResponse(
        answer=answer,
        sources=sources,
        chunks_retrieved=len(chunks),
    )


@app.get("/api/health")
async def health():
    """Health check endpoint for Kubernetes readiness/liveness probes."""
    return {"status": "healthy"}


@app.get("/", response_class=HTMLResponse)
async def chat_ui():
    """Simple HTML chat interface for testing the RAG application."""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RAG Application</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            color: #333;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 2rem;
        }
        h1 { margin-bottom: 0.5rem; color: #1a1a1a; }
        .subtitle { color: #666; margin-bottom: 2rem; font-size: 0.95rem; }
        .container {
            width: 100%;
            max-width: 800px;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            padding: 2rem;
        }
        .input-group {
            display: flex;
            gap: 0.75rem;
            margin-bottom: 1.5rem;
        }
        input[type="text"] {
            flex: 1;
            padding: 0.75rem 1rem;
            border: 1px solid #ddd;
            border-radius: 6px;
            font-size: 1rem;
            outline: none;
            transition: border-color 0.2s;
        }
        input[type="text"]:focus { border-color: #0066cc; }
        button {
            padding: 0.75rem 1.5rem;
            background: #0066cc;
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 1rem;
            cursor: pointer;
            transition: background 0.2s;
        }
        button:hover { background: #0052a3; }
        button:disabled { background: #999; cursor: not-allowed; }
        .answer-box {
            background: #f9f9f9;
            border: 1px solid #e0e0e0;
            border-radius: 6px;
            padding: 1.25rem;
            margin-bottom: 1rem;
            white-space: pre-wrap;
            line-height: 1.6;
            display: none;
        }
        .sources {
            display: none;
        }
        .sources h3 { font-size: 0.9rem; color: #666; margin-bottom: 0.5rem; }
        .source-item {
            background: #f0f4f8;
            border-left: 3px solid #0066cc;
            padding: 0.75rem 1rem;
            margin-bottom: 0.5rem;
            border-radius: 0 4px 4px 0;
            font-size: 0.9rem;
        }
        .source-meta { color: #666; font-size: 0.8rem; margin-bottom: 0.25rem; }
        .loading { color: #666; font-style: italic; }
        .error { color: #cc0000; }
    </style>
</head>
<body>
    <h1>RAG Application</h1>
    <p class="subtitle">Ask questions about your ingested documents</p>

    <div class="container">
        <div class="input-group">
            <input type="text" id="question" placeholder="Ask a question..."
                   onkeypress="if(event.key==='Enter') askQuestion()">
            <button id="askBtn" onclick="askQuestion()">Ask</button>
        </div>

        <div id="answer" class="answer-box"></div>

        <div id="sources" class="sources"></div>
    </div>

    <script>
        async function askQuestion() {
            const input = document.getElementById('question');
            const answerBox = document.getElementById('answer');
            const sourcesBox = document.getElementById('sources');
            const btn = document.getElementById('askBtn');
            const question = input.value.trim();

            if (!question) return;

            btn.disabled = true;
            answerBox.style.display = 'block';
            answerBox.className = 'answer-box loading';
            answerBox.textContent = 'Thinking...';
            sourcesBox.style.display = 'none';
            sourcesBox.innerHTML = '';

            try {
                const res = await fetch('/api/ask', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ question })
                });

                if (!res.ok) throw new Error(`HTTP ${res.status}`);

                const data = await res.json();

                answerBox.className = 'answer-box';
                answerBox.textContent = data.answer;

                if (data.sources && data.sources.length > 0) {
                    sourcesBox.style.display = 'block';
                    let html = '<h3>Sources (' + data.chunks_retrieved + ' chunks retrieved)</h3>';
                    data.sources.forEach(s => {
                        html += '<div class="source-item">';
                        html += '<div class="source-meta">' + s.source
                              + ' | Chunk ' + s.chunk_index
                              + ' | Similarity: ' + (s.similarity * 100).toFixed(1) + '%</div>';
                        html += '<div>' + s.content_preview + '</div>';
                        html += '</div>';
                    });
                    sourcesBox.innerHTML = html;
                }
            } catch (err) {
                answerBox.className = 'answer-box error';
                answerBox.textContent = 'Error: ' + err.message;
            } finally {
                btn.disabled = false;
            }
        }
    </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Entry point for local development
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
