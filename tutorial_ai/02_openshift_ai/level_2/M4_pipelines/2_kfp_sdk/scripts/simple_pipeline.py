"""
L2-M4.2 -- Simple ML Pipeline with KFP v2 SDK

A 4-step pipeline demonstrating core KFP v2 concepts:
  1. fetch_data     -- generate synthetic classification data
  2. process_data   -- split into train/test sets
  3. train_model    -- train a RandomForest classifier, evaluate it
  4. log_results    -- print final model metadata and metrics

Usage:
  # Compile the pipeline to YAML
  python simple_pipeline.py

  # Then upload simple_ml_pipeline.yaml to the pipeline server via
  # the OpenShift AI dashboard or the kfp.Client (see bottom of file).
"""

from kfp import compiler, dsl
from kfp.dsl import Dataset, Input, Metrics, Model, Output


# ---------------------------------------------------------------------------
# Component 1: Fetch Data
# ---------------------------------------------------------------------------
@dsl.component(
    base_image="python:3.11",
    packages_to_install=["scikit-learn==1.5.0", "pandas==2.2.0"],
)
def fetch_data(
    num_samples: int,
    num_features: int,
    output_dataset: Output[Dataset],
):
    """Generate synthetic classification data and save as CSV."""
    from sklearn.datasets import make_classification
    import pandas as pd

    X, y = make_classification(
        n_samples=num_samples,
        n_features=num_features,
        n_informative=num_features // 2,
        random_state=42,
    )

    feature_cols = [f"feature_{i}" for i in range(num_features)]
    df = pd.DataFrame(X, columns=feature_cols)
    df["target"] = y

    df.to_csv(output_dataset.path, index=False)

    output_dataset.metadata["num_samples"] = num_samples
    output_dataset.metadata["num_features"] = num_features
    print(f"Generated {num_samples} samples with {num_features} features")


# ---------------------------------------------------------------------------
# Component 2: Process Data
# ---------------------------------------------------------------------------
@dsl.component(
    base_image="python:3.11",
    packages_to_install=["pandas==2.2.0", "scikit-learn==1.5.0"],
)
def process_data(
    raw_data: Input[Dataset],
    test_split: float,
    train_dataset: Output[Dataset],
    test_dataset: Output[Dataset],
):
    """Split raw data into train and test sets."""
    import pandas as pd
    from sklearn.model_selection import train_test_split

    df = pd.read_csv(raw_data.path)

    train_df, test_df = train_test_split(
        df, test_size=test_split, random_state=42
    )

    train_df.to_csv(train_dataset.path, index=False)
    test_df.to_csv(test_dataset.path, index=False)

    train_dataset.metadata["num_rows"] = len(train_df)
    test_dataset.metadata["num_rows"] = len(test_df)
    print(f"Split data: {len(train_df)} train, {len(test_df)} test")


# ---------------------------------------------------------------------------
# Component 3: Train Model
# ---------------------------------------------------------------------------
@dsl.component(
    base_image="python:3.11",
    packages_to_install=["pandas==2.2.0", "scikit-learn==1.5.0"],
)
def train_model(
    train_data: Input[Dataset],
    test_data: Input[Dataset],
    learning_rate: float,
    trained_model: Output[Model],
    eval_metrics: Output[Metrics],
):
    """Train a RandomForest classifier and evaluate on the test set."""
    import pandas as pd
    import pickle
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, f1_score

    # Load data
    train_df = pd.read_csv(train_data.path)
    test_df = pd.read_csv(test_data.path)

    X_train = train_df.drop("target", axis=1)
    y_train = train_df["target"]
    X_test = test_df.drop("target", axis=1)
    y_test = test_df["target"]

    # Train -- n_estimators is scaled by learning_rate as a simple knob
    n_trees = max(10, int(100 * learning_rate))
    model = RandomForestClassifier(n_estimators=n_trees, random_state=42)
    model.fit(X_train, y_train)

    # Evaluate
    y_pred = model.predict(X_test)
    accuracy = float(accuracy_score(y_test, y_pred))
    f1 = float(f1_score(y_test, y_pred, average="weighted"))

    # Save model as pickle
    with open(trained_model.path, "wb") as f:
        pickle.dump(model, f)

    trained_model.metadata["framework"] = "scikit-learn"
    trained_model.metadata["algorithm"] = "RandomForestClassifier"
    trained_model.metadata["n_estimators"] = n_trees

    # Log metrics (these appear in the dashboard Metrics tab)
    eval_metrics.log_metric("accuracy", accuracy)
    eval_metrics.log_metric("f1_score", f1)
    eval_metrics.log_metric("n_estimators", n_trees)

    print(f"Model trained: accuracy={accuracy:.4f}, f1={f1:.4f}")


# ---------------------------------------------------------------------------
# Component 4: Log Results
# ---------------------------------------------------------------------------
@dsl.component(base_image="python:3.11")
def log_results(
    model: Input[Model],
    metrics: Input[Metrics],
):
    """Print a summary of the pipeline results."""
    print("=" * 60)
    print("PIPELINE RESULTS")
    print("=" * 60)
    print(f"Model URI:      {model.uri}")
    print(f"Model metadata: {model.metadata}")
    print(f"Metrics:        {metrics.metadata}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Pipeline Definition
# ---------------------------------------------------------------------------
@dsl.pipeline(
    name="simple-ml-pipeline",
    description="Fetch synthetic data, split, train a RandomForest model, and log results.",
)
def simple_ml_pipeline(
    num_samples: int = 500,
    num_features: int = 10,
    test_split: float = 0.2,
    learning_rate: float = 1.0,
):
    """
    A 4-step pipeline that demonstrates core KFP v2 concepts:
    data passing via artifacts, metrics logging, and pipeline parameters.
    """
    # Step 1 -- generate synthetic data
    fetch_task = fetch_data(
        num_samples=num_samples,
        num_features=num_features,
    )

    # Step 2 -- split into train / test
    process_task = process_data(
        raw_data=fetch_task.outputs["output_dataset"],
        test_split=test_split,
    )

    # Step 3 -- train and evaluate
    train_task = train_model(
        train_data=process_task.outputs["train_dataset"],
        test_data=process_task.outputs["test_dataset"],
        learning_rate=learning_rate,
    )

    # Step 4 -- log the final results
    log_results(
        model=train_task.outputs["trained_model"],
        metrics=train_task.outputs["eval_metrics"],
    )


# ---------------------------------------------------------------------------
# Compile and (optionally) Submit
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    compiler.Compiler().compile(
        pipeline_func=simple_ml_pipeline,
        package_path="simple_ml_pipeline.yaml",
    )
    print("Pipeline compiled to simple_ml_pipeline.yaml")

    # -----------------------------------------------------------------------
    # (Optional) Submit via kfp.Client
    # Uncomment the block below to submit directly to the pipeline server.
    #
    # Prerequisites:
    #   oc port-forward -n ml-pipelines-tutorial svc/ds-pipeline-dspa 8888:8888 &
    # -----------------------------------------------------------------------
    #
    # from kfp.client import Client
    #
    # client = Client(host="http://localhost:8888")
    #
    # # Upload the pipeline
    # pipeline = client.upload_pipeline(
    #     pipeline_package_path="simple_ml_pipeline.yaml",
    #     pipeline_name="Simple ML Pipeline",
    # )
    # print(f"Pipeline ID: {pipeline.pipeline_id}")
    #
    # # Create a run with custom parameters
    # run = client.create_run_from_pipeline_package(
    #     pipeline_file="simple_ml_pipeline.yaml",
    #     arguments={
    #         "num_samples": 1000,
    #         "num_features": 20,
    #         "test_split": 0.3,
    #         "learning_rate": 0.5,
    #     },
    #     run_name="SDK test run",
    #     experiment_name="tutorial-experiments",
    # )
    # print(f"Run ID: {run.run_id}")
    #
    # # Wait for the run to complete
    # completed_run = client.wait_for_run_completion(
    #     run_id=run.run_id, timeout=600
    # )
    # print(f"Run status: {completed_run.state}")
