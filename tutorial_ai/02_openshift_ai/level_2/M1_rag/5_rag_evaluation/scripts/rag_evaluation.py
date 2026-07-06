"""
RAG Evaluation Pipeline

Evaluates a RAG system's retrieval and generation quality using standard
information retrieval metrics and LLM-as-judge generation metrics.

This script:
  1. Runs a set of evaluation questions through the full RAG pipeline
     (embed query -> retrieve chunks -> generate answer).
  2. Computes retrieval metrics: precision@K, recall@K, MRR, NDCG@K.
  3. Computes generation metrics: faithfulness, relevance (LLM-as-judge).
  4. Logs parameters, metrics, and artifacts to MLflow for comparison.

Requirements:
    pip install psycopg2-binary requests numpy mlflow

Usage:
    python3 rag_evaluation.py \
      --embedding-url http://embedding-model:8080 \
      --llm-url http://gemma-4-e4b:8080 \
      --db-host pgvector --db-name vectordb \
      --db-user vectordb --db-password vectordb \
      --top-k 5 \
      --chunk-strategy fixed-512 \
      --experiment-name rag-evaluation
"""

import argparse
import json
import logging
import math
import os
import sys
import tempfile
from dataclasses import dataclass, field, asdict

import numpy as np
import psycopg2
import requests

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Evaluation dataset
# ---------------------------------------------------------------------------
# Each entry contains a question, a ground truth answer, and the IDs of
# chunks that should be retrieved. These IDs correspond to `id` values in
# the `document_chunks` table populated by L2-M1.3.
#
# In a production evaluation, you would load this from a JSON file or
# database. For this tutorial, the dataset is defined inline so the script
# is self-contained.
# ---------------------------------------------------------------------------

EVAL_DATASET = [
    {
        "question": "What serving runtimes does OpenShift AI support?",
        "ground_truth": (
            "OpenShift AI supports three serving runtimes: vLLM (the Red Hat "
            "AI Inference Server) for LLMs and generative models, OpenVINO "
            "Model Server for traditional ML models optimized on Intel "
            "hardware, and MLServer for classical ML models like scikit-learn "
            "and XGBoost."
        ),
        "relevant_chunk_ids": [1, 2, 3],
    },
    {
        "question": "How does KServe deploy models on OpenShift AI?",
        "ground_truth": (
            "KServe uses two CRDs: ServingRuntime defines the inference "
            "server configuration (container image, arguments, supported "
            "formats), and InferenceService deploys a specific model using "
            "a ServingRuntime. When you create an InferenceService, KServe "
            "creates the underlying Deployment, Service, and Route."
        ),
        "relevant_chunk_ids": [4, 5],
    },
    {
        "question": "What is the difference between RawDeployment and Serverless mode in KServe?",
        "ground_truth": (
            "RawDeployment mode creates standard Kubernetes Deployments and "
            "Services without requiring extra operators. Serverless mode uses "
            "Knative Serving for automatic scale-to-zero but is deprecated "
            "in OpenShift AI 3.x. RawDeployment is the recommended mode."
        ),
        "relevant_chunk_ids": [4, 6],
    },
    {
        "question": "What is PagedAttention in vLLM?",
        "ground_truth": (
            "PagedAttention is a memory management technique in vLLM that "
            "borrows the concept of virtual memory paging from operating "
            "systems. It breaks the KV cache into fixed-size blocks (pages) "
            "and maps them non-contiguously, resulting in near-zero memory "
            "waste and the ability to serve more concurrent requests per GPU."
        ),
        "relevant_chunk_ids": [7, 8],
    },
    {
        "question": "What chunking strategies are available for document ingestion?",
        "ground_truth": (
            "Three chunking strategies are available: fixed-size chunking "
            "(splits at N tokens with overlap), semantic chunking (splits at "
            "natural language boundaries like paragraphs), and document-aware "
            "chunking (uses document structure like headings and sections to "
            "determine boundaries)."
        ),
        "relevant_chunk_ids": [9, 10, 11],
    },
    {
        "question": "How does pgvector perform similarity search?",
        "ground_truth": (
            "pgvector supports three distance operators for similarity "
            "search: cosine distance (<=>), L2/Euclidean distance (<->), "
            "and negative inner product (<#>). For RAG with normalized "
            "embeddings, cosine distance is the standard choice. Results "
            "are ordered by distance and limited to a top-K."
        ),
        "relevant_chunk_ids": [12, 13],
    },
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RetrievedChunk:
    """A single chunk returned by the retrieval step."""
    chunk_id: int
    content: str
    source: str
    similarity: float


@dataclass
class EvalResult:
    """Evaluation results for a single question."""
    question: str
    ground_truth: str
    generated_answer: str
    retrieved_chunk_ids: list[int] = field(default_factory=list)
    relevant_chunk_ids: list[int] = field(default_factory=list)
    precision_at_k: float = 0.0
    recall_at_k: float = 0.0
    mrr: float = 0.0
    ndcg_at_k: float = 0.0
    faithfulness: float = 0.0
    relevance: float = 0.0


# ---------------------------------------------------------------------------
# Retrieval metrics
# ---------------------------------------------------------------------------

def precision_at_k(retrieved_ids: list[int], relevant_ids: list[int], k: int) -> float:
    """Compute Precision@K.

    Of the top-K retrieved documents, what fraction is relevant?

    Args:
        retrieved_ids: Ordered list of retrieved chunk IDs.
        relevant_ids: Set of ground truth relevant chunk IDs.
        k: Number of top results to consider.

    Returns:
        Precision@K as a float in [0, 1].
    """
    if k == 0:
        return 0.0
    top_k = retrieved_ids[:k]
    relevant_set = set(relevant_ids)
    relevant_in_top_k = sum(1 for cid in top_k if cid in relevant_set)
    return relevant_in_top_k / k


def recall_at_k(retrieved_ids: list[int], relevant_ids: list[int], k: int) -> float:
    """Compute Recall@K.

    Of all relevant documents, what fraction appears in the top-K results?

    Args:
        retrieved_ids: Ordered list of retrieved chunk IDs.
        relevant_ids: Set of ground truth relevant chunk IDs.
        k: Number of top results to consider.

    Returns:
        Recall@K as a float in [0, 1].
    """
    if not relevant_ids:
        return 0.0
    top_k = retrieved_ids[:k]
    relevant_set = set(relevant_ids)
    relevant_in_top_k = sum(1 for cid in top_k if cid in relevant_set)
    return relevant_in_top_k / len(relevant_set)


def mrr(retrieved_ids: list[int], relevant_ids: list[int]) -> float:
    """Compute Reciprocal Rank for a single query.

    Returns 1/rank of the first relevant document, or 0 if no relevant
    document is found.

    Args:
        retrieved_ids: Ordered list of retrieved chunk IDs.
        relevant_ids: Set of ground truth relevant chunk IDs.

    Returns:
        Reciprocal rank as a float in [0, 1].
    """
    relevant_set = set(relevant_ids)
    for rank, cid in enumerate(retrieved_ids, start=1):
        if cid in relevant_set:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved_ids: list[int], relevant_ids: list[int], k: int) -> float:
    """Compute NDCG@K (Normalized Discounted Cumulative Gain).

    Uses binary relevance: a document is either relevant (1) or not (0).

    Args:
        retrieved_ids: Ordered list of retrieved chunk IDs.
        relevant_ids: Set of ground truth relevant chunk IDs.
        k: Number of top results to consider.

    Returns:
        NDCG@K as a float in [0, 1].
    """
    relevant_set = set(relevant_ids)

    # DCG for the actual ranking
    dcg = 0.0
    for i, cid in enumerate(retrieved_ids[:k]):
        rel = 1.0 if cid in relevant_set else 0.0
        dcg += rel / math.log2(i + 2)  # i+2 because positions are 1-indexed

    # Ideal DCG: all relevant documents at the top
    num_relevant_in_k = min(len(relevant_set), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(num_relevant_in_k))

    if idcg == 0.0:
        return 0.0
    return dcg / idcg


# ---------------------------------------------------------------------------
# Generation metrics (LLM-as-judge)
# ---------------------------------------------------------------------------

def faithfulness_score(
    question: str,
    context: str,
    answer: str,
    llm_url: str,
    model_name: str = "gemma-4-e4b",
) -> float:
    """Evaluate faithfulness using LLM-as-judge.

    Asks the LLM to rate how well the answer is grounded in the provided
    context (0 = completely hallucinated, 1 = fully grounded).

    Args:
        question: The original question.
        context: The retrieved context chunks concatenated.
        answer: The generated answer to evaluate.
        llm_url: Base URL of the LLM endpoint.
        model_name: Model name for the API call.

    Returns:
        Faithfulness score as a float in [0, 1].
    """
    judge_prompt = f"""You are an evaluation judge. Your task is to assess the FAITHFULNESS of an answer.

Faithfulness measures whether the answer contains ONLY information that is supported by the provided context. An answer is unfaithful if it includes claims, facts, or details not found in the context.

Context:
---
{context}
---

Question: {question}

Answer to evaluate:
---
{answer}
---

Rate the faithfulness of the answer on a scale from 0.0 to 1.0:
- 1.0: Every claim in the answer is directly supported by the context.
- 0.5: Some claims are supported, but others are not found in the context.
- 0.0: The answer is entirely unsupported by the context.

Respond with ONLY a JSON object in this exact format:
{{"score": <float between 0.0 and 1.0>, "reason": "<brief explanation>"}}"""

    return _call_llm_judge(judge_prompt, llm_url, model_name)


def relevance_score(
    question: str,
    answer: str,
    llm_url: str,
    model_name: str = "gemma-4-e4b",
) -> float:
    """Evaluate answer relevance using LLM-as-judge.

    Asks the LLM to rate how well the answer addresses the original
    question (0 = completely off-topic, 1 = directly addresses the question).

    Args:
        question: The original question.
        answer: The generated answer to evaluate.
        llm_url: Base URL of the LLM endpoint.
        model_name: Model name for the API call.

    Returns:
        Relevance score as a float in [0, 1].
    """
    judge_prompt = f"""You are an evaluation judge. Your task is to assess the RELEVANCE of an answer.

Relevance measures whether the answer actually addresses the question that was asked. An answer can be factually correct but irrelevant if it discusses a different topic than what was asked.

Question: {question}

Answer to evaluate:
---
{answer}
---

Rate the relevance of the answer on a scale from 0.0 to 1.0:
- 1.0: The answer directly and completely addresses the question.
- 0.5: The answer partially addresses the question but misses key aspects.
- 0.0: The answer does not address the question at all.

Respond with ONLY a JSON object in this exact format:
{{"score": <float between 0.0 and 1.0>, "reason": "<brief explanation>"}}"""

    return _call_llm_judge(judge_prompt, llm_url, model_name)


def _call_llm_judge(prompt: str, llm_url: str, model_name: str) -> float:
    """Send a judge prompt to the LLM and extract the score.

    Handles parsing failures gracefully by returning 0.0 with a warning.

    Args:
        prompt: The full judge prompt.
        llm_url: Base URL of the LLM endpoint.
        model_name: Model name for the API call.

    Returns:
        Score as a float in [0, 1], or 0.0 on failure.
    """
    try:
        response = requests.post(
            f"{llm_url}/v1/chat/completions",
            json={
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": 200,
            },
            timeout=60,
        )
        response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"].strip()

        # Try to parse JSON from the response
        # The LLM may wrap the JSON in markdown code fences
        if "```" in content:
            # Extract content between code fences
            parts = content.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    content = part
                    break

        result = json.loads(content)
        score = float(result.get("score", 0.0))
        return max(0.0, min(1.0, score))  # Clamp to [0, 1]

    except (requests.RequestException, json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning("LLM judge call failed: %s. Returning 0.0.", e)
        return 0.0


# ---------------------------------------------------------------------------
# RAG pipeline functions
# ---------------------------------------------------------------------------

def get_query_embedding(question: str, embedding_url: str) -> list[float]:
    """Embed a question using the embedding model's /v1/embeddings endpoint.

    Args:
        question: The question text to embed.
        embedding_url: Base URL of the embedding model endpoint.

    Returns:
        List of floats representing the embedding vector.

    Raises:
        requests.RequestException: If the API call fails.
    """
    response = requests.post(
        f"{embedding_url}/v1/embeddings",
        json={
            "model": "nomic-embed-text-v1.5",
            "input": question,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]


def retrieve_chunks(
    embedding: list[float],
    db_conn,
    top_k: int = 5,
    chunk_strategy: str | None = None,
) -> list[RetrievedChunk]:
    """Retrieve the top-K most similar chunks from pgvector.

    Args:
        embedding: The query embedding vector.
        db_conn: psycopg2 database connection.
        top_k: Number of chunks to retrieve.
        chunk_strategy: If provided, filter chunks by this strategy.

    Returns:
        List of RetrievedChunk objects ordered by similarity (descending).
    """
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    query = """
        SELECT id, content, source_document,
               1 - (embedding <=> %s::vector) AS similarity
        FROM document_chunks
    """
    params = [embedding_str]

    if chunk_strategy:
        query += " WHERE chunk_strategy = %s"
        params.append(chunk_strategy)

    query += " ORDER BY embedding <=> %s::vector LIMIT %s"
    params.extend([embedding_str, top_k])

    with db_conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    return [
        RetrievedChunk(
            chunk_id=row[0],
            content=row[1],
            source=row[2],
            similarity=float(row[3]),
        )
        for row in rows
    ]


def generate_rag_answer(
    question: str,
    chunks: list[RetrievedChunk],
    llm_url: str,
    model_name: str = "gemma-4-e4b",
) -> str:
    """Generate an answer using the RAG approach.

    Constructs an augmented prompt with the retrieved chunks as context
    and sends it to the LLM.

    Args:
        question: The user's question.
        chunks: Retrieved context chunks.
        llm_url: Base URL of the LLM endpoint.
        model_name: Model name for the API call.

    Returns:
        The generated answer as a string.
    """
    # Build context from retrieved chunks
    context_parts = []
    for chunk in chunks:
        context_parts.append(
            f"[Source: {chunk.source}, ID: {chunk.chunk_id}]\n{chunk.content}"
        )
    context = "\n---\n".join(context_parts)

    system_prompt = (
        "You are a helpful assistant. Answer the user's question based ONLY on "
        "the provided context. If the context does not contain enough information "
        "to answer the question, say 'I don't have enough information to answer "
        "that question based on the available documents.'\n\n"
        "When you use information from the context, cite the source.\n\n"
        f"Context:\n---\n{context}\n---"
    )

    try:
        response = requests.post(
            f"{llm_url}/v1/chat/completions",
            json={
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                ],
                "temperature": 0.1,
                "max_tokens": 500,
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()

    except requests.RequestException as e:
        logger.error("LLM generation failed: %s", e)
        return "(Generation failed)"


# ---------------------------------------------------------------------------
# Evaluation pipeline
# ---------------------------------------------------------------------------

def run_evaluation(
    eval_dataset: list[dict],
    embedding_url: str,
    llm_url: str,
    db_conn,
    top_k: int = 5,
    chunk_strategy: str | None = None,
    model_name: str = "gemma-4-e4b",
) -> list[EvalResult]:
    """Run the full evaluation pipeline on the dataset.

    For each question:
      1. Embed the question.
      2. Retrieve top-K chunks from pgvector.
      3. Generate an answer using the RAG approach.
      4. Compute retrieval metrics.
      5. Compute generation metrics (LLM-as-judge).

    Args:
        eval_dataset: List of evaluation entries (question, ground_truth,
            relevant_chunk_ids).
        embedding_url: Base URL of the embedding model endpoint.
        llm_url: Base URL of the LLM endpoint.
        db_conn: psycopg2 database connection.
        top_k: Number of chunks to retrieve per query.
        chunk_strategy: If provided, filter retrieval to this strategy.
        model_name: Model name for LLM API calls.

    Returns:
        List of EvalResult objects, one per question.
    """
    results = []
    total = len(eval_dataset)

    for i, entry in enumerate(eval_dataset, start=1):
        question = entry["question"]
        ground_truth = entry["ground_truth"]
        relevant_ids = entry["relevant_chunk_ids"]

        logger.info(
            "Evaluating question %d/%d: %s", i, total, question[:60]
        )

        # Step 1: Embed the query
        try:
            embedding = get_query_embedding(question, embedding_url)
        except requests.RequestException as e:
            logger.error("  Embedding failed: %s. Skipping.", e)
            continue

        # Step 2: Retrieve chunks
        chunks = retrieve_chunks(embedding, db_conn, top_k, chunk_strategy)
        retrieved_ids = [c.chunk_id for c in chunks]

        if chunks:
            logger.info(
                "  Retrieved %d chunks (top match similarity: %.2f)",
                len(chunks),
                chunks[0].similarity,
            )
        else:
            logger.warning("  No chunks retrieved.")

        # Step 3: Generate answer
        answer = generate_rag_answer(question, chunks, llm_url, model_name)

        # Step 4: Compute retrieval metrics
        p_at_k = precision_at_k(retrieved_ids, relevant_ids, top_k)
        r_at_k = recall_at_k(retrieved_ids, relevant_ids, top_k)
        rr = mrr(retrieved_ids, relevant_ids)
        ndcg = ndcg_at_k(retrieved_ids, relevant_ids, top_k)

        logger.info(
            "  Retrieval: precision@%d=%.2f recall@%d=%.2f mrr=%.2f ndcg@%d=%.2f",
            top_k, p_at_k, top_k, r_at_k, rr, top_k, ndcg,
        )

        # Step 5: Compute generation metrics
        context_text = "\n---\n".join(c.content for c in chunks)
        faith = faithfulness_score(question, context_text, answer, llm_url, model_name)
        relev = relevance_score(question, answer, llm_url, model_name)

        logger.info("  Generation: faithfulness=%.2f relevance=%.2f", faith, relev)

        result = EvalResult(
            question=question,
            ground_truth=ground_truth,
            generated_answer=answer,
            retrieved_chunk_ids=retrieved_ids,
            relevant_chunk_ids=relevant_ids,
            precision_at_k=p_at_k,
            recall_at_k=r_at_k,
            mrr=rr,
            ndcg_at_k=ndcg,
            faithfulness=faith,
            relevance=relev,
        )
        results.append(result)

    return results


def aggregate_metrics(results: list[EvalResult]) -> dict[str, float]:
    """Compute aggregate metrics across all evaluation results.

    Args:
        results: List of per-question EvalResult objects.

    Returns:
        Dictionary of metric_name -> average_value.
    """
    if not results:
        return {}

    return {
        "avg_precision_at_k": float(np.mean([r.precision_at_k for r in results])),
        "avg_recall_at_k": float(np.mean([r.recall_at_k for r in results])),
        "avg_mrr": float(np.mean([r.mrr for r in results])),
        "avg_ndcg_at_k": float(np.mean([r.ndcg_at_k for r in results])),
        "avg_faithfulness": float(np.mean([r.faithfulness for r in results])),
        "avg_relevance": float(np.mean([r.relevance for r in results])),
    }


# ---------------------------------------------------------------------------
# MLflow integration
# ---------------------------------------------------------------------------

def log_to_mlflow(
    results: list[EvalResult],
    metrics: dict[str, float],
    params: dict[str, str],
    tracking_uri: str,
    experiment_name: str,
) -> None:
    """Log evaluation results to MLflow.

    Creates an experiment (if it does not exist), starts a run, and logs:
      - Parameters: chunk_strategy, top_k, model_name, etc.
      - Metrics: avg_precision, avg_recall, avg_faithfulness, etc.
      - Artifacts: Full evaluation results as JSON.

    Args:
        results: List of per-question EvalResult objects.
        metrics: Aggregated metrics dictionary.
        params: Run parameters dictionary.
        tracking_uri: MLflow tracking server URL.
        experiment_name: Name of the MLflow experiment.
    """
    try:
        import mlflow

        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(experiment_name)

        with mlflow.start_run(run_name=params.get("chunk_strategy", "evaluation")):
            # Log parameters
            for key, value in params.items():
                mlflow.log_param(key, value)

            # Log metrics
            for key, value in metrics.items():
                mlflow.log_metric(key, value)

            # Log full results as an artifact
            results_data = [asdict(r) for r in results]
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as f:
                json.dump(results_data, f, indent=2)
                artifact_path = f.name

            mlflow.log_artifact(artifact_path, "evaluation")
            os.unlink(artifact_path)

            # Log the evaluation dataset for reproducibility
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as f:
                json.dump(EVAL_DATASET, f, indent=2)
                dataset_path = f.name

            mlflow.log_artifact(dataset_path, "evaluation")
            os.unlink(dataset_path)

        logger.info("Results logged to MLflow experiment: %s", experiment_name)

    except ImportError:
        logger.warning("mlflow not installed. Skipping MLflow logging.")
    except Exception as e:
        logger.warning("MLflow logging failed: %s. Results were printed above.", e)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="RAG Evaluation Pipeline -- measure retrieval and generation quality",
    )
    parser.add_argument(
        "--embedding-url",
        type=str,
        default=os.environ.get("EMBEDDING_URL", "http://embedding-model:8080"),
        help="Base URL of the embedding model endpoint (default: http://embedding-model:8080)",
    )
    parser.add_argument(
        "--llm-url",
        type=str,
        default=os.environ.get("LLM_URL", "http://gemma-4-e4b:8080"),
        help="Base URL of the LLM endpoint (default: http://gemma-4-e4b:8080)",
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        default=os.environ.get("LLM_MODEL", "gemma-4-e4b"),
        help="Model name for the LLM API call (default: gemma-4-e4b)",
    )
    parser.add_argument(
        "--db-host",
        type=str,
        default=os.environ.get("DB_HOST", "pgvector"),
        help="pgvector database hostname (default: pgvector)",
    )
    parser.add_argument(
        "--db-port",
        type=int,
        default=int(os.environ.get("DB_PORT", "5432")),
        help="pgvector database port (default: 5432)",
    )
    parser.add_argument(
        "--db-name",
        type=str,
        default=os.environ.get("DB_NAME", "vectordb"),
        help="pgvector database name (default: vectordb)",
    )
    parser.add_argument(
        "--db-user",
        type=str,
        default=os.environ.get("DB_USER", "vectordb"),
        help="pgvector database username (default: vectordb)",
    )
    parser.add_argument(
        "--db-password",
        type=str,
        default=os.environ.get("DB_PASSWORD", "vectordb"),
        help="pgvector database password (default: vectordb)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=int(os.environ.get("TOP_K", "5")),
        help="Number of chunks to retrieve per query (default: 5)",
    )
    parser.add_argument(
        "--chunk-strategy",
        type=str,
        default="unknown",
        help="Label for the chunking strategy being evaluated (for MLflow logging)",
    )
    parser.add_argument(
        "--mlflow-tracking-uri",
        type=str,
        default=os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000"),
        help="MLflow tracking server URI (default: http://mlflow:5000)",
    )
    parser.add_argument(
        "--experiment-name",
        type=str,
        default="rag-evaluation",
        help="MLflow experiment name (default: rag-evaluation)",
    )

    args = parser.parse_args()

    logger.info("Starting RAG evaluation pipeline")
    logger.info(
        "Experiment: %s | Run label: %s",
        args.experiment_name,
        args.chunk_strategy,
    )

    # -- Connect to pgvector ---------------------------------------------------
    try:
        db_conn = psycopg2.connect(
            host=args.db_host,
            port=args.db_port,
            dbname=args.db_name,
            user=args.db_user,
            password=args.db_password,
        )
        logger.info("Connected to pgvector at %s:%d", args.db_host, args.db_port)
    except psycopg2.Error as e:
        logger.error("Failed to connect to pgvector: %s", e)
        sys.exit(1)

    # -- Run evaluation --------------------------------------------------------
    results = run_evaluation(
        eval_dataset=EVAL_DATASET,
        embedding_url=args.embedding_url,
        llm_url=args.llm_url,
        db_conn=db_conn,
        top_k=args.top_k,
        chunk_strategy=args.chunk_strategy if args.chunk_strategy != "unknown" else None,
        model_name=args.llm_model,
    )

    # -- Aggregate and display results -----------------------------------------
    metrics = aggregate_metrics(results)

    logger.info("=== Aggregate Results ===")
    for metric_name, value in metrics.items():
        logger.info("  %s: %.2f", metric_name, value)

    # -- Log to MLflow ---------------------------------------------------------
    params = {
        "chunk_strategy": args.chunk_strategy,
        "top_k": str(args.top_k),
        "model_name": args.llm_model,
        "embedding_url": args.embedding_url,
        "llm_url": args.llm_url,
        "eval_dataset_size": str(len(EVAL_DATASET)),
    }

    log_to_mlflow(
        results=results,
        metrics=metrics,
        params=params,
        tracking_uri=args.mlflow_tracking_uri,
        experiment_name=args.experiment_name,
    )

    # -- Clean up --------------------------------------------------------------
    db_conn.close()
    logger.info("Evaluation complete.")


if __name__ == "__main__":
    main()
