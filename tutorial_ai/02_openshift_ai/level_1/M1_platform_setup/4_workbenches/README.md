# L1-M1.4 -- Workbenches

**Level:** Foundations
**Duration:** 30 min

## Overview

This lesson covers workbenches -- containerized IDE environments that run directly on the OpenShift cluster. You will learn how OpenShift AI uses the Kubeflow `Notebook` CRD to manage JupyterLab, VS Code, and RStudio instances with persistent storage, GPU access, and integrated data connections. By the end, you will have a running JupyterLab workbench connected to your S3 storage.

## Prerequisites

- Completed: [L1-M1.3 -- Dashboard and AI Hub Tour](../3_dashboard_ai_hub_tour/)
- Data Science Project `ai-tutorial` created with an S3 data connection
- OpenShift AI operator installed and running
- `oc` CLI authenticated to the cluster

## K8s Context

In vanilla Kubernetes, running a notebook IDE on the cluster requires deploying JupyterHub yourself. You manage the Helm chart, configure OAuth integration, build and maintain notebook images, create PVCs for persistent storage, set up GPU tolerations and device plugin configurations, and handle idle shutdown logic. Each of these is a separate concern that requires its own YAML and operational knowledge.

OpenShift AI replaces this entire stack with the Kubeflow `Notebook` CRD and a dashboard-driven creation flow. The platform manages the notebook lifecycle, storage provisioning, GPU assignment, authentication (via OpenShift OAuth), and idle shutdown -- all from a single form submission.

## Concepts

### What Is a Workbench?

A workbench is a containerized IDE running as a Pod on the OpenShift cluster. It provides a browser-accessible development environment -- JupyterLab, code-server (VS Code), or RStudio -- with direct access to cluster resources, GPUs, and data connections.

Under the hood, a workbench is managed by the Kubeflow Notebook Controller, which watches for `Notebook` custom resources (CRD: `kubeflow.org/v1`) and creates the corresponding Pod, Service, and Route. The controller also handles:

- **Lifecycle management** -- Starting, stopping, and restarting notebook Pods
- **Idle culling** -- Automatically stopping notebooks after a configurable period of inactivity to free cluster resources
- **OAuth proxy** -- Injecting an authentication sidecar so only the workbench owner can access it

When you create a workbench from the dashboard, OpenShift AI creates a `Notebook` CR that the controller reconciles into running infrastructure.

### Available IDEs

OpenShift AI supports three IDE types:

| IDE | Description | Use Case |
|-----|-------------|----------|
| **JupyterLab** | Interactive notebook environment with cell-based execution | Data exploration, model prototyping, visualization |
| **code-server** | VS Code running in the browser | General-purpose development, script writing, debugging |
| **RStudio** | R-focused IDE (Technology Preview) | Statistical analysis, R-based ML workflows |

JupyterLab is the most commonly used and the best supported. Code-server is useful when you prefer a VS Code workflow. RStudio is in Technology Preview and may have limitations.

### Pre-Built Notebook Images

Red Hat provides and maintains several notebook images, each optimized for different workloads:

| Image | Contents | When to Use |
|-------|----------|-------------|
| **Standard Data Science** | Python 3.11, pandas, scikit-learn, matplotlib, boto3 | General data science, no GPU needed |
| **CUDA** | Standard Data Science + CUDA toolkit + cuDNN | GPU workloads, custom frameworks |
| **PyTorch** | CUDA image + PyTorch pre-installed | PyTorch-based training and inference |
| **TensorFlow** | CUDA image + TensorFlow pre-installed | TensorFlow-based training and inference |
| **HabanaAI** | Intel Gaudi (Habana) accelerator support | Workloads on Intel Gaudi hardware |

Each image is based on Red Hat Universal Base Image (UBI), is tested against the OpenShift AI platform, and receives security updates from Red Hat. The images are stored in the internal registry under the `redhat-ods-applications` namespace.

### Custom Workbench Images

You can add custom notebook images through the dashboard Settings. Custom images must meet these requirements:

- **UBI-based** -- Built on Red Hat Universal Base Image for compatibility with OpenShift's security model
- **Health endpoint** -- Must expose a `/api` endpoint that returns HTTP 200 for the liveness/readiness probes
- **Non-root** -- Must run as a non-root user (OpenShift's `restricted` SCC is enforced)
- **Port 8888** -- Must listen on port 8888 (the default notebook port)

### Persistent Storage

When you create a workbench, the dashboard creates a PersistentVolumeClaim (PVC) and mounts it at `/opt/app-root/src` inside the container. This means:

- Notebooks, scripts, and data files persist across Pod restarts
- Stopping and restarting a workbench preserves all your work
- The PVC size is configurable at creation time (default varies by cluster)

The PVC is not deleted when you stop a workbench -- only when you explicitly delete the workbench from the dashboard.

### Data Connection Injection

Workbenches can reference data connections (the S3 Secrets created in L1-M1.3). When you attach a data connection to a workbench, the Secret's keys are injected as environment variables into the notebook container:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_S3_ENDPOINT`
- `AWS_S3_BUCKET`
- `AWS_DEFAULT_REGION`

This means your notebook code can use `boto3` or any S3 client library without hardcoding credentials:

```python
import boto3
import os

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["AWS_S3_ENDPOINT"],
    aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
)

# List buckets -- credentials come from the data connection
buckets = s3.list_buckets()
print([b["Name"] for b in buckets["Buckets"]])
```

## Step-by-Step

### Step 1: Understand the Notebook CRD

Before creating a workbench, examine the Notebook CRD to understand what the dashboard creates:

```bash
oc get crd notebooks.kubeflow.org -o jsonpath='{.spec.group}/{.spec.versions[0].name}'
```

Expected output:

```
kubeflow.org/v1
```

A Notebook CR has the following structure (simplified):

```yaml
apiVersion: kubeflow.org/v1
kind: Notebook
metadata:
  name: my-workbench
  namespace: ai-tutorial
  labels:
    app: my-workbench
    opendatahub.io/notebook-image: "true"
  annotations:
    notebooks.opendatahub.io/notebook-image-name: "CUDA"
    notebooks.opendatahub.io/notebook-image-order: "2"
spec:
  template:
    spec:
      containers:
        - name: my-workbench
          image: <notebook-image>
          ports:
            - containerPort: 8888
              name: notebook-port
              protocol: TCP
          resources:
            requests:
              cpu: "2"
              memory: 8Gi
            limits:
              cpu: "2"
              memory: 8Gi
          volumeMounts:
            - name: workbench-data
              mountPath: /opt/app-root/src
          env:
            - name: NOTEBOOK_ARGS
              value: "--NotebookApp.token='' --NotebookApp.password=''"
      volumes:
        - name: workbench-data
          persistentVolumeClaim:
            claimName: my-workbench-data
```

Key points:
- The `spec.template` follows the same structure as a Pod template in a Deployment
- The Notebook Controller creates a Pod, Service, and Route from this spec
- The OAuth proxy sidecar is injected automatically by the controller (not visible in the CR)
- Volume mounts provide persistent storage at `/opt/app-root/src`

### Step 2: Create a Workbench from the Dashboard

Navigate to **Data Science Projects** in the OpenShift AI dashboard and click on `ai-tutorial`.

Click **Create workbench** and fill in the form:

**Name and image:**
- **Name:** `ai-tutorial-workbench`
- **Notebook image:** Select **CUDA** (this includes the CUDA toolkit for GPU lessons later in the tutorial)
- **Version:** Select the latest available version

**Deployment size:**
- **Container size:** Custom
- **CPUs requested:** `2`
- **Memory requested:** `8Gi`
- **CPUs limit:** `2`
- **Memory limit:** `8Gi`

If your cluster has GPU nodes and accelerator profiles configured, you will see an **Accelerator** dropdown. For now, leave it as "None" -- GPU configuration is covered in L1-M1.5.

**Storage:**
- **Create new persistent storage**
- **Name:** `ai-tutorial-workbench-data`
- **Size:** `2Gi`

**Data connections:**
- Click **Use existing data connection**
- Select `minio-storage` (the data connection created in L1-M1.3)

Click **Create workbench**.

The dashboard creates the Notebook CR, and the Notebook Controller begins reconciling it. You should see the workbench status change from "Starting" to "Running" over 1-3 minutes as the container image is pulled and the Pod starts.

### Step 3: Access the Workbench

Once the workbench status shows "Running", click the **Open** link next to it.

A new browser tab opens with JupyterLab. You are automatically authenticated via OpenShift OAuth -- no separate login is required.

You should see:
- The JupyterLab interface with a file browser on the left
- A launcher tab with options to create notebooks, terminals, and text files
- The `/opt/app-root/src` directory contents in the file browser (initially empty)

Create a new Python 3 notebook from the launcher to verify the environment is working.

### Step 4: Verify the Environment

In a new notebook cell, run the following to verify the Python environment:

```python
import sys
print(f"Python version: {sys.version}")

import pandas as pd
print(f"pandas version: {pd.__version__}")

import sklearn
print(f"scikit-learn version: {sklearn.__version__}")
```

If you selected the CUDA image, check GPU availability:

```python
import torch
print(f"PyTorch version: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU device: {torch.cuda.get_device_name(0)}")
```

Note: `torch.cuda.is_available()` will return `False` if no GPU is assigned to this workbench. This is expected if you did not select an accelerator profile. GPU setup is covered in L1-M1.5.

Verify the S3 data connection environment variables are injected:

```python
import os

s3_vars = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_S3_ENDPOINT", "AWS_S3_BUCKET"]
for var in s3_vars:
    value = os.environ.get(var, "NOT SET")
    # Mask the secret key for safety
    if "SECRET" in var and value != "NOT SET":
        value = value[:3] + "***"
    print(f"{var} = {value}")
```

### Step 5: Examine the Created Resources

Switch back to the terminal and examine what the dashboard created:

```bash
# View the Notebook CR
oc get notebook -n ai-tutorial
```

Expected output:

```
NAME                     AGE
ai-tutorial-workbench    5m
```

Inspect the full Notebook CR:

```bash
oc get notebook ai-tutorial-workbench -n ai-tutorial -o yaml
```

This shows the complete spec including the container image, resource requests, volume mounts, and environment variables injected from the data connection Secret.

View the Pod created by the Notebook Controller:

```bash
oc get pods -n ai-tutorial -l app=ai-tutorial-workbench
```

Expected output:

```
NAME                      READY   STATUS    RESTARTS   AGE
ai-tutorial-workbench-0   2/2     Running   0          5m
```

Note the `2/2` in the READY column -- there are two containers in the Pod:
1. The notebook container (JupyterLab)
2. The OAuth proxy sidecar (handles authentication)

View the PVC:

```bash
oc get pvc -n ai-tutorial
```

Expected output:

```
NAME                          STATUS   VOLUME   CAPACITY   ACCESS MODES   STORAGECLASS   AGE
ai-tutorial-workbench-data    Bound    ...      2Gi        RWO            ...            5m
```

View the Route (how JupyterLab is accessible from your browser):

```bash
oc get route -n ai-tutorial -l app=ai-tutorial-workbench
```

### Step 6: (Optional) Create a Workbench via YAML Manifest

For automation or GitOps workflows, you can create workbenches directly from YAML. An example manifest is provided in `manifests/notebook.yaml` in this lesson directory.

To apply it:

```bash
# Review the manifest first
cat manifests/notebook.yaml

# Apply it (this would create a second workbench -- skip if resources are limited)
# oc apply -f manifests/notebook.yaml
```

The manifest in this lesson's `manifests/` directory shows the full structure of a Notebook CR with annotations, resource requests, volume mounts, and data connection references. Compare it to the YAML output from Step 5 to see how the dashboard-created CR matches the declarative YAML approach.

## Verification

Confirm the following:

1. The workbench is running:

```bash
oc get notebook ai-tutorial-workbench -n ai-tutorial -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
# Expected: True
```

2. The Pod has two containers (notebook + OAuth proxy):

```bash
oc get pod -n ai-tutorial -l app=ai-tutorial-workbench -o jsonpath='{.items[0].spec.containers[*].name}'
# Expected: ai-tutorial-workbench oauth-proxy
```

3. The PVC is bound:

```bash
oc get pvc ai-tutorial-workbench-data -n ai-tutorial -o jsonpath='{.status.phase}'
# Expected: Bound
```

4. JupyterLab is accessible in the browser via the "Open" link in the dashboard.

5. The S3 environment variables are available inside the notebook (verified in Step 4).

## K8s vs OpenShift AI Comparison

| Aspect | Kubernetes | OpenShift AI |
|--------|-----------|-------------|
| Notebook IDE | Deploy JupyterHub via Helm chart, manage lifecycle yourself | Managed workbenches via Notebook CRD, dashboard-driven creation |
| Authentication | Configure JupyterHub OAuth proxy manually, manage user mappings | SSO via OpenShift OAuth, automatic per-user isolation |
| Persistent storage | Manually create PVC, configure volume mounts in Pod spec | Dashboard creates and mounts PVC, configurable size at creation |
| GPU access | Install device plugin, configure tolerations and resource limits | Hardware profiles assign GPU via dashboard dropdown |
| Notebook images | Build, maintain, and update your own container images | Pre-built images (CUDA, PyTorch, TensorFlow) maintained by Red Hat |
| Data connections | Create Secrets manually, mount as env vars or volumes in Pod spec | Dashboard manages Secret creation and injection into workbench |
| Idle shutdown | Deploy and configure a separate culling service | Built-in culling controller with configurable timeout |
| Multi-IDE support | Deploy separate Helm charts for JupyterHub, code-server, RStudio | Single Notebook CRD supports all three IDE types |

## Key Takeaways

- Workbenches are containerized IDEs (JupyterLab, VS Code, RStudio) managed by the Kubeflow `Notebook` CRD (`kubeflow.org/v1`).
- The Notebook Controller creates a Pod, Service, and Route for each workbench, with an OAuth proxy sidecar for authentication.
- Pre-built notebook images include Standard Data Science, CUDA, PyTorch, TensorFlow, and HabanaAI -- all UBI-based and maintained by Red Hat.
- The dashboard handles PVC creation, data connection injection (S3 credentials as environment variables), and GPU assignment.
- Custom workbench images must be UBI-based, expose a `/api` health endpoint, run as non-root, and listen on port 8888.
- Workbenches can also be created from YAML manifests for automation and GitOps workflows.

## Cleanup

The workbench and project will be reused in subsequent lessons. Do not delete them.

To stop the workbench without deleting it (frees compute resources but preserves the PVC and configuration):

```bash
# Stop the workbench by scaling the notebook to zero
# This is equivalent to clicking "Stop" in the dashboard
oc annotate notebook ai-tutorial-workbench -n ai-tutorial \
  kubeflow-resource-stopped="stopped-by-user" --overwrite
```

To restart it later:

```bash
oc annotate notebook ai-tutorial-workbench -n ai-tutorial \
  kubeflow-resource-stopped- --overwrite
```

If you need to fully remove the workbench:

```bash
oc delete notebook ai-tutorial-workbench -n ai-tutorial
oc delete pvc ai-tutorial-workbench-data -n ai-tutorial
```

## Next Steps

Continue to [L1-M1.5 -- GPU and Hardware Setup](../5_gpu_hardware_setup/) to learn how to configure GPU access, create hardware profiles, and assign accelerators to workbenches and model serving deployments.
