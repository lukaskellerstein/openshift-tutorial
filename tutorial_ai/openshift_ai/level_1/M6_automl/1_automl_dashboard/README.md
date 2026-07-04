# L1-M6.1 — AutoML: Automated Model Training

**Level:** Foundations
**Duration:** 45 min
**Feature Status:** Technology Preview (3.4+)

## Overview

AutoML in OpenShift AI automates the most tedious part of classical machine learning: trying dozens of algorithms, tuning hyperparameters, and comparing results. Instead of writing boilerplate training code yourself, you point AutoML at a CSV dataset, pick a target column, choose a problem type, and let it run. Within minutes, you get a ranked model leaderboard, production-ready trained models, and a generated Jupyter notebook for reproducibility.

This is a **Tier 2 dashboard feature** -- it appears in the OpenShift AI dashboard when the required Tier 1 components are enabled. There is nothing extra to install.

## Prerequisites

- Completed: L1-M1 (Platform Setup) -- OpenShift AI installed with dashboard accessible
- The following Tier 1 DSC components must be `Managed`:
  - `dashboard`
  - `aipipelines` (AutoML runs as Kubeflow Pipelines under the hood)
  - `workbenches` (for generated notebooks)
  - `modelregistry` (for registering the winning model)
- A Data Science Project created with an S3 data connection configured
- A pipeline server configured in the project (for AutoML pipeline execution)
- A tabular dataset in CSV format (uploaded to S3 or ready for direct upload)

> **Note:** If you completed L1-M1.3 (Dashboard and AI Hub Tour), you already have a project and S3 data connection. If you completed L1-M4 (Model Registry), your registry is ready for model registration.

## K8s Context

In vanilla Kubernetes, automated machine learning requires assembling your own stack: you would install an AutoML framework like AutoGluon, H2O, or Auto-sklearn in a container, write orchestration code to launch training jobs, build a custom pipeline (or use Kubeflow Pipelines directly), and wire up artifact storage and model tracking yourself. There is no built-in dashboard experience for AutoML in Kubernetes.

OpenShift AI wraps all of this into a dashboard-driven workflow. The underlying engine is AutoGluon running as Kubeflow Pipelines -- the same pipeline infrastructure you already have from the `aipipelines` DSC component. AutoML simply provides a guided UI on top of it.

## Concepts

### What Is AutoML?

AutoML (Automated Machine Learning) automates the process of:

1. **Data preprocessing** -- handling missing values, encoding categorical features, feature engineering
2. **Algorithm selection** -- trying multiple ML algorithms (gradient boosting, random forests, neural networks, linear models, etc.)
3. **Hyperparameter tuning** -- searching for optimal configuration for each algorithm
4. **Model ensembling** -- combining top models for better performance
5. **Model ranking** -- comparing all candidates on your chosen metric

The result is a leaderboard of trained models ranked by performance, with the best one ready for deployment.

### AutoML as a Tier 2 Dashboard Feature

AutoML follows the same pattern as other Tier 2 features (like AutoRAG and GenAI Playground):

| Aspect | Detail |
|--------|--------|
| **What it is** | A composite dashboard feature, not a standalone component |
| **Where it appears** | OpenShift AI dashboard (when Tier 1 dependencies are enabled) |
| **What it runs on** | Kubeflow Pipelines (the `aipipelines` component) |
| **Backend engine** | AutoGluon (open-source AutoML library by AWS) |
| **Install step** | None -- enable the required Tier 1 components, and AutoML appears in the dashboard |

### AutoGluon: The Engine Under the Hood

AutoGluon is the open-source AutoML framework that powers the AutoML feature. It automatically:

- Detects data types (numeric, categorical, text, datetime)
- Applies appropriate preprocessing per feature type
- Trains multiple model types simultaneously (LightGBM, CatBoost, XGBoost, Random Forest, Neural Networks, etc.)
- Performs intelligent hyperparameter search
- Builds stacked ensembles of top models
- Ranks everything by your target metric

You do not interact with AutoGluon directly -- the dashboard abstracts it entirely.

### Supported Problem Types

AutoML supports four types of machine learning tasks:

| Problem Type | Use Case | Example |
|-------------|----------|---------|
| **Binary Classification** | Predict yes/no outcomes | Customer churn (will they leave: yes/no) |
| **Multiclass Classification** | Predict one of N categories | Product category assignment |
| **Regression** | Predict a continuous number | House price prediction, demand forecasting |
| **Time Series** | Predict future values from historical data | Sales forecasting, stock prediction |

### What AutoML Does NOT Do

AutoML in OpenShift AI is designed for **classical ML on tabular/structured data**. It is not for:

- LLM fine-tuning (use Training Hub from L1-M3 instead)
- Image classification or computer vision
- NLP with transformer models
- Reinforcement learning

If your data fits in a CSV with rows and columns, AutoML is the right tool. If you are working with unstructured text, images, or large language models, use the fine-tuning and serving workflows from earlier modules.

## Step-by-Step

### Step 1: Verify Tier 1 Components Are Enabled

Before using AutoML, confirm the required components are active. Check your `DataScienceCluster`:

```bash
oc get datasciencecluster default-dsc -o jsonpath='{.spec.components.dashboard.managementState}'
# Expected: Managed

oc get datasciencecluster default-dsc -o jsonpath='{.spec.components.aipipelines.managementState}'
# Expected: Managed

oc get datasciencecluster default-dsc -o jsonpath='{.spec.components.workbenches.managementState}'
# Expected: Managed

oc get datasciencecluster default-dsc -o jsonpath='{.spec.components.modelregistry.managementState}'
# Expected: Managed
```

All four must return `Managed`. If any returns `Removed`, update the `DataScienceCluster` CR:

```bash
oc patch datasciencecluster default-dsc --type merge -p '{"spec":{"components":{"aipipelines":{"managementState":"Managed"}}}}'
```

Wait for the component to become ready:

```bash
oc get datasciencecluster default-dsc -o jsonpath='{.status.conditions}' | python3 -m json.tool
```

Look for conditions like `PipelinesReady: True`.

### Step 2: Ensure a Pipeline Server Is Running

AutoML executes as KFP (Kubeflow Pipelines) pipeline runs. Your Data Science Project must have a pipeline server configured.

1. Open the OpenShift AI dashboard
2. Navigate to **Data Science Projects** and select your project
3. Click the **Pipelines** tab
4. If no pipeline server exists, click **Configure pipeline server**
5. Select your S3 data connection for artifact storage
6. Click **Configure**

Verify from the CLI:

```bash
# List DataSciencePipelinesApplication instances in your project namespace
oc get datasciencepipelinesapplication -n <your-project>
```

Expected output:

```
NAME      READY   AGE
dspa      True    5m
```

The pipeline server must show `READY: True` before proceeding.

### Step 3: Prepare Your Training Data

AutoML accepts tabular data in CSV format. You can either upload a CSV directly through the dashboard or point to a file already stored in S3.

For this lesson, we will use a sample dataset. If you do not have one, create a simple classification dataset:

```python
# Run this in a workbench notebook or locally
import pandas as pd
import numpy as np

np.random.seed(42)
n = 1000

data = pd.DataFrame({
    'age': np.random.randint(18, 70, n),
    'income': np.random.normal(50000, 15000, n).astype(int),
    'credit_score': np.random.randint(300, 850, n),
    'num_products': np.random.randint(1, 5, n),
    'tenure_months': np.random.randint(1, 120, n),
    'has_credit_card': np.random.choice([0, 1], n),
    'is_active': np.random.choice([0, 1], n, p=[0.3, 0.7]),
})

# Target: churn (binary classification)
churn_prob = 1 / (1 + np.exp(-(
    -2
    + 0.02 * (data['age'] - 40)
    - 0.00003 * data['income']
    - 0.003 * data['credit_score']
    + 0.3 * data['num_products']
    - 0.01 * data['tenure_months']
    + np.random.normal(0, 0.5, n)
)))
data['churned'] = (np.random.random(n) < churn_prob).astype(int)

data.to_csv('customer_churn.csv', index=False)
print(f"Dataset shape: {data.shape}")
print(f"Churn rate: {data['churned'].mean():.1%}")
print(data.head())
```

Expected output:

```
Dataset shape: (1000, 8)
Churn rate: 28.3%
   age  income  credit_score  num_products  tenure_months  has_credit_card  is_active  churned
0   56   57234           501             4             83                0          1        0
1   46   43866           780             1             45                1          1        0
2   64   73235           432             3            107                1          1        0
3   67   66091           607             2             97                0          1        0
4   29   38965           659             4             26                0          1        1
```

Upload the CSV to your S3 bucket:

```bash
# Using the AWS CLI (or MinIO mc client)
aws s3 cp customer_churn.csv s3://<your-bucket>/automl/customer_churn.csv \
  --endpoint-url <your-s3-endpoint>
```

### Step 4: Create an AutoML Optimization Run

1. Open the **OpenShift AI dashboard**
2. Navigate to the **AutoML** section (this appears in the dashboard when the required components are enabled)
3. Select your **Data Science Project**
4. Click **Create AutoML optimization run**

In the configuration wizard:

**Run Details:**
- **Name:** `customer-churn-experiment` (or any descriptive name)
- **Description:** (optional) `Binary classification to predict customer churn`

**Data Configuration:**
- **Data source:** Select your S3 data connection, then browse to `automl/customer_churn.csv` -- or upload the CSV directly
- **Target column:** Select `churned` (the column you want to predict)

**Algorithm Configuration:**
- **Problem type:** Select **Binary Classification**
  - The dashboard auto-detects the problem type based on the target column, but you can override it
- AutoGluon handles algorithm selection, hyperparameter ranges, and ensemble strategies automatically -- no manual configuration needed

5. Click **Create run** to start the optimization

### Step 5: Monitor Pipeline Execution

After launching, AutoML creates a Kubeflow Pipeline run behind the scenes. You can monitor it in two places:

**From the AutoML page:**
- The run status updates in real time (Pending, Running, Completed, Failed)
- Progress indicators show which stage is active

**From the Pipelines page:**
- Navigate to **Data Science Pipelines** > **Runs** in your project
- Find the AutoML-generated pipeline run
- Click into it to see individual task statuses

From the CLI, you can also monitor the pipeline pods:

```bash
# Watch pipeline pods in your project namespace
oc get pods -n <your-project> -l pipeline/runid --watch
```

Expected output while running:

```
NAME                                                READY   STATUS    RESTARTS   AGE
automl-customer-churn-experiment-xxxxx-data-prep     1/1     Running   0          2m
```

As the pipeline progresses, you will see pods for data preprocessing, model training (one per algorithm), and evaluation.

> **Timing:** A typical AutoML run on a 1,000-row dataset completes in 5-15 minutes depending on cluster resources. Larger datasets or time series problems take longer.

> **Known Issue (RHOAIENG-64768):** In some 3.4 releases, AutoML pipeline runs fail with `ImagePullBackOff` errors because the default pipeline definitions reference container image digests not yet available in the production registry. **Workaround:** Download updated pipeline definitions from the `rhoai-3.4-fixed` branch of the `red-hat-data-services/pipelines-components` repository on GitHub. Upload the corrected pipeline definition as a new version and re-run the experiment.

### Step 6: View the Model Leaderboard

Once the run completes, the AutoML page displays a **model leaderboard** -- a ranked table of all trained models:

| Rank | Model | Algorithm | Accuracy | F1 Score | Training Time |
|------|-------|-----------|----------|----------|---------------|
| 1 | WeightedEnsemble_L2 | Ensemble | 0.847 | 0.792 | 45s |
| 2 | LightGBM_BAG_L2 | LightGBM | 0.839 | 0.781 | 12s |
| 3 | CatBoost_BAG_L2 | CatBoost | 0.835 | 0.774 | 18s |
| 4 | XGBoost_BAG_L2 | XGBoost | 0.831 | 0.768 | 15s |
| 5 | RandomForest_BAG_L2 | Random Forest | 0.822 | 0.754 | 8s |
| 6 | NeuralNetFastAI_BAG_L2 | Neural Net | 0.818 | 0.745 | 30s |

> The exact models, rankings, and metrics will vary based on your data and cluster resources. The table above is illustrative.

Key observations from the leaderboard:

- **WeightedEnsemble** often ranks first -- AutoGluon automatically stacks the best individual models
- **Accuracy and F1** are reported for classification tasks; for regression, you see RMSE and R-squared
- **Training Time** shows how long each model took -- useful for production resource planning
- Click any model row for detailed metrics (confusion matrix, feature importance, etc.)

### Step 7: Explore the Generated Notebook

AutoML generates a Jupyter notebook that contains:

1. **Data loading code** -- reads the same CSV from S3
2. **Best model configuration** -- the exact AutoGluon parameters that produced the top model
3. **Training code** -- reproducible Python code to retrain the model
4. **Evaluation code** -- metrics, confusion matrix, feature importance plots
5. **Prediction code** -- how to use the model for inference

To access the notebook:

1. On the model leaderboard page, click the **notebook icon** or **"Open Notebook"** for the top model
2. This opens the notebook in a workbench (or prompts you to create one)
3. Run all cells to verify you can reproduce the result

The generated notebook typically looks like:

```python
from autogluon.tabular import TabularPredictor

# Load data
train_data = TabularDataset('s3://<your-bucket>/automl/customer_churn.csv')

# Train with the winning configuration
predictor = TabularPredictor(label='churned', eval_metric='f1').fit(
    train_data,
    time_limit=300,
    presets='best_quality',
)

# View leaderboard
leaderboard = predictor.leaderboard(train_data)
print(leaderboard)

# Make predictions
predictions = predictor.predict(test_data)
```

This notebook is your bridge from "dashboard experiment" to "production-ready code." You can modify it, add custom preprocessing, change the time budget, or restrict the algorithm search space.

### Step 8: Register the Best Model in Model Registry

Once you have identified the best model from the leaderboard, register it in the Model Registry for lifecycle management:

1. On the model leaderboard, select the top-ranked model
2. Click **Register model** (or the registration action)
3. Fill in the registration details:
   - **Model name:** `customer-churn-predictor`
   - **Version:** `v1.0`
   - **Description:** `AutoML-trained binary classifier for customer churn prediction`
   - Add any relevant labels or metadata

From the CLI, verify the registration:

```bash
# Check Model Registry for the registered model
oc get registeredmodels -n <your-project>
```

You can also register the model programmatically using the Model Registry Python SDK:

```python
from model_registry import ModelRegistry

registry = ModelRegistry(
    server_address="https://<model-registry-route>",
    author="tutorial-user",
)

registered_model = registry.register_model(
    "customer-churn-predictor",
    uri="s3://<your-bucket>/automl/models/WeightedEnsemble_L2/",
    version="1.0",
    description="AutoML-trained binary classifier for customer churn prediction",
    model_format_name="autogluon",
    metadata={
        "accuracy": "0.847",
        "f1_score": "0.792",
        "algorithm": "WeightedEnsemble_L2",
        "training_method": "AutoML",
    },
)
```

### Step 9: (Optional) Deploy the Best Model via KServe

If your model is a classical ML model (as AutoML produces), you can deploy it using the **MLServer** serving runtime (GA in 3.4), which supports native model formats without conversion to ONNX:

1. In the OpenShift AI dashboard, go to **Model Serving**
2. Click **Deploy model**
3. Select the registered model from Model Registry
4. Choose the **MLServer** runtime (for scikit-learn, XGBoost, LightGBM models)
5. Configure resource limits and replicas
6. Click **Deploy**

Alternatively, deploy from the CLI by creating an `InferenceService`:

```yaml
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  name: customer-churn-predictor
  labels:
    app: customer-churn-predictor
    tutorial-level: "1"
    tutorial-module: "M6"
spec:
  predictor:
    model:
      modelFormat:
        name: lightgbm  # or sklearn, xgboost depending on your top model
      storageUri: s3://<your-bucket>/automl/models/LightGBM_BAG_L2/
      runtime: mlserver
      resources:
        requests:
          cpu: "1"
          memory: 2Gi
        limits:
          cpu: "2"
          memory: 4Gi
```

```bash
oc apply -f inferenceservice.yaml -n <your-project>
```

Test the deployed model:

```bash
# Get the model endpoint
MODEL_URL=$(oc get inferenceservice customer-churn-predictor -n <your-project> \
  -o jsonpath='{.status.url}')

# Send a prediction request
curl -X POST "${MODEL_URL}/v2/models/customer-churn-predictor/infer" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": [
      {
        "name": "input",
        "shape": [1, 7],
        "datatype": "FP64",
        "data": [45, 55000, 720, 2, 36, 1, 1]
      }
    ]
  }'
```

## Verification

Confirm the lesson objectives by checking each deliverable:

**1. AutoML optimization run completed:**

```bash
# Check pipeline run status
oc get pipelineruns -n <your-project> -l automl --no-headers
```

Expected: The run shows `Succeeded`.

You can also verify from the dashboard: navigate to the AutoML section and confirm the run status shows **Completed** with a green checkmark.

**2. Model leaderboard with ranked results:**

In the dashboard, the AutoML page displays the leaderboard with:
- Multiple models ranked by the primary metric (accuracy for classification, RMSE for regression)
- Each model showing its algorithm type, metric scores, and training time
- The top model highlighted

**3. Best model registered (and optionally deployed):**

```bash
# Verify model is in the registry
oc get registeredmodels -n <your-project>

# If deployed, verify the InferenceService is ready
oc get inferenceservice customer-churn-predictor -n <your-project>
```

Expected output for the InferenceService:

```
NAME                        URL                                                          READY   AGE
customer-churn-predictor    https://customer-churn-predictor-<project>.apps.<cluster>     True    5m
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift AI |
|--------|-----------|--------------|
| AutoML availability | None built-in; deploy AutoGluon/H2O/Auto-sklearn manually | Tier 2 dashboard feature -- appears automatically |
| Setup effort | Install framework, write pipeline YAML, configure storage | Enable Tier 1 components, feature appears in dashboard |
| Pipeline orchestration | Install Kubeflow Pipelines, write pipeline code | `aipipelines` component provides pipelines; AutoML auto-generates pipeline runs |
| Model comparison | Build custom tracking with MLflow or W&B | Built-in leaderboard in the dashboard |
| Reproducibility | Write your own training scripts | Auto-generated Jupyter notebook with exact configuration |
| Model registration | Manual SDK calls or custom pipeline steps | One-click registration from leaderboard to Model Registry |
| Model deployment | Write InferenceService YAML manually | Deploy directly from registry via dashboard |

## Key Takeaways

- **AutoML is a Tier 2 dashboard feature** that requires four Tier 1 components (`dashboard`, `aipipelines`, `workbenches`, `modelregistry`). There is nothing extra to install -- enable the dependencies and it appears in the dashboard.

- **AutoML is for classical ML on tabular data**, not for LLM fine-tuning. It supports binary classification, multiclass classification, regression, and time series. If your problem involves structured data in CSV format, AutoML is the fastest path to a trained model.

- **AutoGluon powers the backend**, automatically trying multiple algorithms (LightGBM, CatBoost, XGBoost, Random Forest, Neural Networks, etc.), tuning hyperparameters, and building stacked ensembles. You do not need to know AutoGluon to use the feature.

- **The generated notebook bridges experimentation and production.** AutoML produces a reproducible Jupyter notebook with the exact training configuration, so you can iterate, customize, and integrate the model into production workflows.

- **The end-to-end flow stays within the platform**: data in S3, training via KFP pipelines, results on the leaderboard, registration in Model Registry, deployment via KServe with MLServer -- no external tools needed.

## Cleanup

Remove the resources created in this lesson:

```bash
# Delete the deployed InferenceService (if created in Step 9)
oc delete inferenceservice customer-churn-predictor -n <your-project>

# Delete pipeline runs from the AutoML experiment
oc delete pipelineruns -n <your-project> -l automl

# Remove the training data from S3 (optional)
aws s3 rm s3://<your-bucket>/automl/ --recursive \
  --endpoint-url <your-s3-endpoint>

# Remove registered model from Model Registry (optional -- via dashboard or SDK)
# Navigate to Model Registry in the dashboard and delete the registered model
```

> **Note:** Do not delete the pipeline server or Tier 1 components -- they are shared infrastructure used by other features and lessons.

## Next Steps

### Level 1 Complete

Congratulations -- you have completed all of Level 1. Here is a summary of what you accomplished across 19 lessons and approximately 12-14 hours:

| Module | What You Learned |
|--------|-----------------|
| **M1: Platform Setup** | Installed OpenShift AI, explored the dashboard and AI Hub, set up workbenches, configured GPUs, and tested the GenAI Playground |
| **M2: Model Serving** | Deployed Gemma4-e4b on vLLM via KServe, used the OpenAI-compatible API, and configured autoscaling |
| **M3: Fine-Tuning** | Fine-tuned Gemma4-e4b with LoRA/QLoRA using Training Hub and deployed the fine-tuned model |
| **M4: Model Registry** | Set up Model Registry, registered base and fine-tuned models with versioning |
| **M5: Evaluation** | Benchmarked models with LMEvalJob and GuideLLM, set up vLLM metrics in Grafana |
| **M6: AutoML** | Ran automated model training for classical ML, explored the leaderboard, and registered the best model |

You now have a solid foundation in OpenShift AI: you can deploy, fine-tune, evaluate, and serve both LLM and classical ML models on the platform.

### What Level 2 Covers

Level 2 (Practitioner) builds on these foundations with production workflows:

- **RAG on OpenShift AI** -- vector databases, document ingestion, end-to-end RAG applications, and AutoRAG optimization
- **MCP Server Deployment** -- deploying MCP servers with the Lifecycle Operator and MCP Gateway
- **AI Agent Deployment** -- containerizing and deploying LangChain/LangGraph agents on OpenShift
- **Data Science Pipelines** -- building end-to-end training and ingestion pipelines with KFP
- **Observability** -- MLflow tracing, OpenTelemetry, TrustyAI monitoring, and production dashboards
- **Distributed Workloads** -- KubeRay, Kueue, distributed fine-tuning, and Apache Spark

Continue to [Level 2, Module 1: RAG Architecture with OGX](../../../level_2/M1_rag/1_rag_architecture_ogx/).
