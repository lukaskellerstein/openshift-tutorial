"""
MLflow Experiment: Iris Classification with Random Forest

This script connects to an MLflow tracking server on OpenShift AI,
trains a Random Forest classifier on the Iris dataset, and logs
parameters, metrics, artifacts, and the model.

Usage:
    # With default hyperparameters
    python mlflow_experiment.py

    # With custom hyperparameters via environment variables
    N_ESTIMATORS=200 MAX_DEPTH=10 python mlflow_experiment.py

Requirements:
    pip install mlflow scikit-learn

Environment:
    MLFLOW_TRACKING_URI  -- URL of the MLflow tracking server
                            (internal Service URL or Route URL)
    N_ESTIMATORS         -- Number of trees (default: 100)
    MAX_DEPTH            -- Maximum tree depth (default: 5)
"""

import os
import tempfile

import mlflow
from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split


def main():
    # ----------------------------------------------------------------
    # Configuration
    # ----------------------------------------------------------------
    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI")
    if not tracking_uri:
        print("ERROR: MLFLOW_TRACKING_URI environment variable is not set.")
        print("Set it to your MLflow tracking server URL, for example:")
        print("  export MLFLOW_TRACKING_URI='http://mlflow.mlflow-tutorial.svc.cluster.local:8080'")
        print("  export MLFLOW_TRACKING_URI='https://mlflow-mlflow-tutorial.apps.<cluster>'")
        raise SystemExit(1)

    n_estimators = int(os.environ.get("N_ESTIMATORS", "100"))
    max_depth = int(os.environ.get("MAX_DEPTH", "5"))
    random_state = 42
    test_size = 0.2

    experiment_name = "iris-classification"

    print(f"MLflow Tracking URI: {tracking_uri}")

    # ----------------------------------------------------------------
    # Connect to MLflow
    # ----------------------------------------------------------------
    mlflow.set_tracking_uri(tracking_uri)

    experiment = mlflow.get_experiment_by_name(experiment_name)
    if experiment is None:
        experiment_id = mlflow.create_experiment(experiment_name)
        print(f"Experiment '{experiment_name}' created with ID: {experiment_id}")
    else:
        experiment_id = experiment.experiment_id
        print(f"Experiment '{experiment_name}' found with ID: {experiment_id}")

    mlflow.set_experiment(experiment_name)

    # ----------------------------------------------------------------
    # Load and split data
    # ----------------------------------------------------------------
    iris = load_iris()
    X_train, X_test, y_train, y_test = train_test_split(
        iris.data, iris.target,
        test_size=test_size,
        random_state=random_state,
    )

    # ----------------------------------------------------------------
    # Train and log
    # ----------------------------------------------------------------
    print("\nStarting training run...")

    with mlflow.start_run() as run:
        run_id = run.info.run_id

        # -- Parameters --
        print("  Logging parameters...")
        mlflow.log_param("n_estimators", n_estimators)
        mlflow.log_param("max_depth", max_depth)
        mlflow.log_param("random_state", random_state)
        mlflow.log_param("test_size", test_size)

        # -- Tags --
        mlflow.set_tag("model_type", "RandomForest")
        mlflow.set_tag("dataset", "iris")
        mlflow.set_tag("tutorial_lesson", "L2-M5.1")

        # -- Train --
        print("  Training Random Forest model...")
        model = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            random_state=random_state,
        )
        model.fit(X_train, y_train)

        # -- Metrics --
        y_pred = model.predict(X_test)

        accuracy = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred, average="weighted")
        precision = precision_score(y_test, y_pred, average="weighted")
        recall = recall_score(y_test, y_pred, average="weighted")

        print("  Logging metrics...")
        print(f"    accuracy: {accuracy:.4f}")
        print(f"    f1_score: {f1:.4f}")
        print(f"    precision: {precision:.4f}")
        print(f"    recall: {recall:.4f}")

        mlflow.log_metric("accuracy", accuracy)
        mlflow.log_metric("f1_score", f1)
        mlflow.log_metric("precision", precision)
        mlflow.log_metric("recall", recall)

        # -- Step metrics (simulated training loss) --
        print("  Logging step metrics (simulated training loss)...")
        import math
        for step in range(1, 11):
            # Simulated exponential decay loss
            loss = 1.0 * math.exp(-0.3 * step) + 0.05
            mlflow.log_metric("training_loss", round(loss, 4), step=step)

        # -- Artifacts --
        print("  Logging artifacts...")
        with tempfile.TemporaryDirectory() as tmpdir:
            summary_path = os.path.join(tmpdir, "model_summary.txt")
            with open(summary_path, "w") as f:
                f.write("Model Summary\n")
                f.write("=============\n\n")
                f.write(f"Model Type:    RandomForestClassifier\n")
                f.write(f"Dataset:       Iris (sklearn)\n")
                f.write(f"Train samples: {len(X_train)}\n")
                f.write(f"Test samples:  {len(X_test)}\n\n")
                f.write(f"Hyperparameters:\n")
                f.write(f"  n_estimators: {n_estimators}\n")
                f.write(f"  max_depth:    {max_depth}\n")
                f.write(f"  random_state: {random_state}\n\n")
                f.write(f"Metrics:\n")
                f.write(f"  accuracy:  {accuracy:.4f}\n")
                f.write(f"  f1_score:  {f1:.4f}\n")
                f.write(f"  precision: {precision:.4f}\n")
                f.write(f"  recall:    {recall:.4f}\n\n")
                f.write(f"Feature Importances:\n")
                for i, importance in enumerate(model.feature_importances_):
                    f.write(f"  {iris.feature_names[i]}: {importance:.4f}\n")

            mlflow.log_artifact(summary_path)

        # -- Model --
        print("  Logging model...")
        mlflow.sklearn.log_model(model, "random-forest-model")

    # ----------------------------------------------------------------
    # Print results
    # ----------------------------------------------------------------
    experiment_url = f"{tracking_uri.rstrip('/')}/#/experiments/{experiment_id}"

    print(f"\nRun completed successfully.")
    print(f"  Run ID: {run_id}")
    print(f"  Experiment URL: {experiment_url}")
    print(f"\nView your experiment at the URL above.")


if __name__ == "__main__":
    main()
