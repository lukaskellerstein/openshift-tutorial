# L1-M1.3 -- Dashboard and AI Hub Tour

**Level:** Foundations
**Duration:** 20 min

## Overview

This lesson walks through the OpenShift AI dashboard and the AI Hub (Gen AI Studio), the two primary interfaces data scientists and ML engineers use daily. You will learn how to navigate the dashboard, create a Data Science Project, configure data connections, and understand the user roles that control platform access.

## Prerequisites

- Completed: [L1-M1.2 -- Installing OpenShift AI](../2_installing_openshift_ai/)
- OpenShift AI operator installed and running
- Access to the OpenShift cluster (Developer Sandbox or self-managed)
- `oc` CLI authenticated to the cluster

## K8s Context

In vanilla Kubernetes, there is no built-in ML dashboard. The closest equivalent is the Kubeflow Central Dashboard, which provides basic navigation to notebooks, pipelines, and experiments. Project creation means running `kubectl create namespace`, and there is no concept of managed data connections or model catalogs. Everything -- from RBAC to storage configuration to model management -- requires manual YAML and CLI work.

OpenShift AI replaces this fragmented experience with a unified dashboard that handles project creation, data connections, model serving, and user management through a single interface.

## Concepts

### The OpenShift AI Dashboard

The OpenShift AI dashboard is a web application deployed in the `redhat-ods-applications` namespace. It provides two main areas:

1. **Core Dashboard** -- The traditional OpenShift AI interface with Data Science Projects, Model Serving, Data Science Pipelines, and Settings.
2. **AI Hub (Gen AI Studio)** -- Introduced in OpenShift AI 3.3, this is a dedicated section for generative AI workflows including a Model Catalog, Model Registry, Deployments, Endpoints, and an interactive Playground.

The dashboard is the primary interface for data scientists. While everything it does can also be accomplished with `oc` commands and YAML manifests, the dashboard handles the orchestration of multiple Kubernetes resources (Namespaces, Secrets, PVCs, CRDs) behind simple form submissions.

### Dashboard Navigation

The main navigation menu includes:

- **Applications** -- Links to enabled applications (JupyterHub, etc.) and quick-start guides
- **Data Science Projects** -- Create and manage projects (OpenShift namespaces with AI-specific metadata and labels)
- **Data Science Pipelines** -- Manage ML pipeline servers and pipeline runs (Kubeflow Pipelines integration)
- **Model Serving** -- View and manage deployed models across all projects
- **Resources** -- Documentation links, tutorials, and how-to guides

### AI Hub / Gen AI Studio

AI Hub is the generative AI section of the dashboard, available in OpenShift AI 3.3 and later. It consolidates GenAI-specific features into a dedicated area:

- **Model Catalog** -- Browse Red Hat-validated models (Granite, Llama, Mistral, and others). Each model card shows size, license, supported tasks, and deployment instructions. You can deploy directly from the catalog.
- **Model Registry** -- A centralized registry for tracking model versions, metadata, and lineage across teams and projects.
- **Deployments** -- View all active model deployments across the cluster.
- **Endpoints** -- See the API endpoints for deployed models, with connection details and usage examples.
- **Playground** -- An interactive chat interface for testing deployed models with different prompts, parameters (temperature, top-p, max tokens), and system instructions. No code required.

### Data Science Projects

A Data Science Project is an OpenShift project (namespace) with additional labels and annotations that the OpenShift AI dashboard recognizes. Creating a project from the dashboard automatically:

- Creates the OpenShift namespace
- Applies the `opendatahub.io/dashboard: "true"` label so the dashboard tracks it
- Sets up default RBAC bindings for the creating user
- Makes the project available for workbenches, pipelines, and model serving

### Data Connections

A data connection is a Kubernetes Secret with a specific set of keys that OpenShift AI components understand. Data connections provide access to S3-compatible object storage (for model weights, training data, pipeline artifacts). The Secret contains:

- `AWS_ACCESS_KEY_ID` -- S3 access key
- `AWS_SECRET_ACCESS_KEY` -- S3 secret key
- `AWS_S3_ENDPOINT` -- S3 endpoint URL
- `AWS_S3_BUCKET` -- Default bucket name
- `AWS_DEFAULT_REGION` -- Region (can be empty for MinIO)

The dashboard creates and manages these Secrets. Workbenches and model serving components can reference them by name to access storage without embedding credentials in manifests.

### User Roles

OpenShift AI defines two user groups that control platform access:

- **`rhods-admins`** -- Full platform administration. Members can manage cluster-wide settings, configure serving runtimes, manage notebook images, set accelerator profiles, and control which applications are enabled. This maps to the Settings section of the dashboard.
- **`rhods-users`** -- Standard platform users. Members can create Data Science Projects, launch workbenches, deploy models within their projects, and run pipelines. They cannot modify cluster-wide settings.

These groups work alongside standard OpenShift RBAC. A user must be in `rhods-users` (or `rhods-admins`) to access the dashboard at all. Project-level permissions follow normal OpenShift role bindings.

## Step-by-Step

### Step 1: Access the Dashboard

Find the dashboard URL by querying the route in the `redhat-ods-applications` namespace:

```bash
oc get routes -n redhat-ods-applications
```

Expected output:

```
NAME                    HOST/PORT                                                    PATH   SERVICES                PORT    TERMINATION     WILDCARD
rhods-dashboard         rhods-dashboard-redhat-ods-applications.apps.<cluster>               rhods-dashboard         8443    reencrypt/None  None
```

Open the URL from the `HOST/PORT` column in your browser. You will be redirected to the OpenShift OAuth login page. Log in with your OpenShift credentials.

Alternatively, you can construct the URL directly:

```bash
# Get just the URL
oc get route rhods-dashboard -n redhat-ods-applications -o jsonpath='{.spec.host}'
```

On the Developer Sandbox, the dashboard is also accessible from the OpenShift Web Console by clicking the grid icon (application launcher) in the top navigation bar and selecting "Red Hat OpenShift AI".

### Step 2: Explore the Main Navigation

After logging in, you will see the OpenShift AI dashboard landing page. Take a few minutes to explore each section:

**Applications page:** Shows enabled applications and quick-start tutorials. You should see links to launch JupyterHub and access documentation.

**Data Science Projects page:** Currently empty if this is a fresh installation. This is where you will create and manage your projects. Each project card shows the project name, description, and counts of workbenches, models, and pipelines.

**Data Science Pipelines page:** Shows pipeline servers and runs. Pipelines require a pipeline server to be configured within a project (covered in later modules).

**Model Serving page:** A cluster-wide view of all deployed models, their status, endpoints, and resource usage. Currently empty.

**Resources page:** Links to official documentation, tutorials, and how-to guides. Useful reference material as you work through the tutorial.

### Step 3: Explore AI Hub / Gen AI Studio

In the left navigation, look for the **AI Hub** section (labeled "Gen AI Studio" in some versions). This section contains:

**Model Catalog:** Browse available models. Click on any model card to see details including:
- Model description and use cases
- Model size and quantization options
- License information
- Deployment instructions (one-click deploy to a project)

You should see models from the Granite family, Llama, Mistral, and others depending on your cluster configuration.

**Model Registry:** Initially empty. This becomes populated as you register models through the dashboard or API. The registry tracks model versions, artifacts, and metadata.

**Deployments:** Shows all active model deployments across the cluster. Each deployment shows the model name, runtime, replicas, and resource usage.

**Endpoints:** Lists API endpoints for deployed models with connection details. Includes the endpoint URL, authentication requirements, and example curl commands.

**Playground:** An interactive chat interface. Once you have a model deployed, you can select it from the dropdown and start chatting. The playground supports:
- System instructions (system prompt)
- Temperature, top-p, and max token controls
- Conversation history
- Multiple model comparison (side-by-side)

Note: The Playground requires at least one model to be deployed and serving. You will deploy your first model in Module 2.

### Step 4: Create a Data Science Project

Navigate to **Data Science Projects** and click **Create data science project**.

Fill in the form:

- **Name:** `ai-tutorial`
- **Description:** `OpenShift AI tutorial project`

Click **Create**.

The dashboard creates an OpenShift namespace with the appropriate labels. You can verify this from the CLI:

```bash
oc get project ai-tutorial -o yaml
```

Expected output (relevant fields):

```yaml
apiVersion: project.openshift.io/v1
kind: Project
metadata:
  name: ai-tutorial
  labels:
    kubernetes.io/metadata.name: ai-tutorial
    opendatahub.io/dashboard: "true"
  annotations:
    openshift.io/description: OpenShift AI tutorial project
    openshift.io/display-name: ai-tutorial
```

The key label is `opendatahub.io/dashboard: "true"` -- this tells the OpenShift AI dashboard to include this project in its views.

You can also create Data Science Projects from the CLI by creating a namespace with the correct label:

```bash
# Equivalent CLI approach (for reference -- we already created it via the dashboard)
oc new-project ai-tutorial --display-name="ai-tutorial" --description="OpenShift AI tutorial project"
oc label namespace ai-tutorial opendatahub.io/dashboard=true
```

### Step 5: Configure an S3 Data Connection

Within the `ai-tutorial` project page, click **Add data connection**.

If you set up MinIO in L1-M1.2, fill in the form with your MinIO credentials:

- **Name:** `minio-storage`
- **Access key:** `minioadmin` (or your configured access key)
- **Secret key:** `minioadmin` (or your configured secret key)
- **Endpoint:** `http://minio.minio.svc.cluster.local:9000`
- **Region:** leave empty (not required for MinIO)
- **Bucket:** `ai-tutorial`

Click **Add data connection**.

The dashboard creates a Kubernetes Secret in the `ai-tutorial` namespace. Verify it from the CLI:

```bash
oc get secrets -n ai-tutorial -l opendatahub.io/dashboard=true
```

Inspect the secret structure (keys only, not values):

```bash
oc get secret minio-storage -n ai-tutorial -o jsonpath='{.data}' | python3 -c "import sys,json; print('\n'.join(json.loads(sys.stdin.read()).keys()))"
```

Expected keys:

```
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_S3_ENDPOINT
AWS_S3_BUCKET
AWS_DEFAULT_REGION
```

You can also create data connections from the CLI by creating a Secret with the expected keys:

```bash
# Equivalent CLI approach (for reference)
oc create secret generic minio-storage \
  -n ai-tutorial \
  --from-literal=AWS_ACCESS_KEY_ID=minioadmin \
  --from-literal=AWS_SECRET_ACCESS_KEY=minioadmin \
  --from-literal=AWS_S3_ENDPOINT=http://minio.minio.svc.cluster.local:9000 \
  --from-literal=AWS_S3_BUCKET=ai-tutorial \
  --from-literal=AWS_DEFAULT_REGION=""

oc label secret minio-storage -n ai-tutorial \
  opendatahub.io/dashboard=true \
  opendatahub.io/managed=true
```

### Step 6: Explore Settings (Admin Only)

If you are logged in as a cluster admin or a member of the `rhods-admins` group, click **Settings** in the left navigation. This section includes:

**Notebook images:** Manage the container images available for workbenches. You can see the pre-built images (Standard Data Science, CUDA, PyTorch, TensorFlow) and add custom images.

**Serving runtimes:** Configure the model serving runtimes available to users. The default is the Red Hat AI Inference Server (vLLM-based). You can add custom runtimes for specialized model formats.

**Cluster settings:** Platform-wide configuration including:
- PVC size defaults for workbenches
- Culling (idle notebook shutdown) configuration
- Telemetry settings
- Model serving platform configuration (single-model vs multi-model serving)

**Accelerator profiles:** Define GPU and accelerator profiles that users can select when creating workbenches or deploying models. Profiles map to Kubernetes resource names (e.g., `nvidia.com/gpu`).

**User management:** View and manage `rhods-admins` and `rhods-users` group memberships.

If you are logged in as a regular user, the Settings section will not be visible. This is controlled by group membership, not by OpenShift RBAC roles.

## Verification

Confirm the following:

1. You can access the OpenShift AI dashboard via the route URL:

```bash
oc get route rhods-dashboard -n redhat-ods-applications -o jsonpath='{.spec.host}'
```

2. The `ai-tutorial` project exists with the correct label:

```bash
oc get namespace ai-tutorial -o jsonpath='{.metadata.labels.opendatahub\.io/dashboard}'
# Expected: true
```

3. The data connection Secret exists in the project:

```bash
oc get secret minio-storage -n ai-tutorial
# Expected: secret/minio-storage listed with Opaque type
```

4. In the dashboard, the `ai-tutorial` project appears under Data Science Projects with the data connection listed.

## K8s vs OpenShift AI Comparison

| Aspect | Kubernetes | OpenShift AI |
|--------|-----------|-------------|
| ML dashboard | Kubeflow Central Dashboard (basic navigation, manual setup) | Full-featured AI dashboard with integrated project management |
| Project creation | `kubectl create namespace` + manual RBAC setup | Dashboard creates project with auto RBAC and AI-specific labels |
| Model catalog | No built-in catalog; manually browse HuggingFace or model zoos | AI Hub Model Catalog with validated models and one-click deploy |
| Data connections | Manually create Secrets with arbitrary keys | Dashboard-managed Secrets with standardized S3 key format |
| User management | RBAC roles and bindings only | `rhods-admins` / `rhods-users` groups with dashboard-level access control |
| GenAI playground | No equivalent; deploy a separate chat UI | Built-in Playground for interactive model testing |
| Model registry | No built-in registry; use MLflow or similar externally | Integrated Model Registry with versioning and metadata |
| Settings management | Edit ConfigMaps and CRDs manually | Dashboard Settings UI for notebook images, runtimes, accelerators |

## Key Takeaways

- The OpenShift AI dashboard is the primary interface for data scientists -- it orchestrates multiple Kubernetes resources (Namespaces, Secrets, CRDs) behind simple form submissions.
- AI Hub / Gen AI Studio (OpenShift AI 3.3+) provides a Model Catalog, Playground, and deployment management specifically for generative AI workflows.
- Data Science Projects are OpenShift namespaces with the `opendatahub.io/dashboard: "true"` label, which makes them visible to the dashboard.
- S3 data connections are stored as Kubernetes Secrets with standardized keys (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_ENDPOINT`, `AWS_S3_BUCKET`, `AWS_DEFAULT_REGION`).
- Two user groups control platform access: `rhods-admins` (full settings and administration) and `rhods-users` (project-level operations within their own projects).

## Cleanup

The `ai-tutorial` project will be reused in subsequent lessons. Do not delete it.

If you need to start over:

```bash
# Delete the data connection only
oc delete secret minio-storage -n ai-tutorial

# Delete the entire project (will remove all resources within it)
oc delete project ai-tutorial
```

## Next Steps

Continue to [L1-M1.4 -- Workbenches](../4_workbenches/) to learn how to create containerized IDE environments (JupyterLab, VS Code) that run directly on the cluster with GPU access and persistent storage.
