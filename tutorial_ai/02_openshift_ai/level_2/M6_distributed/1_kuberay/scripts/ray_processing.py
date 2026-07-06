"""
Distributed document processing with Ray Data.

This script demonstrates using Ray Data to process a collection of text
documents in parallel across a Ray cluster. It simulates a real-world
scenario: preprocessing text documents for RAG ingestion by cleaning,
chunking, and computing metadata.

Usage:
  - Copy to the Ray head node and run via oc exec (see README Step 6)
  - Or run interactively from a workbench with CodeFlare SDK

L2-M6.1 -- KubeRay and Ray Clusters
"""

import ray
import time
import re
import hashlib
from typing import Dict, Any


# --- Document Processing Functions ---

def clean_text(text: str) -> str:
    """Remove extra whitespace and normalize text."""
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    return text


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> list:
    """Split text into overlapping chunks for RAG ingestion.

    Args:
        text: The input text to chunk.
        chunk_size: Number of words per chunk.
        overlap: Number of overlapping words between consecutive chunks.

    Returns:
        A list of text chunks.
    """
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start = end - overlap
    return chunks


def compute_metadata(text: str) -> Dict[str, Any]:
    """Compute metadata for a text document."""
    words = text.split()
    # Count word frequencies for the top-words summary
    word_freq = {}
    for w in words:
        w_lower = w.lower().strip(".,;:!?\"'()")
        if len(w_lower) > 2:
            word_freq[w_lower] = word_freq.get(w_lower, 0) + 1
    return {
        "word_count": len(words),
        "char_count": len(text),
        "unique_words": len(word_freq),
        "content_hash": hashlib.md5(text.encode()).hexdigest(),
        "word_freq": word_freq,
    }


# --- Ray Data Processing Pipeline ---

def process_document(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a single document row. This function runs in parallel
    across the Ray cluster workers.

    Each worker independently cleans, analyzes, and chunks its assigned
    documents. Ray Data handles the distribution automatically.
    """
    text = row["text"]

    # Step 1: Clean the text
    cleaned = clean_text(text)

    # Step 2: Compute metadata
    metadata = compute_metadata(cleaned)

    # Step 3: Chunk the text for RAG ingestion
    chunks = chunk_text(cleaned)

    return {
        "doc_id": row["doc_id"],
        "topic": row["topic"],
        "original_length": len(text),
        "cleaned_length": len(cleaned),
        "num_chunks": len(chunks),
        "word_count": metadata["word_count"],
        "unique_words": metadata["unique_words"],
        "content_hash": metadata["content_hash"],
        "first_chunk_preview": chunks[0][:200] if chunks else "",
    }


def generate_sample_documents(num_docs: int = 200) -> list:
    """
    Generate sample documents for processing.

    In production, this would read from S3, a database, or a file system.
    Each document contains multiple paragraphs on a rotating set of topics,
    giving enough text to demonstrate meaningful chunking.
    """
    documents = []
    topics = [
        "machine learning model training and optimization techniques",
        "distributed computing architectures and fault tolerance",
        "natural language processing and transformer architectures",
        "kubernetes container orchestration and pod scheduling",
        "data pipeline engineering and stream processing systems",
    ]

    for i in range(num_docs):
        topic = topics[i % len(topics)]
        # Generate a document with multiple paragraphs
        paragraphs = []
        for p in range(10):
            paragraphs.append(
                f"Document {i}, paragraph {p}: This section discusses {topic}. "
                f"It covers key concepts including resource allocation, performance "
                f"tuning, and best practices for production deployments. "
                f"Understanding these fundamentals is essential for building "
                f"scalable and reliable systems in enterprise environments. "
                f"The approach described here has been validated across multiple "
                f"organizations and workload patterns."
            )
        text = "\n\n".join(paragraphs)
        documents.append({
            "doc_id": f"doc-{i:04d}",
            "topic": topic,
            "text": text,
        })

    return documents


def main():
    # Initialize Ray -- connects to the existing cluster when run on a head node
    ray.init()

    print("=" * 60)
    print("Ray Data -- Distributed Document Processing")
    print("=" * 60)

    # Show cluster info
    resources = ray.cluster_resources()
    print(f"\nRay cluster resources: {resources}")
    print(f"Available nodes: {len(ray.nodes())}")

    # Generate sample documents
    num_docs = 200
    print(f"\n--- Generating {num_docs} sample documents ---")
    documents = generate_sample_documents(num_docs=num_docs)
    print(f"Generated {len(documents)} documents across 5 topics")

    # Create a Ray Dataset from the documents
    print("\n--- Creating Ray Dataset ---")
    ds = ray.data.from_items(documents)
    print(f"Dataset count: {ds.count()}")

    # Process documents in parallel using map
    # Ray Data automatically partitions the data across available workers
    print("\n--- Processing documents (distributed across workers) ---")
    start_time = time.time()

    processed_ds = ds.map(process_document)

    # Materialize the dataset to trigger execution
    results = processed_ds.take_all()

    elapsed = time.time() - start_time

    # Compute summary statistics
    total_chunks = sum(r["num_chunks"] for r in results)
    total_words = sum(r["word_count"] for r in results)
    total_unique = sum(r["unique_words"] for r in results)
    avg_chunks = total_chunks / len(results) if results else 0

    print(f"\nProcessing completed in {elapsed:.2f} seconds")

    print("\n--- Processing Summary ---")
    print(f"  Total documents processed: {len(results)}")
    print(f"  Total chunks created:      {total_chunks}")
    print(f"  Average chunks per doc:    {avg_chunks:.1f}")
    print(f"  Total words processed:     {total_words:,}")
    print(f"  Total unique words:        {total_unique:,}")
    print(f"  Throughput:                {len(results) / elapsed:.1f} docs/sec")

    # Show per-topic breakdown
    print("\n--- Per-Topic Breakdown ---")
    topic_stats = {}
    for r in results:
        topic = r["topic"]
        if topic not in topic_stats:
            topic_stats[topic] = {"count": 0, "words": 0, "chunks": 0}
        topic_stats[topic]["count"] += 1
        topic_stats[topic]["words"] += r["word_count"]
        topic_stats[topic]["chunks"] += r["num_chunks"]

    for topic, stats in topic_stats.items():
        print(f"  {topic[:50]:50s}  docs={stats['count']:3d}  "
              f"words={stats['words']:6,}  chunks={stats['chunks']:3d}")

    # Show a sample result
    if results:
        sample = results[0]
        print(f"\n--- Sample Result (doc_id={sample['doc_id']}) ---")
        print(f"  Topic:           {sample['topic']}")
        print(f"  Original length: {sample['original_length']:,} chars")
        print(f"  Cleaned length:  {sample['cleaned_length']:,} chars")
        print(f"  Number of chunks: {sample['num_chunks']}")
        print(f"  Word count:      {sample['word_count']}")
        print(f"  Unique words:    {sample['unique_words']}")
        print(f"  Content hash:    {sample['content_hash']}")
        print(f"  First chunk:     {sample['first_chunk_preview'][:100]}...")

    # Shutdown Ray
    ray.shutdown()
    print("\n" + "=" * 60)
    print("Done. Ray cluster connection closed.")
    print("=" * 60)


if __name__ == "__main__":
    main()
