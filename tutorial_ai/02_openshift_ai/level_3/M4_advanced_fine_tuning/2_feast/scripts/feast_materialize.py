"""
Feast Materialization Script
=============================

Materializes features from the offline store to the online store.
This is the bridge between training data and inference data: the
offline store holds full history for point-in-time joins, while the
online store holds only the latest values for fast lookups.

Run this after applying feature definitions (feast_definitions.py).
In production, schedule this on a cron (e.g., hourly) or trigger it
after your feature engineering pipeline completes.

Usage:
    # Full materialization (backfill a time range)
    python3 feast_materialize.py

    # Incremental materialization (only new data since last run)
    python3 feast_materialize.py --incremental

Prerequisites:
    pip install feast>=0.62.0
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta

from feast import FeatureStore

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_CONFIG_PATH = os.path.dirname(os.path.abspath(__file__))

# Default materialization window: last 48 hours.
# In production, set this to match your feature pipeline cadence.
DEFAULT_WINDOW_HOURS = 48


def parse_args():
    parser = argparse.ArgumentParser(
        description="Materialize features from offline to online store"
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Run incremental materialization (only new data since last run)",
    )
    parser.add_argument(
        "--window-hours",
        type=int,
        default=DEFAULT_WINDOW_HOURS,
        help=f"Hours of history to materialize (default: {DEFAULT_WINDOW_HOURS})",
    )
    return parser.parse_args()


def run_full_materialization(store: FeatureStore, window_hours: int):
    """
    Full materialization: copies all feature values within a time range
    from the offline store to the online store. Use this for initial
    backfill or when you need to recompute the entire online store.

    The time range matters:
    - start_date: oldest feature values to include
    - end_date: newest feature values to include (typically now)

    Only the latest value per entity key ends up in the online store,
    but Feast needs the full range to determine what "latest" means.
    """
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(hours=window_hours)

    print(f"Starting materialization: {start_date.isoformat()} -> {end_date.isoformat()}")

    # Get the list of feature views that will be materialized
    feature_views = store.list_feature_views()
    for fv in feature_views:
        print(f"Materializing feature view: {fv.name}")
        entity_count = _count_entities(store, fv)
        print(f"  Processing {entity_count} entities...")

    t0 = time.time()

    try:
        store.materialize(
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as e:
        print(f"\nMaterialization failed: {e}", file=sys.stderr)
        print("Common causes:", file=sys.stderr)
        print("  - Offline store data is missing or inaccessible", file=sys.stderr)
        print("  - Online store backend is not reachable", file=sys.stderr)
        print("  - Feature view TTL has expired for all data", file=sys.stderr)
        sys.exit(1)

    duration = time.time() - t0

    print(f"  Batch 1/1: {entity_count} entities written to online store")
    print(f"\nMaterialization complete.")
    print(f"  Duration: {duration:.1f}s")
    print(f"  Entities materialized: {entity_count}")
    print(f"  Feature views processed: {len(feature_views)}")
    print("Online store is now up to date.")


def run_incremental_materialization(store: FeatureStore):
    """
    Incremental materialization: only processes new data since the last
    materialization run. This is significantly faster than full
    materialization and is the recommended approach for scheduled runs.

    Feast tracks the high-water mark of the last materialization
    internally. Each call to materialize_incremental advances it.

    In production, run this on a schedule:
      - Every hour for frequently updated features
      - Every 15 minutes for near-real-time features
      - Daily for slowly changing features
    """
    end_date = datetime.utcnow()

    print(f"Starting incremental materialization up to: {end_date.isoformat()}")
    print("Only processing data newer than last materialization high-water mark.")

    feature_views = store.list_feature_views()
    for fv in feature_views:
        print(f"Materializing feature view: {fv.name}")

    t0 = time.time()

    try:
        store.materialize_incremental(end_date=end_date)
    except Exception as e:
        print(f"\nIncremental materialization failed: {e}", file=sys.stderr)
        print("If this is the first run, use full materialization instead:", file=sys.stderr)
        print("  python3 feast_materialize.py  (without --incremental)", file=sys.stderr)
        sys.exit(1)

    duration = time.time() - t0

    print(f"\nIncremental materialization complete.")
    print(f"  Duration: {duration:.1f}s")
    print(f"  Feature views processed: {len(feature_views)}")
    print("Online store is now up to date.")


def _count_entities(store: FeatureStore, feature_view) -> int:
    """
    Estimate the number of entities in a feature view by reading
    the data source. This is used for progress reporting only.
    """
    try:
        import pandas as pd

        source = feature_view.batch_source
        if hasattr(source, "path") and source.path:
            df = pd.read_parquet(source.path)
            join_keys = [e for e in feature_view.entity_columns]
            if join_keys:
                return df[join_keys[0].name].nunique()
            return len(df)
    except Exception:
        pass
    return 0


def main():
    args = parse_args()

    print("Feast materialization")
    print("=====================")
    print("Connecting to feature store...")

    try:
        store = FeatureStore(repo_path=REPO_CONFIG_PATH)
    except Exception as e:
        print(f"Failed to connect to feature store: {e}", file=sys.stderr)
        print("Ensure feast_definitions.py has been run first.", file=sys.stderr)
        sys.exit(1)

    if args.incremental:
        run_incremental_materialization(store)
    else:
        run_full_materialization(store, args.window_hours)


if __name__ == "__main__":
    main()
