"""
Document Ingestion Pipeline for RAG on OpenShift AI

This script implements the full ingestion pipeline for a RAG system:
  1. Parse documents (Docling or plain text fallback)
  2. Chunk text using one of three strategies (fixed, semantic, document-aware)
  3. Generate vector embeddings via the vLLM embedding model API
  4. Store chunks + embeddings + metadata in pgvector (PostgreSQL)

Requirements:
  pip install psycopg2-binary requests

Optional (for advanced document parsing):
  pip install docling

Usage:
  python ingestion_pipeline.py \
      --embedding-url http://embedding-model:8080/v1/embeddings \
      --db-host pgvector --db-port 5432 \
      --db-name vectordb --db-user vectordb --db-password vectordb \
      --chunk-strategy fixed --chunk-size 512 --chunk-overlap 50

  # Ingest files from a directory:
  python ingestion_pipeline.py --documents-dir /path/to/docs ...

  # Use built-in sample documents (no --documents-dir):
  python ingestion_pipeline.py ...
"""

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ParsedDocument:
    """Represents a document after parsing, with optional structure info."""

    source: str  # file path or document name
    text: str  # full extracted text
    # List of (heading_level, heading_text, section_text) tuples.
    # heading_level: 1 for '#', 2 for '##', etc.  0 means no heading.
    sections: list = field(default_factory=list)


@dataclass
class Chunk:
    """A single chunk of text with metadata."""

    content: str
    source_document: str
    chunk_index: int
    section_heading: Optional[str] = None
    chunk_strategy: str = "fixed"
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Sample documents (used when no --documents-dir is provided)
# ---------------------------------------------------------------------------

SAMPLE_DOCUMENTS = {
    "OpenShift AI Architecture (inline)": """\
# OpenShift AI Architecture

OpenShift AI is Red Hat's managed MLOps and GenAIOps platform built on top of \
OpenShift. It packages open-source ML tools behind a single operator and a \
unified dashboard.

## Core Components

The DataScienceCluster custom resource exposes 14 components, each independently \
toggleable via a managementState field. Key components include kserve for model \
serving, aipipelines for workflow orchestration, ray for distributed compute, \
and mlflowoperator for experiment tracking.

## Operator Model

Everything is managed through the Kubernetes Operator pattern. The RHODS operator \
watches the DataScienceCluster CR and reconciles the desired state. When you set a \
component to Managed, the operator installs it. When you set it to Removed, the \
operator uninstalls it.

## Three-Tier Architecture

Tier 1 consists of operator-managed components controlled via the DSC CR. \
Tier 2 consists of dashboard features built on Tier 1 components, such as \
AutoRAG and the GenAI Playground. Tier 3 consists of Python libraries used \
inside workbenches and pipeline steps, including the KFP SDK, Ray SDK, and \
MLflow SDK.

## Integration Points

OpenShift AI integrates with the broader OpenShift ecosystem: Routes for external \
access, RBAC for authorization, Prometheus for monitoring, and the OpenShift \
Web Console for cluster administration. It also integrates with external services \
like S3-compatible object storage for model artifacts and Git repositories for \
pipeline definitions.
""",
    "KServe Model Serving (inline)": """\
# KServe Model Serving

KServe is the model serving framework that powers inference on OpenShift AI. It \
introduces two primary CRDs: ServingRuntime and InferenceService.

## ServingRuntime

A ServingRuntime defines the inference server configuration: which container image \
to use, command-line arguments, exposed ports, and supported model formats. Think \
of it as a template for an inference server. OpenShift AI ships pre-built runtimes \
for vLLM, OpenVINO, and MLServer.

## InferenceService

An InferenceService deploys a specific model using a ServingRuntime. It specifies \
the model location, resource requests (CPU, memory, GPU), replica count, and \
scaling behavior. When created, KServe provisions the underlying Deployment, \
Service, and optionally a Route.

## Deployment Modes

KServe supports two deployment modes. Serverless mode uses Knative Serving with \
automatic scale-to-zero but is deprecated in OpenShift AI 3.x. RawDeployment \
mode uses standard Kubernetes Deployments and Services and is the recommended \
approach going forward.

## vLLM Integration

vLLM ships as the Red Hat AI Inference Server, a UBI-based container image \
pre-configured for LLM inference. It provides PagedAttention for efficient \
KV-cache management, continuous batching for high throughput, and an \
OpenAI-compatible API that works with existing client libraries.
""",
    "RAG Pipeline Components (inline)": """\
# RAG Pipeline Components

Retrieval-Augmented Generation (RAG) enhances LLM responses by retrieving \
relevant context from a knowledge base before generating an answer. The pipeline \
consists of several stages.

## Document Ingestion

The ingestion stage converts raw documents into vector embeddings stored in a \
vector database. This involves document parsing (extracting text from PDFs, \
DOCX, HTML), chunking (splitting text into smaller pieces), embedding generation \
(converting text to vectors), and storage in a vector database like pgvector.

## Retrieval

When a user asks a question, the retrieval stage converts the query into an \
embedding using the same model used during ingestion. It then performs a \
similarity search in the vector database to find the most relevant chunks. \
Advanced retrieval may include re-ranking, hybrid search combining dense and \
sparse retrieval, and metadata filtering.

## Augmented Generation

The retrieved chunks are inserted into the LLM prompt as context. The LLM \
generates a response grounded in the retrieved information. This reduces \
hallucination because the model has access to factual source material rather \
than relying solely on its training data.

## Evaluation

RAG systems require evaluation at multiple levels: retrieval quality (are the \
right chunks being retrieved?), generation quality (is the LLM answer faithful \
to the context?), and end-to-end quality (does the system answer user questions \
correctly?). Metrics include precision, recall, faithfulness, and relevance.

## OpenShift AI Integration

On OpenShift AI, the RAG pipeline leverages KServe for model serving (both \
embedding and generation models), pgvector for vector storage, Kubeflow \
Pipelines for orchestrating the ingestion workflow, and AutoRAG for automated \
evaluation and optimization of the pipeline configuration.
""",
}

# ---------------------------------------------------------------------------
# Stage 1: Document Parsing
# ---------------------------------------------------------------------------


def parse_document(source: str, text: Optional[str] = None) -> ParsedDocument:
    """
    Parse a document into structured text.

    If `text` is provided, parse it directly (used for inline sample documents).
    If `source` is a file path, attempt to parse it with Docling first, then
    fall back to plain text reading.

    Args:
        source: File path or document name.
        text:   Raw text content (if already available).

    Returns:
        ParsedDocument with extracted text and section structure.
    """
    if text is not None:
        # Parse inline text -- extract sections from Markdown headings
        sections = _extract_markdown_sections(text)
        return ParsedDocument(source=source, text=text, sections=sections)

    # File path provided -- try Docling first, then fall back to plain text
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {source}")

    suffix = path.suffix.lower()

    # Attempt Docling for supported formats
    if suffix in (".pdf", ".docx", ".html", ".htm", ".md", ".markdown"):
        try:
            return _parse_with_docling(path)
        except ImportError:
            logger.warning(
                "Docling not installed. Falling back to plain text for %s. "
                "Install with: pip install docling",
                source,
            )
        except Exception as e:
            logger.warning(
                "Docling failed for %s: %s. Falling back to plain text.",
                source,
                e,
            )

    # Fallback: read as plain text
    content = path.read_text(encoding="utf-8", errors="replace")
    sections = _extract_markdown_sections(content) if suffix in (".md", ".markdown") else []
    return ParsedDocument(source=str(path), text=content, sections=sections)


def _parse_with_docling(path: Path) -> ParsedDocument:
    """
    Parse a document using Docling.

    Docling returns a structured document object with headings, paragraphs,
    tables, and lists.  We convert it into our ParsedDocument format.
    """
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    result = converter.convert(str(path))
    doc = result.document

    # Extract full text
    full_text = doc.export_to_markdown()

    # Extract sections from the Docling document structure
    sections = []
    for item in doc.iterate_items():
        # Docling items have a label attribute indicating their type
        label = getattr(item, "label", None)
        if label and "heading" in str(label).lower():
            level = int(label[-1]) if label[-1].isdigit() else 1
            heading_text = item.text if hasattr(item, "text") else str(item)
            sections.append((level, heading_text, ""))
        elif hasattr(item, "text") and sections:
            # Append text to the most recent section
            level, heading, existing = sections[-1]
            sections[-1] = (level, heading, existing + "\n" + item.text)

    return ParsedDocument(source=str(path), text=full_text, sections=sections)


def _extract_markdown_sections(text: str) -> list:
    """
    Extract sections from Markdown-formatted text by splitting on headings.

    Returns a list of (heading_level, heading_text, section_text) tuples.
    """
    lines = text.split("\n")
    sections = []
    current_level = 0
    current_heading = ""
    current_text_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            # Save the previous section if any
            if current_heading or current_text_lines:
                sections.append((
                    current_level,
                    current_heading,
                    "\n".join(current_text_lines).strip(),
                ))

            # Parse the new heading
            hashes = len(stripped) - len(stripped.lstrip("#"))
            current_level = hashes
            current_heading = stripped.lstrip("#").strip()
            current_text_lines = []
        else:
            current_text_lines.append(line)

    # Don't forget the last section
    if current_heading or current_text_lines:
        sections.append((
            current_level,
            current_heading,
            "\n".join(current_text_lines).strip(),
        ))

    return sections


# ---------------------------------------------------------------------------
# Stage 2: Chunking
# ---------------------------------------------------------------------------


def chunk_text(
    doc: ParsedDocument,
    strategy: str = "fixed",
    chunk_size: int = 512,
    chunk_overlap: int = 50,
) -> list[Chunk]:
    """
    Split a parsed document into chunks using the specified strategy.

    Args:
        doc:           The parsed document.
        strategy:      One of 'fixed', 'semantic', or 'document-aware'.
        chunk_size:    Target chunk size in characters (used by fixed strategy).
        chunk_overlap: Overlap in characters between consecutive chunks (fixed).

    Returns:
        List of Chunk objects with text and metadata.
    """
    if strategy == "fixed":
        return _chunk_fixed(doc, chunk_size, chunk_overlap)
    elif strategy == "semantic":
        return _chunk_semantic(doc, chunk_size)
    elif strategy == "document-aware":
        return _chunk_document_aware(doc, chunk_size)
    else:
        raise ValueError(f"Unknown chunk strategy: {strategy}. Use: fixed, semantic, document-aware")


def _chunk_fixed(doc: ParsedDocument, chunk_size: int, overlap: int) -> list[Chunk]:
    """
    Fixed-size chunking: split text into chunks of `chunk_size` characters
    with `overlap` characters of overlap between consecutive chunks.

    This is the simplest strategy.  It treats the document as a flat string
    and slices it at regular intervals.  It may split mid-sentence or
    mid-paragraph, but produces consistent chunk sizes.
    """
    text = doc.text.strip()
    chunks = []
    start = 0
    idx = 0

    while start < len(text):
        end = start + chunk_size
        chunk_text_str = text[start:end]

        # If we're not at the end, try to break at a whitespace boundary
        # to avoid splitting a word in half.
        if end < len(text):
            last_space = chunk_text_str.rfind(" ")
            if last_space > chunk_size // 2:
                end = start + last_space
                chunk_text_str = text[start:end]

        chunks.append(Chunk(
            content=chunk_text_str.strip(),
            source_document=doc.source,
            chunk_index=idx,
            section_heading=None,
            chunk_strategy="fixed",
            metadata={"chunk_size": chunk_size, "overlap": overlap},
        ))

        idx += 1
        step = max(1, end - start - overlap)
        start += step

    return chunks


def _chunk_semantic(doc: ParsedDocument, max_chunk_size: int) -> list[Chunk]:
    """
    Semantic chunking: split at paragraph boundaries.

    Paragraphs are identified by double newlines.  Short consecutive
    paragraphs are merged until the combined length exceeds max_chunk_size.
    This respects natural language boundaries better than fixed-size chunking.

    A full semantic chunking implementation would also use embedding similarity
    to decide merge boundaries, but that requires calling the embedding model
    during chunking (expensive).  This simplified version uses paragraph
    boundaries only, which is a good practical compromise.
    """
    text = doc.text.strip()

    # Split into paragraphs (double newline is the standard separator)
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks = []
    current_paragraphs = []
    current_length = 0
    idx = 0

    for para in paragraphs:
        para_len = len(para)

        # If adding this paragraph would exceed the limit, finalize the
        # current chunk (unless it's empty).
        if current_length + para_len > max_chunk_size and current_paragraphs:
            chunk_content = "\n\n".join(current_paragraphs)
            # Try to identify the section heading for this chunk
            heading = _find_heading_for_text(chunk_content, doc.sections)
            chunks.append(Chunk(
                content=chunk_content,
                source_document=doc.source,
                chunk_index=idx,
                section_heading=heading,
                chunk_strategy="semantic",
            ))
            idx += 1
            current_paragraphs = []
            current_length = 0

        current_paragraphs.append(para)
        current_length += para_len

    # Finalize the last chunk
    if current_paragraphs:
        chunk_content = "\n\n".join(current_paragraphs)
        heading = _find_heading_for_text(chunk_content, doc.sections)
        chunks.append(Chunk(
            content=chunk_content,
            source_document=doc.source,
            chunk_index=idx,
            section_heading=heading,
            chunk_strategy="semantic",
        ))

    return chunks


def _chunk_document_aware(doc: ParsedDocument, max_chunk_size: int) -> list[Chunk]:
    """
    Document-aware chunking: use document structure (headings, sections) to
    determine chunk boundaries.

    Each section (defined by a heading) becomes a chunk.  If a section exceeds
    max_chunk_size, it is split at paragraph boundaries within the section.
    This preserves semantic coherence because chunks align with the author's
    intended structure.

    Requires the document to have been parsed with structure preservation
    (e.g., Docling or Markdown heading extraction).
    """
    if not doc.sections:
        # No structure available -- fall back to semantic chunking
        logger.warning(
            "No document structure found for '%s'. "
            "Falling back to semantic chunking.",
            doc.source,
        )
        return _chunk_semantic(doc, max_chunk_size)

    chunks = []
    idx = 0

    for level, heading, section_text in doc.sections:
        if not section_text.strip():
            continue

        # If the section fits in one chunk, keep it whole
        if len(section_text) <= max_chunk_size:
            chunks.append(Chunk(
                content=section_text.strip(),
                source_document=doc.source,
                chunk_index=idx,
                section_heading=heading,
                chunk_strategy="document-aware",
                metadata={"heading_level": level},
            ))
            idx += 1
        else:
            # Section is too long -- split at paragraph boundaries
            paragraphs = [p.strip() for p in section_text.split("\n\n") if p.strip()]
            current_parts = []
            current_length = 0

            for para in paragraphs:
                if current_length + len(para) > max_chunk_size and current_parts:
                    chunks.append(Chunk(
                        content="\n\n".join(current_parts),
                        source_document=doc.source,
                        chunk_index=idx,
                        section_heading=heading,
                        chunk_strategy="document-aware",
                        metadata={"heading_level": level, "split": True},
                    ))
                    idx += 1
                    current_parts = []
                    current_length = 0

                current_parts.append(para)
                current_length += len(para)

            if current_parts:
                chunks.append(Chunk(
                    content="\n\n".join(current_parts),
                    source_document=doc.source,
                    chunk_index=idx,
                    section_heading=heading,
                    chunk_strategy="document-aware",
                    metadata={"heading_level": level},
                ))
                idx += 1

    return chunks


def _find_heading_for_text(text: str, sections: list) -> Optional[str]:
    """
    Given a chunk of text and the document's section list, find the heading
    that this text most likely belongs to.

    Uses a simple heuristic: check if the first 80 characters of the chunk
    appear in any section's text.
    """
    if not sections:
        return None
    prefix = text[:80]
    for _level, heading, section_text in sections:
        if prefix in section_text:
            return heading
    return None


# ---------------------------------------------------------------------------
# Stage 3: Embedding Generation
# ---------------------------------------------------------------------------


def generate_embeddings(
    chunks: list[Chunk],
    embedding_url: str,
    model_name: str = "nomic-embed-text-v1.5",
    batch_size: int = 32,
) -> list[list[float]]:
    """
    Generate vector embeddings for a list of chunks by calling the vLLM
    embedding model API.

    The API follows the OpenAI /v1/embeddings spec.  Chunks are sent in
    batches to reduce HTTP overhead.

    Args:
        chunks:        List of Chunk objects to embed.
        embedding_url: URL of the embedding endpoint
                       (e.g., http://embedding-model:8080/v1/embeddings).
        model_name:    Model identifier expected by the server.
        batch_size:    Number of texts to embed per API call.

    Returns:
        List of embedding vectors (each a list of floats), in the same
        order as the input chunks.
    """
    all_embeddings = []

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c.content for c in batch]

        payload = {
            "model": model_name,
            "input": texts,
        }

        try:
            resp = requests.post(embedding_url, json=payload, timeout=120)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error("Embedding API request failed: %s", e)
            raise

        data = resp.json()

        # The API returns embeddings in the same order as the input texts,
        # but we sort by index to be safe.
        sorted_items = sorted(data["data"], key=lambda x: x["index"])
        batch_embeddings = [item["embedding"] for item in sorted_items]
        all_embeddings.extend(batch_embeddings)

    return all_embeddings


# ---------------------------------------------------------------------------
# Stage 4: Storage in pgvector
# ---------------------------------------------------------------------------


def store_in_pgvector(
    chunks: list[Chunk],
    embeddings: list[list[float]],
    db_host: str,
    db_port: int,
    db_name: str,
    db_user: str,
    db_password: str,
    table_name: str = "document_chunks",
) -> int:
    """
    Store chunks and their embeddings in a pgvector-enabled PostgreSQL database.

    Creates the table and indexes if they do not exist.  Inserts each chunk
    as a row with its embedding, source metadata, and timestamps.

    Args:
        chunks:      List of Chunk objects.
        embeddings:  Corresponding list of embedding vectors.
        db_host:     PostgreSQL host.
        db_port:     PostgreSQL port.
        db_name:     Database name.
        db_user:     Database user.
        db_password: Database password.
        table_name:  Target table name.

    Returns:
        Number of rows inserted.
    """
    import psycopg2

    if len(chunks) != len(embeddings):
        raise ValueError(
            f"Mismatch: {len(chunks)} chunks but {len(embeddings)} embeddings"
        )

    # Determine embedding dimension from the first vector
    embedding_dim = len(embeddings[0]) if embeddings else 768

    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_password,
    )
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            # Ensure the pgvector extension is available
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

            # Create the table if it does not exist
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id SERIAL PRIMARY KEY,
                    content TEXT NOT NULL,
                    embedding vector({embedding_dim}),
                    source_document TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    section_heading TEXT,
                    chunk_strategy TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata_json JSONB DEFAULT '{{}}'::jsonb
                );
            """)

            # Create indexes for efficient search
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{table_name}_embedding
                    ON {table_name} USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 100);
            """)
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{table_name}_source
                    ON {table_name} (source_document);
            """)

            # Insert chunks
            insert_sql = f"""
                INSERT INTO {table_name}
                    (content, embedding, source_document, chunk_index,
                     section_heading, chunk_strategy, metadata_json)
                VALUES (%s, %s::vector, %s, %s, %s, %s, %s)
            """

            rows_inserted = 0
            for chunk, embedding in zip(chunks, embeddings):
                # Convert embedding list to the pgvector string format:
                # [0.1, 0.2, 0.3, ...]
                embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

                cur.execute(insert_sql, (
                    chunk.content,
                    embedding_str,
                    chunk.source_document,
                    chunk.chunk_index,
                    chunk.section_heading,
                    chunk.chunk_strategy,
                    json.dumps(chunk.metadata),
                ))
                rows_inserted += 1

            conn.commit()
            return rows_inserted

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------


def ingest_document(
    source: str,
    text: Optional[str],
    embedding_url: str,
    db_config: dict,
    chunk_strategy: str = "fixed",
    chunk_size: int = 512,
    chunk_overlap: int = 50,
) -> int:
    """
    Run the full ingestion pipeline for a single document.

    Args:
        source:         Document name or file path.
        text:           Raw text (for inline documents). None to read from file.
        embedding_url:  URL of the embedding model API.
        db_config:      Dict with keys: host, port, name, user, password.
        chunk_strategy: Chunking strategy (fixed, semantic, document-aware).
        chunk_size:     Target chunk size in characters.
        chunk_overlap:  Overlap between chunks (fixed strategy only).

    Returns:
        Number of chunks stored.
    """
    # Stage 1: Parse
    logger.info("Processing document: %s", source)
    doc = parse_document(source, text)
    logger.info("  Parsed: %d characters", len(doc.text))

    # Stage 2: Chunk
    chunks = chunk_text(doc, strategy=chunk_strategy, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    logger.info("  Chunked: %d chunks (%s strategy)", len(chunks), chunk_strategy)

    if not chunks:
        logger.warning("  No chunks produced. Skipping.")
        return 0

    # Stage 3: Embed
    embeddings = generate_embeddings(chunks, embedding_url)
    dim = len(embeddings[0]) if embeddings else 0
    logger.info("  Generated %d embeddings (%d dimensions)", len(embeddings), dim)

    # Stage 4: Store
    rows = store_in_pgvector(
        chunks,
        embeddings,
        db_host=db_config["host"],
        db_port=db_config["port"],
        db_name=db_config["name"],
        db_user=db_config["user"],
        db_password=db_config["password"],
    )
    logger.info("  Stored %d chunks in pgvector", rows)

    return rows


def ingest_directory(
    directory: str,
    embedding_url: str,
    db_config: dict,
    chunk_strategy: str = "fixed",
    chunk_size: int = 512,
    chunk_overlap: int = 50,
) -> int:
    """
    Ingest all supported documents from a directory.

    Supported extensions: .txt, .md, .markdown, .html, .htm, .pdf, .docx

    Args:
        directory:      Path to the directory containing documents.
        embedding_url:  URL of the embedding model API.
        db_config:      Database connection config.
        chunk_strategy: Chunking strategy.
        chunk_size:     Target chunk size.
        chunk_overlap:  Chunk overlap.

    Returns:
        Total number of chunks stored.
    """
    supported_extensions = {".txt", ".md", ".markdown", ".html", ".htm", ".pdf", ".docx"}
    dir_path = Path(directory)

    if not dir_path.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")

    files = sorted(
        f for f in dir_path.iterdir()
        if f.is_file() and f.suffix.lower() in supported_extensions
    )

    if not files:
        logger.warning("No supported documents found in %s", directory)
        return 0

    logger.info("Found %d documents in %s", len(files), directory)

    total_chunks = 0
    for file_path in files:
        try:
            count = ingest_document(
                source=str(file_path),
                text=None,
                embedding_url=embedding_url,
                db_config=db_config,
                chunk_strategy=chunk_strategy,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            total_chunks += count
        except Exception as e:
            logger.error("Failed to ingest %s: %s", file_path, e)

    return total_chunks


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main():
    """
    Main entry point.  Parses CLI arguments and runs the ingestion pipeline.

    If --documents-dir is provided, ingests all supported files from that
    directory.  Otherwise, uses the built-in sample documents.
    """
    parser = argparse.ArgumentParser(
        description="Document ingestion pipeline for RAG on OpenShift AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Ingest sample documents with fixed chunking:
  python ingestion_pipeline.py \\
      --embedding-url http://embedding-model:8080/v1/embeddings \\
      --chunk-strategy fixed

  # Ingest a directory of documents with semantic chunking:
  python ingestion_pipeline.py \\
      --documents-dir /data/docs \\
      --chunk-strategy semantic \\
      --chunk-size 1024

  # Use environment variables for database config:
  export DB_HOST=pgvector DB_PORT=5432 DB_NAME=vectordb
  export DB_USER=vectordb DB_PASSWORD=vectordb
  python ingestion_pipeline.py
        """,
    )

    # Embedding model configuration
    parser.add_argument(
        "--embedding-url",
        default=os.environ.get("EMBEDDING_URL", "http://embedding-model:8080/v1/embeddings"),
        help="URL of the embedding model API (default: http://embedding-model:8080/v1/embeddings)",
    )
    parser.add_argument(
        "--model-name",
        default=os.environ.get("MODEL_NAME", "nomic-embed-text-v1.5"),
        help="Model name for the embedding API (default: nomic-embed-text-v1.5)",
    )

    # Database configuration
    parser.add_argument(
        "--db-host",
        default=os.environ.get("DB_HOST", "pgvector"),
        help="PostgreSQL host (default: pgvector)",
    )
    parser.add_argument(
        "--db-port",
        type=int,
        default=int(os.environ.get("DB_PORT", "5432")),
        help="PostgreSQL port (default: 5432)",
    )
    parser.add_argument(
        "--db-name",
        default=os.environ.get("DB_NAME", "vectordb"),
        help="PostgreSQL database name (default: vectordb)",
    )
    parser.add_argument(
        "--db-user",
        default=os.environ.get("DB_USER", "vectordb"),
        help="PostgreSQL user (default: vectordb)",
    )
    parser.add_argument(
        "--db-password",
        default=os.environ.get("DB_PASSWORD", "vectordb"),
        help="PostgreSQL password (default: vectordb)",
    )

    # Chunking configuration
    parser.add_argument(
        "--chunk-strategy",
        choices=["fixed", "semantic", "document-aware"],
        default="fixed",
        help="Chunking strategy: fixed, semantic, or document-aware (default: fixed)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=512,
        help="Target chunk size in characters (default: 512)",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=50,
        help="Overlap between chunks in characters, fixed strategy only (default: 50)",
    )

    # Document source
    parser.add_argument(
        "--documents-dir",
        default=None,
        help="Path to a directory of documents to ingest. If not provided, uses built-in sample documents.",
    )

    args = parser.parse_args()

    db_config = {
        "host": args.db_host,
        "port": args.db_port,
        "name": args.db_name,
        "user": args.db_user,
        "password": args.db_password,
    }

    logger.info("Starting document ingestion pipeline")
    logger.info(
        "Chunk strategy: %s, chunk_size=%d, overlap=%d",
        args.chunk_strategy,
        args.chunk_size,
        args.chunk_overlap,
    )
    logger.info("Embedding URL: %s", args.embedding_url)
    logger.info("Database: %s@%s:%d/%s", args.db_user, args.db_host, args.db_port, args.db_name)

    start_time = time.time()
    total_chunks = 0

    if args.documents_dir:
        # Ingest from directory
        total_chunks = ingest_directory(
            directory=args.documents_dir,
            embedding_url=args.embedding_url,
            db_config=db_config,
            chunk_strategy=args.chunk_strategy,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
        )
    else:
        # Use built-in sample documents
        logger.info("No --documents-dir provided. Using %d built-in sample documents.", len(SAMPLE_DOCUMENTS))
        for doc_name, doc_text in SAMPLE_DOCUMENTS.items():
            try:
                count = ingest_document(
                    source=doc_name,
                    text=doc_text,
                    embedding_url=args.embedding_url,
                    db_config=db_config,
                    chunk_strategy=args.chunk_strategy,
                    chunk_size=args.chunk_size,
                    chunk_overlap=args.chunk_overlap,
                )
                total_chunks += count
            except Exception as e:
                logger.error("Failed to ingest '%s': %s", doc_name, e)

    elapsed = time.time() - start_time
    logger.info("Ingestion complete. Total chunks: %d (%.1f seconds)", total_chunks, elapsed)


if __name__ == "__main__":
    main()
