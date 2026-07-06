"""
L3-M4.3 -- Continuous Learning Patterns
Drift monitor: tracks model quality metrics over rolling time windows
and triggers a retraining pipeline run when degradation exceeds thresholds.

This script is designed to run as either:
  - A periodic CronJob (e.g., hourly) that checks metrics and exits
  - A manual check to inspect current model quality

It queries the feedback service for recent feedback, calculates rolling
quality metrics, and compares them against configurable thresholds.

Usage:
  # Dry run (report only, do not trigger pipeline)
  python drift_monitor.py \\
    --feedback-url http://feedback-service:8080 \\
    --window-days 7 \\
    --accuracy-threshold 0.85 \\
    --dry-run

  # Full run (trigger pipeline if drift detected)
  python drift_monitor.py \\
    --feedback-url http://feedback-service:8080 \\
    --window-days 7 \\
    --accuracy-threshold 0.85 \\
    --negative-rate-threshold 0.15 \\
    --min-samples 50 \\
    --pipeline-server https://ds-pipeline-dspa-myproject.apps.cluster.com

Expected output (no drift):
  === Drift Monitor Report ===
  Time window:         7 days (2025-01-08 to 2025-01-15)
  Total feedback:      127
  Average rating:      4.2 / 5.0
  Rolling accuracy:    0.89 (threshold: 0.85)
  Negative rate:       0.08 (threshold: 0.15)
  Confidence trend:    stable

  Status: NO DRIFT DETECTED
  No retraining needed at this time.

Expected output (drift detected):
  === Drift Monitor Report ===
  Time window:         7 days (2025-01-08 to 2025-01-15)
  Total feedback:      203
  Average rating:      2.8 / 5.0
  Rolling accuracy:    0.71 (threshold: 0.85)
  Negative rate:       0.24 (threshold: 0.15)
  Confidence trend:    declining (-12% over window)

  Status: DRIFT DETECTED
  Breached thresholds:
    - Rolling accuracy: 0.71 < 0.85
    - Negative rate: 0.24 > 0.15

  Action: Triggering retraining pipeline...
  Pipeline run submitted: continuous-learning-drift-triggered-20250115
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import requests


def fetch_feedback(feedback_url: str, since: str) -> list[dict]:
    """Fetch feedback entries from the feedback service since a given timestamp."""
    response = requests.get(
        f"{feedback_url}/feedback/export",
        params={"since": since, "format": "jsonl"},
        timeout=30,
    )
    response.raise_for_status()

    entries = []
    for line in response.text.strip().split("\n"):
        if line.strip():
            entries.append(json.loads(line))
    return entries


def calculate_metrics(entries: list[dict]) -> dict:
    """Calculate rolling quality metrics from feedback entries.

    Returns a dictionary with:
      - total: number of entries
      - average_rating: mean rating (1-5)
      - rolling_accuracy: proportion of positive ratings (>= 4)
      - negative_rate: proportion of negative ratings (<= 2)
      - correction_rate: proportion of entries with corrections
      - confidence_trend: "stable", "improving", or "declining" based on
        comparing the first half of the window to the second half
    """
    if not entries:
        return {
            "total": 0,
            "average_rating": 0.0,
            "rolling_accuracy": 0.0,
            "negative_rate": 0.0,
            "correction_rate": 0.0,
            "confidence_trend": "unknown",
            "trend_delta": 0.0,
        }

    ratings = [e.get("rating", 3) for e in entries]
    total = len(ratings)

    average_rating = sum(ratings) / total
    positive_count = sum(1 for r in ratings if r >= 4)
    negative_count = sum(1 for r in ratings if r <= 2)
    corrections = sum(1 for e in entries if e.get("correction"))

    rolling_accuracy = positive_count / total
    negative_rate = negative_count / total
    correction_rate = corrections / total

    # Calculate trend by comparing first half to second half of the window
    midpoint = total // 2
    if midpoint > 0:
        first_half_avg = sum(ratings[:midpoint]) / midpoint
        second_half_avg = sum(ratings[midpoint:]) / (total - midpoint)
        trend_delta = (second_half_avg - first_half_avg) / first_half_avg * 100

        if trend_delta > 5:
            confidence_trend = "improving"
        elif trend_delta < -5:
            confidence_trend = "declining"
        else:
            confidence_trend = "stable"
    else:
        confidence_trend = "unknown"
        trend_delta = 0.0

    return {
        "total": total,
        "average_rating": round(average_rating, 2),
        "rolling_accuracy": round(rolling_accuracy, 4),
        "negative_rate": round(negative_rate, 4),
        "correction_rate": round(correction_rate, 4),
        "confidence_trend": confidence_trend,
        "trend_delta": round(trend_delta, 1),
    }


def check_thresholds(
    metrics: dict,
    accuracy_threshold: float,
    negative_rate_threshold: float,
) -> list[str]:
    """Check if any metrics breach their thresholds.

    Returns a list of breach descriptions. Empty list means no drift.
    """
    breaches = []

    if metrics["rolling_accuracy"] < accuracy_threshold:
        breaches.append(
            f"Rolling accuracy: {metrics['rolling_accuracy']:.4f} < {accuracy_threshold:.4f}"
        )

    if metrics["negative_rate"] > negative_rate_threshold:
        breaches.append(
            f"Negative rate: {metrics['negative_rate']:.4f} > {negative_rate_threshold:.4f}"
        )

    return breaches


def trigger_pipeline(
    pipeline_server: str,
    pipeline_name: str = "continuous-learning-pipeline",
) -> str:
    """Trigger a retraining pipeline run via the KFP API.

    Returns the run ID of the submitted pipeline run.
    """
    # Get auth token from the cluster
    try:
        token = subprocess.check_output(
            ["oc", "whoami", "-t"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise RuntimeError(
            "Could not get auth token. Ensure 'oc' is installed and you are logged in."
        )

    from kfp.client import Client

    client = Client(
        host=pipeline_server,
        existing_token=token,
    )

    now = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_name = f"continuous-learning-drift-triggered-{now}"

    run = client.create_run_from_pipeline_package(
        pipeline_file="continuous_learning_pipeline.yaml",
        arguments={
            "feedback_service_url": (
                "http://feedback-service."
                "continuous-learning-tutorial.svc.cluster.local:8080"
            ),
            "model_name": "granite-3b-product-classifier",
            "replay_ratio": 0.7,
            "min_feedback_count": 10,
            "improvement_threshold": 0.01,
        },
        run_name=run_name,
        experiment_name="continuous-learning",
    )

    return run.run_id


def print_report(
    metrics: dict,
    window_days: int,
    accuracy_threshold: float,
    negative_rate_threshold: float,
    breaches: list[str],
):
    """Print a formatted drift monitoring report."""
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=window_days)

    print("=== Drift Monitor Report ===")
    print(
        f"Time window:         {window_days} days "
        f"({window_start.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')})"
    )
    print(f"Total feedback:      {metrics['total']}")
    print(f"Average rating:      {metrics['average_rating']} / 5.0")
    print(
        f"Rolling accuracy:    {metrics['rolling_accuracy']:.2f} "
        f"(threshold: {accuracy_threshold:.2f})"
    )
    print(
        f"Negative rate:       {metrics['negative_rate']:.2f} "
        f"(threshold: {negative_rate_threshold:.2f})"
    )

    trend_str = metrics["confidence_trend"]
    if metrics["trend_delta"] != 0:
        trend_str += f" ({metrics['trend_delta']:+.0f}% over window)"
    print(f"Confidence trend:    {trend_str}")

    print()

    if breaches:
        print("Status: DRIFT DETECTED")
        print("Breached thresholds:")
        for breach in breaches:
            print(f"  - {breach}")
    else:
        print("Status: NO DRIFT DETECTED")
        print("No retraining needed at this time.")


def main():
    parser = argparse.ArgumentParser(
        description="Monitor model quality drift and trigger retraining"
    )
    parser.add_argument(
        "--feedback-url",
        required=True,
        help="URL of the feedback collection service",
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=7,
        help="Rolling window size in days (default: 7)",
    )
    parser.add_argument(
        "--accuracy-threshold",
        type=float,
        default=0.85,
        help="Minimum acceptable rolling accuracy (default: 0.85)",
    )
    parser.add_argument(
        "--negative-rate-threshold",
        type=float,
        default=0.15,
        help="Maximum acceptable negative feedback rate (default: 0.15)",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=50,
        help="Minimum feedback entries in window before triggering (default: 50)",
    )
    parser.add_argument(
        "--pipeline-server",
        default=None,
        help="KFP pipeline server URL (required unless --dry-run)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report only, do not trigger pipeline even if drift is detected",
    )

    args = parser.parse_args()

    # Calculate the time window
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=args.window_days)).isoformat()

    # Fetch feedback within the window
    try:
        entries = fetch_feedback(args.feedback_url, since)
    except requests.RequestException as e:
        print(f"ERROR: Could not fetch feedback from {args.feedback_url}: {e}")
        sys.exit(1)

    # Calculate metrics
    metrics = calculate_metrics(entries)

    # Check thresholds
    breaches = check_thresholds(
        metrics,
        args.accuracy_threshold,
        args.negative_rate_threshold,
    )

    # Print report
    print_report(
        metrics,
        args.window_days,
        args.accuracy_threshold,
        args.negative_rate_threshold,
        breaches,
    )

    # Decide whether to trigger retraining
    if not breaches:
        sys.exit(0)

    if metrics["total"] < args.min_samples:
        print()
        print(
            f"Note: Only {metrics['total']} samples in window "
            f"(minimum: {args.min_samples}). "
            f"Drift detected but not enough data to be confident. "
            f"Skipping pipeline trigger."
        )
        sys.exit(0)

    if args.dry_run:
        print()
        print("Dry run mode: would trigger retraining pipeline but --dry-run is set.")
        sys.exit(0)

    if not args.pipeline_server:
        print()
        print(
            "ERROR: --pipeline-server is required to trigger retraining. "
            "Use --dry-run for report-only mode."
        )
        sys.exit(1)

    # Trigger the retraining pipeline
    print()
    print("Action: Triggering retraining pipeline...")
    try:
        run_id = trigger_pipeline(args.pipeline_server)
        print(f"Pipeline run submitted: {run_id}")
    except Exception as e:
        print(f"ERROR: Failed to trigger pipeline: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
