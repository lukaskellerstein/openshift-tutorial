"""
Feast Feature Serving Script
==============================

Demonstrates two feature retrieval patterns:

  1. Training mode (offline):  Point-in-time join against the offline
     store. Returns historical feature values aligned to each training
     example's timestamp, preventing data leakage.

  2. Inference mode (online):  Low-latency lookup of the latest feature
     values for a single entity from the online store / feature server.
     Used to enrich inference requests before passing them to the model.

Usage:
    # Training: build a feature-enriched training dataset
    python3 feast_serving.py --mode training

    # Inference: look up features for a single customer
    python3 feast_serving.py --mode inference

    # Inference with a specific customer ID
    python3 feast_serving.py --mode inference --entity-id CUST-0042

Prerequisites:
    pip install feast>=0.62.0 pandas requests
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

from feast import FeatureStore

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_CONFIG_PATH = os.path.dirname(os.path.abspath(__file__))

# The feature server route. Set this when running outside the cluster.
FEATURE_SERVER_URL = os.getenv("FEAST_SERVER_URL", "")

# Features to request. The format is "feature_view:feature_name".
FEATURE_REFS = [
    "customer_features:purchase_count",
    "customer_features:avg_order_value",
    "customer_features:days_since_last_purchase",
    "customer_features:total_spend",
    "customer_features:return_rate",
    "customer_features:customer_segment",
]

# Number of training examples to generate for the demo
N_TRAINING_EXAMPLES = 50


def parse_args():
    parser = argparse.ArgumentParser(
        description="Retrieve features from the Feast feature store"
    )
    parser.add_argument(
        "--mode",
        choices=["training", "inference"],
        required=True,
        help="Retrieval mode: 'training' for offline batch, 'inference' for online single-entity",
    )
    parser.add_argument(
        "--entity-id",
        default="CUST-0042",
        help="Customer ID for inference mode (default: CUST-0042)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Training Mode: Offline Feature Retrieval
# ---------------------------------------------------------------------------

def retrieve_training_features(store: FeatureStore):
    """
    Retrieve historical features for training using a point-in-time join.

    How it works:
    1. You provide an "entity DataFrame" with entity keys and timestamps.
       Each row represents a training example: "give me the features for
       this customer as of this timestamp."

    2. Feast performs a point-in-time join: for each row, it finds the
       feature values that were valid at the specified timestamp. This
       prevents data leakage -- the model never sees future features.

    3. The result is a single DataFrame ready for model training.

    Why point-in-time correctness matters:
    - Without it, you might train on features computed today but label
      events from last month. The model sees "the future" during training
      and performs artificially well, then degrades in production.
    """
    print("Feast feature retrieval -- Training Mode")
    print("=========================================")

    # Build an entity DataFrame simulating training examples.
    # In a real scenario, this comes from your label/event data store.
    import numpy as np

    np.random.seed(42)
    now = datetime.now()

    entity_df = pd.DataFrame({
        "customer_id": [f"CUST-{np.random.randint(0, 200):04d}"
                        for _ in range(N_TRAINING_EXAMPLES)],
        "event_timestamp": [now - timedelta(hours=np.random.randint(1, 72))
                            for _ in range(N_TRAINING_EXAMPLES)],
        "label": np.random.randint(0, 2, size=N_TRAINING_EXAMPLES),
    })

    print(f"Building entity DataFrame with {len(entity_df)} training examples...")
    print("Performing point-in-time join against offline store...")

    t0 = time.time()

    try:
        training_df = store.get_historical_features(
            entity_df=entity_df,
            features=FEATURE_REFS,
        ).to_df()
    except Exception as e:
        print(f"\nOffline retrieval failed: {e}", file=sys.stderr)
        print("Ensure feast_definitions.py has been run and data is available.",
              file=sys.stderr)
        sys.exit(1)

    duration = time.time() - t0

    print(f"\nTraining dataset (first 5 rows):")
    # Format output as an aligned table
    display_cols = [
        "customer_id", "event_timestamp", "purchase_count",
        "avg_order_value", "days_since_last_purchase", "total_spend",
        "return_rate", "customer_segment", "label",
    ]
    available_cols = [c for c in display_cols if c in training_df.columns]
    print(training_df[available_cols].head(5).to_string(index=False))

    print(f"\nDataset shape: {training_df.shape}")
    print(f"Point-in-time join duration: {duration:.1f}s")
    print("No future data leakage: features are as-of each entity's event_timestamp.")

    return training_df


# ---------------------------------------------------------------------------
# Inference Mode: Online Feature Retrieval
# ---------------------------------------------------------------------------

def retrieve_inference_features_sdk(store: FeatureStore, entity_id: str):
    """
    Retrieve the latest features for a single entity using the Feast
    Python SDK. This reads directly from the online store.

    Use this pattern when:
    - Your inference code runs inside the cluster (e.g., a KFP component
      or a pre/post-processing container alongside the model)
    - You want the simplest possible integration
    """
    print("Feast feature retrieval -- Inference Mode (SDK)")
    print("================================================")
    print(f"Looking up features for entity: {entity_id}\n")

    t0 = time.time()

    try:
        result = store.get_online_features(
            features=FEATURE_REFS,
            entity_rows=[{"customer_id": entity_id}],
        ).to_dict()
    except Exception as e:
        print(f"\nOnline retrieval failed: {e}", file=sys.stderr)
        print("Ensure materialization has been run (feast_materialize.py).",
              file=sys.stderr)
        sys.exit(1)

    latency_ms = (time.time() - t0) * 1000

    print("Response:")
    print(json.dumps(result, indent=2, default=str))

    # Extract numeric features for model input (exclude segment string)
    numeric_features = [
        result.get("purchase_count", [None])[0],
        result.get("avg_order_value", [None])[0],
        result.get("days_since_last_purchase", [None])[0],
        result.get("total_spend", [None])[0],
        result.get("return_rate", [None])[0],
    ]
    print(f"\nFeature vector for model input: {numeric_features}")
    print(f"Lookup latency: {latency_ms:.0f}ms (target: <10ms)")

    return result


def retrieve_inference_features_rest(entity_id: str, server_url: str):
    """
    Retrieve the latest features via the Feast feature server REST API.

    Use this pattern when:
    - Your inference service is in a different language (Go, Java, etc.)
    - You want a clean HTTP interface without a Python dependency
    - You are calling from outside the cluster

    The feature server is deployed automatically by the FeatureStore CR
    and exposed via an OpenShift Route.
    """
    print("Feast feature retrieval -- Inference Mode (REST)")
    print("=================================================")
    print(f"Looking up features for entity: {entity_id}\n")
    print(f"Feature server URL: {server_url}")

    payload = {
        "features": FEATURE_REFS,
        "entities": {
            "customer_id": [entity_id],
        },
    }

    print(f"Request payload:")
    print(json.dumps(payload, indent=2))

    t0 = time.time()

    try:
        resp = requests.post(
            f"{server_url}/get-online-features",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        print(f"\nCannot reach feature server at {server_url}", file=sys.stderr)
        print("Set FEAST_SERVER_URL or check the route:", file=sys.stderr)
        print("  oc get route shopinsights-features-feature-server "
              "-o jsonpath='{.spec.host}'", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"\nFeature server returned an error: {e}", file=sys.stderr)
        sys.exit(1)

    latency_ms = (time.time() - t0) * 1000

    result = resp.json()
    print(f"\nResponse ({latency_ms:.0f}ms):")
    print(json.dumps(result, indent=2))
    print(f"\nLookup latency: {latency_ms:.0f}ms (target: <10ms)")

    # ---------------------------------------------------------------
    # Integration example: enrich an inference request
    # ---------------------------------------------------------------
    # In a real pipeline, you would take the feature values and pass
    # them alongside the raw request to your model endpoint:
    #
    #   features = result["results"][0]["values"]
    #   model_input = {
    #       "instances": [features[:5]]  # numeric features only
    #   }
    #   model_response = requests.post(
    #       "https://model-endpoint/v1/models/recommender:predict",
    #       json=model_input,
    #   )
    #
    # This pattern ensures the model receives the same features it was
    # trained on, computed by the same Feast pipeline -- eliminating
    # training-serving skew.
    # ---------------------------------------------------------------

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    if args.mode == "training":
        store = FeatureStore(repo_path=REPO_CONFIG_PATH)
        retrieve_training_features(store)

    elif args.mode == "inference":
        # Try the REST API first if a server URL is configured,
        # otherwise fall back to the SDK (direct online store access).
        if FEATURE_SERVER_URL:
            retrieve_inference_features_rest(args.entity_id, FEATURE_SERVER_URL)
        else:
            print("No FEAST_SERVER_URL set. Using SDK for direct online store access.")
            print("To use the REST API, set FEAST_SERVER_URL:")
            print("  export FEAST_SERVER_URL=https://$(oc get route "
                  "shopinsights-features-feature-server -o jsonpath='{.spec.host}')\n")
            store = FeatureStore(repo_path=REPO_CONFIG_PATH)
            retrieve_inference_features_sdk(store, args.entity_id)


if __name__ == "__main__":
    main()
