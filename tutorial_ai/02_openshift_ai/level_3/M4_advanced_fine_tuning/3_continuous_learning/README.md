# L3-M4.3 -- Continuous Learning Patterns

**Level:** Expert
**Duration:** 1 hour

## Overview

Models degrade over time as the world changes -- user behavior shifts, new products appear, language patterns evolve, and the distribution of real-world inputs drifts away from what the model was originally trained on. Continuous learning closes the loop: collect feedback on model predictions, curate that feedback into training data, retrain automatically, evaluate against the current production model, and promote if the new version is better.

This lesson builds a complete continuous learning loop using OpenShift AI's pipeline, registry, and monitoring capabilities. You will deploy a feedback collection service, build a KFP retraining pipeline with replay buffers to prevent catastrophic forgetting, set up scheduled retraining with a CronJob, and implement drift monitoring to trigger retraining when model quality degrades.

## Prerequisites

- Completed: [L3-M4.2 -- Feature Stores with Feast](../2_feast/)
- Completed: [L2-M4.2 -- Building Pipelines with the KFP SDK](../../../../level_2/M4_pipelines/2_kfp_sdk/) (KFP v2 components, artifacts, pipeline submission)
- Completed: [L2-M5.1 -- MLflow on OpenShift AI](../../../../level_2/M5_observability/1_mlflow_openshift_ai/) (experiment tracking, model logging)
- Familiarity with fine-tuning concepts from [L1-M3.1](../../../../level_1/M3_fine_tuning/1_fine_tuning_concepts/) (LoRA, OSFT)
- OpenShift AI 3.4+ with pipeline server deployed and model registry enabled
- `oc` CLI authenticated with project-admin privileges
- Python 3.11+ with `kfp>=2.0`, `mlflow`, `fastapi`, `uvicorn` installed

## Concepts

### Why Models Degrade

A model trained today is a snapshot of the world at training time. Three forces erode its accuracy:

| Drift Type | Definition | Example |
|-----------|-----------|---------|
| **Data drift** | The distribution of inputs changes | Customer demographics shift; new product categories appear |
| **Concept drift** | The relationship between inputs and outputs changes | "Good customer" criteria evolve; sentiment around a brand shifts |
| **Feedback loops** | The model's own predictions influence future data | A recommendation model creates filter bubbles that skew future training data |

Without continuous learning, you only discover degradation when users complain or a quarterly audit reveals accuracy has dropped from 92% to 74%.

---

### The Five-Stage Continuous Learning Architecture

```
+------------------+     +------------------+     +------------------+
|  1. COLLECT      |     |  2. CURATE       |     |  3. RETRAIN      |
|  FEEDBACK        |---->|  TRAINING DATA   |---->|  MODEL           |
|                  |     |                  |     |                  |
|  - User ratings  |     |  - Filter noise  |     |  - LoRA / OSFT   |
|  - Corrections   |     |  - Deduplicate   |     |  - Replay buffer |
|  - Quality scores|     |  - Merge replay  |     |  - Mixed dataset |
+------------------+     +------------------+     +------------------+
                                                          |
                                                          v
+------------------+     +------------------+
|  5. PROMOTE      |     |  4. EVALUATE     |
|  (if better)     |<----|  NEW vs CURRENT  |
|                  |     |                  |
|  - Auto-promote  |     |  - Held-out set  |
|  - Human gate    |     |  - A/B metrics   |
|  - Canary rollout|     |  - Safety checks |
+------------------+     +------------------+
```

Each stage maps to an OpenShift AI component:

| Stage | OpenShift AI Component | Implementation |
|-------|----------------------|----------------|
| Collect | MLflow `log_assessment` + custom service | FastAPI endpoint stores user feedback |
| Curate | KFP pipeline component | Filter, deduplicate, merge with replay buffer |
| Retrain | Training Hub (KFP component) | LoRA fine-tuning on curated dataset |
| Evaluate | KFP component + LMEvalJob | Compare new model against production model |
| Promote | Model Registry (KFP component) | Register new version, update stage to Production |

---

### Feedback Collection Patterns

Feedback comes in two forms. **Explicit feedback** is what the user actively tells you -- thumbs up/down, star ratings, text corrections. **Implicit feedback** is inferred from behavior -- click-through rates, dwell time, task completion. Explicit feedback is higher signal but lower volume; implicit feedback is abundant but noisy. A production system collects both and weights them differently during curation.

---

### Retraining Triggers

| Retraining Trigger | When to Use | Pros | Cons |
|-------------------|-------------|------|------|
| **Scheduled (CronJob)** | Predictable workloads with steady feedback volume | Simple, predictable resource usage | May retrain unnecessarily or too late |
| **Threshold-based** | Quality-sensitive applications where drift matters | Retrains only when needed, efficient | Requires monitoring infrastructure |
| **Event-based** | High-feedback environments with rapid data accumulation | Most responsive to changes | Complex to configure, may trigger too often |

In practice, start with scheduled retraining (weekly or bi-weekly) and add threshold-based triggers as your monitoring matures.

---

### Evaluation Gates and Promotion Strategies

Before a retrained model reaches production, it must pass evaluation gates. **Automated gates** compare the new model against the current production model on a held-out test set -- accuracy must improve by a configurable margin, safety benchmarks must pass, and latency must not regress. **Human-in-the-loop gates** require a reviewer to inspect sample outputs and sign off before promotion. **Canary deployment** routes a small percentage of traffic (e.g., 10%) to the new model and gradually increases if metrics are stable.

---

### Preventing Catastrophic Forgetting

When you fine-tune on new feedback data alone, the model risks "forgetting" what it learned from the original training data -- it gets better at recent examples but worse at everything else. Three techniques mitigate this:

**Replay buffers** -- Mix old training data with new feedback (e.g., 70:30 ratio). Simplest approach and the one we implement in this lesson.

**OSFT (Orthogonal Subspace Fine-Tuning)** -- Constrain weight updates to a subspace orthogonal to the original model's, mathematically guaranteeing no interference. Covered in [L1-M3.1](../../../../level_1/M3_fine_tuning/1_fine_tuning_concepts/). More expensive but stronger guarantees.

**Elastic Weight Consolidation (EWC)** -- Penalize changes to important weights using the Fisher information matrix. Effective but adds memory overhead for storing the matrix.

---

### Quality Drift Monitoring

Drift monitoring answers: "Is the model still good enough, or do we need to retrain?" Key signals to track: rolling accuracy from feedback ratings (e.g., below 85% over a 7-day window), negative feedback rate (above 15%), prediction confidence trends, and response latency. When any metric breaches its threshold, the drift monitor triggers a retraining pipeline run.

## Step-by-Step

### Step 1: Set Up the Project and Prerequisites

Create a project for the continuous learning demo and verify that the pipeline server and model registry are available:

```bash
oc new-project continuous-learning-tutorial
```

Expected output:

```
Now using project "continuous-learning-tutorial" on server "https://api.your-cluster:6443".
```

Verify the pipeline server is accessible:

```bash
oc get dspa -n continuous-learning-tutorial
```

Expected output:

```
NAME   READY   AGE
dspa   True    5m
```

If no DSPA exists, refer to [L2-M4.1](../../../../level_2/M4_pipelines/1_pipeline_setup/) for setup instructions.

Verify the model registry is available:

```bash
oc get modelregistry -n odh-model-registries
```

Expected output:

```
NAME             AGE   AVAILABLE
model-registry   10d   true
```

---

### Step 2: Deploy the Feedback Collection Service

The feedback service provides a REST API for submitting user assessments of model predictions. Deploy it from the lesson manifests:

```bash
oc apply -f manifests/feedback-service.yaml
```

Expected output:

```
persistentvolumeclaim/feedback-data created
deployment.apps/feedback-service created
service/feedback-service created
```

Verify the service is running:

```bash
oc get pods -l app=feedback-service
```

Expected output:

```
NAME                               READY   STATUS    RESTARTS   AGE
feedback-service-7b8c9d4e5f-x2k9p  1/1     Running   0          30s
```

The feedback collector (`scripts/feedback_collector.py`) implements these endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/feedback` | POST | Submit feedback: prediction ID, rating (1-5), optional correction text |
| `/feedback/stats` | GET | Return aggregate statistics: total count, average rating, correction rate |
| `/feedback/export` | GET | Export all feedback since a given timestamp as JSON Lines |
| `/health` | GET | Health check |

Test the service by submitting sample feedback:

```bash
FEEDBACK_URL=$(oc get svc feedback-service -o jsonpath='{.metadata.name}').$(oc project -q).svc.cluster.local

# Submit some test feedback
oc run curl-test --rm -i --restart=Never --image=curlimages/curl -- \
  curl -s -X POST "http://${FEEDBACK_URL}:8080/feedback" \
  -H "Content-Type: application/json" \
  -d '{
    "prediction_id": "pred-001",
    "model_version": "v1.0",
    "rating": 4,
    "correction": null,
    "timestamp": "2025-01-15T10:30:00Z"
  }'
```

Expected output:

```json
{"status": "ok", "feedback_id": "fb-20250115-001"}
```

Submit additional entries with varying ratings and corrections to build up a dataset. Check aggregate statistics at any time with `GET /feedback/stats`.

---

### Step 3: Understand the Data Curation Component

Before retraining, raw feedback must be curated into training data. The curation step in the pipeline (`scripts/continuous_learning_pipeline.py`, component 2) performs: **filter** (remove ambiguous 3/5 ratings), **deduplicate** (keep latest per prediction), **quality score** (weight corrections higher), **format** (convert to instruction/response pairs), and **merge with replay buffer** (combine new feedback with original training data to prevent catastrophic forgetting).

The replay buffer ratio is configurable:

| Scenario | Replay Ratio (old:new) | Rationale |
|----------|----------------------|-----------|
| Stable domain, minor corrections | 80:20 | Preserve existing behavior |
| Moderate drift (default) | 70:30 | Balanced starting point |
| Major distribution shift | 50:50 | Aggressively adapt |
| Complete domain pivot | 30:70 | Nearly full retraining on new data |

---

### Step 4: Build and Submit the Retraining Pipeline

The retraining pipeline (`scripts/continuous_learning_pipeline.py`) orchestrates the full continuous learning loop as a KFP v2 pipeline with five components:

1. `collect_feedback` -- Query the feedback service for entries since the last training run
2. `curate_training_data` -- Filter, deduplicate, and merge with replay buffer
3. `retrain_model` -- Fine-tune using LoRA on the curated dataset
4. `evaluate_model` -- Compare new model against current production model on a held-out test set
5. `promote_model` -- Conditionally register and promote if metrics improve

Compile and submit the pipeline:

```bash
cd scripts/
python continuous_learning_pipeline.py --compile-only --output ../continuous_learning_pipeline.yaml
```

Expected output:

```
Pipeline compiled to ../continuous_learning_pipeline.yaml
```

Upload and trigger a pipeline run:

```bash
# Get the pipeline server route
ROUTE=$(oc get route ds-pipeline-dspa -n continuous-learning-tutorial -o jsonpath='{.spec.host}')
TOKEN=$(oc whoami -t)

python -c "
from kfp.client import Client
client = Client(host='https://${ROUTE}', existing_token='${TOKEN}')

# Upload the pipeline
client.upload_pipeline(
    pipeline_package_path='../continuous_learning_pipeline.yaml',
    pipeline_name='continuous-learning-pipeline',
    description='Feedback -> Curate -> Retrain -> Evaluate -> Promote'
)

# Create a run
run = client.create_run_from_pipeline_package(
    pipeline_file='../continuous_learning_pipeline.yaml',
    arguments={
        'feedback_service_url': 'http://feedback-service.continuous-learning-tutorial.svc.cluster.local:8080',
        'model_name': 'granite-3b-product-classifier',
        'replay_ratio': 0.7,
        'min_feedback_count': 10,
        'improvement_threshold': 0.01,
    },
    run_name='continuous-learning-manual-run',
    experiment_name='continuous-learning',
)
print(f'Run submitted: {run.run_id}')
"
```

Expected output:

```
Run submitted: a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

Monitor the pipeline run:

```bash
oc get pods -l pipeline/runid -w
```

Expected output (pods appear and complete sequentially):

```
NAME                                              READY   STATUS      RESTARTS   AGE
continuous-learning-manual-run-collect-feedback    0/1     Completed   0          2m
continuous-learning-manual-run-curate-data         0/1     Completed   0          1m
continuous-learning-manual-run-retrain-model       0/1     Completed   0          30s
continuous-learning-manual-run-evaluate-model      1/1     Running     0          10s
```

---

### Step 5: Set Up Scheduled Retraining with a CronJob

For automated retraining on a schedule, deploy the CronJob manifest:

```bash
oc apply -f manifests/retraining-cronjob.yaml
```

Expected output:

```
serviceaccount/retraining-sa created
role.rbac.authorization.k8s.io/retraining-pipeline-role created
rolebinding.rbac.authorization.k8s.io/retraining-pipeline-binding created
cronjob.batch/scheduled-retraining created
```

The CronJob runs weekly (every Sunday at 2:00 AM) and triggers the retraining pipeline via the KFP API. Verify the CronJob was created:

```bash
oc get cronjob scheduled-retraining
```

Expected output:

```
NAME                   SCHEDULE      SUSPEND   ACTIVE   LAST SCHEDULE   AGE
scheduled-retraining   0 2 * * 0     False     0        <none>          10s
```

To test the CronJob without waiting for the schedule, create a one-off Job from it:

```bash
oc create job --from=cronjob/scheduled-retraining test-retraining-run
```

Expected output:

```
job.batch/test-retraining-run created
```

Check the Job's logs to verify it triggered the pipeline:

```bash
oc logs job/test-retraining-run
```

Expected output:

```
Connecting to pipeline server at https://ds-pipeline-dspa-continuous-learning-tutorial...
Pipeline run submitted: continuous-learning-scheduled-20250115
Run ID: b2c3d4e5-f6a7-8901-bcde-f12345678901
```

---

### Step 6: Deploy Drift Monitoring

The drift monitor (`scripts/drift_monitor.py`) tracks model quality metrics over rolling time windows and triggers retraining when degradation exceeds a threshold. Key parameters: `--window-days` (default 7), `--accuracy-threshold` (default 0.85), `--negative-rate-threshold` (default 0.15), `--min-samples` (default 50).

Run it manually to check current model quality:

```bash
python scripts/drift_monitor.py \
  --feedback-url "http://feedback-service.continuous-learning-tutorial.svc.cluster.local:8080" \
  --window-days 7 \
  --accuracy-threshold 0.85 \
  --negative-rate-threshold 0.15 \
  --min-samples 50 \
  --pipeline-server "https://$(oc get route ds-pipeline-dspa -o jsonpath='{.spec.host}')" \
  --dry-run
```

Expected output (no drift):

```
=== Drift Monitor Report ===
Time window:         7 days (2025-01-08 to 2025-01-15)
Total feedback:      127
Average rating:      4.2 / 5.0
Rolling accuracy:    0.89 (threshold: 0.85)
Negative rate:       0.08 (threshold: 0.15)
Confidence trend:    stable

Status: NO DRIFT DETECTED
No retraining needed at this time.
```

When drift is detected, the output shows `Status: DRIFT DETECTED` with a list of breached thresholds, and (unless `--dry-run` is set) triggers a retraining pipeline run automatically.

For production, deploy the drift monitor as a CronJob (similar to the retraining CronJob) that runs hourly with `schedule: "0 * * * *"`, using the `retraining-sa` ServiceAccount.

---

### Step 7: Test the Full Continuous Learning Loop

Test the complete loop end-to-end by simulating model degradation. Submit a batch of negative feedback, then run the drift monitor to trigger retraining:

```bash
FEEDBACK_URL="http://feedback-service.continuous-learning-tutorial.svc.cluster.local:8080"

# Submit 20 negative feedback entries to simulate degradation
for i in $(seq 1 20); do
  oc run "feedback-batch-${i}" --rm -i --restart=Never --image=curlimages/curl -- \
    curl -s -X POST "${FEEDBACK_URL}/feedback" \
    -H "Content-Type: application/json" \
    -d "{
      \"prediction_id\": \"pred-batch-${i}\",
      \"model_version\": \"v1.0\",
      \"rating\": 1,
      \"correction\": \"Wrong category predicted\",
      \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
    }" 2>/dev/null
done
```

Run the drift monitor (with a low `--min-samples` for testing):

```bash
python scripts/drift_monitor.py \
  --feedback-url "${FEEDBACK_URL}" \
  --window-days 1 \
  --accuracy-threshold 0.85 \
  --min-samples 10 \
  --pipeline-server "https://$(oc get route ds-pipeline-dspa -o jsonpath='{.spec.host}')"
```

Expected output:

```
=== Drift Monitor Report ===
...
Status: DRIFT DETECTED
...
Action: Triggering retraining pipeline...
Pipeline run submitted: continuous-learning-drift-triggered-20250115
```

After the pipeline completes, verify the new model version in the registry:

```bash
oc get pods -l pipeline/runid --sort-by=.metadata.creationTimestamp | tail -5
# Expected: pipeline pods progressing through collect -> curate -> retrain -> evaluate -> promote
```

## Verification

Confirm all components of the continuous learning loop are operational:

```bash
# 1. Feedback service is running
oc get pods -l app=feedback-service
# Expected: 1/1 Running

# 2. Feedback data is being stored
oc run verify-feedback --rm -i --restart=Never --image=curlimages/curl -- \
  curl -s "http://feedback-service.continuous-learning-tutorial.svc.cluster.local:8080/feedback/stats"
# Expected: JSON with total_feedback > 0

# 3. CronJob is configured
oc get cronjob scheduled-retraining
# Expected: SCHEDULE = "0 2 * * 0", SUSPEND = False

# 4. At least one pipeline run completed
oc get pods -l pipeline/runid --field-selector=status.phase=Succeeded
# Expected: completed pipeline pods
```

## Key Takeaways

- Models degrade over time due to data drift, concept drift, and feedback loops -- continuous learning automates the detection and correction cycle rather than relying on periodic manual retraining.
- The five-stage architecture (collect, curate, retrain, evaluate, promote) maps cleanly onto OpenShift AI components: FastAPI feedback service, KFP pipeline components, Training Hub, LMEvalJob, and Model Registry.
- Replay buffers are the simplest and most effective defense against catastrophic forgetting -- mixing 70% original training data with 30% new feedback maintains baseline performance while incorporating improvements.
- Start with scheduled retraining (weekly CronJob) and add threshold-based triggers (drift monitoring) as your observability matures -- over-engineering triggers early adds complexity without proportional benefit.
- Evaluation gates are non-negotiable: never auto-promote a retrained model without comparing it against the current production model on a held-out test set. A model that scores well on new feedback but regresses on the original distribution is worse than no update at all.

## Cleanup

```bash
# Delete all tutorial resources via label selector
oc delete all -l tutorial-level=3,tutorial-module=M4
oc delete pvc feedback-data
oc delete cronjob drift-monitor 2>/dev/null
oc delete rolebinding retraining-pipeline-binding
oc delete role retraining-pipeline-role
oc delete serviceaccount retraining-sa
oc delete job test-retraining-run 2>/dev/null

# Or delete the entire project
oc delete project continuous-learning-tutorial
```

## Next Steps

In **[L3-M5.1 -- GitOps for ML](../../../M5_production/1_gitops/)**, you will bring everything together by managing model deployments, pipeline configurations, and continuous learning settings through GitOps. You will define the entire ML lifecycle -- from model serving configurations to retraining schedules -- as declarative YAML in a Git repository, with ArgoCD automatically reconciling your desired state with the cluster.
