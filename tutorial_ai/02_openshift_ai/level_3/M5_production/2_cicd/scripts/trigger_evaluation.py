#!/usr/bin/env python3
"""Trigger a KFP evaluation pipeline and wait for results.

This script bridges Tekton and Kubeflow Pipelines.  It is called by the
trigger-evaluation Tekton Task as part of the AI CI/CD pipeline
(L3-M5.2).

The script:
  1. Connects to the KFP API endpoint.
  2. Finds the evaluation pipeline by name.
  3. Creates a PipelineRun with the model endpoint and dataset as
     parameters.
  4. Polls the run until completion or timeout.
  5. Extracts the primary evaluation score.
  6. Writes results to a JSON file for downstream Tekton tasks.

Usage:
  python3 trigger_evaluation.py \
    --endpoint https://gemma-4-e4b.ai-workloads-prod.svc.cluster.local/v1 \
    --dataset default-eval-set \
    --kfp-endpoint https://ds-pipeline-dspa.redhat-ods-applications.svc.cluster.local:8443 \
    --pipeline-name model-evaluation-pipeline \
    --output-file /tmp/eval-results.json

Exit codes:
  0 -- Evaluation completed successfully (check output for score)
  1 -- Evaluation failed, timed out, or encountered an error
"""

import argparse
import json
import sys
import time
from datetime import datetime


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Trigger a KFP evaluation pipeline and wait for results."
    )
    parser.add_argument(
        "--endpoint",
        required=True,
        help="URL of the model inference endpoint to evaluate",
    )
    parser.add_argument(
        "--dataset",
        default="default-eval-set",
        help="Name or path of the evaluation dataset (default: default-eval-set)",
    )
    parser.add_argument(
        "--kfp-endpoint",
        default="https://ds-pipeline-dspa.redhat-ods-applications.svc.cluster.local:8443",
        help="Kubeflow Pipelines API endpoint URL",
    )
    parser.add_argument(
        "--pipeline-name",
        default="model-evaluation-pipeline",
        help="Name of the KFP evaluation pipeline to trigger",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=30,
        help="Seconds between status polls (default: 30)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Maximum seconds to wait for evaluation (default: 1800 = 30 min)",
    )
    parser.add_argument(
        "--output-file",
        default="/tmp/eval-results.json",
        help="Path to write evaluation results JSON",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Optional threshold -- if set, exit 1 when score is below this value",
    )
    return parser.parse_args()


def connect_to_kfp(endpoint: str):
    """Connect to the KFP API and return a client.

    Uses the kfp SDK.  In OpenShift AI, the Data Science Pipelines
    Application (DSPA) provides the KFP-compatible API.  The endpoint
    is typically the in-cluster service URL.
    """
    try:
        from kfp import client as kfp_client
    except ImportError:
        print("ERROR: kfp package not installed.  Run: pip install kfp", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to KFP at {endpoint}...")

    # When running inside the cluster, use the service account token
    # for authentication.  The DSPA endpoint uses mTLS in production.
    kfp_c = kfp_client.Client(
        host=endpoint,
        existing_token=_get_service_account_token(),
        ssl_ca_cert="/var/run/secrets/kubernetes.io/serviceaccount/ca.crt",
    )
    print("Connected to KFP API.")
    return kfp_c


def _get_service_account_token() -> str:
    """Read the pod's service account token for KFP authentication."""
    token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    try:
        with open(token_path) as f:
            return f.read().strip()
    except FileNotFoundError:
        # Running outside the cluster (local testing) -- return empty
        print("WARNING: No service account token found.  Running outside cluster?")
        return ""


def find_pipeline(kfp_c, pipeline_name: str):
    """Find a pipeline by name and return its ID.

    Raises SystemExit if the pipeline is not found.
    """
    print(f"Looking for pipeline: {pipeline_name}...")
    pipelines = kfp_c.list_pipelines(filter=f'name="{pipeline_name}"')

    if pipelines.pipelines is None or len(pipelines.pipelines) == 0:
        print(f"ERROR: Pipeline '{pipeline_name}' not found in KFP.", file=sys.stderr)
        print("Available pipelines:", file=sys.stderr)
        all_pipelines = kfp_c.list_pipelines()
        if all_pipelines.pipelines:
            for p in all_pipelines.pipelines:
                print(f"  - {p.name} (ID: {p.id})", file=sys.stderr)
        sys.exit(1)

    pipeline = pipelines.pipelines[0]
    print(f"Found pipeline: {pipeline.name} (ID: {pipeline.id})")
    return pipeline.id


def create_run(kfp_c, pipeline_id: str, endpoint: str, dataset: str) -> str:
    """Create a KFP PipelineRun and return its run ID.

    Passes the model endpoint and evaluation dataset as pipeline
    parameters.  The evaluation pipeline is expected to accept these
    parameters and produce metrics.
    """
    run_name = f"eval-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
    print(f"Creating PipelineRun: {run_name}...")

    run = kfp_c.create_run_from_pipeline_id(
        pipeline_id=pipeline_id,
        run_name=run_name,
        params={
            "model_endpoint": endpoint,
            "eval_dataset": dataset,
        },
    )

    run_id = run.run_id
    print(f"PipelineRun created: {run_id}")
    return run_id


def wait_for_completion(kfp_c, run_id: str, poll_interval: int, timeout: int) -> dict:
    """Poll the KFP run until it completes or times out.

    Returns the run details on success.
    Calls sys.exit(1) on failure or timeout.
    """
    start_time = time.time()
    terminal_states = {"SUCCEEDED", "FAILED", "ERROR", "SKIPPED", "CANCELED"}

    print(f"Waiting for run {run_id} (timeout: {timeout}s, poll: {poll_interval}s)...")

    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout:
            print(f"ERROR: Evaluation timed out after {timeout}s.", file=sys.stderr)
            sys.exit(1)

        run = kfp_c.get_run(run_id)
        status = run.status or "UNKNOWN"

        remaining = int(timeout - elapsed)
        print(f"  Status: {status} (elapsed: {int(elapsed)}s, remaining: {remaining}s)")

        if status.upper() in terminal_states:
            if status.upper() == "SUCCEEDED":
                print(f"Run completed successfully in {int(elapsed)}s.")
                return run
            else:
                print(f"ERROR: Run finished with status: {status}", file=sys.stderr)
                sys.exit(1)

        time.sleep(poll_interval)


def extract_metrics(kfp_c, run_id: str) -> dict:
    """Extract evaluation metrics from a completed KFP run.

    The evaluation pipeline is expected to produce metrics as run
    artifacts.  This function reads the primary score from the run
    metrics.

    If metrics cannot be extracted (e.g., the pipeline does not produce
    standard KFP metrics), this function returns a placeholder score
    with a warning.
    """
    print("Extracting evaluation metrics...")

    try:
        # Attempt to read metrics from the KFP run artifacts
        run = kfp_c.get_run(run_id)

        # KFP v2 stores metrics as artifacts.  The evaluation pipeline
        # should output a "metrics" artifact with a "primary_score" key.
        # This is a simplified extraction -- production pipelines would
        # use the KFP metrics API.
        metrics = {}
        if hasattr(run, "metrics") and run.metrics:
            for metric in run.metrics:
                metrics[metric.name] = metric.number_value

        if "primary_score" in metrics:
            return {
                "primary_score": metrics["primary_score"],
                "all_metrics": metrics,
            }

        # Fallback: try to read from run parameters/outputs
        print("WARNING: Could not extract structured metrics from run.")
        print("  Returning default score.  Configure your evaluation pipeline")
        print("  to output a 'primary_score' metric for production use.")
        return {
            "primary_score": 0.0,
            "all_metrics": {},
            "warning": "Metrics not found -- using default score",
        }

    except Exception as e:
        print(f"WARNING: Error extracting metrics: {e}", file=sys.stderr)
        return {
            "primary_score": 0.0,
            "all_metrics": {},
            "error": str(e),
        }


def write_results(output_file: str, run_id: str, metrics: dict) -> None:
    """Write evaluation results to a JSON file.

    The output format is consumed by downstream Tekton tasks
    (check-quality-gate, register-model-version).
    """
    results = {
        "run_id": run_id,
        "primary_score": metrics["primary_score"],
        "all_metrics": metrics.get("all_metrics", {}),
        "timestamp": datetime.utcnow().isoformat(),
    }

    if "warning" in metrics:
        results["warning"] = metrics["warning"]
    if "error" in metrics:
        results["error"] = metrics["error"]

    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Results written to {output_file}")
    print(f"  Run ID:        {run_id}")
    print(f"  Primary Score: {metrics['primary_score']:.4f}")


def main() -> None:
    """Main entry point."""
    args = parse_args()

    # 1. Connect to KFP
    kfp_c = connect_to_kfp(args.kfp_endpoint)

    # 2. Find the evaluation pipeline
    pipeline_id = find_pipeline(kfp_c, args.pipeline_name)

    # 3. Create a PipelineRun
    run_id = create_run(kfp_c, pipeline_id, args.endpoint, args.dataset)

    # 4. Wait for completion
    wait_for_completion(kfp_c, run_id, args.poll_interval, args.timeout)

    # 5. Extract metrics
    metrics = extract_metrics(kfp_c, run_id)

    # 6. Write results
    write_results(args.output_file, run_id, metrics)

    # 7. Optional threshold check
    if args.threshold is not None:
        score = metrics["primary_score"]
        if score < args.threshold:
            print(f"FAILED: Score {score:.4f} is below threshold {args.threshold:.4f}")
            sys.exit(1)
        else:
            print(f"PASSED: Score {score:.4f} meets threshold {args.threshold:.4f}")

    print("Evaluation trigger complete.")


if __name__ == "__main__":
    main()
