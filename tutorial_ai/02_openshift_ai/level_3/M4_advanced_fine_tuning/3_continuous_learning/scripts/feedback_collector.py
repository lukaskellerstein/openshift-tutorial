"""
L3-M4.3 -- Continuous Learning Patterns
Feedback collection service: FastAPI application for collecting user feedback
on model predictions and storing it for retraining.

Endpoints:
  POST /feedback       -- Submit user feedback (prediction_id, rating, correction)
  GET  /feedback/stats -- Return aggregate feedback statistics
  GET  /feedback/export -- Export feedback as JSON Lines (for pipeline consumption)
  GET  /health         -- Health check

Storage:
  Feedback is stored as JSON Lines in a local file (mounted via PVC in
  production). Each line is a self-contained JSON object.

Usage:
  # Run locally for testing
  pip install fastapi uvicorn
  python feedback_collector.py

  # Or with uvicorn directly
  uvicorn feedback_collector:app --host 0.0.0.0 --port 8080

  # Submit feedback via curl
  curl -X POST http://localhost:8080/feedback \\
    -H "Content-Type: application/json" \\
    -d '{"prediction_id": "pred-001", "model_version": "v1.0", "rating": 4}'

  # Check stats
  curl http://localhost:8080/feedback/stats

  # Export feedback (for pipeline consumption)
  curl "http://localhost:8080/feedback/export?since=2025-01-01T00:00:00Z"

Expected output (POST /feedback):
  {"status": "ok", "feedback_id": "fb-20250115-001"}

Expected output (GET /feedback/stats):
  {
    "total_feedback": 42,
    "average_rating": 3.7,
    "correction_rate": 0.23,
    "rating_distribution": {"1": 5, "2": 3, "3": 8, "4": 14, "5": 12},
    "earliest": "2025-01-01T10:00:00Z",
    "latest": "2025-01-15T14:30:00Z"
  }
"""

import json
import logging
import os
import threading
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = os.environ.get("FEEDBACK_DATA_DIR", "/data/feedback")
FEEDBACK_FILE = os.path.join(DATA_DIR, "feedback.jsonl")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Thread lock for file writes (FastAPI is async but file I/O is blocking)
_write_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class FeedbackRequest(BaseModel):
    """Schema for incoming feedback submissions."""

    prediction_id: str = Field(
        ..., description="Unique identifier for the prediction being rated"
    )
    model_version: str = Field(
        default="unknown", description="Version of the model that made the prediction"
    )
    rating: int = Field(
        ..., ge=1, le=5, description="User rating from 1 (bad) to 5 (excellent)"
    )
    correction: Optional[str] = Field(
        default=None,
        description="User-provided correction if the prediction was wrong",
    )
    input_text: Optional[str] = Field(
        default=None, description="The original input that was sent to the model"
    )
    prediction: Optional[str] = Field(
        default=None, description="The model's prediction/output"
    )
    timestamp: Optional[str] = Field(
        default=None,
        description="ISO 8601 timestamp. Auto-generated if not provided.",
    )
    metadata: Optional[dict] = Field(
        default=None, description="Additional metadata (user_id, session_id, etc.)"
    )


class FeedbackResponse(BaseModel):
    """Schema for feedback submission response."""

    status: str
    feedback_id: str


class FeedbackStats(BaseModel):
    """Schema for aggregate feedback statistics."""

    total_feedback: int
    average_rating: float
    correction_rate: float
    rating_distribution: dict
    earliest: Optional[str]
    latest: Optional[str]


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Feedback Collector",
    description="Collects user feedback on model predictions for continuous learning",
    version="1.0.0",
)


def _ensure_data_dir():
    """Create the data directory if it does not exist."""
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)


def _load_all_feedback() -> list[dict]:
    """Load all feedback entries from the JSON Lines file."""
    entries = []
    if not os.path.exists(FEEDBACK_FILE):
        return entries
    with open(FEEDBACK_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning(f"Skipping malformed feedback line: {line[:80]}")
    return entries


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
def health_check():
    """Health check endpoint for Kubernetes liveness/readiness probes."""
    return {"status": "healthy", "service": "feedback-collector"}


@app.post("/feedback", response_model=FeedbackResponse)
def submit_feedback(feedback: FeedbackRequest):
    """Accept user feedback on a model prediction.

    Each feedback entry is appended to the JSON Lines file as a single line.
    """
    _ensure_data_dir()

    # Generate a unique feedback ID
    now = datetime.now(timezone.utc)
    feedback_id = f"fb-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"

    # Build the storage record
    record = {
        "feedback_id": feedback_id,
        "prediction_id": feedback.prediction_id,
        "model_version": feedback.model_version,
        "rating": feedback.rating,
        "correction": feedback.correction,
        "input_text": feedback.input_text,
        "prediction": feedback.prediction,
        "timestamp": feedback.timestamp or now.isoformat(),
        "metadata": feedback.metadata,
        "received_at": now.isoformat(),
    }

    # Append to file (thread-safe)
    with _write_lock:
        with open(FEEDBACK_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")

    logger.info(
        f"Recorded feedback {feedback_id}: prediction={feedback.prediction_id}, "
        f"rating={feedback.rating}, has_correction={feedback.correction is not None}"
    )

    # --- Optional: Log to MLflow ---
    # If MLflow is available, also log the assessment for tracking:
    #
    #   import mlflow
    #   mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI"))
    #   with mlflow.start_run(run_name=f"feedback-{feedback_id}"):
    #       mlflow.log_assessment(
    #           evaluation_id=feedback.prediction_id,
    #           source=mlflow.entities.AssessmentSource(
    #               source_type="HUMAN",
    #               source_id=feedback.metadata.get("user_id", "anonymous"),
    #           ),
    #           boolean_value=feedback.rating >= 4,
    #           rationale=feedback.correction,
    #       )

    return FeedbackResponse(status="ok", feedback_id=feedback_id)


@app.get("/feedback/stats", response_model=FeedbackStats)
def feedback_stats():
    """Return aggregate statistics about collected feedback."""
    entries = _load_all_feedback()

    if not entries:
        return FeedbackStats(
            total_feedback=0,
            average_rating=0.0,
            correction_rate=0.0,
            rating_distribution={},
            earliest=None,
            latest=None,
        )

    ratings = [e.get("rating", 0) for e in entries]
    corrections = sum(1 for e in entries if e.get("correction"))
    timestamps = sorted(
        [e.get("timestamp", "") for e in entries if e.get("timestamp")]
    )

    rating_dist = dict(Counter(str(r) for r in ratings))

    return FeedbackStats(
        total_feedback=len(entries),
        average_rating=round(sum(ratings) / len(ratings), 2) if ratings else 0.0,
        correction_rate=round(corrections / len(entries), 2) if entries else 0.0,
        rating_distribution=rating_dist,
        earliest=timestamps[0] if timestamps else None,
        latest=timestamps[-1] if timestamps else None,
    )


@app.get("/feedback/export", response_class=PlainTextResponse)
def export_feedback(
    since: Optional[str] = Query(
        default=None,
        description="ISO 8601 timestamp. Only export feedback after this time.",
    ),
    format: str = Query(
        default="jsonl",
        description="Export format. Currently only 'jsonl' is supported.",
    ),
):
    """Export feedback entries as JSON Lines for pipeline consumption.

    Optionally filter by timestamp to only get feedback since the last
    training run.
    """
    entries = _load_all_feedback()

    if since:
        entries = [
            e for e in entries
            if e.get("timestamp", "") >= since
        ]

    if format != "jsonl":
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {format}. Use 'jsonl'.",
        )

    lines = [json.dumps(e) for e in entries]
    return "\n".join(lines) + "\n" if lines else ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    logger.info(f"Starting feedback collector on port {port}")
    logger.info(f"Data directory: {DATA_DIR}")
    uvicorn.run(app, host="0.0.0.0", port=port)
