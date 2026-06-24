# L3-M4.2 — OpenShift AI (RHOAI)

**Level:** Expert
**Duration:** 1 hr

## Overview

Red Hat OpenShift AI (RHOAI, formerly Red Hat OpenShift Data Science / RHODS) is an enterprise MLOps platform built on top of OpenShift that provides managed JupyterHub notebooks, model serving infrastructure (KServe and ModelMesh), Kubeflow-based data science pipelines, and GPU scheduling via the NVIDIA GPU Operator. If you have used standalone Kubeflow, JupyterHub, or KServe on vanilla Kubernetes, RHOAI bundles these with operator-managed lifecycle, integrated RBAC through OpenShift OAuth, and production-grade defaults -- all configured through a single `DataScienceCluster` Custom Resource.

This lesson walks through deploying and operating RHOAI in a production environment: installing the operator and its dependencies, provisioning notebooks and model-serving runtimes, building data science pipelines, configuring GPU scheduling, and handling failure modes you will encounter at scale.

## Prerequisites

- L3-M1 completed (Cluster Administration -- installation, upgrades, node management, resource quotas)
- L2-M2 completed (Operators -- OLM, OperatorHub, Subscriptions)
- L1-M6 completed (Monitoring & Logging -- Prometheus, alerting)
- OpenShift 4.12+ cluster with cluster-admin access (CRC or production cluster)
- At least 16 GB of RAM available on worker nodes for RHOAI components
- (Optional) NVIDIA GPU hardware for GPU scheduling exercises; CPU-only alternatives are provided for CRC

## K8s Context

On vanilla Kubernetes, building an ML platform means installing and integrating multiple independent projects:

- **JupyterHub** (via Helm or custom manifests) for notebook environments
- **KServe** or **Seldon Core** for model inference serving
- **Kubeflow Pipelines** for ML workflow orchestration
- **NVIDIA GPU Operator** (or manual device plugin installation) for GPU access
- **Prometheus + Grafana** for monitoring each component separately
- **Istio or Knative** as prerequisites for KServe

Each project has its own release cadence, CRDs, RBAC model, and upgrade path. You are responsible for compatibility between versions, security patching, and coordinating upgrades across all of them. Authentication typically requires configuring each component separately against your OIDC provider.

## Concepts

### DataScienceCluster CR -- The Single Control Plane

RHOAI is managed entirely through a single `DataScienceCluster` CR. This CR controls which components are deployed and how:

```
DataScienceCluster
  |
  +-- dashboard              (RHOAI Web Console)
  +-- workbenches             (JupyterHub / Notebook Controller)
  +-- datasciencepipelines    (Kubeflow Pipelines)
  +-- modelmeshserving        (ModelMesh inference)
  +-- kserve                  (KServe single-model serving)
  +-- codeflare               (Distributed computing -- Ray, MCAD)
  +-- ray                     (Ray cluster management)
  +-- kueue                   (Job queuing for batch/ML workloads)
  +-- trainingoperator        (Kubeflow Training Operator -- PyTorchJob, etc.)
```

Each component can be set to `Managed` (operator handles it), `Removed` (not deployed), or in some cases `Unmanaged` (user manages the component themselves).

### Architecture Overview

```
+-----------------------------------------------------------------------+
|                        OpenShift Cluster                              |
|                                                                       |
|  +-------------------+    +------------------------------------------+|
|  | RHOAI Operator    |    |  redhat-ods-applications namespace       ||
|  | (rhods-operator)  |--->|                                          ||
|  |                   |    |  +-------------+  +-----------------+    ||
|  +-------------------+    |  | Dashboard   |  | Notebook Ctrl   |    ||
|                           |  | (Web UI)    |  | (JupyterHub)    |    ||
|  +-------------------+    |  +------+------+  +--------+--------+    ||
|  | NVIDIA GPU        |    |         |                  |             ||
|  | Operator          |    |  +------+------+  +--------+--------+    ||
|  | (gpu-operator-    |    |  | Model       |  | DS Pipelines    |    ||
|  |  certified-addon) |    |  | Serving     |  | (Kubeflow)      |    ||
|  +-------------------+    |  | (KServe /   |  +--------+--------+    ||
|         |                 |  |  ModelMesh)  |           |            ||
|         v                 |  +------+------+           |            ||
|  +-------------------+    |         |                  |             ||
|  | Node Feature      |    +---+-----+------------------+-----+------+|
|  | Discovery (NFD)   |        |                        |      |      |
|  +-------------------+        v                        v      v      |
|                           +--------+  +-----------+ +------+ +-----+ |
|  +-------------------+    |  User  |  | S3/Minio  | | Mariadb| |Argo||
|  | OpenShift          |   | Project|  | (artifact | | (pipe- | |Wrkfl|
|  | Serverless         |   |(nb, inf|  |  store)   | | line   | |Srvr||
|  | (Knative Serving)  |   | pods)  |  +-----------+ | meta)  | +-----+
|  +-------------------+    +--------+                 +------+        |
|                                                                       |
+-----------------------------------------------------------------------+
```

### JupyterHub / Workbenches

RHOAI replaces raw JupyterHub with "Workbenches" -- managed notebook environments that:

- Use OpenShift OAuth for authentication (no separate JupyterHub login)
- Run as non-root pods that comply with OpenShift's `restricted` SCC
- Support custom notebook images (add libraries, GPU drivers, etc.)
- Persist user data via PVCs automatically
- Can attach data connections (S3, databases) as environment variables

### Model Serving: KServe vs ModelMesh

RHOAI offers two model serving runtimes:

| Aspect | KServe (Single-Model) | ModelMesh (Multi-Model) |
|--------|----------------------|------------------------|
| Deployment model | One InferenceService = one pod | Multiple models share a pod pool |
| Scale-to-zero | Yes (via Knative Serving) | No (always running) |
| Best for | Large models, GPU-heavy | Many small models, CPU inference |
| Dependencies | OpenShift Serverless (Knative) | None beyond RHOAI |
| Autoscaling | Knative autoscaler (KPA/HPA) | ModelMesh internal scaling |
| Protocol | REST / gRPC | REST / gRPC |

### Data Science Pipelines

Built on Kubeflow Pipelines v2, RHOAI pipelines provide:

- A pipeline server per data-science project (namespace-scoped)
- S3-compatible artifact storage (typically Minio or external S3)
- MariaDB for pipeline metadata
- Argo Workflows as the execution engine
- Python SDK (`kfp`) for pipeline authoring

### GPU Scheduling

The NVIDIA GPU Operator automates:

1. **Node Feature Discovery (NFD)** -- detects GPU hardware on nodes
2. **GPU device plugin** -- exposes `nvidia.com/gpu` resources to the scheduler
3. **GPU driver containers** -- installs NVIDIA drivers as containers (no host-level install)
4. **DCGM Exporter** -- Prometheus metrics for GPU utilization, temperature, memory
5. **MIG (Multi-Instance GPU)** support -- partition A100/H100 GPUs

Pods request GPUs via standard resource requests:

```yaml
resources:
  requests:
    nvidia.com/gpu: "1"
  limits:
    nvidia.com/gpu: "1"
```

## Step-by-Step

### Step 1: Install the RHOAI Operator and Dependencies

RHOAI requires the OpenShift Serverless operator (for KServe scale-to-zero) and the OpenShift Service Mesh operator (for model serving networking). Install them first.

```bash
# Create the required namespaces
oc apply -f manifests/namespace-redhat-ods-operator.yaml

# Install OpenShift Serverless Operator (dependency for KServe)
oc apply -f manifests/serverless-operator-subscription.yaml

# Wait for Serverless operator to be ready
oc wait --for=condition=CatalogSourcesUnhealthy=False \
  subscription/serverless-operator \
  -n openshift-serverless-operator \
  --timeout=300s 2>/dev/null || echo "Waiting for operator..."

# Install the RHOAI operator
oc apply -f manifests/rhoai-operator-subscription.yaml
```

Wait for the operator pods to become ready:

```bash
# Watch the operator namespace
oc get pods -n redhat-ods-operator -w
```

You should see `rhods-operator-*` pods in `Running` state.

### Step 2: Create the DataScienceCluster

Apply the `DataScienceCluster` CR. This is the central configuration that controls all RHOAI components.

```bash
oc apply -f manifests/datasciencecluster.yaml
```

Review the CR:

```yaml
# From manifests/datasciencecluster.yaml
apiVersion: datasciencecluster.opendatahub.io/v1
kind: DataScienceCluster
metadata:
  name: default-dsc
  labels:
    app: rhoai
    tutorial-level: "3"
    tutorial-module: "M4"
spec:
  components:
    dashboard:
      managementState: Managed
    workbenches:
      managementState: Managed
    datasciencepipelines:
      managementState: Managed
    modelmeshserving:
      managementState: Managed
    kserve:
      managementState: Managed
      serving:
        ingressGateway:
          certificate:
            type: SelfSigned
        managementState: Managed
        name: knative-serving
    codeflare:
      managementState: Managed
    ray:
      managementState: Managed
    kueue:
      managementState: Managed
    trainingoperator:
      managementState: Managed
```

Monitor the rollout:

```bash
# Check DSC status
oc get datasciencecluster default-dsc -o jsonpath='{.status.conditions[*].type}{"\n"}'

# Watch all pods come up in the RHOAI application namespace
oc get pods -n redhat-ods-applications -w
```

All components should reach `Running` status within 5-10 minutes.

### Step 3: Configure GPU Scheduling (NVIDIA GPU Operator)

If your cluster has NVIDIA GPUs, install the GPU Operator.

```bash
# Install Node Feature Discovery operator first
oc apply -f manifests/nfd-operator-subscription.yaml

# Wait for NFD to be ready, then create the NFD instance
oc wait --for=condition=Available deployment/nfd-controller-manager \
  -n openshift-nfd --timeout=300s
oc apply -f manifests/nfd-instance.yaml

# Install the NVIDIA GPU Operator
oc apply -f manifests/gpu-operator-subscription.yaml

# Once the operator is running, create the ClusterPolicy
oc apply -f manifests/gpu-clusterpolicy.yaml
```

Verify GPU discovery:

```bash
# Check that NFD has labeled GPU nodes
oc get nodes -l feature.node.kubernetes.io/pci-10de.present=true

# Verify GPU resources are schedulable
oc get node <gpu-node-name> -o jsonpath='{.status.allocatable}' | python3 -m json.tool | grep nvidia
```

Expected output shows `nvidia.com/gpu` in allocatable resources.

> **CRC note:** CRC does not have GPUs. For the GPU exercises, you can verify the operator installation and CR creation without actual GPU hardware. The operator will report `NodeNotReady` for GPU components, which is expected. All other RHOAI features (notebooks, pipelines, CPU model serving) work on CRC.

### Step 4: Create a Data Science Project and Workbench

Create a project (namespace) for data science work, then launch a notebook workbench.

```bash
# Create the data science project
oc apply -f manifests/ds-project.yaml

# Create a PVC for notebook storage
oc apply -f manifests/notebook-pvc.yaml

# Create data connection secret (for S3/Minio access)
oc apply -f manifests/data-connection-secret.yaml

# Launch a workbench (notebook)
oc apply -f manifests/workbench.yaml
```

The workbench manifest creates a `Notebook` CR (from the Kubeflow Notebook Controller CRD) that provisions a JupyterLab pod:

```yaml
# Key parts of manifests/workbench.yaml
apiVersion: kubeflow.org/v1
kind: Notebook
metadata:
  name: ml-workbench
  namespace: ds-project
  labels:
    app: ml-workbench
    opendatahub.io/dashboard: "true"
spec:
  template:
    spec:
      containers:
        - name: ml-workbench
          image: image-registry.openshift-image-registry.svc:5000/redhat-ods-applications/jupyter-datascience-notebook:2024.1
          resources:
            requests:
              cpu: "1"
              memory: 4Gi
            limits:
              cpu: "2"
              memory: 8Gi
```

Access the notebook through the RHOAI Dashboard:

```bash
# Get the RHOAI Dashboard URL
oc get route rhods-dashboard -n redhat-ods-applications -o jsonpath='{.spec.host}'
```

Navigate to: `https://<dashboard-url>` and log in with your OpenShift credentials.

### Step 5: Deploy a Model with KServe (Single-Model Serving)

Deploy a scikit-learn model using KServe's InferenceService. This example uses a pre-trained model stored in S3-compatible storage.

```bash
# Create a ServingRuntime for sklearn models
oc apply -f manifests/kserve-serving-runtime.yaml

# Deploy the InferenceService
oc apply -f manifests/kserve-inference-service.yaml
```

Review the InferenceService manifest:

```yaml
# From manifests/kserve-inference-service.yaml
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  name: sklearn-iris
  namespace: ds-project
  labels:
    app: sklearn-iris
    tutorial-level: "3"
    tutorial-module: "M4"
  annotations:
    serving.kserve.io/deploymentMode: Serverless
spec:
  predictor:
    model:
      modelFormat:
        name: sklearn
        version: "1"
      runtime: kserve-sklearnserver
      storageUri: "s3://models/sklearn/iris"
      resources:
        requests:
          cpu: "500m"
          memory: 512Mi
        limits:
          cpu: "1"
          memory: 1Gi
```

Monitor the rollout:

```bash
# Check InferenceService status
oc get inferenceservice sklearn-iris -n ds-project

# Watch for the Knative service to become ready
oc get ksvc -n ds-project -w
```

When the `READY` column shows `True`, send a test inference:

```bash
# Get the inference endpoint URL
ISVC_URL=$(oc get inferenceservice sklearn-iris -n ds-project \
  -o jsonpath='{.status.url}')

# Send a prediction request
curl -k "${ISVC_URL}/v1/models/sklearn-iris:predict" \
  -H "Content-Type: application/json" \
  -d '{"instances": [[5.1, 3.5, 1.4, 0.2]]}'
```

Expected response:

```json
{"predictions": [0]}
```

### Step 6: Deploy a Model with ModelMesh (Multi-Model Serving)

For scenarios with many small models, ModelMesh is more efficient because it shares a pool of pods across models.

```bash
# Create a ModelMesh ServingRuntime
oc apply -f manifests/modelmesh-serving-runtime.yaml

# Deploy an InferenceService using ModelMesh
oc apply -f manifests/modelmesh-inference-service.yaml
```

The key difference is the annotation that selects ModelMesh:

```yaml
# From manifests/modelmesh-inference-service.yaml
metadata:
  annotations:
    serving.kserve.io/deploymentMode: ModelMesh
```

Check model status:

```bash
# List ModelMesh models
oc get inferenceservice -n ds-project -l serving.kserve.io/deploymentMode=ModelMesh

# Check the model is loaded
oc get inferenceservice sklearn-mm -n ds-project \
  -o jsonpath='{.status.modelStatus.states.activeModelState}'
```

The model state should show `Loaded`.

### Step 7: Create a Data Science Pipeline

Deploy a pipeline server and run a sample pipeline.

```bash
# Deploy the DataSciencePipelinesApplication CR
oc apply -f manifests/dspa.yaml
```

The DSPA creates the pipeline infrastructure in your project:

```bash
# Verify pipeline components
oc get pods -n ds-project -l app=ds-pipeline

# Expected pods:
# ds-pipeline-*                  (API server)
# ds-pipeline-persistenceagent-* (syncs run status)
# ds-pipeline-scheduledworkflow-* (cron pipeline runs)
# mariadb-*                      (metadata store)
# minio-*                        (artifact store, if using internal Minio)
```

Create and run a pipeline:

```bash
# Apply a sample pipeline run
oc apply -f manifests/sample-pipeline-run.yaml

# Watch pipeline execution
oc get workflow -n ds-project -w
```

You can also submit pipelines through the RHOAI Dashboard UI or programmatically using the `kfp` Python SDK from a workbench notebook.

### Step 8: Configure Production Monitoring and Alerting

Set up monitoring for RHOAI components and GPU metrics.

```bash
# Deploy ServiceMonitor for RHOAI metrics
oc apply -f manifests/rhoai-servicemonitor.yaml

# Deploy GPU monitoring dashboard and alerts (if GPUs present)
oc apply -f manifests/gpu-prometheus-rules.yaml
```

Key metrics to monitor:

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| `DCGM_FI_DEV_GPU_UTIL` | GPU utilization % | < 10% for 1h (underutilized) |
| `DCGM_FI_DEV_MEM_COPY_UTIL` | GPU memory bandwidth | > 95% sustained |
| `DCGM_FI_DEV_GPU_TEMP` | GPU temperature (C) | > 85C |
| `kserve_request_latency_seconds` | Inference latency | p99 > 5s |
| `modelmesh_loaded_model_size_bytes` | ModelMesh model cache | > 80% capacity |
| `notebook_idle_seconds` | Idle notebook time | > 3600s (auto-cull) |

## Verification

Run through this checklist to verify the full RHOAI installation:

```bash
# 1. DataScienceCluster is healthy
oc get datasciencecluster default-dsc \
  -o jsonpath='{range .status.conditions[*]}{.type}={.status}{"\n"}{end}'

# Expected: all conditions show True

# 2. RHOAI Dashboard is accessible
DASHBOARD_URL=$(oc get route rhods-dashboard \
  -n redhat-ods-applications -o jsonpath='{.spec.host}')
echo "Dashboard: https://${DASHBOARD_URL}"
curl -sk "https://${DASHBOARD_URL}" | grep -q "Open Data Hub" && echo "Dashboard OK"

# 3. Workbench notebook pod is running
oc get notebook ml-workbench -n ds-project \
  -o jsonpath='{.status.conditions[-1].type}={.status.conditions[-1].status}'
# Expected: Running=True

# 4. KServe InferenceService is ready
oc get inferenceservice sklearn-iris -n ds-project \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
# Expected: True

# 5. Pipeline server is running
oc get dspa ds-pipeline-dspa -n ds-project \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
# Expected: True

# 6. GPU nodes detected (if GPUs present)
oc get nodes -o json | python3 -c "
import json, sys
nodes = json.load(sys.stdin)
for n in nodes['items']:
  gpus = n['status']['allocatable'].get('nvidia.com/gpu', '0')
  if gpus != '0':
    print(f\"{n['metadata']['name']}: {gpus} GPU(s)\")
" 2>/dev/null || echo "No GPU nodes detected (expected on CRC)"
```

Access the RHOAI Dashboard in your browser and verify:

1. The Dashboard loads and shows the "Data Science Projects" page
2. Your `ds-project` appears in the project list
3. The workbench shows as "Running"
4. Model Serving shows the deployed models
5. Pipelines section shows the pipeline server and any executed runs

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift AI (RHOAI) |
|--------|-----------|----------------------|
| Notebook environment | Install JupyterHub via Helm; configure auth separately | Managed workbenches with OpenShift OAuth integration |
| Model serving | Install KServe + Knative + Istio manually; version compatibility is your problem | KServe and ModelMesh managed by operator; tested version matrix |
| ML pipelines | Install Kubeflow Pipelines; manage Argo, Minio, MySQL separately | DataSciencePipelinesApplication CR deploys full stack per project |
| GPU scheduling | Install NVIDIA device plugin + driver containers + NFD manually | GPU Operator automates entire stack with ClusterPolicy CR |
| Security model | Pods run as root by default; must add PodSecurity or OPA | Non-root by default (SCC `restricted`); notebook images built for non-root |
| Monitoring | Install Prometheus exporters per component | DCGM exporter + ServiceMonitors auto-configured by operators |
| Lifecycle management | Upgrade each component independently; test compatibility | Single operator upgrade covers all components; tested matrix |
| Multi-tenancy | Manual RBAC per component | Project-scoped resources; RHOAI Dashboard enforces namespace isolation |
| Configuration | Multiple Helm values files + CRDs across namespaces | Single `DataScienceCluster` CR controls everything |
| Idle resource reclaim | Build custom culling logic for JupyterHub | Built-in notebook idle culler with configurable timeout |

## Key Takeaways

- **Single CR, entire platform**: The `DataScienceCluster` CR is your single source of truth for the RHOAI platform. Changing a component from `Managed` to `Removed` cleanly tears it down; switching back reinstalls it. This eliminates the "which version of KServe works with which Knative?" problem.

- **KServe vs ModelMesh is an architectural decision**: Use KServe (Serverless mode) for large models that benefit from scale-to-zero and dedicated resources. Use ModelMesh for serving many small models efficiently with shared infrastructure. You can run both simultaneously in the same cluster.

- **GPU scheduling requires a three-layer stack**: Node Feature Discovery detects hardware, the GPU Operator installs drivers and device plugins, and Kubernetes scheduling uses `nvidia.com/gpu` resource requests. A failure at any layer silently prevents GPU access -- always verify the full chain.

- **Data science pipelines are namespace-scoped**: Each `DataSciencePipelinesApplication` creates an independent pipeline server in its namespace. This provides multi-tenant isolation but means pipeline definitions cannot be shared across projects without re-importing them.

- **Monitor idle notebooks aggressively**: Notebook pods consume significant memory (4-8 GB typically). Configure the idle culler (via RHOAI Dashboard admin settings) to stop notebooks after 1 hour of inactivity in production. CRC environments should use an even shorter timeout.

## Failure Modes and Recovery

### Operator Installation Failures

**Symptom:** RHOAI operator pod is in `CrashLoopBackOff`.

**Diagnosis:**
```bash
oc logs -n redhat-ods-operator deployment/rhods-operator --tail=50
oc get csv -n redhat-ods-operator
```

**Common causes and fixes:**
- Missing dependency operator (Serverless, Service Mesh) -- install the prerequisite operators first
- Insufficient cluster resources -- RHOAI components need at least 8 GB of available memory across worker nodes
- OLM catalog source not reachable -- check network/proxy settings with `oc get catalogsource -n openshift-marketplace`

### Notebook Fails to Start

**Symptom:** Workbench stays in "Starting" state indefinitely.

**Diagnosis:**
```bash
oc get events -n ds-project --sort-by=.lastTimestamp | tail -20
oc describe notebook ml-workbench -n ds-project
oc get pods -n ds-project -l notebook-name=ml-workbench -o yaml
```

**Common causes:**
- PVC cannot be provisioned (check StorageClass availability)
- Image pull error (internal registry or network issue)
- Insufficient resources (check ResourceQuota in the namespace)
- SCC violation (custom notebook image tries to run as root)

**Recovery:**
```bash
# Delete and recreate the notebook
oc delete notebook ml-workbench -n ds-project
# Fix the underlying issue, then re-apply
oc apply -f manifests/workbench.yaml
```

### KServe InferenceService Not Ready

**Symptom:** InferenceService stays in `Unknown` or `False` ready state.

**Diagnosis:**
```bash
oc get inferenceservice sklearn-iris -n ds-project -o yaml
oc get ksvc -n ds-project
oc get pods -n ds-project -l serving.kserve.io/inferenceservice=sklearn-iris
oc logs -n ds-project -l serving.kserve.io/inferenceservice=sklearn-iris --tail=30
```

**Common causes:**
- Knative Serving not installed or not ready (check `oc get knativeserving -A`)
- Model storage URI unreachable (S3 credentials incorrect or bucket missing)
- Insufficient resources for the predictor pod
- Certificate issues with the serving gateway

**Recovery:**
```bash
# Check and fix Knative Serving
oc get knativeserving knative-serving -n knative-serving -o jsonpath='{.status.conditions[*].message}'

# Delete and recreate the InferenceService after fixing the cause
oc delete inferenceservice sklearn-iris -n ds-project
oc apply -f manifests/kserve-inference-service.yaml
```

### GPU Not Visible to Pods

**Symptom:** Pod requesting `nvidia.com/gpu` stays in `Pending`.

**Diagnosis:**
```bash
# Check NFD labels
oc get nodes -l feature.node.kubernetes.io/pci-10de.present=true

# Check GPU operator pods
oc get pods -n nvidia-gpu-operator

# Check device plugin logs
oc logs -n nvidia-gpu-operator daemonset/nvidia-device-plugin-daemonset --tail=30

# Verify allocatable resources
oc describe node <node-name> | grep -A5 "Allocatable"
```

**Common causes:**
- NFD not detecting GPU hardware (driver issue at host level)
- GPU driver container failed to build (kernel version mismatch)
- Device plugin daemonset not running on GPU nodes
- All GPUs already allocated to other pods

**Recovery:**
```bash
# Restart the GPU operator components
oc delete clusterpolicy gpu-cluster-policy
oc apply -f manifests/gpu-clusterpolicy.yaml

# Force NFD re-scan
oc delete pods -n openshift-nfd -l app=nfd-worker
```

### Pipeline Run Failures

**Symptom:** Pipeline run shows `Failed` status.

**Diagnosis:**
```bash
# Check the Argo Workflow status
oc get workflow -n ds-project
oc describe workflow <workflow-name> -n ds-project

# Check individual step pods
oc get pods -n ds-project -l workflows.argoproj.io/workflow=<workflow-name>
oc logs -n ds-project <failed-pod-name> --all-containers
```

**Common causes:**
- S3/Minio artifact storage unreachable
- Pipeline step image not available
- Insufficient resources for pipeline step pods
- ServiceAccount missing required permissions

## Cleanup

```bash
# Remove the data science project and all its resources
oc delete namespace ds-project

# Remove the DataScienceCluster
oc delete datasciencecluster default-dsc

# Remove GPU Operator resources (if installed)
oc delete clusterpolicy gpu-cluster-policy 2>/dev/null
oc delete csv -n nvidia-gpu-operator -l operators.coreos.com/gpu-operator-certified.nvidia-gpu-operator 2>/dev/null
oc delete subscription gpu-operator-certified -n nvidia-gpu-operator 2>/dev/null
oc delete namespace nvidia-gpu-operator 2>/dev/null

# Remove NFD resources (if installed)
oc delete nodefeaturediscovery nfd-instance -n openshift-nfd 2>/dev/null
oc delete csv -n openshift-nfd -l operators.coreos.com/nfd.openshift-nfd 2>/dev/null
oc delete subscription nfd -n openshift-nfd 2>/dev/null
oc delete namespace openshift-nfd 2>/dev/null

# Remove the RHOAI operator
oc delete csv -n redhat-ods-operator -l operators.coreos.com/rhods-operator.redhat-ods-operator 2>/dev/null
oc delete subscription rhods-operator -n redhat-ods-operator 2>/dev/null
oc delete namespace redhat-ods-operator 2>/dev/null
oc delete namespace redhat-ods-applications 2>/dev/null
oc delete namespace redhat-ods-monitoring 2>/dev/null

# Remove Serverless operator (if installed for this lesson)
oc delete csv -n openshift-serverless-operator -l operators.coreos.com/serverless-operator.openshift-serverless-operator 2>/dev/null
oc delete subscription serverless-operator -n openshift-serverless-operator 2>/dev/null

# Clean up CRDs (optional -- only if no other RHOAI instances exist)
oc get crd | grep -E 'opendatahub|kserve|datasciencecluster' | awk '{print $1}' | xargs oc delete crd 2>/dev/null
```

## Next Steps

In **L3-M4.3 -- Stateful Workloads at Scale**, you will learn how to run operator-managed databases (CrunchyData PostgreSQL, Strimzi Kafka) and other stateful workloads with proper storage performance tuning, backup strategies, and high-availability configurations -- skills that complement the model storage and pipeline persistence you configured in this lesson.
