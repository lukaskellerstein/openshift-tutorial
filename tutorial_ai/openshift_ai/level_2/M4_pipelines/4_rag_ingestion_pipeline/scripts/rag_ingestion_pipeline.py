"""
L2-M4.4 -- RAG Ingestion Pipeline

KFP v2 pipeline that automates the RAG document ingestion workflow:
  1. fetch_documents      -- Pull documents from an S3 bucket (simulated with sample data)
  2. parse_documents      -- Parse raw documents into structured text using Docling
  3. chunk_documents      -- Split parsed text into chunks with configurable strategy
  4. generate_embeddings  -- Generate vector embeddings for each chunk
  5. store_in_vector_db   -- Write embeddings and metadata to a vector database

Pipeline parameters:
  - source_bucket:     S3 bucket name (default: "documents")
  - source_prefix:     S3 key prefix (default: "raw/")
  - chunk_size:        Maximum chunk size in characters (default: 512)
  - chunk_overlap:     Overlap between consecutive chunks (default: 50)
  - chunking_strategy: One of "fixed", "semantic", "document-aware" (default: "fixed")
  - embedding_model:   Model name for the embedding endpoint (default: "nomic-embed-text-v1.5")
  - embedding_endpoint: URL of the embedding API (default: "http://embedding-model:8080/v1/embeddings")
  - vector_db_host:    Hostname of the vector database (default: "milvus-service")
  - vector_db_port:    Port of the vector database (default: 19530)
  - collection_name:   Target collection in the vector database (default: "documents")

Usage:
  # Compile to YAML
  python rag_ingestion_pipeline.py --compile-only

  # Compile and submit to the pipeline server
  python rag_ingestion_pipeline.py
"""

from kfp import dsl, compiler
from kfp.dsl import Dataset, Input, Metrics, Output


# ---------------------------------------------------------------------------
# Component 1: Fetch Documents
# ---------------------------------------------------------------------------
@dsl.component(
    base_image="python:3.11",
    packages_to_install=["boto3==1.34.0"],
)
def fetch_documents(
    source_bucket: str,
    source_prefix: str,
    documents_out: Output[Dataset],
):
    """Fetch documents from an S3 bucket.

    In a production environment, this component pulls documents from an S3
    bucket (e.g., OpenShift Data Foundation, MinIO, or AWS S3). For this
    tutorial, it generates realistic sample documents so the pipeline runs
    without external dependencies.

    To connect to a real S3 bucket, uncomment the boto3 section below and
    provide credentials via environment variables or a Kubernetes secret.
    """
    import json

    # -----------------------------------------------------------------
    # Option A: Fetch from a real S3 bucket (uncomment for production)
    # -----------------------------------------------------------------
    # import boto3
    # import os
    #
    # s3 = boto3.client(
    #     "s3",
    #     endpoint_url=os.environ.get("S3_ENDPOINT", "http://minio:9000"),
    #     aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
    #     aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    # )
    #
    # documents = []
    # paginator = s3.get_paginator("list_objects_v2")
    # for page in paginator.paginate(Bucket=source_bucket, Prefix=source_prefix):
    #     for obj in page.get("Contents", []):
    #         key = obj["Key"]
    #         if key.endswith((".pdf", ".docx", ".html", ".md", ".txt")):
    #             body = s3.get_object(Bucket=source_bucket, Key=key)["Body"].read()
    #             documents.append({
    #                 "name": key.split("/")[-1],
    #                 "source": f"s3://{source_bucket}/{key}",
    #                 "content_bytes": body.decode("utf-8", errors="replace"),
    #                 "format": key.rsplit(".", 1)[-1],
    #             })
    # print(f"Fetched {len(documents)} documents from s3://{source_bucket}/{source_prefix}")

    # -----------------------------------------------------------------
    # Option B: Generate sample documents (tutorial mode)
    # -----------------------------------------------------------------
    documents = [
        {
            "name": "openshift_ai_architecture.md",
            "source": f"s3://{source_bucket}/{source_prefix}openshift_ai_architecture.md",
            "format": "md",
            "content": (
                "# OpenShift AI Architecture\n\n"
                "## Overview\n\n"
                "OpenShift AI is Red Hat's AI/ML platform built on top of OpenShift "
                "Container Platform. It provides a managed environment for data scientists "
                "and ML engineers to develop, train, and deploy machine learning models.\n\n"
                "The platform integrates open-source projects like Jupyter, KServe, "
                "Kubeflow Pipelines, Ray, and ModelMesh into a cohesive experience "
                "managed through the OpenShift AI operator.\n\n"
                "## Components\n\n"
                "### Workbenches\n\n"
                "Workbenches are containerized Jupyter notebook environments that run as "
                "pods in the user's data science project. Each workbench uses a notebook "
                "image that includes pre-installed ML libraries (TensorFlow, PyTorch, "
                "scikit-learn) and tools.\n\n"
                "### Model Serving\n\n"
                "OpenShift AI supports two model serving platforms: KServe for single-model "
                "serving with autoscaling and canary deployments, and ModelMesh for "
                "multi-model serving with shared GPU resources. Both expose REST and gRPC "
                "inference endpoints.\n\n"
                "### Data Science Pipelines\n\n"
                "Data Science Pipelines is the managed Kubeflow Pipelines v2 deployment. "
                "It runs ML workflows as directed acyclic graphs (DAGs) with automatic "
                "artifact tracking, experiment management, and scheduling.\n\n"
            ),
        },
        {
            "name": "kserve_deployment_guide.md",
            "source": f"s3://{source_bucket}/{source_prefix}kserve_deployment_guide.md",
            "format": "md",
            "content": (
                "# KServe Deployment Guide\n\n"
                "## Prerequisites\n\n"
                "Before deploying a model with KServe on OpenShift AI, ensure you have "
                "a trained model stored in an S3-compatible object store, a data science "
                "project with the model serving platform enabled, and a ServingRuntime "
                "that matches your model format.\n\n"
                "## Creating an InferenceService\n\n"
                "The InferenceService custom resource defines what model to serve, which "
                "runtime to use, and how to scale. Here is a minimal example that deploys "
                "a model stored in S3:\n\n"
                "```yaml\n"
                "apiVersion: serving.kserve.io/v1beta1\n"
                "kind: InferenceService\n"
                "metadata:\n"
                "  name: my-model\n"
                "spec:\n"
                "  predictor:\n"
                "    model:\n"
                "      modelFormat:\n"
                "        name: onnx\n"
                "      storageUri: s3://models/my-model/\n"
                "```\n\n"
                "## Scaling Configuration\n\n"
                "KServe supports autoscaling based on concurrent requests. The default "
                "scale-to-zero behavior means pods are terminated after a period of "
                "inactivity and cold-started when new requests arrive. You can configure "
                "minimum replicas to keep at least one pod warm:\n\n"
                "Set `minReplicas: 1` in the predictor spec to disable scale-to-zero "
                "for latency-sensitive workloads.\n\n"
                "## Canary Deployments\n\n"
                "KServe supports traffic splitting between model revisions. Deploy a new "
                "model version with `canaryTrafficPercent: 10` to send 10 percent of "
                "traffic to the new revision while the rest goes to the stable version.\n\n"
            ),
        },
        {
            "name": "pipeline_best_practices.md",
            "source": f"s3://{source_bucket}/{source_prefix}pipeline_best_practices.md",
            "format": "md",
            "content": (
                "# Pipeline Best Practices\n\n"
                "## Component Design\n\n"
                "Each pipeline component should do one thing well. Keep components small "
                "and focused so they can be reused across pipelines. Avoid putting your "
                "entire workflow in a single component -- this defeats the purpose of "
                "pipeline orchestration.\n\n"
                "Use typed inputs and outputs (Dataset, Model, Metrics) instead of "
                "passing file paths as strings. KFP tracks typed artifacts in the "
                "metadata store, giving you lineage and provenance for free.\n\n"
                "## Error Handling\n\n"
                "Components run as containers in isolated pods. If a component fails, "
                "KFP marks the step as failed and stops downstream steps. Design "
                "components to fail fast with clear error messages rather than silently "
                "producing bad data.\n\n"
                "Implement retry logic for transient failures (network timeouts, API "
                "rate limits) using the `set_retry` method on task objects.\n\n"
                "## Resource Management\n\n"
                "Set explicit CPU and memory requests on components that process large "
                "datasets. Without resource requests, the Kubernetes scheduler may place "
                "your component on a node without enough memory, causing OOM kills.\n\n"
                "For GPU-intensive components (training, embedding generation), use "
                "`set_accelerator_type` and `set_accelerator_limit` to request GPUs. "
                "On OpenShift AI, GPU allocation is managed by Kueue when enabled.\n\n"
                "## Parameterization\n\n"
                "Make pipelines configurable through parameters instead of hardcoding "
                "values. This lets you reuse the same pipeline for different datasets, "
                "models, and environments without modifying code.\n\n"
            ),
        },
    ]

    print(f"Fetched {len(documents)} documents from s3://{source_bucket}/{source_prefix}")
    for doc in documents:
        print(f"  - {doc['name']} ({doc['format']}, {len(doc['content'])} chars)")

    # Write documents as JSON Lines (one JSON object per line)
    with open(documents_out.path, "w") as f:
        for doc in documents:
            f.write(json.dumps(doc) + "\n")

    documents_out.metadata["num_documents"] = str(len(documents))
    documents_out.metadata["source_bucket"] = source_bucket
    documents_out.metadata["source_prefix"] = source_prefix


# ---------------------------------------------------------------------------
# Component 2: Parse Documents
# ---------------------------------------------------------------------------
@dsl.component(
    base_image="python:3.11",
    packages_to_install=["docling==2.31.0"],
)
def parse_documents(
    raw_documents: Input[Dataset],
    parsed_out: Output[Dataset],
):
    """Parse raw documents into structured text using Docling.

    Docling converts diverse document formats (PDF, DOCX, HTML, Markdown)
    into a unified representation that preserves document structure --
    headings, paragraphs, tables, lists. This structure is essential for
    document-aware chunking.

    For Markdown and plain text files, Docling is lightweight. For PDF and
    DOCX files, Docling uses layout analysis and OCR, which requires more
    compute (and optionally a GPU for faster processing).

    If Docling is not available (e.g., in a minimal container), the component
    falls back to plain text extraction.
    """
    import json
    import traceback

    documents = []
    with open(raw_documents.path, "r") as f:
        for line in f:
            documents.append(json.loads(line.strip()))

    print(f"Parsing {len(documents)} documents")

    parsed_documents = []

    # Try Docling first, fall back to plain text
    try:
        from docling.document_converter import DocumentConverter
        from docling.datamodel.base_models import InputFormat
        import tempfile
        import os

        converter = DocumentConverter()
        use_docling = True
        print("Using Docling for document parsing")
    except ImportError:
        use_docling = False
        print("Docling not available -- falling back to plain text parsing")

    for doc in documents:
        doc_name = doc["name"]
        content = doc.get("content", "")
        doc_format = doc.get("format", "txt")

        if use_docling and doc_format in ("md", "pdf", "docx", "html"):
            try:
                # Write content to a temp file for Docling to process
                suffix_map = {"md": ".md", "pdf": ".pdf", "docx": ".docx", "html": ".html"}
                suffix = suffix_map.get(doc_format, ".txt")

                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=suffix, delete=False
                ) as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name

                result = converter.convert(tmp_path)
                parsed_text = result.document.export_to_markdown()
                os.unlink(tmp_path)

                print(f"  Parsed with Docling: {doc_name} -> {len(parsed_text)} chars")
            except Exception as e:
                print(f"  Docling failed for {doc_name}: {e}")
                traceback.print_exc()
                parsed_text = content
                print(f"  Falling back to plain text: {doc_name} -> {len(parsed_text)} chars")
        else:
            # Plain text fallback -- just use content as-is
            parsed_text = content
            print(f"  Plain text parse: {doc_name} -> {len(parsed_text)} chars")

        parsed_documents.append({
            "name": doc_name,
            "source": doc.get("source", doc_name),
            "format": doc_format,
            "parsed_text": parsed_text,
            "char_count": len(parsed_text),
        })

    # Write parsed documents as JSON Lines
    with open(parsed_out.path, "w") as f:
        for doc in parsed_documents:
            f.write(json.dumps(doc) + "\n")

    total_chars = sum(d["char_count"] for d in parsed_documents)
    parsed_out.metadata["num_documents"] = str(len(parsed_documents))
    parsed_out.metadata["total_characters"] = str(total_chars)
    print(f"Parsing complete: {len(parsed_documents)} documents, {total_chars} total characters")


# ---------------------------------------------------------------------------
# Component 3: Chunk Documents
# ---------------------------------------------------------------------------
@dsl.component(
    base_image="python:3.11",
    packages_to_install=["numpy==1.26.4"],
)
def chunk_documents(
    parsed_documents: Input[Dataset],
    chunk_size: int,
    chunk_overlap: int,
    chunking_strategy: str,
    chunks_out: Output[Dataset],
):
    """Split parsed documents into chunks using the specified strategy.

    Supported strategies:
      - "fixed":          Split by character count with overlap.
      - "semantic":       Split at paragraph boundaries, merge short paragraphs.
      - "document-aware": Split at heading boundaries, respecting document structure.

    Each chunk includes metadata: source document, chunk index, section heading
    (if available), and the strategy used.
    """
    import json
    import re

    # Load parsed documents
    documents = []
    with open(parsed_documents.path, "r") as f:
        for line in f:
            documents.append(json.loads(line.strip()))

    print(f"Chunking {len(documents)} documents with strategy='{chunking_strategy}', "
          f"chunk_size={chunk_size}, overlap={chunk_overlap}")

    def fixed_size_chunk(text, size, overlap):
        """Split text into fixed-size chunks with overlap."""
        chunks = []
        start = 0
        while start < len(text):
            end = start + size
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append({"text": chunk_text, "section_heading": None})
            start += size - overlap
        return chunks

    def semantic_chunk(text, max_size):
        """Split at paragraph boundaries, merging short paragraphs."""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            # Skip heading-only paragraphs (merge into next)
            if para.startswith("#") and len(para) < 100:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
                continue

            candidate = (current_chunk + "\n\n" + para).strip() if current_chunk else para

            if len(candidate) <= max_size:
                current_chunk = candidate
            else:
                if current_chunk:
                    chunks.append({"text": current_chunk, "section_heading": None})
                current_chunk = para

        if current_chunk:
            chunks.append({"text": current_chunk, "section_heading": None})

        return chunks

    def document_aware_chunk(text, max_size):
        """Split at heading boundaries, respecting document structure."""
        # Split on markdown headings (## or ###)
        heading_pattern = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
        sections = []
        last_end = 0
        last_heading = None

        for match in heading_pattern.finditer(text):
            if last_end > 0 or text[:match.start()].strip():
                section_text = text[last_end:match.start()].strip()
                if section_text:
                    sections.append({
                        "text": section_text,
                        "heading": last_heading,
                    })
            last_heading = match.group(2).strip()
            last_end = match.end()

        # Capture trailing text after the last heading
        remaining = text[last_end:].strip()
        if remaining:
            sections.append({"text": remaining, "heading": last_heading})

        # Merge short sections, split long ones
        chunks = []
        for section in sections:
            section_text = section["text"]
            heading = section["heading"]

            if len(section_text) <= max_size:
                chunks.append({
                    "text": section_text,
                    "section_heading": heading,
                })
            else:
                # Split long sections at paragraph boundaries
                sub_chunks = semantic_chunk(section_text, max_size)
                for sc in sub_chunks:
                    sc["section_heading"] = heading
                    chunks.append(sc)

        return chunks

    # Process each document
    all_chunks = []
    strategy_func = {
        "fixed": lambda text: fixed_size_chunk(text, chunk_size, chunk_overlap),
        "semantic": lambda text: semantic_chunk(text, chunk_size),
        "document-aware": lambda text: document_aware_chunk(text, chunk_size),
    }

    if chunking_strategy not in strategy_func:
        raise ValueError(
            f"Unknown chunking strategy: '{chunking_strategy}'. "
            f"Must be one of: {list(strategy_func.keys())}"
        )

    for doc in documents:
        doc_name = doc["name"]
        parsed_text = doc["parsed_text"]
        source = doc.get("source", doc_name)

        chunks = strategy_func[chunking_strategy](parsed_text)

        for i, chunk in enumerate(chunks):
            all_chunks.append({
                "doc_name": doc_name,
                "source": source,
                "chunk_index": i,
                "text": chunk["text"],
                "section_heading": chunk.get("section_heading"),
                "chunk_strategy": chunking_strategy,
                "char_count": len(chunk["text"]),
            })

        print(f"  {doc_name}: {len(chunks)} chunks")

    # Write chunks as JSON Lines
    with open(chunks_out.path, "w") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk) + "\n")

    chunks_out.metadata["total_chunks"] = str(len(all_chunks))
    chunks_out.metadata["chunking_strategy"] = chunking_strategy
    chunks_out.metadata["chunk_size"] = str(chunk_size)
    chunks_out.metadata["chunk_overlap"] = str(chunk_overlap)
    print(f"Chunking complete: {len(all_chunks)} total chunks")


# ---------------------------------------------------------------------------
# Component 4: Generate Embeddings
# ---------------------------------------------------------------------------
@dsl.component(
    base_image="python:3.11",
    packages_to_install=["requests==2.31.0", "numpy==1.26.4"],
)
def generate_embeddings(
    chunks_in: Input[Dataset],
    embedding_model: str,
    embedding_endpoint: str,
    embeddings_out: Output[Dataset],
):
    """Generate vector embeddings for each text chunk.

    Calls an OpenAI-compatible /v1/embeddings endpoint (e.g., vLLM serving
    nomic-embed-text or another embedding model). Falls back to generating
    random vectors if the endpoint is unreachable, so the pipeline can run
    end-to-end in environments without a served embedding model.

    For production use, always use a real embedding model -- random vectors
    will not produce meaningful similarity search results.
    """
    import json
    import numpy as np
    import requests

    # Load chunks
    chunks = []
    with open(chunks_in.path, "r") as f:
        for line in f:
            chunks.append(json.loads(line.strip()))

    print(f"Generating embeddings for {len(chunks)} chunks")
    print(f"Embedding model: {embedding_model}")
    print(f"Embedding endpoint: {embedding_endpoint}")

    # Batch processing settings
    BATCH_SIZE = 16
    embedding_dim = None
    all_embeddings = []

    def get_embeddings_from_api(texts):
        """Call the embedding API for a batch of texts."""
        response = requests.post(
            embedding_endpoint,
            json={"model": embedding_model, "input": texts},
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()["data"]
        # Sort by index to maintain order
        data.sort(key=lambda x: x["index"])
        return [item["embedding"] for item in data]

    def get_random_embeddings(texts, dim=768):
        """Generate random embeddings as a fallback (for testing only)."""
        rng = np.random.default_rng(seed=42)
        embeddings = []
        for text in texts:
            # Use text hash as seed for reproducibility
            text_seed = hash(text) % (2**31)
            text_rng = np.random.default_rng(seed=text_seed)
            vec = text_rng.standard_normal(dim).astype(float)
            # Normalize to unit length
            vec = vec / np.linalg.norm(vec)
            embeddings.append(vec.tolist())
        return embeddings

    # Try the real API first, fall back to random
    use_api = True
    try:
        test_result = get_embeddings_from_api(["test"])
        embedding_dim = len(test_result[0])
        print(f"Embedding API reachable -- dimension: {embedding_dim}")
    except Exception as e:
        use_api = False
        embedding_dim = 768
        print(f"Embedding API not reachable ({e})")
        print(f"Falling back to random embeddings (dim={embedding_dim}) -- for testing only")

    # Process in batches
    for batch_start in range(0, len(chunks), BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, len(chunks))
        batch_texts = [c["text"] for c in chunks[batch_start:batch_end]]

        if use_api:
            batch_embeddings = get_embeddings_from_api(batch_texts)
        else:
            batch_embeddings = get_random_embeddings(batch_texts, dim=embedding_dim)

        all_embeddings.extend(batch_embeddings)
        print(f"  Batch {batch_start // BATCH_SIZE + 1}: "
              f"embedded {len(batch_texts)} chunks")

    # Write chunks with their embeddings as JSON Lines
    with open(embeddings_out.path, "w") as f:
        for chunk, embedding in zip(chunks, all_embeddings):
            record = {**chunk, "embedding": embedding}
            f.write(json.dumps(record) + "\n")

    embeddings_out.metadata["total_chunks"] = str(len(chunks))
    embeddings_out.metadata["embedding_dim"] = str(embedding_dim)
    embeddings_out.metadata["embedding_model"] = embedding_model
    embeddings_out.metadata["used_real_api"] = str(use_api)
    print(f"Embedding complete: {len(chunks)} chunks, dim={embedding_dim}")


# ---------------------------------------------------------------------------
# Component 5: Store in Vector DB
# ---------------------------------------------------------------------------
@dsl.component(
    base_image="python:3.11",
    packages_to_install=["pymilvus==2.4.0"],
)
def store_in_vector_db(
    embeddings_in: Input[Dataset],
    vector_db_host: str,
    vector_db_port: int,
    collection_name: str,
    ingestion_metrics: Output[Metrics],
):
    """Store embeddings and metadata in a Milvus vector database.

    Creates the collection if it does not exist, then inserts all chunks
    with their embeddings and metadata. Reports ingestion metrics (document
    count, chunk count, collection size) as KFP Metrics for dashboard
    visibility.

    If Milvus is not reachable, the component simulates the write and still
    reports metrics, so the pipeline can run end-to-end for testing.

    To use pgvector instead of Milvus, replace the pymilvus calls with
    psycopg2 (see L2-M1.3 for the pgvector ingestion pattern).
    """
    import json
    from datetime import datetime

    # Load chunks with embeddings
    records = []
    with open(embeddings_in.path, "r") as f:
        for line in f:
            records.append(json.loads(line.strip()))

    print(f"Storing {len(records)} chunks in vector database")
    print(f"Target: {vector_db_host}:{vector_db_port}/{collection_name}")

    # Determine embedding dimension from first record
    embedding_dim = len(records[0]["embedding"]) if records else 768

    # Track unique source documents
    source_docs = set()
    for r in records:
        source_docs.add(r.get("source", r.get("doc_name", "unknown")))

    use_milvus = True
    try:
        from pymilvus import (
            connections,
            utility,
            Collection,
            CollectionSchema,
            FieldSchema,
            DataType,
        )

        connections.connect(
            alias="default",
            host=vector_db_host,
            port=str(vector_db_port),
        )
        print("Connected to Milvus")

        # Create collection if it does not exist
        if not utility.has_collection(collection_name):
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64,
                            is_primary=True, auto_id=True),
                FieldSchema(name="content", dtype=DataType.VARCHAR,
                            max_length=8192),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR,
                            dim=embedding_dim),
                FieldSchema(name="source_document", dtype=DataType.VARCHAR,
                            max_length=512),
                FieldSchema(name="chunk_index", dtype=DataType.INT64),
                FieldSchema(name="section_heading", dtype=DataType.VARCHAR,
                            max_length=512),
                FieldSchema(name="chunk_strategy", dtype=DataType.VARCHAR,
                            max_length=64),
                FieldSchema(name="created_at", dtype=DataType.VARCHAR,
                            max_length=64),
            ]
            schema = CollectionSchema(
                fields=fields,
                description="RAG document chunks with embeddings",
            )
            collection = Collection(
                name=collection_name,
                schema=schema,
            )
            print(f"Created collection: {collection_name}")

            # Create IVF_FLAT index on the embedding field
            index_params = {
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128},
            }
            collection.create_index(
                field_name="embedding",
                index_params=index_params,
            )
            print("Created vector index (IVF_FLAT, cosine)")
        else:
            collection = Collection(name=collection_name)
            print(f"Using existing collection: {collection_name}")

        # Prepare data for insertion
        now = datetime.utcnow().isoformat()

        contents = []
        embeddings = []
        sources = []
        chunk_indices = []
        headings = []
        strategies = []
        timestamps = []

        for r in records:
            # Truncate content to fit Milvus VARCHAR limit
            text = r["text"][:8000]
            contents.append(text)
            embeddings.append(r["embedding"])
            sources.append(r.get("source", r.get("doc_name", "unknown")))
            chunk_indices.append(r.get("chunk_index", 0))
            headings.append(r.get("section_heading") or "")
            strategies.append(r.get("chunk_strategy", "unknown"))
            timestamps.append(now)

        # Insert in batches
        BATCH_SIZE = 100
        total_inserted = 0
        for i in range(0, len(contents), BATCH_SIZE):
            end = min(i + BATCH_SIZE, len(contents))
            batch_data = [
                contents[i:end],
                embeddings[i:end],
                sources[i:end],
                chunk_indices[i:end],
                headings[i:end],
                strategies[i:end],
                timestamps[i:end],
            ]
            collection.insert(batch_data)
            total_inserted += end - i
            print(f"  Inserted batch: {total_inserted}/{len(contents)}")

        # Flush to ensure data is persisted
        collection.flush()

        # Get collection stats
        collection_size = collection.num_entities
        print(f"Collection '{collection_name}' now has {collection_size} entities")

    except Exception as e:
        use_milvus = False
        print(f"Milvus not reachable ({e}) -- simulating vector DB write")
        total_inserted = len(records)
        collection_size = len(records)
        print(f"  Simulated insert of {total_inserted} chunks")
        print(f"  Simulated collection size: {collection_size}")

    # Log metrics -- these appear in the pipeline run's Metrics tab
    ingestion_metrics.log_metric("num_source_documents", len(source_docs))
    ingestion_metrics.log_metric("num_chunks_inserted", total_inserted)
    ingestion_metrics.log_metric("embedding_dimension", embedding_dim)
    ingestion_metrics.log_metric("collection_total_entities", collection_size)
    ingestion_metrics.log_metric("used_real_milvus", 1.0 if use_milvus else 0.0)

    print(f"\nIngestion Summary:")
    print(f"  Source documents:    {len(source_docs)}")
    print(f"  Chunks inserted:     {total_inserted}")
    print(f"  Embedding dimension: {embedding_dim}")
    print(f"  Collection size:     {collection_size}")
    print(f"  Used real Milvus:    {use_milvus}")


# ---------------------------------------------------------------------------
# Pipeline Definition
# ---------------------------------------------------------------------------
@dsl.pipeline(
    name="rag-ingestion-pipeline",
    description=(
        "RAG document ingestion pipeline: fetch documents from S3, parse with "
        "Docling, chunk text, generate embeddings, and store in a vector database."
    ),
)
def rag_ingestion_pipeline(
    source_bucket: str = "documents",
    source_prefix: str = "raw/",
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    chunking_strategy: str = "fixed",
    embedding_model: str = "nomic-embed-text-v1.5",
    embedding_endpoint: str = "http://embedding-model:8080/v1/embeddings",
    vector_db_host: str = "milvus-service",
    vector_db_port: int = 19530,
    collection_name: str = "documents",
):
    # Step 1: Fetch documents from source
    fetch_task = fetch_documents(
        source_bucket=source_bucket,
        source_prefix=source_prefix,
    )

    # Step 2: Parse documents into structured text
    parse_task = parse_documents(
        raw_documents=fetch_task.outputs["documents_out"],
    )

    # Step 3: Chunk parsed text
    chunk_task = chunk_documents(
        parsed_documents=parse_task.outputs["parsed_out"],
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        chunking_strategy=chunking_strategy,
    )

    # Step 4: Generate embeddings for each chunk
    embed_task = generate_embeddings(
        chunks_in=chunk_task.outputs["chunks_out"],
        embedding_model=embedding_model,
        embedding_endpoint=embedding_endpoint,
    )

    # Step 5: Store embeddings in the vector database
    store_in_vector_db(
        embeddings_in=embed_task.outputs["embeddings_out"],
        vector_db_host=vector_db_host,
        vector_db_port=vector_db_port,
        collection_name=collection_name,
    )


# ---------------------------------------------------------------------------
# Compile and (optionally) Submit
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Compile or submit the RAG ingestion pipeline"
    )
    parser.add_argument(
        "--compile-only",
        action="store_true",
        help="Only compile to YAML, do not submit",
    )
    parser.add_argument(
        "--output",
        default="rag_ingestion_pipeline.yaml",
        help="Output YAML path (default: rag_ingestion_pipeline.yaml)",
    )
    args = parser.parse_args()

    # Always compile
    compiler.Compiler().compile(
        pipeline_func=rag_ingestion_pipeline,
        package_path=args.output,
    )
    print(f"Pipeline compiled to {args.output}")

    if args.compile_only:
        print("Compile-only mode -- skipping submission.")
    else:
        import subprocess
        from kfp.client import Client

        # Get the DSP route and auth token from the cluster
        route = subprocess.check_output(
            ["oc", "get", "route", "ds-pipeline-dspa", "-n", "ml-pipelines-tutorial",
             "-o", "jsonpath={.spec.host}"],
        ).decode().strip()

        token = subprocess.check_output(
            ["oc", "whoami", "-t"],
        ).decode().strip()

        print(f"Connecting to pipeline server at https://{route}")

        client = Client(
            host=f"https://{route}",
            existing_token=token,
        )

        # Create a run with default parameters
        run = client.create_run_from_pipeline_package(
            pipeline_file=args.output,
            arguments={
                "source_bucket": "documents",
                "source_prefix": "raw/",
                "chunk_size": 512,
                "chunk_overlap": 50,
                "chunking_strategy": "fixed",
                "embedding_model": "nomic-embed-text-v1.5",
                "embedding_endpoint": "http://embedding-model:8080/v1/embeddings",
                "vector_db_host": "milvus-service",
                "vector_db_port": 19530,
                "collection_name": "documents",
            },
            run_name="rag-ingestion-run",
            experiment_name="tutorial-experiments",
        )

        print(f"Run submitted: {run.run_id}")
        print("View in dashboard: Data Science Projects > ml-pipelines-tutorial > Runs")
