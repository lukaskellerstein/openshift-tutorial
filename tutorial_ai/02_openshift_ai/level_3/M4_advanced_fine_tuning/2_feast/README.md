# L3-M4.2 -- Feature Store with Feast

**Level:** Expert
**Duration:** 45 min

## Overview

You have built training pipelines and served models, but there is a gap between those two worlds: how do you guarantee that the exact same feature transformations used during training are applied during inference? This gap -- called training-serving skew -- is one of the most common sources of silent model degradation in production. Feast is the leading open-source feature store, and OpenShift AI integrates it natively via the FeatureStore custom resource (GA in RHOAI 3.4, Feast v0.62.0). In this lesson you will deploy a Feast feature store on OpenShift AI, define entities and feature views for an e-commerce scenario, materialize features from an offline store to an online store, and retrieve features for both training and real-time inference.

## Prerequisites

- Completed: [L1-M3.1 -- Fine-Tuning Concepts](../../../level_1/M3_fine_tuning/1_fine_tuning_concepts/)
- Completed: [L3-M4.1 -- InstructLab](../1_instructlab/) (recommended)
- OpenShift AI 3.4+ with the Feast component enabled in the DataScienceCluster
- `oc` CLI authenticated with project-admin or cluster-admin privileges
- Python 3.11+ with `feast>=0.62.0` installed (`pip install feast`)

## Concepts

### Why Feature Stores Exist

In a typical ML workflow without a feature store, feature engineering code is duplicated across at least two places: the training notebook that computes features from raw data, and the serving pipeline that recomputes features from live data before calling the model. This duplication creates three problems:

| Problem | Description |
|---------|-------------|
| **Training-serving skew** | Subtle differences in feature computation between training and serving cause model accuracy to silently degrade |
| **Feature duplication** | Multiple teams recompute the same features independently, wasting compute and storage |
| **Point-in-time incorrectness** | Training on features computed "as of now" rather than "as of the event time" causes data leakage and inflated metrics |

A feature store solves all three by providing a single, versioned definition of each feature that is used identically for training and serving.

---

### Feast Architecture

Feast has three core infrastructure components:

```
+------------------+       +-------------------+       +------------------+
|                  |       |                   |       |                  |
|   Data Sources   +------>+   Offline Store   +------>+   Online Store   |
|   (Parquet, DB)  |       |   (batch queries) |       |   (low-latency)  |
|                  |       |                   |       |                  |
+------------------+       +--------+----------+       +--------+---------+
                                    |                           |
                           Training retrieval            Inference retrieval
                           (point-in-time join)          (single-entity lookup)
                                    |                           |
                                    v                           v
                           +--------+----------+       +--------+---------+
                           |  Training Pipeline |       |  Feature Server  |
                           |  (batch features)  |       |  (REST API)      |
                           +-------------------+       +------------------+
                                                                |
                                                                v
                                                       +--------+---------+
                                                       |  Model Endpoint  |
                                                       |  (InferenceService)|
                                                       +------------------+
```

- **Offline Store** -- Historical feature values for training. Performs point-in-time joins: given entity keys and timestamps, returns feature values valid at those exact times. Backed by Parquet, PostgreSQL, or BigQuery.
- **Online Store** -- Latest feature values for inference. Low-latency lookups (under 10ms). Backed by Redis, DynamoDB, or SQLite.
- **Feature Server** -- REST API fronting the online store for standardized feature retrieval at inference time.

---

### The FeatureStore CRD on OpenShift AI

OpenShift AI 3.4 introduced the `FeatureStore` custom resource as a native way to deploy Feast. When you create a FeatureStore CR, the operator deploys:

| Component | What It Does |
|-----------|-------------|
| **Registry** | Stores feature definitions (entities, feature views, data sources) as metadata |
| **Offline Store** | Serves batch feature queries for training data generation |
| **Online Store** | Serves low-latency feature queries for inference |
| **Feature Server** | REST API fronting the online store |
| **Web UI** | Browser interface for exploring and discovering features |

The operator manages the lifecycle of all these components, handling upgrades, scaling, and health checks.

### Key Feast Concepts

| Concept | Description | Example |
|---------|-------------|---------|
| **Entity** | The "thing" you compute features for. Defined by a join key. | `customer` entity with `customer_id` as the join key |
| **DataSource** | Where raw feature data lives. Points to a file or table. | Parquet file at `s3://bucket/customer_features.parquet` |
| **FeatureView** | Maps a data source to a set of typed features for an entity. | `customer_features` view with `purchase_count`, `avg_order_value` |
| **FeatureService** | Groups one or more feature views into a named set for serving. | `customer_scoring_service` combining purchase and browsing features |

---

### Offline vs Online Stores

| Aspect | Offline Store | Online Store |
|--------|--------------|-------------|
| **Purpose** | Training data generation | Real-time inference |
| **Query pattern** | Batch: many entities, point-in-time join | Single: one entity, latest values |
| **Latency** | Seconds to minutes | Milliseconds |
| **Data scope** | Full history | Latest values only |
| **Typical backend** | Parquet, PostgreSQL, BigQuery | Redis, DynamoDB, SQLite |
| **When to use** | Building training datasets | Enriching inference requests |

**Materialization** is the process of copying computed feature values from the offline store to the online store. You run it on a schedule (e.g., hourly) or trigger it after a batch feature computation completes.

## Step-by-Step

### Step 1: Verify Feast Is Available

Feast requires the `featurestore` component to be enabled in the DataScienceCluster. Check its status:

```bash
oc get datasciencecluster default-dsc \
  -o jsonpath='{.spec.components.featurestore}' | python3 -m json.tool
```

Expected output:

```json
{
    "managementState": "Managed"
}
```

If the component is set to `Removed`, enable it:

```bash
oc patch datasciencecluster default-dsc --type merge \
  -p '{"spec":{"components":{"featurestore":{"managementState":"Managed"}}}}'
```

Verify the Feast operator pods are running:

```bash
oc get pods -n redhat-ods-applications -l app.kubernetes.io/part-of=feast
```

Expected output:

```
NAME                                      READY   STATUS    RESTARTS   AGE
feast-operator-controller-manager-abc12   1/1     Running   0          3m
```

---

### Step 2: Create a Project and Deploy the FeatureStore CR

Create a dedicated project for the feature store:

```bash
oc new-project feast-tutorial
```

Apply the FeatureStore custom resource:

```bash
oc apply -f manifests/featurestore.yaml
```

Expected output:

```
featurestore.feast.dev/shopinsights-features created
```

Wait for all components to become ready:

```bash
oc get featurestore shopinsights-features -w
```

Expected output:

```
NAME                     READY   STATUS    AGE
shopinsights-features    True    Ready     2m
```

---

### Step 3: Prepare Sample Data

Before defining features, create a sample Parquet file with customer data. This simulates a data pipeline that has already computed raw features from transactional data:

```bash
python3 -c "
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

np.random.seed(42)
n_customers = 200

now = datetime.now()
data = {
    'customer_id': [f'CUST-{i:04d}' for i in range(n_customers)],
    'purchase_count': np.random.poisson(lam=15, size=n_customers),
    'avg_order_value': np.round(np.random.lognormal(mean=3.5, sigma=0.8, size=n_customers), 2),
    'days_since_last_purchase': np.random.randint(0, 90, size=n_customers),
    'total_spend': np.round(np.random.lognormal(mean=6.0, sigma=1.0, size=n_customers), 2),
    'return_rate': np.round(np.random.beta(2, 10, size=n_customers), 4),
    'event_timestamp': [now - timedelta(hours=np.random.randint(1, 48)) for _ in range(n_customers)],
    'created_timestamp': [now - timedelta(days=np.random.randint(30, 365)) for _ in range(n_customers)],
}
df = pd.DataFrame(data)
df.to_parquet('/tmp/customer_features.parquet', index=False)
print(f'Created /tmp/customer_features.parquet with {len(df)} rows')
print(df.head(3).to_string(index=False))
"
```

Expected output:

```
Created /tmp/customer_features.parquet with 200 rows
```

---

### Step 4: Define Entities, Data Sources, and Feature Views

Run the feature definitions script. This registers your feature schema with the Feast registry:

```bash
python3 scripts/feast_definitions.py
```

Expected output:

```
Feast feature definitions
=========================
Connecting to Feast registry at: shopinsights-features-registry.feast-tutorial.svc:6570
Registered entity: customer (join key: customer_id)
Registered data source: customer_data_source (path: /tmp/customer_features.parquet)
Registered feature view: customer_features (6 features)
  - purchase_count (INT64)
  - avg_order_value (FLOAT)
  - days_since_last_purchase (INT64)
  - total_spend (FLOAT)
  - return_rate (FLOAT)
  - customer_segment (STRING)
Registered feature service: customer_scoring_service
Feature definitions applied successfully.
```

---

### Step 5: Materialize Features from Offline to Online Store

Materialization copies the latest feature values into the online store so they can be served with low latency at inference time:

```bash
python3 scripts/feast_materialize.py
```

Expected output:

```
Feast materialization
=====================
Connecting to feature store...
Starting materialization: 2026-07-03T00:00:00 -> 2026-07-04T12:00:00
Materializing feature view: customer_features
  Processing 200 entities...
  Batch 1/1: 200 entities written to online store
Materialization complete.
  Duration: 4.2s
  Entities materialized: 200
  Feature views processed: 1
Online store is now up to date.
```

Verify the online store has data by checking the feature server health:

```bash
FEAST_SERVER=$(oc get route shopinsights-features-feature-server \
  -o jsonpath='{.spec.host}')
curl -s "https://${FEAST_SERVER}/health" | python3 -m json.tool
```

Expected output:

```json
{
    "status": "healthy"
}
```

---

### Step 6: Retrieve Features for Training (Offline)

For training, you need historical feature values joined to your training entities at their exact event timestamps. This prevents data leakage by ensuring the model only sees features that were available at the time of each training example:

```bash
python3 scripts/feast_serving.py --mode training
```

Expected output:

```
Feast feature retrieval -- Training Mode
=========================================
Building entity DataFrame with 50 training examples...
Performing point-in-time join against offline store...

Training dataset (first 3 rows):
  customer_id       event_timestamp  purchase_count  avg_order_value  total_spend  label
    CUST-0012  2026-07-01 10:00:00              18            42.31       761.58      1
    CUST-0045  2026-07-02 14:30:00               7            15.89       111.23      0
    CUST-0078  2026-07-01 08:15:00              22            67.45      1483.90      1

Dataset shape: (50, 9)
Point-in-time join duration: 1.3s
No future data leakage: features are as-of each entity's event_timestamp.
```

---

### Step 7: Retrieve Features for Inference (Online)

For inference, you need the latest feature values for a single entity with minimal latency. The feature server provides a REST API for this:

```bash
python3 scripts/feast_serving.py --mode inference
```

Expected output:

```
Feast feature retrieval -- Inference Mode
==========================================
Looking up features for entity: CUST-0042
Response (3ms):
  purchase_count: 16
  avg_order_value: 38.92
  days_since_last_purchase: 8
  total_spend: 622.72
  return_rate: 0.1105
  customer_segment: regular

Feature vector for model input: [16, 38.92, 8, 622.72, 0.1105]
Lookup latency: 3ms (target: <10ms)
```

You can also call the feature server directly with `curl`:

```bash
FEAST_SERVER=$(oc get route shopinsights-features-feature-server \
  -o jsonpath='{.spec.host}')

curl -s -X POST "https://${FEAST_SERVER}/get-online-features" \
  -H "Content-Type: application/json" \
  -d '{
    "features": [
      "customer_features:purchase_count",
      "customer_features:avg_order_value",
      "customer_features:days_since_last_purchase"
    ],
    "entities": {
      "customer_id": ["CUST-0042"]
    }
  }' | python3 -m json.tool
```

Expected output:

```json
{"metadata":{"feature_names":["purchase_count","avg_order_value","days_since_last_purchase"]},"results":[{"values":[16,38.92,8],"statuses":["PRESENT","PRESENT","PRESENT"]}]}
```

---

### Step 8: Explore Features via the Feast Web UI

The FeatureStore CR deploys a web UI for browsing and discovering features. Get the route:

```bash
oc get route shopinsights-features-ui -o jsonpath='{.spec.host}'
```

Expected output:

```
shopinsights-features-ui-feast-tutorial.apps.sandbox.example.com
```

Open the URL in your browser. The Feast UI shows:

- **Entities** -- All registered entities with their join keys and descriptions
- **Feature Views** -- Each feature view with its schema, data source, and TTL
- **Feature Services** -- Groupings of feature views available for serving
- **Data Sources** -- Registered data sources with their connection details

This is valuable for feature discovery across teams. When a data scientist needs customer features for a new model, they can search the UI instead of asking around or duplicating existing work.

## Verification

Confirm all lesson objectives are met:

```bash
# 1. FeatureStore CR is ready (expected: True)
oc get featurestore shopinsights-features \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'

# 2. Feature definitions are registered (expected: 1)
feast -c scripts/ entities list 2>/dev/null | grep -c customer

# 3. Online store has materialized data (expected: Online store OK)
FEAST_SERVER=$(oc get route shopinsights-features-feature-server \
  -o jsonpath='{.spec.host}')
curl -s -X POST "https://${FEAST_SERVER}/get-online-features" \
  -H "Content-Type: application/json" \
  -d '{"features":["customer_features:purchase_count"],"entities":{"customer_id":["CUST-0001"]}}' \
  | python3 -c "import sys,json; r=json.load(sys.stdin); print('Online store OK' if r['results'][0]['statuses'][0]=='PRESENT' else 'MISSING')"

# 4. Feature server responds within latency target (expected: <0.010s)
curl -s -o /dev/null -w "Latency: %{time_total}s\n" \
  -X POST "https://${FEAST_SERVER}/get-online-features" \
  -H "Content-Type: application/json" \
  -d '{"features":["customer_features:purchase_count"],"entities":{"customer_id":["CUST-0001"]}}'
```

## Key Takeaways

- Feature stores eliminate training-serving skew by providing a single source of truth for feature definitions, used identically in training (offline retrieval with point-in-time joins) and inference (online retrieval with low-latency lookups).
- The FeatureStore CRD on OpenShift AI (GA in RHOAI 3.4) deploys the full Feast stack -- registry, offline store, online store, feature server, and web UI -- as a managed resource.
- Materialization is the bridge between offline and online: it copies the latest computed feature values into the online store so the feature server can serve them in milliseconds.
- Point-in-time joins are critical for correct training data: they prevent data leakage by ensuring the model only sees features that existed at the time of each training example.
- The Feast web UI enables feature discovery and reuse across teams, reducing duplicated feature engineering work.

## Cleanup

```bash
# Delete the FeatureStore CR (removes all deployed components)
oc delete featurestore shopinsights-features -n feast-tutorial

# Remove sample data
rm -f /tmp/customer_features.parquet

# Delete the project
oc delete project feast-tutorial
```

## Next Steps

In [L3-M4.3 -- Continuous Learning Pipelines](../3_continuous_learning/), you will combine the feature store with automated retraining. You will build a pipeline that detects data drift in feature distributions, triggers retraining when drift exceeds a threshold, evaluates the retrained model, and promotes it to production -- closing the loop from feature engineering to model deployment.
