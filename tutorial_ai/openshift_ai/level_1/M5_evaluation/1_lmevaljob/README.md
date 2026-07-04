# L1-M5.1 -- LMEvalJob -- Model Quality Benchmarking

**Level:** Foundations
**Duration:** 45 min

## Overview

After fine-tuning a model, you need to know whether it actually improved. Did accuracy go up on the tasks you care about? Did it regress on general knowledge? LMEvalJob is the OpenShift AI answer to this question: a Kubernetes-native CRD that wraps the industry-standard EleutherAI LM Evaluation Harness, letting you submit benchmark jobs as YAML manifests and collect results through familiar `oc` commands. In this lesson, you will benchmark both the base and fine-tuned Gemma4-e4b models against the same suite of tasks and compare the results side by side.

## Prerequisites

- Completed: L1-M2 (Model Serving) -- Gemma4-e4b base model deployed via InferenceService
- Completed: L1-M3.3 (Deploying the Fine-Tuned Model) -- Fine-tuned model stored on a PVC
- OpenShift AI installed with the `trustyai` component set to `Managed` in the `DataScienceCluster` CR
- GPU node available (evaluation loads the full model into GPU memory)
- Hugging Face account with access to `google/gemma-4-E4B-it` (accepted the model license)
- A Kubernetes Secret named `hf-token-secret` containing your Hugging Face token (created in L1-M2.2)

## K8s Context

On vanilla Kubernetes, there is no built-in way to evaluate language models. You would write a Job manifest that pulls the `lm-evaluation-harness` container image, mount the model weights, pass benchmark names as command-line arguments, and parse the JSON output from pod logs manually. Scaling this to multiple models or tracking results over time requires custom scripting. OpenShift AI replaces this with a purpose-built CRD (`LMEvalJob`) managed by the TrustyAI operator, which handles pod lifecycle, result extraction, and integration with the OpenShift AI dashboard.

## Concepts

### TrustyAI and LMEvalJob

TrustyAI is the responsible AI component of OpenShift AI. It provides model explainability, bias detection, and -- most relevant here -- model evaluation. When the `trustyai` component is enabled in the `DataScienceCluster` CR, the TrustyAI operator installs the `LMEvalJob` CRD and the controller that reconciles it.

The `LMEvalJob` CRD follows the same pattern as other OpenShift AI CRDs: you declare what you want (which model, which benchmarks, what resources), and the operator creates a pod that runs the evaluation and reports results back through the CR's `.status` field.

### EleutherAI LM Evaluation Harness (lm-eval)

Under the hood, `LMEvalJob` runs the [EleutherAI LM Evaluation Harness](https://github.com/EleutherAI/lm-evaluation-harness) (`lm-eval`). This is the most widely used open-source framework for evaluating language models. It supports 400+ benchmark tasks and provides a standardized evaluation pipeline:

1. Load the model (from Hugging Face, a local path, or an API endpoint)
2. For each task, generate prompts from the benchmark dataset
3. Run inference to get model predictions
4. Score the predictions against ground truth using task-specific metrics
5. Aggregate scores into a final result per task

The `LMEvalJob` CRD maps directly to `lm-eval` parameters:

| LMEvalJob Field | lm-eval Equivalent | Purpose |
|-----------------|-------------------|---------|
| `spec.model` | `--model` | Model type (`hf`, `vllm`, `local-completions`) |
| `spec.modelArgs` | `--model_args` | Model loading arguments (pretrained path, dtype) |
| `spec.taskList` | `--tasks` | List of benchmark tasks to run |
| `spec.limit` | `--limit` | Max samples per task (for faster runs) |
| `spec.batchSize` | `--batch_size` | Batch size for inference |
| `spec.logSamples` | `--log_samples` | Log individual predictions |

### Benchmarks Used in This Lesson

We evaluate both models on four benchmarks, chosen to cover different capabilities:

| Benchmark | What It Measures | Metric | Full Size | Tutorial Subset |
|-----------|-----------------|--------|-----------|-----------------|
| **MMLU** (abstract_algebra) | Academic knowledge across 57 subjects; we use one subject for speed | Accuracy | 100 questions | 50 |
| **HellaSwag** | Commonsense reasoning via sentence completion | Accuracy (normalized) | 10,042 | 50 |
| **ARC-Easy** | Grade-school science questions (easy subset of AI2 Reasoning Challenge) | Accuracy | 2,376 | 50 |
| **TruthfulQA MC2** | Tendency to produce truthful vs. popular-but-wrong answers | Accuracy (normalized) | 817 | 50 |

We limit each task to 50 samples (`spec.limit: "50"`) so the evaluation completes in minutes rather than hours. For production evaluations, remove the limit to run the full benchmark.

### Unitxt Integration

The LM Evaluation Harness integrates with [Unitxt](https://github.com/IBM/unitxt), an extensible framework for text processing and evaluation. Unitxt provides additional tasks beyond the built-in lm-eval tasks, with configurable prompt templates, data preprocessing, and metrics. To use a Unitxt task, prefix the task name with `unitxt/` in the `taskList`:

```yaml
taskList:
  - taskName: "unitxt/wnli[template=templates.classification.multi_class.relation.default,num_demos=5,demos_pool_size=100]"
```

This lesson uses the built-in lm-eval tasks. Unitxt tasks become useful when you need custom evaluation protocols or domain-specific benchmarks not included in the standard harness.

### LMEvalJob CRD Structure

The core fields of an `LMEvalJob` manifest:

```yaml
apiVersion: trustyai.opendatahub.io/v1alpha1
kind: LMEvalJob
metadata:
  name: eval-job-name
spec:
  model: hf                      # Model type: hf, vllm, local-completions
  modelArgs:                     # Key-value pairs for model loading
    - name: pretrained
      value: model-name-or-path
    - name: dtype
      value: float16
  taskList:                      # Benchmarks to run
    - taskName: task_name
      numFewShot: 0              # Number of few-shot examples
  limit: "50"                   # Samples per task (string)
  logSamples: true              # Log individual predictions
  batchSize: "auto"             # Batch size ("auto" or integer as string)
  pod:                           # Pod template for resource management
    container:
      env: [...]                 # Environment variables
      resources: {...}           # CPU, memory, GPU requests/limits
      volumeMounts: [...]        # Mount PVCs for local models
    volumes: [...]               # Volume definitions
```

The `model` field accepts several types:

| Model Type | Use Case | Example `modelArgs` |
|------------|----------|---------------------|
| `hf` | Load model directly using Hugging Face Transformers | `pretrained: google/gemma-4-E4B-it` |
| `vllm` | Load model using vLLM engine (for models that need vLLM-specific features) | `pretrained: google/gemma-4-E4B-it` |
| `local-completions` | Evaluate against a running inference endpoint | `model: gemma-4-e4b, base_url: http://service:8080/v1` |

For this lesson we use `hf` (Hugging Face Transformers) for both models, which loads weights directly into GPU memory within the evaluation pod.

## Step-by-Step

### Step 1: Verify TrustyAI Is Installed

Confirm that the `trustyai` component is active in your `DataScienceCluster`:

```bash
oc get datasciencecluster default-dsc -o jsonpath='{.spec.components.trustyai.managementState}'
```

Expected output:

```
Managed
```

Check that the TrustyAI operator pod is running:

```bash
oc get pods -n redhat-ods-applications -l app.kubernetes.io/part-of=trustyai
```

Expected output (pod name will differ):

```
NAME                                          READY   STATUS    RESTARTS   AGE
trustyai-service-operator-abc123-xyz          1/1     Running   0          5d
```

### Step 2: Explore the LMEvalJob CRD

Verify the LMEvalJob CRD is registered on the cluster:

```bash
oc api-resources | grep -i lmeval
```

Expected output:

```
lmevaljobs                        trustyai.opendatahub.io/v1alpha1   true    LMEvalJob
```

Explore the CRD spec to understand available fields:

```bash
oc explain lmevaljob.spec
```

Expected output (abbreviated):

```
KIND:     LMEvalJob
VERSION:  trustyai.opendatahub.io/v1alpha1

RESOURCE: spec <Object>

DESCRIPTION:
     LMEvalJobSpec defines the desired state of LMEvalJob

FIELDS:
   batchSize    <string>
   limit        <string>
   logSamples   <boolean>
   model        <string>
   modelArgs    <[]Object>
   pod          <Object>
   taskList     <[]Object>
```

Explore the task list structure:

```bash
oc explain lmevaljob.spec.taskList
```

Expected output:

```
KIND:     LMEvalJob
VERSION:  trustyai.opendatahub.io/v1alpha1

RESOURCE: taskList <[]Object>

FIELDS:
   numFewShot   <integer>
   taskName     <string>
```

### Step 3: Ensure the Hugging Face Token Secret Exists

The base model evaluation downloads `google/gemma-4-E4B-it` from Hugging Face, which requires authentication (Gemma is a gated model). Verify the secret exists:

```bash
oc get secret hf-token-secret -n gemma-model
```

Expected output:

```
NAME              TYPE     DATA   AGE
hf-token-secret   Opaque   1      10d
```

If the secret does not exist, create it now:

```bash
oc create secret generic hf-token-secret \
  --from-literal=token=hf_YOUR_TOKEN_HERE \
  -n gemma-model
```

Replace `hf_YOUR_TOKEN_HERE` with your actual Hugging Face access token.

### Step 4: Review the Base Model LMEvalJob Manifest

Examine the manifest before applying it:

```bash
cat manifests/lmevaljob-base.yaml
```

Key points to note:

- **`model: hf`** -- Loads the model using Hugging Face Transformers, not through a serving endpoint. The evaluation pod downloads the model weights and runs inference directly.
- **`modelArgs`** -- Specifies the Hugging Face model ID (`google/gemma-4-E4B-it`) and data type (`float16`).
- **`taskList`** -- Four benchmarks, each with an appropriate few-shot setting. MMLU uses 5-shot (standard for this benchmark); the others use 0-shot for simplicity.
- **`limit: "50"`** -- Restricts each task to 50 samples. This is critical for tutorial speed. A full run of HellaSwag alone (10,042 samples) would take hours.
- **`batchSize: "auto"`** -- Lets the harness determine the optimal batch size based on available GPU memory.
- **GPU request** -- 1 NVIDIA GPU with 24Gi memory, matching the Gemma4-e4b requirements.

### Step 5: Run the Base Model Evaluation

Apply the manifest:

```bash
oc apply -f manifests/lmevaljob-base.yaml
```

Expected output:

```
lmevaljob.trustyai.opendatahub.io/eval-base-gemma-4-e4b created
```

Check the job status:

```bash
oc get lmevaljob eval-base-gemma-4-e4b -n gemma-model
```

Expected output (initially):

```
NAME                     STATE      AGE
eval-base-gemma-4-e4b    Running    15s
```

### Step 6: Monitor the Base Model Evaluation

The LMEvalJob creates a pod that runs the evaluation. Watch the pod status:

```bash
oc get pods -n gemma-model -l app=lmeval-base --watch
```

Expected output progression:

```
NAME                              READY   STATUS    RESTARTS   AGE
eval-base-gemma-4-e4b-pod         0/1     Pending   0          5s
eval-base-gemma-4-e4b-pod         0/1     Init:0/1  0          10s
eval-base-gemma-4-e4b-pod         1/1     Running   0          30s
```

The evaluation goes through several phases visible in the pod logs:

1. **Model download** -- Downloads model weights from Hugging Face (first run only; cached after that)
2. **Model loading** -- Loads weights into GPU memory
3. **Task execution** -- Runs each benchmark sequentially
4. **Result aggregation** -- Computes final scores

Follow the logs to watch progress:

```bash
oc logs -f eval-base-gemma-4-e4b-pod -n gemma-model
```

You will see output like:

```
Running loglikelihood requests:  48%|████▊     | 24/50 [00:15<00:17, 1.53it/s]
Running loglikelihood requests: 100%|██████████| 50/50 [00:32<00:00, 1.56it/s]
```

The evaluation typically takes 10-20 minutes with `limit: "50"`, depending on GPU speed and model download time. Wait for the pod to reach `Completed` status:

```bash
oc get pods -n gemma-model -l app=lmeval-base
```

Expected output when finished:

```
NAME                              READY   STATUS      RESTARTS   AGE
eval-base-gemma-4-e4b-pod         0/1     Completed   0          15m
```

### Step 7: Extract Base Model Results

The results are stored in the `LMEvalJob` status. Extract them:

```bash
oc get lmevaljob eval-base-gemma-4-e4b -n gemma-model -o jsonpath='{.status.results}' | python3 -m json.tool
```

Expected output (scores will vary):

```json
{
  "mmlu_abstract_algebra": {
    "acc": 0.34,
    "acc_stderr": 0.068
  },
  "hellaswag": {
    "acc_norm": 0.62,
    "acc_norm_stderr": 0.069
  },
  "arc_easy": {
    "acc": 0.74,
    "acc_stderr": 0.062
  },
  "truthfulqa_mc2": {
    "acc_norm": 0.48,
    "acc_norm_stderr": 0.071
  }
}
```

You can also extract the full results (including per-sample logs) from the pod logs:

```bash
oc logs eval-base-gemma-4-e4b-pod -n gemma-model | tail -50
```

The final section of the log output contains the results table:

```
|    Tasks     |Version|Filter|n-shot| Metric |Value |   |Stderr|
|--------------|------:|------|-----:|--------|-----:|---|-----:|
|mmlu_abstract |      0|none  |     5|acc     |0.3400|+- |0.0680|
|  _algebra    |       |      |      |        |      |   |      |
|hellaswag     |      1|none  |     0|acc_norm|0.6200|+- |0.0690|
|arc_easy      |      1|none  |     0|acc     |0.7400|+- |0.0620|
|truthfulqa_mc2|      2|none  |     0|acc_norm|0.4800|+- |0.0710|
```

Record these values -- you will compare them against the fine-tuned model results.

### Step 8: Verify the Fine-Tuned Model PVC

Before running the fine-tuned model evaluation, confirm the PVC from L1-M3.3 exists and contains the merged model:

```bash
oc get pvc gemma-4-e4b-finetuned-pvc -n gemma-model
```

Expected output:

```
NAME                           STATUS   VOLUME     CAPACITY   ACCESS MODES   STORAGECLASS   AGE
gemma-4-e4b-finetuned-pvc      Bound    pv-...     50Gi       RWO            gp3            3d
```

If the PVC does not exist, go back to L1-M3.3 and complete the fine-tuned model deployment steps first. The PVC should contain the merged model (base weights + LoRA adapter merged together) at the root directory.

### Step 9: Review the Fine-Tuned Model LMEvalJob Manifest

Examine the fine-tuned model manifest:

```bash
cat manifests/lmevaljob-finetuned.yaml
```

Key differences from the base model manifest:

- **`modelArgs.pretrained`** -- Points to `/opt/models/gemma-4-e4b-finetuned`, a local path inside the pod rather than a Hugging Face model ID.
- **No `HF_TOKEN`** -- The model loads from the PVC, not from Hugging Face. No authentication needed.
- **`volumeMounts` and `volumes`** -- The PVC `gemma-4-e4b-finetuned-pvc` is mounted at `/opt/models/gemma-4-e4b-finetuned`.
- **Same `taskList` and `limit`** -- Identical benchmarks and sample limits as the base model. This is critical for a fair comparison.

### Step 10: Run the Fine-Tuned Model Evaluation

Apply the manifest:

```bash
oc apply -f manifests/lmevaljob-finetuned.yaml
```

Expected output:

```
lmevaljob.trustyai.opendatahub.io/eval-finetuned-gemma-4-e4b created
```

Monitor the pod:

```bash
oc get pods -n gemma-model -l app=lmeval-finetuned --watch
```

Since the fine-tuned model loads from a local PVC (no download), the model loading phase is faster. The evaluation itself takes a similar amount of time as the base model.

Wait for completion:

```bash
oc get lmevaljob eval-finetuned-gemma-4-e4b -n gemma-model
```

Expected output when finished:

```
NAME                          STATE       AGE
eval-finetuned-gemma-4-e4b    Complete    12m
```

### Step 11: Extract Fine-Tuned Model Results

```bash
oc get lmevaljob eval-finetuned-gemma-4-e4b -n gemma-model -o jsonpath='{.status.results}' | python3 -m json.tool
```

Expected output (scores will vary -- fine-tuning effects depend on your training data):

```json
{
  "mmlu_abstract_algebra": {
    "acc": 0.36,
    "acc_stderr": 0.069
  },
  "hellaswag": {
    "acc_norm": 0.61,
    "acc_norm_stderr": 0.069
  },
  "arc_easy": {
    "acc": 0.76,
    "acc_stderr": 0.061
  },
  "truthfulqa_mc2": {
    "acc_norm": 0.50,
    "acc_norm_stderr": 0.071
  }
}
```

### Step 12: Compare Base vs Fine-Tuned Results

List both jobs to confirm they both completed:

```bash
oc get lmevaljobs -n gemma-model
```

Expected output:

```
NAME                          STATE       AGE
eval-base-gemma-4-e4b         Complete    25m
eval-finetuned-gemma-4-e4b    Complete    12m
```

Extract both sets of results side by side. The following command pulls the results from both jobs and formats them:

```bash
echo "=== Base Model Results ==="
oc get lmevaljob eval-base-gemma-4-e4b -n gemma-model \
  -o jsonpath='{.status.results}' | python3 -m json.tool

echo ""
echo "=== Fine-Tuned Model Results ==="
oc get lmevaljob eval-finetuned-gemma-4-e4b -n gemma-model \
  -o jsonpath='{.status.results}' | python3 -m json.tool
```

Build a comparison table from your results. The following is an example -- your actual numbers will differ based on training data and model behavior:

| Benchmark | Metric | Base Model | Fine-Tuned | Delta |
|-----------|--------|-----------|------------|-------|
| mmlu_abstract_algebra | acc | 0.34 | 0.36 | +0.02 |
| hellaswag | acc_norm | 0.62 | 0.61 | -0.01 |
| arc_easy | acc | 0.74 | 0.76 | +0.02 |
| truthfulqa_mc2 | acc_norm | 0.48 | 0.50 | +0.02 |

When interpreting results:

- **Small deltas (< 0.02)** are within the margin of error for 50-sample subsets. Run the full benchmark (remove `limit`) for statistically significant comparisons.
- **Improvements on task-specific benchmarks** are expected if your fine-tuning data aligns with those tasks.
- **Regressions on general benchmarks** (like HellaSwag or MMLU) can indicate catastrophic forgetting -- the model lost general knowledge during fine-tuning. This is less common with LoRA than with full fine-tuning.
- **Standard error (`stderr`)** indicates the confidence interval. If the delta is smaller than the stderr, the difference is not statistically significant.

### Step 13: View Results in the OpenShift AI Dashboard (Optional)

If your OpenShift AI dashboard has TrustyAI integration enabled, you can view evaluation results visually:

1. Open the OpenShift AI dashboard.
2. Navigate to **Model Serving** in the left sidebar.
3. Select the `gemma-model` project.
4. Look for an **Evaluations** or **TrustyAI** section that shows completed LMEvalJobs.

The dashboard integration depends on your OpenShift AI version. If evaluations are not visible in the dashboard, the CLI approach in Steps 7 and 11 is the authoritative method for extracting results.

## Verification

Confirm you have completed the following:

1. TrustyAI operator is running and LMEvalJob CRD is registered:

```bash
oc get crd lmevaljobs.trustyai.opendatahub.io
```

Expected: the CRD exists with a creation timestamp.

2. Both evaluation jobs completed:

```bash
oc get lmevaljobs -n gemma-model -o custom-columns=NAME:.metadata.name,STATE:.status.state
```

Expected:

```
NAME                          STATE
eval-base-gemma-4-e4b         Complete
eval-finetuned-gemma-4-e4b    Complete
```

3. Both jobs produced results:

```bash
oc get lmevaljob eval-base-gemma-4-e4b -n gemma-model -o jsonpath='{.status.results}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Base model: {len(d)} tasks evaluated')"
oc get lmevaljob eval-finetuned-gemma-4-e4b -n gemma-model -o jsonpath='{.status.results}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Fine-tuned model: {len(d)} tasks evaluated')"
```

Expected:

```
Base model: 4 tasks evaluated
Fine-tuned model: 4 tasks evaluated
```

4. Evaluation pods ran to completion:

```bash
oc get pods -n gemma-model -l tutorial-module=M5 --no-headers | grep Completed | wc -l
```

Expected: `2`.

## K8s vs OpenShift AI Comparison

| Aspect | Kubernetes (manual) | OpenShift AI (LMEvalJob) |
|--------|-------------------|--------------------------|
| **Evaluation framework** | Install `lm-eval` in a container, write a Job manifest, parse JSON output | `LMEvalJob` CRD wraps `lm-eval` with declarative YAML |
| **Result storage** | Parse pod logs or mount a volume for output files | Results stored in `.status.results` on the CR, queryable via `oc get` |
| **Resource management** | Manually configure GPU requests in Job spec | Pod template in `spec.pod` with the same fields, but managed lifecycle |
| **Model loading** | Mount PVC or configure download in init container | `spec.model` and `spec.modelArgs` handle model loading declaratively |
| **Tracking** | No built-in tracking; use MLflow or custom solution | Jobs are Kubernetes resources: `oc get lmevaljobs` lists all evaluations |
| **Dashboard** | No UI | TrustyAI integration shows results in OpenShift AI dashboard |
| **Comparison** | Write scripts to diff JSON output files | Run two `LMEvalJob` resources with the same `taskList`, compare `.status.results` |
| **Reproducibility** | Save the Job YAML and hope the container image is pinned | LMEvalJob manifests in Git; operator pins the evaluation harness version |

## Key Takeaways

- **LMEvalJob is a CRD, not a script.** You declare what to evaluate (model, benchmarks, resources) in YAML, and the TrustyAI operator handles pod creation, execution, and result collection. Evaluation becomes a first-class Kubernetes resource.
- **Same benchmarks, same limits, same few-shot settings.** Fair comparison requires identical evaluation conditions. Always use the same `taskList`, `limit`, and `numFewShot` values when comparing two models.
- **Limit samples during development, remove limits for final evaluation.** The `limit` field lets you iterate quickly (50 samples in minutes), but production decisions should use full benchmarks (hours) for statistical significance.
- **Check for regression, not just improvement.** Fine-tuning can improve task-specific performance while degrading general capabilities (catastrophic forgetting). Always include general benchmarks like HellaSwag alongside task-specific ones.
- **Results live on the CR.** Unlike running `lm-eval` manually and parsing log files, `LMEvalJob` stores structured results in `.status.results`, making them queryable with `oc get` and `jsonpath`.

## Cleanup

Delete the evaluation jobs and their pods:

```bash
oc delete lmevaljob eval-base-gemma-4-e4b -n gemma-model
oc delete lmevaljob eval-finetuned-gemma-4-e4b -n gemma-model
```

Verify cleanup:

```bash
oc get lmevaljobs -n gemma-model
oc get pods -n gemma-model -l tutorial-module=M5
```

Both commands should return no resources. The fine-tuned model PVC (`gemma-4-e4b-finetuned-pvc`) is not deleted here -- it belongs to the M3 lesson.

## Next Steps

In [L1-M5.2 -- GuideLLM -- Inference Performance Benchmarking](../2_guidellm/), you will shift focus from model *quality* to model *performance*. GuideLLM measures the serving characteristics of your deployed model endpoint -- time to first token, inter-token latency, throughput, and SLO compliance -- answering the question "is this model fast enough?" rather than "is this model accurate enough?"
