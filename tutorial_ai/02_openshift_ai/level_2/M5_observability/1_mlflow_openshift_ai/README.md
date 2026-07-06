# L2-M5.1 -- MLflow on OpenShift AI

**Level:** Practitioner
**Duration:** 45 min


## Overview

MLflow is the standard open-source platform for experiment tracking, model registry, and agent traceability. On vanilla Kubernetes, you deploy MLflow yourself -- a Helm chart, a database, an artifact store, and a lot of glue. OpenShift AI ships MLflow as a managed operator component (`mlflowoperator`), so you declare an `MLflowServer` CR in your data science project and the operator handles the rest: server deployment, storage, Route creation, and lifecycle management. This lesson walks through enabling the component, creating an MLflow server, connecting a workbench, and logging a real experiment.


## Prerequisites

- Completed: [L1-M1.1 -- Architecture Overview](../../../level_1/M1_platform_setup/1_architecture_overview/) (covers DSC components, including `mlflowoperator`)
- OpenShift cluster with OpenShift AI 3.4+ installed
- The `mlflowoperator` component set to `Managed` in the DataScienceCluster CR
- A data science project (namespace) where you have edit access
- Familiarity with MLflow concepts (experiments, runs, parameters, metrics, artifacts)
- `oc` CLI authenticated to the cluster


## Concepts

### MLflow in the OpenShift AI Component Model

Recall from [L1-M1.1](../../../level_1/M1_platform_setup/1_architecture_overview/) that the DataScienceCluster CR exposes 14 components. MLflow is the `mlflowoperator` component:

| DSC Field | What It Deploys | Version (3.4.2) |
|-----------|----------------|-----------------|
| `mlflowoperator` | MLflow experiment tracking server | MLflow v3.10.1 |

When you set `mlflowoperator.managementState: Managed`, the RHODS operator installs the MLflow Operator into the cluster. This operator watches for `MLflowServer` CRs in user namespaces and deploys MLflow tracking server instances in response.

The architecture has three layers:

1. **DSC component** (`mlflowoperator`) -- installs the MLflow Operator cluster-wide
2. **MLflowServer CR** -- created per project, tells the operator to deploy a tracking server in that namespace
3. **MLflow SDK** (Tier 3 library) -- used inside workbenches and pipeline steps to log experiments to the server


### MLflowServer CRD

The `MLflowServer` CRD is the primary resource you interact with. When you create one in your data science project, the MLflow Operator:

1. Deploys a MLflow tracking server pod in your namespace
2. Creates a Service for internal cluster access
3. Creates an OpenShift Route for external access (the MLflow UI)
4. Configures storage for experiment data and artifacts

A minimal `MLflowServer` CR looks like this:

```yaml
apiVersion: mlflow.opendatahub.io/v1alpha1
kind: MLflowServer
metadata:
  name: mlflow
  labels:
    app: mlflow
    tutorial-level: "2"
    tutorial-module: "M5"
spec: {}
```

The empty `spec: {}` is intentional -- the operator uses sensible defaults for storage, resource limits, and server configuration. In production, you would configure external storage (S3, PVC) and resource requests, but for this lesson the defaults are sufficient.


### Connecting to the MLflow Tracking Server

Once the MLflow server pod is running, you connect to it by setting the `MLFLOW_TRACKING_URI` environment variable in your workbench or script. The URI uses the internal Service URL:

```
http://mlflow.<namespace>.svc.cluster.local:8080
```

If you are running code from outside the cluster (e.g., your laptop), use the Route URL instead. The Route is created automatically by the operator and follows the pattern:

```
https://mlflow-<namespace>.apps.<cluster-domain>
```

Inside OpenShift AI workbenches, you typically set the tracking URI as an environment variable in the workbench configuration or at the top of your notebook.


### The MLflow Hierarchy

MLflow organizes tracking data in a simple hierarchy:

```
Experiment (e.g., "iris-classification")
  |
  +-- Run 1 (e.g., "random-forest-v1")
  |     |-- Parameters: learning_rate=0.1, n_estimators=100
  |     |-- Metrics: accuracy=0.95, f1_score=0.94
  |     |-- Artifacts: model.pkl, summary.txt
  |     +-- Tags: model_type=RandomForest
  |
  +-- Run 2 (e.g., "random-forest-v2")
        |-- Parameters: learning_rate=0.05, n_estimators=200
        |-- Metrics: accuracy=0.97, f1_score=0.96
        |-- Artifacts: model.pkl, summary.txt
        +-- Tags: model_type=RandomForest
```

- **Experiment** -- a named collection of runs, typically one per project or model type
- **Run** -- a single execution of your training code
- **Parameters** -- input configuration (hyperparameters, data paths)
- **Metrics** -- output measurements (accuracy, loss, latency), optionally logged at multiple steps
- **Artifacts** -- files produced by the run (models, plots, data samples)

All of this is stored by the MLflow tracking server and viewable in the MLflow UI.


### Integration with Model Registry

The `mlflowoperator` component works alongside the `modelregistry` component. After you identify a good run in MLflow, you can register the model in the Model Registry for versioning, approval workflows, and deployment via KServe. The flow is:

1. Train and log experiments in MLflow
2. Identify the best run
3. Register the model in Model Registry
4. Deploy via InferenceService (KServe)

This lesson focuses on steps 1 and 2. Model Registry integration is covered in later modules.


### Relationship to Standalone MLflow

If you have previously deployed MLflow on vanilla Kubernetes (via Helm, Docker Compose, or a manual Deployment), the OpenShift AI version is the same MLflow -- same Python SDK, same REST API, same UI. The differences are:

- **Lifecycle** -- the operator manages the server; you do not write Deployments, Services, or Routes yourself
- **Authentication** -- the Route integrates with OpenShift OAuth automatically
- **Storage** -- the operator configures storage defaults; you can override with S3 or PVC
- **Multi-tenancy** -- each project gets its own MLflowServer instance, isolated by namespace

Your existing MLflow code works unchanged -- you only need to point `MLFLOW_TRACKING_URI` to the new server.


## Step-by-Step

### Step 1: Verify the mlflowoperator Component Is Enabled

Check that the `mlflowoperator` component is set to `Managed` in the DataScienceCluster CR:

```bash
oc get datasciencecluster default-dsc -o jsonpath='{.spec.components.mlflowoperator.managementState}'
```

Expected output:

```
Managed
```

If it shows `Removed`, a cluster admin needs to enable it:

```bash
oc patch datasciencecluster default-dsc --type merge -p '{"spec":{"components":{"mlflowoperator":{"managementState":"Managed"}}}}'
```

Verify the MLflow Operator pod is running:

```bash
oc get pods -n redhat-ods-operator -l app.kubernetes.io/name=mlflow-operator
```

Expected output:

```
NAME                              READY   STATUS    RESTARTS   AGE
mlflow-operator-6b8f9c4d5-x7k2m  1/1     Running   0          2d
```


### Step 2: Create a Data Science Project

Create a project for this lesson (or use an existing data science project):

```bash
oc new-project mlflow-tutorial
```

Add labels for easy cleanup:

```bash
oc label namespace mlflow-tutorial tutorial-level=2 tutorial-module=M5
```


### Step 3: Create an MLflowServer CR

Apply the MLflowServer manifest to deploy a tracking server in your project:

```yaml
# manifests/mlflowserver.yaml
apiVersion: mlflow.opendatahub.io/v1alpha1
kind: MLflowServer
metadata:
  name: mlflow
  namespace: mlflow-tutorial
  labels:
    app: mlflow
    tutorial-level: "2"
    tutorial-module: "M5"
spec: {}
```

Apply it:

```bash
oc apply -f manifests/mlflowserver.yaml
```

Expected output:

```
mlflowserver.mlflow.opendatahub.io/mlflow created
```


### Step 4: Wait for the MLflow Server to Start

The operator will create a Deployment, Service, and Route. Watch the pod come up:

```bash
oc get pods -n mlflow-tutorial -l app=mlflow -w
```

Wait until you see `1/1 Running`:

```
NAME                      READY   STATUS    RESTARTS   AGE
mlflow-7d8f9a6b4c-t5n2q   1/1     Running   0          45s
```

Press `Ctrl+C` to stop watching.

Verify the Service and Route were created:

```bash
oc get svc,route -n mlflow-tutorial -l app=mlflow
```

Expected output:

```
NAME             TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE
service/mlflow   ClusterIP   172.30.45.123   <none>        8080/TCP   1m

NAME                    HOST/PORT                                      PATH   SERVICES   PORT   TERMINATION     WILDCARD
route.route.openshift.io/mlflow   mlflow-mlflow-tutorial.apps.<cluster>          mlflow     8080   edge/Redirect   None
```


### Step 5: Access the MLflow UI

Get the Route URL:

```bash
oc get route mlflow -n mlflow-tutorial -o jsonpath='{.spec.host}'
```

Open the URL in your browser (prepend `https://`). You will see the MLflow UI with an empty experiment list. This confirms the tracking server is running and accessible.

You can also verify the server is responding from the command line:

```bash
MLFLOW_ROUTE=$(oc get route mlflow -n mlflow-tutorial -o jsonpath='{.spec.host}')
curl -sk "https://${MLFLOW_ROUTE}/api/2.0/mlflow/experiments/search" | python3 -m json.tool
```

Expected output:

```json
{
    "experiments": [
        {
            "experiment_id": "0",
            "name": "Default",
            "artifact_location": "mlflow-artifacts:/0",
            "lifecycle_stage": "active",
            "last_update_time": "1720099200000",
            "creation_time": "1720099200000"
        }
    ]
}
```

The `Default` experiment is created automatically by MLflow.


### Step 6: Set the Tracking URI

For code running inside the cluster (workbenches, pipeline steps), use the internal Service URL:

```bash
export MLFLOW_TRACKING_URI="http://mlflow.mlflow-tutorial.svc.cluster.local:8080"
```

For code running outside the cluster (your laptop, CI/CD), use the Route URL:

```bash
export MLFLOW_TRACKING_URI="https://$(oc get route mlflow -n mlflow-tutorial -o jsonpath='{.spec.host}')"
```

Verify the connection:

```bash
python3 -c "import mlflow; mlflow.set_tracking_uri('${MLFLOW_TRACKING_URI}'); print(mlflow.search_experiments())"
```

Expected output:

```
[<Experiment: artifact_location='mlflow-artifacts:/0', creation_time=1720099200000, experiment_id='0', last_update_time=1720099200000, lifecycle_stage='active', name='Default', tags={}>]
```


### Step 7: Run an Experiment

The `scripts/mlflow_experiment.py` script trains a Random Forest classifier on the Iris dataset and logs everything to MLflow -- parameters, metrics, artifacts, and the model itself.

Review the script before running it:

```bash
cat scripts/mlflow_experiment.py
```

The script does the following:

1. Connects to the MLflow tracking server using `MLFLOW_TRACKING_URI`
2. Creates (or reuses) an experiment named `iris-classification`
3. Starts a run, logging:
   - **Parameters:** `n_estimators`, `max_depth`, `random_state`, `test_size`
   - **Metrics:** `accuracy`, `f1_score`, `precision`, `recall`
   - **Step metrics:** simulated training loss over 10 epochs
   - **Artifacts:** a `model_summary.txt` file with model details
   - **Tags:** `model_type`, `dataset`, `tutorial_lesson`
4. Prints the experiment URL for viewing results

Install the required Python packages (if not already in your workbench image):

```bash
pip install mlflow scikit-learn
```

Run the experiment:

```bash
python3 scripts/mlflow_experiment.py
```

Expected output:

```
MLflow Tracking URI: https://mlflow-mlflow-tutorial.apps.<cluster>
Experiment 'iris-classification' created with ID: 1

Starting training run...
  Logging parameters...
  Training Random Forest model...
  Logging metrics...
    accuracy: 0.9667
    f1_score: 0.9665
    precision: 0.9697
    recall: 0.9667
  Logging step metrics (simulated training loss)...
  Logging artifacts...
  Logging model...

Run completed successfully.
  Run ID: a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6
  Experiment URL: https://mlflow-mlflow-tutorial.apps.<cluster>/#/experiments/1

View your experiment at the URL above.
```

The exact metric values will vary slightly due to random splitting of the dataset.


### Step 8: Run a Second Experiment with Different Parameters

Run the script again with different hyperparameters to see how MLflow tracks multiple runs:

```bash
N_ESTIMATORS=200 MAX_DEPTH=10 python3 scripts/mlflow_experiment.py
```

Expected output:

```
MLflow Tracking URI: https://mlflow-mlflow-tutorial.apps.<cluster>
Experiment 'iris-classification' found with ID: 1

Starting training run...
  Logging parameters...
  Training Random Forest model...
  Logging metrics...
    accuracy: 0.9667
    f1_score: 0.9665
    precision: 0.9697
    recall: 0.9667
  Logging step metrics (simulated training loss)...
  Logging artifacts...
  Logging model...

Run completed successfully.
  Run ID: b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6a7
  Experiment URL: https://mlflow-mlflow-tutorial.apps.<cluster>/#/experiments/1

View your experiment at the URL above.
```

Now you have two runs in the same experiment with different parameters, making it easy to compare results in the MLflow UI.


### Step 9: View Results in the MLflow UI

Open the experiment URL from the script output in your browser. You will see:

1. **Experiment list** -- the `iris-classification` experiment appears alongside the default experiment
2. **Run table** -- both runs are listed with their parameters and metrics side by side
3. **Run detail** -- click a run to see:
   - Parameters tab: `n_estimators`, `max_depth`, `random_state`, `test_size`
   - Metrics tab: `accuracy`, `f1_score`, `precision`, `recall`, and the step-wise `training_loss` chart
   - Artifacts tab: `model_summary.txt` and the logged model

You can also compare runs by selecting both checkboxes and clicking "Compare":
- Parameter differences are highlighted
- Metrics are shown side by side
- The training loss chart overlays both runs

You can also query runs from the CLI:

```bash
python3 -c "
import mlflow
import os
mlflow.set_tracking_uri(os.environ['MLFLOW_TRACKING_URI'])
runs = mlflow.search_runs(experiment_names=['iris-classification'])
print(runs[['run_id', 'params.n_estimators', 'params.max_depth', 'metrics.accuracy', 'metrics.f1_score']].to_string())
"
```

Expected output:

```
                             run_id params.n_estimators params.max_depth  metrics.accuracy  metrics.f1_score
0  b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6a7                 200               10          0.966667          0.966547
1  a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6                 100                5          0.966667          0.966547
```


## Verification

Run through this checklist to confirm the lesson is complete:

1. **MLflow Operator is running:**

```bash
oc get pods -n redhat-ods-operator -l app.kubernetes.io/name=mlflow-operator --no-headers | grep Running
```

2. **MLflowServer CR exists and is ready:**

```bash
oc get mlflowserver mlflow -n mlflow-tutorial
```

3. **MLflow server pod is running:**

```bash
oc get pods -n mlflow-tutorial -l app=mlflow --no-headers | grep Running
```

4. **Route is accessible:**

```bash
MLFLOW_ROUTE=$(oc get route mlflow -n mlflow-tutorial -o jsonpath='{.spec.host}')
curl -sk -o /dev/null -w "%{http_code}" "https://${MLFLOW_ROUTE}/api/2.0/mlflow/experiments/search"
```

Expected: `200`

5. **Experiments were logged:**

```bash
curl -sk "https://${MLFLOW_ROUTE}/api/2.0/mlflow/experiments/search" | python3 -c "
import json, sys
data = json.load(sys.stdin)
experiments = data.get('experiments', [])
print(f'Total experiments: {len(experiments)}')
for exp in experiments:
    print(f'  - {exp[\"name\"]} (ID: {exp[\"experiment_id\"]})')
"
```

Expected output:

```
Total experiments: 2
  - Default (ID: 0)
  - iris-classification (ID: 1)
```


## Key Takeaways

- MLflow on OpenShift AI is a managed component -- enable `mlflowoperator` in the DSC, create an `MLflowServer` CR, and the operator deploys a fully configured tracking server with a Route, Service, and storage
- The `MLflowServer` CRD provides per-project MLflow instances, isolated by namespace -- no shared server contention
- Connection is via `MLFLOW_TRACKING_URI` pointing to the internal Service URL (in-cluster) or the Route URL (external) -- your existing MLflow code works unchanged
- MLflow tracks the full experiment hierarchy: experiments contain runs, runs contain parameters, metrics (including step-wise metrics), artifacts, and tags
- The MLflow UI is automatically exposed via an OpenShift Route with edge TLS termination -- no manual Ingress configuration
- MLflow integrates with Model Registry for the full lifecycle: experiment, identify best run, register model, deploy


## Cleanup

Remove the MLflowServer and the project:

```bash
oc delete mlflowserver mlflow -n mlflow-tutorial
oc delete project mlflow-tutorial
```

If you want to keep the project but remove only the MLflow server:

```bash
oc delete mlflowserver mlflow -n mlflow-tutorial
```


## Next Steps

In the next lesson, [L2-M5.2 -- Agent Tracing with MLflow](../2_agent_tracing/), you will use MLflow's tracing capabilities to instrument LLM agent workflows -- capturing tool calls, LLM invocations, retrieval steps, and chain-of-thought reasoning as structured traces viewable in the MLflow UI.
