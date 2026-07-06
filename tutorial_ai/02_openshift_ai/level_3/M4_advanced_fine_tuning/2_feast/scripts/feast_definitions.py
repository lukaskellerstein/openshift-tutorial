"""
Feast Feature Definitions for ShopInsights
===========================================

This script defines the feature schema for the ShopInsights e-commerce
scenario and applies it to the Feast registry. It covers four core Feast
concepts:

  1. Entity       -- the "thing" you compute features for (customer)
  2. DataSource   -- where raw feature data lives (Parquet file)
  3. FeatureView  -- maps a data source to typed features for an entity
  4. FeatureService -- groups feature views into a named serving set

Run this script after deploying the FeatureStore CR (Step 4 in the lesson).

Usage:
    python3 feast_definitions.py

Prerequisites:
    pip install feast>=0.62.0 pandas
"""

import os
import sys
from datetime import timedelta

from feast import Entity, FeatureService, FeatureStore, FeatureView, Field
from feast.infra.offline_stores.file_source import FileSource
from feast.types import Float32, Int64, String

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# The Feast registry endpoint deployed by the FeatureStore CR.
# When running inside the cluster (e.g., from a workbench), use the
# in-cluster service DNS. When running externally, use the route.
REGISTRY_HOST = os.getenv(
    "FEAST_REGISTRY_HOST",
    "shopinsights-features-registry.feast-tutorial.svc",
)
REGISTRY_PORT = os.getenv("FEAST_REGISTRY_PORT", "6570")

# Path to the Parquet file containing precomputed customer features.
# In production this would point to an S3 bucket or database table.
DATA_PATH = os.getenv("FEAST_DATA_PATH", "/tmp/customer_features.parquet")

REPO_CONFIG_PATH = os.path.dirname(os.path.abspath(__file__))


def main():
    print("Feast feature definitions")
    print("=========================")
    print(f"Connecting to Feast registry at: {REGISTRY_HOST}:{REGISTRY_PORT}")

    # ------------------------------------------------------------------
    # 1. Define an Entity
    # ------------------------------------------------------------------
    # An Entity represents the "thing" you compute features for. In this
    # e-commerce scenario, the entity is a customer. The join_key is the
    # column name in your data that uniquely identifies each customer.
    #
    # When you request features, you provide entity key values (e.g.,
    # customer_id = "CUST-0042") and Feast looks up the corresponding
    # feature values.
    # ------------------------------------------------------------------
    customer = Entity(
        name="customer",
        join_keys=["customer_id"],
        description="A ShopInsights e-commerce customer",
    )
    print(f"Registered entity: {customer.name} (join key: {customer.join_keys})")

    # ------------------------------------------------------------------
    # 2. Define a DataSource
    # ------------------------------------------------------------------
    # A DataSource tells Feast where to find the raw feature data. For
    # this tutorial we use a local Parquet file. In production you would
    # use a database or object storage:
    #
    #   from feast.infra.offline_stores.contrib.postgres_offline_store.postgres_source import (
    #       PostgreSQLSource,
    #   )
    #   customer_source = PostgreSQLSource(
    #       name="customer_data_source",
    #       query="SELECT * FROM customer_features",
    #       timestamp_field="event_timestamp",
    #       created_timestamp_column="created_timestamp",
    #   )
    #
    # The timestamp_field is critical: Feast uses it for point-in-time
    # joins during training to prevent data leakage.
    # ------------------------------------------------------------------
    customer_source = FileSource(
        name="customer_data_source",
        path=DATA_PATH,
        timestamp_field="event_timestamp",
        created_timestamp_column="created_timestamp",
    )
    print(f"Registered data source: {customer_source.name} (path: {DATA_PATH})")

    # ------------------------------------------------------------------
    # 3. Define a FeatureView
    # ------------------------------------------------------------------
    # A FeatureView maps a data source to a set of typed features for a
    # specific entity. It is the central abstraction in Feast.
    #
    # Key parameters:
    #   - entities: which entity this view is for
    #   - schema: the features with their types
    #   - source: the data source to read from
    #   - ttl: time-to-live -- how long a feature value is considered
    #     valid. After the TTL expires, the feature is treated as stale.
    #     Set this based on how often your feature data is refreshed.
    #   - online: whether to serve this view from the online store
    # ------------------------------------------------------------------
    customer_features = FeatureView(
        name="customer_features",
        entities=[customer],
        schema=[
            Field(name="purchase_count", dtype=Int64,
                  description="Total number of purchases"),
            Field(name="avg_order_value", dtype=Float32,
                  description="Average order value in USD"),
            Field(name="days_since_last_purchase", dtype=Int64,
                  description="Days since the customer's most recent purchase"),
            Field(name="total_spend", dtype=Float32,
                  description="Lifetime total spend in USD"),
            Field(name="return_rate", dtype=Float32,
                  description="Fraction of orders returned (0.0 to 1.0)"),
            Field(name="customer_segment", dtype=String,
                  description="Derived segment: high_value, regular, at_risk, churned"),
        ],
        source=customer_source,
        # Features older than 48 hours are considered stale. Adjust based
        # on your data pipeline refresh frequency.
        ttl=timedelta(hours=48),
        online=True,
        description="Customer behavioral features for recommendation scoring",
    )

    feature_names = [f.name for f in customer_features.schema]
    feature_types = [str(f.dtype) for f in customer_features.schema]
    print(f"Registered feature view: {customer_features.name} ({len(feature_names)} features)")
    for name, dtype in zip(feature_names, feature_types):
        print(f"  - {name} ({dtype})")

    # ------------------------------------------------------------------
    # 4. Define a FeatureService
    # ------------------------------------------------------------------
    # A FeatureService groups one or more feature views into a named
    # serving endpoint. This is what inference pipelines reference when
    # requesting features. Grouping views into services lets you version
    # and manage which features each model consumes.
    #
    # In a larger system, you might have:
    #   - customer_scoring_service (customer_features + browsing_features)
    #   - fraud_detection_service (customer_features + transaction_features)
    #
    # Each model references its own service, and you can update the
    # service definition without changing the model code.
    # ------------------------------------------------------------------
    customer_scoring_service = FeatureService(
        name="customer_scoring_service",
        features=[customer_features],
        description="Features for the customer recommendation scoring model",
    )
    print(f"Registered feature service: {customer_scoring_service.name}")

    # ------------------------------------------------------------------
    # 5. Apply definitions to the registry
    # ------------------------------------------------------------------
    # The apply() call writes all definitions to the Feast registry.
    # This is idempotent: running it again updates existing definitions
    # without duplicating them.
    # ------------------------------------------------------------------
    try:
        store = FeatureStore(repo_path=REPO_CONFIG_PATH)
        store.apply([customer, customer_source, customer_features, customer_scoring_service])
        print("\nFeature definitions applied successfully.")
    except Exception as e:
        print(f"\nError applying feature definitions: {e}", file=sys.stderr)
        print("Ensure the FeatureStore CR is deployed and the registry is reachable.",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
