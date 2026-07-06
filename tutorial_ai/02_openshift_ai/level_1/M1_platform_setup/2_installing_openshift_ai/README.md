# L1-M1.2 -- Installing OpenShift AI

**Level:** Foundations
**Duration:** 45 min

## Overview

In this lesson you will install OpenShift AI on an OpenShift cluster by deploying the RHODS operator, creating the cluster-wide initialization CR, and configuring the DataScienceCluster with the components you need. You will also set up MinIO as a lightweight S3-compatible object store for development use. By the end, the OpenShift AI dashboard will be accessible and core components will be running.

## Prerequisites

- Completed: [L1-M1.1 -- Architecture Overview](../1_architecture_overview/)
- OpenShift 4.19+ cluster with cluster-admin access
- `oc` CLI installed and authenticated as cluster-admin
- Internet access from the cluster (to pull operator images from OperatorHub)

**Environment limitations:**
- **CRC (OpenShift Local):** Works but has no GPU -- CPU-only inference is possible for small models
- **Red Hat Developer Sandbox:** Does not provide cluster-admin access -- you cannot install operators. Use a full cluster instead.

## K8s Context

On vanilla Kubernetes, setting up an ML platform requires installing multiple Helm charts independently:

```bash
# Typical K8s approach -- many independent installs
helm install cert-manager jetstack/cert-manager --namespace cert-manager
helm install kserve kserve/kserve --namespace kserve
helm install kubeflow-pipelines ...
helm install mlflow community-charts/mlflow ...
helm install kuberay kuberay/kuberay-operator ...
helm install kueue kubernetes-sigs/kueue ...
```

Each chart has its own values file, its own CRDs, and its own upgrade path. Compatibility between versions is your responsibility.

OpenShift AI replaces all of that with a single operator install and two CRs: `DSCInitialization` for global settings and `DataScienceCluster` for component selection.

## Concepts

### Installation Flow

The installation follows four phases:

1. **Install prerequisite operators** -- cert-manager (for TLS in KServe) and JobSet (for Training Hub)
2. **Install the RHODS operator** -- the main OpenShift AI operator from OperatorHub
3. **Create DSCInitialization** -- cluster-wide settings (monitoring, trusted CAs, default namespace)
4. **Create DataScienceCluster** -- select which of the 14 components to enable

### Prerequisite Operators

Two operators must be installed before OpenShift AI:

- **cert-manager** -- Required by the `kserve` component for automated TLS certificate management. Without it, KServe's webhook and serving infrastructure will not function.
- **JobSet** -- Required by the `trainer` component. JobSet manages sets of related Kubernetes Jobs, which Training Hub uses for distributed fine-tuning workloads.

### DSCInitialization

The `DSCInitialization` CR configures cluster-wide settings that apply to all OpenShift AI components:

- **Monitoring** -- whether to enable the built-in monitoring stack
- **Trusted CA bundle** -- custom CA certificates for corporate proxies or internal registries
- **Applications namespace** -- where operator-managed components are deployed (default: `redhat-ods-applications`)

There should be exactly one `DSCInitialization` CR per cluster.

### DataScienceCluster

The `DataScienceCluster` CR (API v2) is where you select which components to enable. Each of the 14 components has a `managementState` field:

- **`Managed`** -- the operator installs and maintains this component
- **`Removed`** -- the operator does not install this component (or removes it if previously installed)

There should be exactly one `DataScienceCluster` CR per cluster.

### S3 Storage

Many OpenShift AI components need S3-compatible object storage:

- **Pipelines** store artifacts in S3
- **Model serving** loads models from S3
- **MLflow** stores experiment artifacts in S3
- **Model Registry** references model artifacts in S3

For production, use AWS S3, Google Cloud Storage (with S3-compatible API), or Ceph/NooBaa. For development, MinIO provides a lightweight, self-hosted S3-compatible store that runs as a single pod.

## Step-by-Step

### Step 1: Install cert-manager Operator

cert-manager is required for the `kserve` component. Install it from OperatorHub.

```bash
# Create the cert-manager operator namespace
oc create namespace cert-manager-operator
```

```bash
# Create the Subscription to install cert-manager
oc apply -f - <<EOF
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: openshift-cert-manager-operator
  namespace: cert-manager-operator
spec:
  channel: stable-v1
  installPlanApproval: Automatic
  name: openshift-cert-manager-operator
  source: redhat-operators
  sourceNamespace: openshift-marketplace
EOF
```

Wait for the operator to install:

```bash
# Check that the operator pod is running
oc get pods -n cert-manager-operator -w
```

Expected output (after 1-2 minutes):

```
NAME                                      READY   STATUS    RESTARTS   AGE
cert-manager-operator-xxxxx-xxxxx         1/1     Running   0          90s
```

Verify cert-manager components are ready:

```bash
oc get pods -n cert-manager
```

Expected output:

```
NAME                                       READY   STATUS    RESTARTS   AGE
cert-manager-xxxxx-xxxxx                   1/1     Running   0          60s
cert-manager-cainjector-xxxxx-xxxxx        1/1     Running   0          60s
cert-manager-webhook-xxxxx-xxxxx           1/1     Running   0          60s
```

### Step 2: Install JobSet Operator

JobSet is required for the `trainer` component (Training Hub).

```bash
# Create the jobset-operator namespace and OperatorGroup
oc create namespace jobset-operator

oc apply -f - <<EOF
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: jobset-operator
  namespace: jobset-operator
spec:
  targetNamespaces: []
EOF
```

```bash
# Create the Subscription to install JobSet
oc apply -f - <<EOF
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: jobset-operator
  namespace: jobset-operator
spec:
  channel: stable
  installPlanApproval: Automatic
  name: jobset-operator
  source: community-operators
  sourceNamespace: openshift-marketplace
EOF
```

Wait for the operator pod:

```bash
oc get pods -n jobset-operator -w
```

Expected output:

```
NAME                                READY   STATUS    RESTARTS   AGE
jobset-operator-xxxxx-xxxxx         1/1     Running   0          60s
```

### Step 3: Install the RHODS Operator

The RHODS (Red Hat OpenShift Data Science) operator is the main OpenShift AI operator.

```bash
# Create the namespace for the operator
oc create namespace redhat-ods-operator
```

```bash
# Create the OperatorGroup
oc apply -f - <<EOF
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: rhods-operator
  namespace: redhat-ods-operator
spec: {}
EOF
```

```bash
# Subscribe to the RHODS operator (stable-3.x channel)
oc apply -f - <<EOF
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: rhods-operator
  namespace: redhat-ods-operator
spec:
  channel: stable-3.x
  installPlanApproval: Automatic
  name: rhods-operator
  source: redhat-operators
  sourceNamespace: openshift-marketplace
EOF
```

Wait for the operator to install (this may take 2-3 minutes):

```bash
oc get pods -n redhat-ods-operator -w
```

Expected output:

```
NAME                              READY   STATUS    RESTARTS   AGE
rhods-operator-xxxxx-xxxxx        1/1     Running   0          120s
```

Verify the operator CSV is in `Succeeded` phase:

```bash
oc get csv -n redhat-ods-operator | grep rhods
```

Expected output:

```
rhods-operator.3.4.2   Red Hat OpenShift AI   3.4.2   rhods-operator.3.4.1   Succeeded
```

### Step 4: Create the DSCInitialization CR

The `DSCInitialization` CR configures cluster-wide settings. Apply the manifest from the `manifests/` directory:

```bash
oc apply -f manifests/dsciinitialization.yaml
```

The manifest (`manifests/dsciinitialization.yaml`):

```yaml
apiVersion: dscinitialization.opendatahub.io/v1
kind: DSCInitialization
metadata:
  name: default-dsci
  labels:
    app: openshift-ai
    tutorial-level: "1"
    tutorial-module: "M1"
spec:
  applicationsNamespace: redhat-ods-applications
  monitoring:
    managementState: Managed
    namespace: redhat-ods-monitoring
  trustedCABundle:
    managementState: Managed
```

Verify the DSCInitialization is ready:

```bash
oc get dsci default-dsci -o jsonpath='{.status.phase}'
```

Expected output:

```
Ready
```

### Step 5: Create the DataScienceCluster CR

Now create the `DataScienceCluster` to enable the components you need. Apply the manifest:

```bash
oc apply -f manifests/datasciencecluster.yaml
```

The manifest (`manifests/datasciencecluster.yaml`) enables core components and disables optional ones. Review the file to understand each component's role.

Watch the components come up:

```bash
# Watch pods being created in the applications namespace
oc get pods -n redhat-ods-applications -w
```

This will take several minutes. You should see pods appearing for each enabled component (dashboard, workbenches controller, KServe controller, model registry, MLflow, TrustyAI, pipelines, Ray operator, Feast operator, and trainer).

Check the DataScienceCluster status:

```bash
oc get datasciencecluster default-dsc -o jsonpath='{.status.phase}'
```

Expected output:

```
Ready
```

For detailed component status:

```bash
oc get datasciencecluster default-dsc -o jsonpath='{.status.conditions[*].type}' | tr ' ' '\n'
```

Expected output (one condition per component):

```
dashboardReady
workbenchesReady
kserveReady
modelregistryReady
...
```

### Step 6: Verify Component Pods

Check that pods are running for each enabled component:

```bash
oc get pods -n redhat-ods-applications --sort-by=.metadata.name
```

Expected output (abbreviated -- you will see many pods):

```
NAME                                              READY   STATUS    RESTARTS   AGE
dashboard-xxxxx-xxxxx                             2/2     Running   0          5m
kserve-controller-manager-xxxxx-xxxxx             1/1     Running   0          5m
mlflow-operator-controller-manager-xxxxx          1/1     Running   0          5m
model-registry-operator-xxxxx-xxxxx               1/1     Running   0          5m
notebook-controller-manager-xxxxx-xxxxx           1/1     Running   0          5m
...
```

### Step 7: Access the OpenShift AI Dashboard

Get the dashboard route:

```bash
oc get route -n redhat-ods-applications -l app=rhods-dashboard
```

Expected output:

```
NAME             HOST/PORT                                              PATH   SERVICES         PORT    TERMINATION   WILDCARD
rhods-dashboard  rhods-dashboard-redhat-ods-applications.apps.<domain>         rhods-dashboard  https   reencrypt     None
```

Open the URL in your browser. You should see the OpenShift AI dashboard with:

- **Home** page with getting started information
- **Data Science Projects** for creating and managing projects
- **Gen AI Studio** with Playground (if `kserve` is enabled)
- **Settings** for cluster configuration

### Step 8: Set Up MinIO for Development S3 Storage

Many components need S3 storage. For development, MinIO provides a lightweight solution.

First, create a project for MinIO:

```bash
oc new-project minio-storage
```

Apply the MinIO manifest:

```bash
oc apply -f manifests/minio-setup.yaml -n minio-storage
```

Wait for MinIO to start:

```bash
oc get pods -n minio-storage -w
```

Expected output:

```
NAME                     READY   STATUS    RESTARTS   AGE
minio-xxxxx-xxxxx        1/1     Running   0          30s
```

Get the MinIO console URL:

```bash
oc get route minio-console -n minio-storage -o jsonpath='{.spec.host}'
```

Access the MinIO console in your browser using the default credentials:
- **Username:** `minioadmin`
- **Password:** `minioadmin`

The MinIO API endpoint (for configuring OpenShift AI components) is available as a service:

```bash
# Internal endpoint for other components to use
echo "http://minio.minio-storage.svc.cluster.local:9000"
```

### Step 9: Create a Bucket in MinIO

Create a bucket for pipeline artifacts and model storage using the MinIO client (`mc`) or the web console.

Using `oc exec`:

```bash
oc exec -n minio-storage deployment/minio -- \
  mc alias set local http://localhost:9000 minioadmin minioadmin

oc exec -n minio-storage deployment/minio -- \
  mc mb local/openshift-ai
```

Expected output:

```
Added `local` successfully.
Bucket created successfully `local/openshift-ai`.
```

## Verification

Run through this checklist to confirm the installation is complete:

```bash
# 1. RHODS operator is running
oc get pods -n redhat-ods-operator | grep Running

# 2. DSCInitialization is Ready
oc get dsci default-dsci -o jsonpath='{.status.phase}' && echo

# 3. DataScienceCluster is Ready
oc get datasciencecluster default-dsc -o jsonpath='{.status.phase}' && echo

# 4. Dashboard is accessible
oc get route -n redhat-ods-applications -l app=rhods-dashboard -o jsonpath='{.items[0].spec.host}' && echo

# 5. Core component pods are running
oc get pods -n redhat-ods-applications --field-selector=status.phase=Running --no-headers | wc -l

# 6. MinIO is running (if installed)
oc get pods -n minio-storage | grep Running
```

All commands should succeed. The pod count in step 5 will vary depending on which components you enabled (expect 10-20+ pods for a full installation).

## K8s vs OpenShift AI Comparison

| Aspect | Kubernetes | OpenShift AI |
|--------|-----------|--------------|
| Install model serving | `helm install kserve ...` + cert-manager + Istio | Set `kserve: Managed` in DSC |
| Install experiment tracking | Deploy MLflow via Helm/manifests | Set `mlflowoperator: Managed` |
| Install pipelines | Deploy Kubeflow Pipelines + Argo | Set `aipipelines: Managed` |
| Upgrade components | Upgrade each Helm chart individually | Operator handles upgrades automatically |
| Dependency management | Manual (cert-manager for KServe, etc.) | Documented, operator validates |
| Uninstall a component | Delete each Helm release individually | Set component to `Removed` |
| Global configuration | No unified config -- each tool configured separately | DSCInitialization CR |
| Component selection | Install/skip each Helm chart | `Managed` / `Removed` per component |

## Key Takeaways

- OpenShift AI installs via a single operator (`rhods-operator`) from OperatorHub on the `stable-3.x` channel
- `DSCInitialization` configures cluster-wide settings (monitoring, trusted CAs, applications namespace)
- `DataScienceCluster` (API v2) controls which of the 14 components are enabled via `managementState`
- cert-manager and JobSet are prerequisites for `kserve` and `trainer` respectively -- install them first
- MinIO provides a lightweight S3-compatible object store for development environments
- The dashboard route gives you a web UI for managing all AI/ML workflows

## Cleanup

To remove OpenShift AI and its components:

```bash
# Remove MinIO
oc delete project minio-storage

# Remove the DataScienceCluster (this removes all enabled components)
oc delete datasciencecluster default-dsc

# Remove the DSCInitialization
oc delete dsci default-dsci

# Remove the RHODS operator subscription
oc delete subscription rhods-operator -n redhat-ods-operator
oc delete csv -n redhat-ods-operator -l operators.coreos.com/rhods-operator.redhat-ods-operator

# Remove prerequisite operators (optional)
oc delete subscription jobset-operator -n jobset-operator
oc delete subscription openshift-cert-manager-operator -n cert-manager-operator

# Remove namespaces
oc delete namespace redhat-ods-operator redhat-ods-applications redhat-ods-monitoring
oc delete namespace jobset-operator cert-manager-operator cert-manager
```

## Next Steps

In the next lesson, [L1-M1.3 -- Dashboard and AI Hub Tour](../3_dashboard_ai_hub_tour/), you will explore the OpenShift AI dashboard in detail -- navigating data science projects, the Gen AI Studio, model serving configuration, and cluster settings.
