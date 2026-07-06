# L1-M4.1 — Model Registry Setup

**Level:** Foundations
**Duration:** 30 min

## Overview

You have a base Gemma4-e4b and a fine-tuned version deployed on your cluster. Both serve inference, but there is no centralized record of what models exist, which versions are live, where their artifacts are stored, or how they relate to each other. The Model Registry fills that gap -- it is a metadata store that tracks registered models, their versions, and their artifacts across your entire platform.

In this lesson you enable the Model Registry component in your DataScienceCluster, deploy a MySQL database to back it, create a `ModelRegistry` custom resource, and verify the registry is accessible from the OpenShift AI dashboard.

## Prerequisites

- Completed: [L1-M1 — Platform Setup](../../M1_platform_setup/) (OpenShift AI installed, dashboard accessible)
- Completed: [L1-M2 — Model Serving](../../M2_model_serving/) (Gemma4-e4b deployed)
- Completed: [L1-M3 — Fine-Tuning](../../M3_fine_tuning/) (fine-tuned model deployed)
- OpenShift cluster running with cluster-admin access
- `oc` CLI authenticated

## K8s Context

In vanilla Kubernetes, there is no built-in model registry. Teams typically use external tools -- MLflow Model Registry, Weights & Biases, or a custom database -- to track trained models. These require separate installation, their own authentication, and manual integration with serving infrastructure. When you want to deploy a model, you manually copy the S3 URI from the registry into your KServe InferenceService manifest.

OpenShift AI integrates the Kubeflow Model Registry as a managed component. You enable it in the DataScienceCluster CR, create a `ModelRegistry` custom resource, and the operator handles the deployment. The dashboard provides a UI for browsing and registering models. Deployment from the registry is a button click -- the dashboard creates the InferenceService for you with the correct storage URI.

## Concepts

### Model Registry Architecture

The Model Registry is a **metadata store**, not an artifact store. It does not store model weights or binaries. Instead, it records:

- **What models exist** (names, descriptions, owners)
- **Which versions of each model** (with metadata, labels, custom properties)
- **Where model artifacts live** (S3 URIs, OCI image references, PVC paths)
- **What format they are in** (vLLM, ONNX, sklearn, etc.)

The actual model files remain in S3 (or wherever you stored them). The registry points to them.

```
                    Model Registry (metadata)
                    ========================
                    RegisteredModel: "gemma4-e4b"
                      |
                      +-- ModelVersion: "v1-base"
                      |     +-- ModelArtifact: uri="s3://models/gemma4-e4b/base"
                      |
                      +-- ModelVersion: "v2-finetuned"
                            +-- ModelArtifact: uri="s3://models/gemma4-e4b/finetuned-lora"

                    Actual Storage (artifacts)
                    ==========================
                    S3 bucket: model weights, adapters, configs
```

### Data Model: Three-Level Hierarchy

The registry uses a three-level hierarchy:

| Level | Resource | Description |
|-------|----------|-------------|
| 1 | **RegisteredModel** | A logical model (e.g., "gemma4-e4b"). Has a unique name, description, owner, and state (`LIVE` or `ARCHIVED`). |
| 2 | **ModelVersion** | A specific version of a registered model (e.g., "v1-base", "v2-finetuned"). Has metadata, author, and custom properties. |
| 3 | **ModelArtifact** | The physical location of model files for a version. Contains the storage URI, model format, and storage credentials reference. |

Each `RegisteredModel` has one or many `ModelVersion` entries. Each `ModelVersion` has zero or more `ModelArtifact` entries (typically one, but you might have both a full model and a LoRA adapter for the same version).

### Component Architecture

The Model Registry consists of:

1. **ModelRegistry Operator** -- Part of the OpenShift AI operator. Watches `ModelRegistry` CRs and deploys the registry server.
2. **Registry Server** -- A Go service exposing REST (`/api/model_registry/v1alpha3/`) and gRPC APIs. Built on Google's ML-Metadata (MLMD) library.
3. **Database Backend** -- MySQL or PostgreSQL. Stores the metadata. You provide this; the operator does not create it.
4. **Dashboard Integration** -- The OpenShift AI dashboard connects to the registry for browsing, registering, and deploying models.
5. **Python SDK** -- The `model-registry` package for programmatic access from notebooks and scripts.

### The ModelRegistry CRD

The `ModelRegistry` CRD (`modelregistry.opendatahub.io/v1beta1`) defines a registry instance:

```yaml
apiVersion: modelregistry.opendatahub.io/v1beta1
kind: ModelRegistry
metadata:
  name: my-registry
spec:
  rest:
    port: 8080
  grpc:
    port: 9090
  mysql:                    # or postgres: -- mutually exclusive
    host: model-registry-db
    port: 3306
    database: model_registry
    username: registryuser
    passwordSecret:
      name: model-registry-db-credentials
      key: database-password
```

Key fields:

| Field | Purpose |
|-------|---------|
| `spec.rest` | REST API configuration (port, TLS) |
| `spec.grpc` | gRPC API configuration (port, TLS) |
| `spec.mysql` | MySQL connection details (host, port, database, credentials) |
| `spec.postgres` | PostgreSQL connection details (alternative to MySQL) |
| `spec.istio` | Service mesh configuration (if Istio is enabled) |

When you create this CR, the operator deploys:
- A Deployment (registry server pod with kube-rbac-proxy sidecar)
- A Service (ClusterIP, ports 8080 and 9090)
- A Route (HTTPS, for dashboard access)
- A ServiceAccount with appropriate RBAC
- A Group (`<registry-name>-users`) for access control

## Step-by-Step

### Step 1: Verify the Model Registry Component is Enabled

The `modelregistry` component must be set to `Managed` in your DataScienceCluster. If you followed L1-M1.2, it should already be enabled.

```bash
oc get datasciencecluster default-dsc -o jsonpath='{.spec.components.modelregistry.managementState}'
```

Expected output:

```
Managed
```

If it shows `Removed`, patch the DSC to enable it:

```bash
oc patch datasciencecluster default-dsc --type merge -p '{"spec":{"components":{"modelregistry":{"managementState":"Managed"}}}}'
```

Verify the model registry operator pods are running:

```bash
oc get pods -n redhat-ods-applications -l app=model-registry-operator
```

Expected output:

```
NAME                                        READY   STATUS    RESTARTS   AGE
model-registry-operator-xxxxx-yyyyy         1/1     Running   0          5m
```

### Step 2: Create a Namespace for the Registry

The registry and its database will live in a dedicated namespace. OpenShift AI typically uses `rhoai-model-registries` for registry instances.

```bash
oc new-project rhoai-model-registries
```

### Step 3: Deploy the MySQL Database

The Model Registry needs a relational database backend. We will deploy a lightweight MySQL instance. In production, you would use a managed database service (Amazon RDS, Azure Database for MySQL, etc.).

First, create the database credentials secret:

```bash
oc create secret generic model-registry-db \
  --from-literal=database-password='registry-db-pass' \
  --from-literal=database-user='registryuser' \
  --from-literal=database-name='model_registry' \
  -n rhoai-model-registries
```

Now deploy MySQL using the manifest:

```bash
oc apply -f manifests/mysql-deployment.yaml -n rhoai-model-registries
```

Wait for the MySQL pod to become ready:

```bash
oc wait --for=condition=available deployment/model-registry-db \
  -n rhoai-model-registries --timeout=120s
```

Verify the database is running:

```bash
oc get pods -n rhoai-model-registries -l app=model-registry-db
```

Expected output:

```
NAME                                  READY   STATUS    RESTARTS   AGE
model-registry-db-xxxxx-yyyyy         1/1     Running   0          30s
```

### Step 4: Create the ModelRegistry Custom Resource

Apply the `ModelRegistry` CR that points to the MySQL database:

```bash
oc apply -f manifests/modelregistry.yaml -n rhoai-model-registries
```

The `modelregistry.yaml` creates a registry named `tutorial-registry` connected to the MySQL database you just deployed.

Watch the registry pods come up:

```bash
oc get pods -n rhoai-model-registries -l app=tutorial-registry -w
```

Expected output (after 30-60 seconds):

```
NAME                                      READY   STATUS    RESTARTS   AGE
model-registry-tutorial-registry-xxxxx    2/2     Running   0          45s
```

The pod has 2 containers: the registry server and a kube-rbac-proxy sidecar for authentication.

### Step 5: Verify the Registry Service

Check that the Service and Route were created:

```bash
oc get svc -n rhoai-model-registries -l app=tutorial-registry
```

Expected output:

```
NAME                                   TYPE        CLUSTER-IP     EXTERNAL-IP   PORT(S)             AGE
model-registry-tutorial-registry       ClusterIP   172.30.x.x     <none>        8080/TCP,9090/TCP   1m
```

```bash
oc get route -n rhoai-model-registries -l app=tutorial-registry
```

Verify the REST API is responding. From within the cluster (or using port-forwarding):

```bash
# Port-forward the registry service
oc port-forward svc/model-registry-tutorial-registry 8080:8080 \
  -n rhoai-model-registries &

# Test the API
curl -s http://localhost:8080/api/model_registry/v1alpha3/registered_models | python3 -m json.tool
```

Expected output:

```json
{
    "items": [],
    "nextPageToken": "",
    "pageSize": 0,
    "size": 0
}
```

An empty list is correct -- you have not registered any models yet. Stop the port-forward:

```bash
kill %1
```

### Step 6: Verify Dashboard Integration

Open the OpenShift AI dashboard in your browser:

```bash
# Get the dashboard URL
oc get route rhods-dashboard -n redhat-ods-applications -o jsonpath='{.spec.host}'
```

Navigate to:

1. **AI hub** (left sidebar) > **Registry**
2. You should see the `tutorial-registry` listed
3. Click on it -- the registry is empty (no models registered yet)

If the registry does not appear in the dashboard, check that:
- The `ModelRegistry` CR status is `Available`
- The registry pod is running with 2/2 containers
- Your user is in the registry's user group

```bash
# Check the CR status
oc get modelregistry tutorial-registry -n rhoai-model-registries -o jsonpath='{.status.conditions}' | python3 -m json.tool
```

## Verification

Run these checks to confirm everything is working:

```bash
# 1. ModelRegistry CR exists and is healthy
oc get modelregistry -n rhoai-model-registries
# Expected: tutorial-registry listed

# 2. Registry pod is running (2/2 containers)
oc get pods -n rhoai-model-registries -l app=tutorial-registry
# Expected: 2/2 Running

# 3. MySQL database is running
oc get pods -n rhoai-model-registries -l app=model-registry-db
# Expected: 1/1 Running

# 4. Services are created
oc get svc -n rhoai-model-registries
# Expected: model-registry-tutorial-registry and model-registry-db services

# 5. REST API is responsive (port-forward test)
oc port-forward svc/model-registry-tutorial-registry 8080:8080 -n rhoai-model-registries &
curl -s http://localhost:8080/api/model_registry/v1alpha3/registered_models | python3 -m json.tool
kill %1
# Expected: empty items list (JSON)
```

## K8s vs OpenShift AI Comparison

| Aspect | Kubernetes | OpenShift AI |
|--------|-----------|--------------|
| Registry availability | None built-in; install MLflow, W&B, or custom solution | `ModelRegistry` CRD -- declare and the operator deploys it |
| Database setup | Manual (Helm charts, operators, or cloud services) | You provide the DB; operator handles the registry server |
| Dashboard UI | None (CLI or external web UIs only) | Integrated into OpenShift AI dashboard -- browse, register, deploy |
| Deploy from registry | Manual: copy URI into InferenceService YAML | One-click deploy from dashboard, or `model-registry://` URI scheme |
| Access control | Depends on external tool | Automatic: RBAC roles, user groups, and OAuth proxy per registry |
| API | Varies by tool (MLflow REST, W&B GraphQL, etc.) | Standardized Kubeflow Model Registry REST + gRPC + Python SDK |

## Key Takeaways

- The Model Registry is a **metadata store** -- it tracks what models exist and where their artifacts live, but does not store the model files themselves.
- The data model is a **three-level hierarchy**: RegisteredModel > ModelVersion > ModelArtifact.
- You enable it via the `modelregistry` component in the DataScienceCluster CR, then create a `ModelRegistry` custom resource pointing to a MySQL or PostgreSQL database.
- The operator creates the registry server, service, route, and RBAC resources automatically.
- The dashboard provides a UI for browsing models, and in the next lesson you will use it to register and deploy models.

## Cleanup

If you need to remove the registry (not recommended -- you will use it in the next lesson):

```bash
# Delete the ModelRegistry CR
oc delete modelregistry tutorial-registry -n rhoai-model-registries

# Delete the MySQL database
oc delete -f manifests/mysql-deployment.yaml -n rhoai-model-registries

# Delete the credentials secret
oc delete secret model-registry-db -n rhoai-model-registries

# Delete the namespace (removes everything)
oc delete project rhoai-model-registries
```

## Next Steps

In [L1-M4.2 — Registering and Managing Models](../2_registering_models/), you will register both the base Gemma4-e4b and the fine-tuned version in the registry using the dashboard, the Python SDK, and the REST API. You will then deploy a model directly from the registry.
