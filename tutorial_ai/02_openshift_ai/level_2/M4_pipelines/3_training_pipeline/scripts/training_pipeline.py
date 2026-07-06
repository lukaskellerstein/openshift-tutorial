"""
L2-M4.3 -- Training Pipeline: Data Prep, Train, Evaluate, Register

End-to-end ML pipeline demonstrating the five-stage pattern:
  1. prepare_data    -- generate synthetic classification data, split train/test
  2. train_model     -- train a RandomForest classifier
  3. evaluate_model  -- evaluate on test set, log metrics, return accuracy
  4. register_model  -- conditionally register in Model Registry (quality gate)

The deploy_model component is included as a commented-out reference.

Usage:
  # Compile to YAML
  python training_pipeline.py

  # Then upload training_pipeline.yaml to the pipeline server via
  # the OpenShift AI dashboard or the kfp.Client (see bottom of file).

Requirements:
  pip install kfp>=2.0 scikit-learn
"""

import datetime

from kfp import compiler, dsl
from kfp.dsl import Dataset, Input, Metrics, Model, Output


# ---------------------------------------------------------------------------
# Component 1: Prepare Data
# ---------------------------------------------------------------------------
@dsl.component(
    base_image="python:3.11",
    packages_to_install=["scikit-learn==1.5.0", "pandas==2.2.0"],
)
def prepare_data(
    dataset_size: int,
    num_features: int,
    test_split: float,
    train_dataset: Output[Dataset],
    test_dataset: Output[Dataset],
):
    """Generate synthetic classification data and split into train/test sets."""
    from sklearn.datasets import make_classification
    from sklearn.model_selection import train_test_split
    import pandas as pd

    # Generate synthetic classification data
    X, y = make_classification(
        n_samples=dataset_size,
        n_features=num_features,
        n_informative=num_features // 2,
        n_redundant=2,
        random_state=42,
    )

    feature_cols = [f"feature_{i}" for i in range(num_features)]
    df = pd.DataFrame(X, columns=feature_cols)
    df["target"] = y

    # Stratified split to maintain class balance
    train_df, test_df = train_test_split(
        df, test_size=test_split, random_state=42, stratify=y
    )

    train_df.to_csv(train_dataset.path, index=False)
    test_df.to_csv(test_dataset.path, index=False)

    train_dataset.metadata["num_rows"] = len(train_df)
    train_dataset.metadata["num_features"] = num_features
    test_dataset.metadata["num_rows"] = len(test_df)

    print(f"Data prepared: {len(train_df)} train, {len(test_df)} test samples")
    print(f"Features: {num_features}, Informative: {num_features // 2}")


# ---------------------------------------------------------------------------
# Component 2: Train Model
# ---------------------------------------------------------------------------
@dsl.component(
    base_image="python:3.11",
    packages_to_install=["scikit-learn==1.5.0", "pandas==2.2.0"],
)
def train_model(
    train_data: Input[Dataset],
    model_name: str,
    n_estimators: int,
    max_depth: int,
    trained_model: Output[Model],
):
    """Train a RandomForest classifier and save as a pickle artifact.

    Note on GPU resources:
      For LLM fine-tuning or large model training, request GPUs on the
      task object in the pipeline function, not inside the component:

          train_task = train_model(...)
          train_task.set_gpu_limit(1)
          train_task.set_memory_limit("32Gi")
          train_task.set_cpu_limit("8")
    """
    import pandas as pd
    import pickle
    from sklearn.ensemble import RandomForestClassifier

    train_df = pd.read_csv(train_data.path)
    X_train = train_df.drop("target", axis=1)
    y_train = train_df["target"]

    # max_depth=0 means no limit (None)
    effective_depth = max_depth if max_depth > 0 else None

    model = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=effective_depth,
        random_state=42,
    )
    model.fit(X_train, y_train)

    # Save model as pickle
    with open(trained_model.path, "wb") as f:
        pickle.dump(model, f)

    trained_model.metadata["model_name"] = model_name
    trained_model.metadata["framework"] = "scikit-learn"
    trained_model.metadata["algorithm"] = "RandomForestClassifier"
    trained_model.metadata["n_estimators"] = n_estimators
    trained_model.metadata["max_depth"] = max_depth

    train_accuracy = model.score(X_train, y_train)
    print(f"Model '{model_name}' trained:")
    print(f"  Algorithm:      RandomForestClassifier")
    print(f"  n_estimators:   {n_estimators}")
    print(f"  max_depth:      {effective_depth}")
    print(f"  Train accuracy: {train_accuracy:.4f}")


# ---------------------------------------------------------------------------
# Component 3: Evaluate Model
# ---------------------------------------------------------------------------
@dsl.component(
    base_image="python:3.11",
    packages_to_install=["scikit-learn==1.5.0", "pandas==2.2.0"],
)
def evaluate_model(
    test_data: Input[Dataset],
    trained_model: Input[Model],
    eval_metrics: Output[Metrics],
) -> float:
    """Evaluate the model on test data and return the accuracy score.

    The returned float is used by the quality gate (dsl.If) to decide
    whether to register the model.
    """
    import pandas as pd
    import pickle
    from sklearn.metrics import (
        accuracy_score,
        f1_score,
        precision_score,
        recall_score,
    )

    # Load model
    with open(trained_model.path, "rb") as f:
        model = pickle.load(f)

    # Load test data
    test_df = pd.read_csv(test_data.path)
    X_test = test_df.drop("target", axis=1)
    y_test = test_df["target"]

    # Predict and compute metrics
    y_pred = model.predict(X_test)
    accuracy = float(accuracy_score(y_test, y_pred))
    f1 = float(f1_score(y_test, y_pred, average="weighted"))
    precision = float(precision_score(y_test, y_pred, average="weighted"))
    recall = float(recall_score(y_test, y_pred, average="weighted"))

    # Log all metrics (visible in the dashboard Metrics tab)
    eval_metrics.log_metric("accuracy", accuracy)
    eval_metrics.log_metric("f1_score", f1)
    eval_metrics.log_metric("precision", precision)
    eval_metrics.log_metric("recall", recall)
    eval_metrics.log_metric("test_samples", len(y_test))

    print(f"Evaluation results:")
    print(f"  Accuracy:  {accuracy:.4f}")
    print(f"  F1 Score:  {f1:.4f}")
    print(f"  Precision: {precision:.4f}")
    print(f"  Recall:    {recall:.4f}")
    print(f"  Samples:   {len(y_test)}")

    # Return accuracy for the quality gate
    return accuracy


# ---------------------------------------------------------------------------
# Component 4: Register Model (conditional -- quality gate must pass)
# ---------------------------------------------------------------------------
@dsl.component(
    base_image="python:3.11",
    packages_to_install=["requests==2.32.0"],
)
def register_model(
    model_name: str,
    model_version: str,
    accuracy: float,
    model: Input[Model],
    registry_url: str,
):
    """Register the model in the Model Registry via REST API."""
    import requests

    print(f"Registering model '{model_name}' version '{model_version}'")
    print(f"  Accuracy: {accuracy:.4f}")
    print(f"  Model URI: {model.uri}")

    # Step 1: Create or find the RegisteredModel
    registered_model_payload = {
        "name": model_name,
        "description": "Tutorial model trained via pipeline",
    }

    try:
        resp = requests.post(
            f"{registry_url}/api/model_registry/v1alpha3/registered_models",
            json=registered_model_payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        if resp.status_code == 409:
            # Model already exists -- look it up
            resp = requests.get(
                f"{registry_url}/api/model_registry/v1alpha3/registered_models",
                params={"name": model_name},
                timeout=30,
            )
            resp.raise_for_status()
            registered_model = resp.json()["items"][0]
        else:
            resp.raise_for_status()
            registered_model = resp.json()

        registered_model_id = registered_model["id"]
        print(f"  RegisteredModel ID: {registered_model_id}")

    except requests.exceptions.ConnectionError:
        print(f"  WARNING: Could not connect to Model Registry at {registry_url}")
        print(f"  Model registration skipped.")
        print(f"  Ensure the Model Registry is deployed and accessible.")
        return

    # Step 2: Create a ModelVersion
    version_payload = {
        "name": model_version,
        "registeredModelId": registered_model_id,
        "description": f"accuracy={accuracy:.4f}",
    }

    resp = requests.post(
        f"{registry_url}/api/model_registry/v1alpha3/model_versions",
        json=version_payload,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    model_version_obj = resp.json()
    model_version_id = model_version_obj["id"]
    print(f"  ModelVersion ID: {model_version_id}")

    # Step 3: Create a ModelArtifact pointing to the model's S3 URI
    artifact_payload = {
        "name": f"{model_name}-{model_version}-artifact",
        "modelFormatName": "sklearn",
        "modelFormatVersion": "1.5.0",
        "uri": model.uri,
        "artifactType": "model-artifact",
    }

    resp = requests.post(
        f"{registry_url}/api/model_registry/v1alpha3/model_versions/{model_version_id}/artifacts",
        json=artifact_payload,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()

    print(f"  Model registered successfully!")
    print(f"  View in dashboard: Model Registry > {model_name} > {model_version}")


# ---------------------------------------------------------------------------
# Component 5: Deploy Model (optional -- commented out)
# ---------------------------------------------------------------------------
# This component is included for reference. Deploying an InferenceService
# from within a pipeline requires RBAC permissions to create resources in the
# target namespace. In production, deployment is typically triggered through
# GitOps (ArgoCD) or the OpenShift AI dashboard.
#
# @dsl.component(
#     base_image="python:3.11",
#     packages_to_install=["kubernetes==29.0.0"],
# )
# def deploy_model(
#     model_name: str,
#     model_version: str,
#     serving_namespace: str,
# ):
#     """Create or update an InferenceService for the registered model."""
#     from kubernetes import client, config
#
#     config.load_incluster_config()
#     custom_api = client.CustomObjectsApi()
#
#     isvc_body = {
#         "apiVersion": "serving.kserve.io/v1beta1",
#         "kind": "InferenceService",
#         "metadata": {
#             "name": model_name,
#             "namespace": serving_namespace,
#         },
#         "spec": {
#             "predictor": {
#                 "model": {
#                     "modelFormat": {"name": "sklearn"},
#                     "storageUri": f"s3://models/{model_name}/{model_version}/",
#                 },
#             },
#         },
#     }
#
#     try:
#         custom_api.create_namespaced_custom_object(
#             group="serving.kserve.io",
#             version="v1beta1",
#             namespace=serving_namespace,
#             plural="inferenceservices",
#             body=isvc_body,
#         )
#         print(f"Created InferenceService: {model_name}")
#     except client.exceptions.ApiException as e:
#         if e.status == 409:
#             custom_api.patch_namespaced_custom_object(
#                 group="serving.kserve.io",
#                 version="v1beta1",
#                 namespace=serving_namespace,
#                 plural="inferenceservices",
#                 name=model_name,
#                 body=isvc_body,
#             )
#             print(f"Updated InferenceService: {model_name}")
#         else:
#             raise


# ---------------------------------------------------------------------------
# Pipeline Definition
# ---------------------------------------------------------------------------
@dsl.pipeline(
    name="training-pipeline",
    description="End-to-end: data prep, train, evaluate, conditionally register.",
)
def training_pipeline(
    model_name: str = "tutorial-classifier",
    dataset_size: int = 1000,
    num_features: int = 15,
    test_split: float = 0.2,
    n_estimators: int = 100,
    max_depth: int = 10,
    quality_threshold: float = 0.8,
    registry_url: str = "http://model-registry-service:8080",
):
    """
    End-to-end training pipeline with quality gate:
      1. Prepare data (generate + split)
      2. Train model (RandomForest)
      3. Evaluate model (accuracy, f1, precision, recall)
      4. If accuracy > threshold: register model in Model Registry
    """
    # Version string for this run
    model_version = datetime.datetime.now().strftime("v%Y%m%d-%H%M%S")

    # Step 1: Prepare data
    data_task = prepare_data(
        dataset_size=dataset_size,
        num_features=num_features,
        test_split=test_split,
    )

    # Step 2: Train model
    train_task = train_model(
        train_data=data_task.outputs["train_dataset"],
        model_name=model_name,
        n_estimators=n_estimators,
        max_depth=max_depth,
    )

    # Optional: request GPU resources for training
    # train_task.set_gpu_limit(1)
    # train_task.set_memory_limit("16Gi")
    # train_task.set_cpu_limit("4")

    # Step 3: Evaluate
    evaluate_task = evaluate_model(
        test_data=data_task.outputs["test_dataset"],
        trained_model=train_task.outputs["trained_model"],
    )

    # Step 4: Quality gate -- register only if accuracy exceeds threshold
    with dsl.If(evaluate_task.output > quality_threshold):
        register_model(
            model_name=model_name,
            model_version=model_version,
            accuracy=evaluate_task.output,
            model=train_task.outputs["trained_model"],
            registry_url=registry_url,
        )


# ---------------------------------------------------------------------------
# Compile and (optionally) Submit
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    compiler.Compiler().compile(
        pipeline_func=training_pipeline,
        package_path="training_pipeline.yaml",
    )
    print("Pipeline compiled to training_pipeline.yaml")

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
    # run = client.create_run_from_pipeline_package(
    #     pipeline_file="training_pipeline.yaml",
    #     arguments={
    #         "model_name": "tutorial-classifier",
    #         "dataset_size": 1000,
    #         "num_features": 15,
    #         "n_estimators": 100,
    #         "max_depth": 10,
    #         "quality_threshold": 0.8,
    #     },
    #     run_name="training-pipeline-run",
    #     experiment_name="tutorial-experiments",
    # )
    # print(f"Run ID: {run.run_id}")
    #
    # # Wait for completion
    # completed = client.wait_for_run_completion(run_id=run.run_id, timeout=600)
    # print(f"Run status: {completed.state}")
