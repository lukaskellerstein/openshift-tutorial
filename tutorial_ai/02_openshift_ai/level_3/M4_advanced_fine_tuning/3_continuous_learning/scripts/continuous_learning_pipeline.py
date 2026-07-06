"""
L3-M4.3 -- Continuous Learning Patterns
KFP v2 pipeline: feedback collection -> data curation -> retrain -> evaluate -> promote

This pipeline implements the five-stage continuous learning loop:
  1. collect_feedback   -- Query stored feedback since the last training run
  2. curate_training_data -- Filter, deduplicate, combine with replay buffer
  3. retrain_model      -- Fine-tune using LoRA on the curated dataset
  4. evaluate_model     -- Compare new model against current production model
  5. promote_model      -- Conditionally register and promote if metrics improve

Usage:
  # Compile to YAML
  python continuous_learning_pipeline.py --compile-only

  # Compile and submit
  python continuous_learning_pipeline.py
"""

from kfp import compiler, dsl
from kfp.dsl import Dataset, Input, Metrics, Model, Output


# ---------------------------------------------------------------------------
# Component 1: Collect Feedback
# ---------------------------------------------------------------------------
@dsl.component(
    base_image="python:3.11-slim",
    packages_to_install=["requests==2.32.3"],
)
def collect_feedback(
    feedback_service_url: str,
    min_feedback_count: int,
    feedback_out: Output[Dataset],
) -> int:
    """Query the feedback service for entries since the last training run.

    Returns the number of feedback entries collected. If fewer than
    min_feedback_count entries are available, the pipeline should stop
    (checked by downstream components).
    """
    import json

    import requests

    # Export all feedback from the service
    response = requests.get(
        f"{feedback_service_url}/feedback/export",
        params={"format": "jsonl"},
        timeout=30,
    )
    response.raise_for_status()

    feedback_entries = []
    for line in response.text.strip().split("\n"):
        if line.strip():
            feedback_entries.append(json.loads(line))

    total = len(feedback_entries)
    print(f"Collected {total} feedback entries")
    print(f"Minimum required: {min_feedback_count}")

    if total < min_feedback_count:
        print(
            f"WARNING: Only {total} entries available, below minimum "
            f"of {min_feedback_count}. Pipeline will skip retraining."
        )

    # Write feedback to output artifact as JSON Lines
    with open(feedback_out.path, "w") as f:
        for entry in feedback_entries:
            f.write(json.dumps(entry) + "\n")

    feedback_out.metadata["total_entries"] = str(total)
    feedback_out.metadata["source"] = feedback_service_url

    # Count entries with corrections (these are highest-signal training data)
    corrections = sum(1 for e in feedback_entries if e.get("correction"))
    print(f"Entries with corrections: {corrections}")
    feedback_out.metadata["correction_count"] = str(corrections)

    return total


# ---------------------------------------------------------------------------
# Component 2: Curate Training Data
# ---------------------------------------------------------------------------
@dsl.component(
    base_image="python:3.11-slim",
    packages_to_install=["numpy==1.26.4"],
)
def curate_training_data(
    raw_feedback: Input[Dataset],
    replay_ratio: float,
    feedback_count: int,
    min_feedback_count: int,
    curated_out: Output[Dataset],
    curation_metrics: Output[Metrics],
) -> bool:
    """Filter, deduplicate, and combine feedback with a replay buffer.

    The replay buffer mixes original training data with new feedback to
    prevent catastrophic forgetting. replay_ratio controls the proportion
    of original data (e.g., 0.7 = 70% original, 30% new).

    Returns True if there is enough curated data to proceed with retraining.
    """
    import hashlib
    import json

    import numpy as np

    if feedback_count < min_feedback_count:
        print(
            f"Insufficient feedback ({feedback_count} < {min_feedback_count}). "
            f"Skipping curation."
        )
        # Write empty dataset
        with open(curated_out.path, "w") as f:
            pass
        curation_metrics.log_metric("curated_count", 0)
        curation_metrics.log_metric("skipped", 1)
        return False

    # Load raw feedback
    entries = []
    with open(raw_feedback.path, "r") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))

    print(f"Loaded {len(entries)} raw feedback entries")

    # --- Step 1: Filter ---
    # Keep only entries with clear signal (rating <= 2 or rating >= 4)
    # Ratings of 3 are ambiguous and add noise
    filtered = [
        e for e in entries
        if e.get("rating", 3) <= 2 or e.get("rating", 3) >= 4
    ]
    print(f"After filtering ambiguous ratings: {len(filtered)} entries")

    # --- Step 2: Deduplicate ---
    # Use prediction_id to remove duplicates (keep the latest)
    seen = {}
    for entry in filtered:
        pid = entry.get("prediction_id", "")
        key = hashlib.md5(pid.encode()).hexdigest()
        # Keep the latest entry for each prediction
        if key not in seen or entry.get("timestamp", "") > seen[key].get("timestamp", ""):
            seen[key] = entry
    deduped = list(seen.values())
    print(f"After deduplication: {len(deduped)} entries")

    # --- Step 3: Quality scoring ---
    # Entries with corrections are highest signal (weight = 2.0)
    # Entries with extreme ratings (1 or 5) are high signal (weight = 1.5)
    # Other clear ratings (2 or 4) are standard signal (weight = 1.0)
    for entry in deduped:
        rating = entry.get("rating", 3)
        if entry.get("correction"):
            entry["quality_weight"] = 2.0
        elif rating in (1, 5):
            entry["quality_weight"] = 1.5
        else:
            entry["quality_weight"] = 1.0

    # --- Step 4: Format as training data ---
    # Convert feedback into instruction/response pairs for LoRA fine-tuning
    training_examples = []
    for entry in deduped:
        if entry.get("correction"):
            # Use the correction as the desired response
            example = {
                "instruction": entry.get("input_text", entry.get("prediction_id", "")),
                "response": entry["correction"],
                "weight": entry["quality_weight"],
                "source": "user_correction",
            }
        elif entry.get("rating", 3) >= 4:
            # Positive feedback -- reinforce the original prediction
            example = {
                "instruction": entry.get("input_text", entry.get("prediction_id", "")),
                "response": entry.get("prediction", ""),
                "weight": entry["quality_weight"],
                "source": "positive_feedback",
            }
        else:
            # Negative feedback without correction -- skip (no target to train on)
            continue
        training_examples.append(example)

    print(f"Formatted {len(training_examples)} training examples from feedback")

    # --- Step 5: Merge with replay buffer ---
    # In a real system, the replay buffer would be loaded from the previous
    # training dataset stored in S3/PVC. Here we simulate it.
    rng = np.random.default_rng(seed=42)

    # Calculate sizes based on replay_ratio
    total_size = max(len(training_examples) * 2, 100)  # at least 100 examples
    n_replay = int(total_size * replay_ratio)
    n_new = total_size - n_replay

    # Sample new examples (with replacement if needed)
    if len(training_examples) > 0:
        new_indices = rng.choice(
            len(training_examples),
            size=min(n_new, len(training_examples)),
            replace=False,
        )
        new_examples = [training_examples[i] for i in new_indices]
    else:
        new_examples = []

    # Simulate replay buffer (in production, load from previous training data)
    replay_examples = [
        {
            "instruction": f"replay_example_{i}",
            "response": f"original_response_{i}",
            "weight": 1.0,
            "source": "replay_buffer",
        }
        for i in range(n_replay)
    ]

    curated = new_examples + replay_examples
    rng.shuffle(curated)

    print(f"Final curated dataset: {len(curated)} examples")
    print(f"  New feedback: {len(new_examples)} ({100 * len(new_examples) / max(len(curated), 1):.0f}%)")
    print(f"  Replay buffer: {len(replay_examples)} ({100 * len(replay_examples) / max(len(curated), 1):.0f}%)")

    # Write curated dataset
    with open(curated_out.path, "w") as f:
        for example in curated:
            f.write(json.dumps(example) + "\n")

    # Log curation metrics
    curation_metrics.log_metric("raw_count", len(entries))
    curation_metrics.log_metric("filtered_count", len(filtered))
    curation_metrics.log_metric("deduped_count", len(deduped))
    curation_metrics.log_metric("curated_count", len(curated))
    curation_metrics.log_metric("new_examples", len(new_examples))
    curation_metrics.log_metric("replay_examples", len(replay_examples))
    curation_metrics.log_metric("replay_ratio", replay_ratio)
    curation_metrics.log_metric("skipped", 0)

    curated_out.metadata["total_examples"] = str(len(curated))
    curated_out.metadata["replay_ratio"] = str(replay_ratio)

    return True


# ---------------------------------------------------------------------------
# Component 3: Retrain Model
# ---------------------------------------------------------------------------
@dsl.component(
    base_image="python:3.11-slim",
    packages_to_install=["requests==2.32.3"],
)
def retrain_model(
    curated_data: Input[Dataset],
    model_name: str,
    should_retrain: bool,
    retrained_model: Output[Model],
    training_metrics: Output[Metrics],
) -> str:
    """Fine-tune the model using LoRA on the curated dataset.

    In a production system, this component would:
    1. Upload the curated dataset to S3
    2. Create a Training Hub FineTuningJob CR via the API
    3. Wait for training to complete
    4. Download the trained adapter weights

    Returns the path to the retrained model artifacts, or an empty string
    if retraining was skipped.
    """
    import json
    import os

    if not should_retrain:
        print("Retraining skipped: insufficient curated data")
        training_metrics.log_metric("skipped", 1)
        training_metrics.log_metric("epochs", 0)
        with open(retrained_model.path, "w") as f:
            json.dump({"status": "skipped"}, f)
        return ""

    # Load curated data to verify
    examples = []
    with open(curated_data.path, "r") as f:
        for line in f:
            if line.strip():
                examples.append(json.loads(line))

    print(f"Retraining {model_name} on {len(examples)} curated examples")

    # --- In production, submit a Training Hub FineTuningJob ---
    # This would look like:
    #
    #   from openshift_ai import TrainingHubClient
    #   client = TrainingHubClient()
    #   job = client.create_fine_tuning_job(
    #       model=model_name,
    #       method="lora",
    #       dataset_path="s3://training-data/curated/latest.jsonl",
    #       hyperparameters={
    #           "num_epochs": 3,
    #           "learning_rate": 2e-5,
    #           "lora_rank": 16,
    #           "lora_alpha": 32,
    #           "batch_size": 4,
    #       },
    #   )
    #   job.wait_for_completion(timeout=3600)
    #
    # For this tutorial, we simulate the training output.

    # Simulate training metrics
    simulated_metrics = {
        "training_loss": 0.342,
        "validation_loss": 0.389,
        "num_epochs": 3,
        "learning_rate": 2e-5,
        "lora_rank": 16,
        "training_examples": len(examples),
        "training_time_seconds": 1200,
    }

    for key, value in simulated_metrics.items():
        training_metrics.log_metric(key, value)

    # Write simulated model output
    model_output = {
        "status": "completed",
        "model_name": model_name,
        "adapter_path": f"s3://models/{model_name}/adapters/latest",
        "base_model": model_name,
        "metrics": simulated_metrics,
    }

    with open(retrained_model.path, "w") as f:
        json.dump(model_output, f, indent=2)

    retrained_model.metadata["model_name"] = model_name
    retrained_model.metadata["method"] = "lora"
    retrained_model.metadata["status"] = "completed"

    print(f"Training completed:")
    print(f"  Loss: {simulated_metrics['training_loss']:.4f}")
    print(f"  Epochs: {simulated_metrics['num_epochs']}")
    print(f"  Time: {simulated_metrics['training_time_seconds']}s")

    return retrained_model.path


# ---------------------------------------------------------------------------
# Component 4: Evaluate Model
# ---------------------------------------------------------------------------
@dsl.component(
    base_image="python:3.11-slim",
    packages_to_install=["requests==2.32.3", "numpy==1.26.4"],
)
def evaluate_model(
    retrained_model: Input[Model],
    model_name: str,
    model_path: str,
    improvement_threshold: float,
    eval_metrics: Output[Metrics],
) -> bool:
    """Compare the retrained model against the current production model.

    Runs both models on a held-out test set and compares key metrics.
    Returns True if the new model meets the improvement threshold.

    In production, this would:
    1. Deploy the new model as a temporary InferenceService
    2. Run the held-out test set through both models
    3. Compare accuracy, latency, and safety metrics
    4. Optionally create an LMEvalJob for formal benchmarking
    """
    import json

    import numpy as np

    if not model_path:
        print("No model to evaluate (retraining was skipped)")
        eval_metrics.log_metric("skipped", 1)
        eval_metrics.log_metric("should_promote", 0)
        return False

    # Load model info
    with open(retrained_model.path, "r") as f:
        model_info = json.load(f)

    print(f"Evaluating retrained model: {model_info.get('model_name', 'unknown')}")

    # --- In production, run evaluation against both models ---
    # This would deploy the new model, run test data through both, and compare.
    #
    #   from openshift_ai import InferenceClient
    #   production_client = InferenceClient(model=model_name, version="production")
    #   candidate_client = InferenceClient(model=model_name, version="candidate")
    #
    #   for test_input in test_set:
    #       prod_output = production_client.predict(test_input)
    #       cand_output = candidate_client.predict(test_input)
    #       # Compare outputs against ground truth

    # Simulate evaluation results
    rng = np.random.default_rng(seed=42)

    production_accuracy = 0.85
    # New model is typically slightly better due to feedback incorporation
    new_accuracy = production_accuracy + rng.uniform(-0.02, 0.08)
    new_accuracy = min(new_accuracy, 0.99)

    production_latency_ms = 120.0
    new_latency_ms = production_latency_ms * rng.uniform(0.95, 1.10)

    improvement = new_accuracy - production_accuracy

    print(f"Production model accuracy: {production_accuracy:.4f}")
    print(f"New model accuracy:        {new_accuracy:.4f}")
    print(f"Improvement:               {improvement:+.4f}")
    print(f"Improvement threshold:     {improvement_threshold:.4f}")
    print(f"Production latency (ms):   {production_latency_ms:.1f}")
    print(f"New model latency (ms):    {new_latency_ms:.1f}")

    # Log all evaluation metrics
    eval_metrics.log_metric("production_accuracy", production_accuracy)
    eval_metrics.log_metric("new_accuracy", float(new_accuracy))
    eval_metrics.log_metric("improvement", float(improvement))
    eval_metrics.log_metric("improvement_threshold", improvement_threshold)
    eval_metrics.log_metric("production_latency_ms", production_latency_ms)
    eval_metrics.log_metric("new_latency_ms", float(new_latency_ms))

    # Decision: promote if improvement exceeds threshold AND latency does not
    # regress more than 20%
    latency_ok = new_latency_ms <= production_latency_ms * 1.20
    accuracy_ok = improvement >= improvement_threshold

    should_promote = accuracy_ok and latency_ok

    eval_metrics.log_metric("latency_ok", int(latency_ok))
    eval_metrics.log_metric("accuracy_ok", int(accuracy_ok))
    eval_metrics.log_metric("should_promote", int(should_promote))
    eval_metrics.log_metric("skipped", 0)

    if should_promote:
        print(f"PASS: New model meets promotion criteria")
    else:
        reasons = []
        if not accuracy_ok:
            reasons.append(
                f"accuracy improvement {improvement:+.4f} < threshold {improvement_threshold:.4f}"
            )
        if not latency_ok:
            reasons.append(
                f"latency {new_latency_ms:.1f}ms exceeds 120% of production ({production_latency_ms * 1.2:.1f}ms)"
            )
        print(f"FAIL: New model does not meet promotion criteria: {'; '.join(reasons)}")

    return should_promote


# ---------------------------------------------------------------------------
# Component 5: Promote Model
# ---------------------------------------------------------------------------
@dsl.component(
    base_image="python:3.11-slim",
    packages_to_install=["model-registry==0.2.10", "requests==2.32.3"],
)
def promote_model(
    retrained_model: Input[Model],
    model_name: str,
    should_promote: bool,
    promotion_metrics: Output[Metrics],
):
    """Register and promote the new model version in the Model Registry.

    If should_promote is False, this component logs the skip and exits.
    If True, it:
    1. Registers the new model version in the Model Registry
    2. Sets its state to LIVE
    3. Archives the previous production version
    """
    import json

    if not should_promote:
        print("Promotion skipped: evaluation criteria not met")
        promotion_metrics.log_metric("promoted", 0)
        promotion_metrics.log_metric("reason", "evaluation_failed")
        return

    # Load model info
    with open(retrained_model.path, "r") as f:
        model_info = json.load(f)

    if model_info.get("status") == "skipped":
        print("Promotion skipped: no retrained model available")
        promotion_metrics.log_metric("promoted", 0)
        promotion_metrics.log_metric("reason", "no_model")
        return

    print(f"Promoting model: {model_name}")

    # --- In production, register with the Model Registry ---
    #
    #   from model_registry import ModelRegistry
    #
    #   registry = ModelRegistry(
    #       server_address="https://model-registry-service:443",
    #       author="continuous-learning-pipeline",
    #   )
    #
    #   # Get or create the registered model
    #   reg_model = registry.get_registered_model(model_name)
    #
    #   # Register the new version
    #   version = registry.register_model_version(
    #       model=reg_model,
    #       version_name=f"v{next_version}",
    #       uri=model_info["adapter_path"],
    #       description="Auto-promoted by continuous learning pipeline",
    #       metadata={
    #           "training_method": "lora",
    #           "feedback_examples": model_info["metrics"]["training_examples"],
    #           "pipeline_run": os.environ.get("KFP_RUN_ID", "unknown"),
    #       },
    #   )
    #
    #   # Create a model artifact
    #   artifact = registry.register_model_artifact(
    #       model_version=version,
    #       uri=model_info["adapter_path"],
    #       model_format_name="pytorch",
    #       model_format_version="2.0",
    #   )
    #
    #   # Transition the new version to LIVE
    #   registry.update_model_version_state(version, "LIVE")
    #
    #   # Archive the previous production version
    #   # (find and update the currently LIVE version)

    # Simulate successful promotion
    print(f"Registered new version in Model Registry")
    print(f"  Model: {model_name}")
    print(f"  Adapter path: {model_info.get('adapter_path', 'N/A')}")
    print(f"  State: LIVE")
    print(f"  Previous version: ARCHIVED")

    promotion_metrics.log_metric("promoted", 1)
    promotion_metrics.log_metric("model_name", model_name)


# ---------------------------------------------------------------------------
# Pipeline Definition
# ---------------------------------------------------------------------------
@dsl.pipeline(
    name="continuous-learning-pipeline",
    description=(
        "Continuous learning loop: collect feedback, curate training data "
        "with replay buffer, retrain via LoRA, evaluate against production "
        "model, and promote if improved."
    ),
)
def continuous_learning_pipeline(
    feedback_service_url: str = "http://feedback-service:8080",
    model_name: str = "granite-3b-product-classifier",
    replay_ratio: float = 0.7,
    min_feedback_count: int = 10,
    improvement_threshold: float = 0.01,
):
    """Orchestrate the five-stage continuous learning loop.

    Args:
        feedback_service_url: URL of the feedback collection service.
        model_name: Name of the model to retrain (must exist in registry).
        replay_ratio: Proportion of original data in the training mix (0.0-1.0).
            Higher values preserve more of the original model behavior.
        min_feedback_count: Minimum feedback entries required to trigger
            retraining. Below this threshold, the pipeline exits early.
        improvement_threshold: Minimum accuracy improvement required for
            the new model to be promoted (e.g., 0.01 = 1% improvement).
    """
    # Stage 1: Collect feedback
    collect_task = collect_feedback(
        feedback_service_url=feedback_service_url,
        min_feedback_count=min_feedback_count,
    )

    # Stage 2: Curate training data
    curate_task = curate_training_data(
        raw_feedback=collect_task.outputs["feedback_out"],
        replay_ratio=replay_ratio,
        feedback_count=collect_task.output,
        min_feedback_count=min_feedback_count,
    )

    # Stage 3: Retrain model
    retrain_task = retrain_model(
        curated_data=curate_task.outputs["curated_out"],
        model_name=model_name,
        should_retrain=curate_task.output,
    )

    # Stage 4: Evaluate new model against production
    eval_task = evaluate_model(
        retrained_model=retrain_task.outputs["retrained_model"],
        model_name=model_name,
        model_path=retrain_task.output,
        improvement_threshold=improvement_threshold,
    )

    # Stage 5: Promote if evaluation passes
    promote_model(
        retrained_model=retrain_task.outputs["retrained_model"],
        model_name=model_name,
        should_promote=eval_task.output,
    )


# ---------------------------------------------------------------------------
# Compile and (optionally) Submit
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Compile or submit the continuous learning pipeline"
    )
    parser.add_argument(
        "--compile-only",
        action="store_true",
        help="Only compile, do not submit",
    )
    parser.add_argument(
        "--output",
        default="continuous_learning_pipeline.yaml",
        help="Output YAML path (default: continuous_learning_pipeline.yaml)",
    )
    args = parser.parse_args()

    # Compile
    compiler.Compiler().compile(
        pipeline_func=continuous_learning_pipeline,
        package_path=args.output,
    )
    print(f"Pipeline compiled to {args.output}")

    if args.compile_only:
        print("Compile-only mode -- skipping submission.")
    else:
        import subprocess

        from kfp.client import Client

        # Get the pipeline server route and auth token
        route = subprocess.check_output(
            [
                "oc", "get", "route", "ds-pipeline-dspa",
                "-n", "continuous-learning-tutorial",
                "-o", "jsonpath={.spec.host}",
            ],
        ).decode().strip()

        token = subprocess.check_output(
            ["oc", "whoami", "-t"],
        ).decode().strip()

        print(f"Connecting to pipeline server at https://{route}")

        client = Client(
            host=f"https://{route}",
            existing_token=token,
        )

        run = client.create_run_from_pipeline_package(
            pipeline_file=args.output,
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
            run_name="continuous-learning-run",
            experiment_name="continuous-learning",
        )

        print(f"Run submitted: {run.run_id}")
        print("View in dashboard: Data Science Projects > continuous-learning-tutorial > Runs")
