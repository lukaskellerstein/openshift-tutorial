# L2-M1.3 — OpenShift GitOps (ArgoCD)

**Level:** Practitioner
**Duration:** 1 hr

## Overview

In Kubernetes, adopting GitOps means installing ArgoCD (or Flux) yourself, configuring RBAC, setting up ingress for the UI, and managing upgrades. OpenShift provides a fully supported GitOps operator that installs, configures, and upgrades ArgoCD with a single Subscription -- pre-integrated with OpenShift OAuth, Routes, and RBAC. In this lesson you will install the OpenShift GitOps operator, understand the ArgoCD Application CRD, configure sync policies (manual vs automatic), structure a Git repository with Kustomize base + overlays for multi-environment deployments, and implement the app-of-apps pattern to manage multiple applications declaratively.

## Prerequisites

- Completed: L2-M1.1 (OpenShift Pipelines / Tekton)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in as `kubeadmin` (operator installation requires cluster-admin)
- `oc` CLI installed and on PATH
- A GitHub account (to fork or reference the sample GitOps repo)
- Familiarity with Kustomize basics (L1-M3.5 covers Templates & Kustomize)

## K8s Context

In vanilla Kubernetes, GitOps is a workflow pattern, not a platform feature. You would:

1. **Install ArgoCD manually** -- apply raw manifests or use a Helm chart into an `argocd` namespace.
2. **Create an Ingress** (or port-forward) to access the ArgoCD UI.
3. **Configure RBAC** manually -- create ServiceAccounts, ClusterRoles, and RoleBindings so ArgoCD can manage your namespaces.
4. **Manage upgrades yourself** -- watch for new ArgoCD releases, test, and roll out.
5. **Set up authentication** -- configure ArgoCD's built-in Dex or an external OIDC provider.

The ArgoCD Application CRD itself is the same on both platforms. What changes is how ArgoCD gets installed, integrated with the cluster's auth, and exposed to users.

## Concepts

### What Is GitOps?

GitOps treats Git as the single source of truth for your infrastructure and application configuration. The core principles:

- **Declarative configuration**: All desired state is described in YAML/JSON stored in Git.
- **Version controlled**: Every change goes through a Git commit, providing audit trails and rollback.
- **Automated reconciliation**: An agent (ArgoCD) continuously compares the desired state in Git with the live state in the cluster, and either alerts or auto-corrects drift.
- **Pull-based delivery**: Unlike traditional CI/CD that pushes to a cluster, GitOps pulls -- the controller running inside the cluster fetches state from Git.

### OpenShift GitOps Operator

The OpenShift GitOps operator provides:

- **Managed ArgoCD instance**: Installed in the `openshift-gitops` namespace with a pre-configured Route, OAuth integration, and cluster-scoped permissions.
- **Automatic upgrades**: The operator manages ArgoCD lifecycle through OLM (Operator Lifecycle Manager). No manual version bumps.
- **OpenShift OAuth integration**: Users can log in to ArgoCD using their OpenShift credentials -- no separate identity provider configuration needed.
- **Pre-configured Route**: ArgoCD UI is immediately accessible via an OpenShift Route with TLS, no Ingress setup required.
- **RBAC alignment**: The operator respects OpenShift's RBAC model. ArgoCD's built-in RBAC layers on top of OpenShift project permissions.

### ArgoCD Application CRD

The `Application` CRD is the core abstraction. It tells ArgoCD:

- **Where to find the manifests**: `spec.source` -- a Git repo URL, branch/tag, and path within the repo.
- **Where to deploy them**: `spec.destination` -- a cluster API server URL and target namespace.
- **How to sync**: `spec.syncPolicy` -- manual (human clicks Sync) or automated (ArgoCD syncs on every Git change).

### Sync Policies: Manual vs Automatic

| Policy | Behavior | Use Case |
|--------|----------|----------|
| Manual (`syncPolicy: {}`) | ArgoCD detects drift but waits for human approval to sync | Production environments, regulated workloads |
| Automated (`syncPolicy.automated`) | ArgoCD syncs automatically when Git changes are detected | Dev/staging environments, rapid iteration |
| Auto + Prune (`prune: true`) | Deletes resources in the cluster that were removed from Git | Keeps cluster state exactly matching Git |
| Auto + Self-Heal (`selfHeal: true`) | Reverts manual `kubectl` / `oc` changes that deviate from Git | Prevents configuration drift from ad-hoc changes |

### Git Repository Structure for GitOps

A well-structured GitOps repo uses Kustomize base + overlays to manage multiple environments from a single set of base manifests:

```
gitops-repo/
  base/
    deployment.yaml
    service.yaml
    route.yaml
    kustomization.yaml
  overlays/
    staging/
      kustomization.yaml      # patches: 2 replicas, lower resources
    production/
      kustomization.yaml      # patches: 3 replicas, higher resources, stricter limits
```

This pattern avoids duplicating entire manifest sets per environment. The base contains the canonical resource definitions; overlays contain only the differences.

### App-of-Apps Pattern

Instead of creating ArgoCD Application resources manually or via the UI, you can store Application manifests in Git too. A single "root" Application points to a directory containing other Application definitions. When ArgoCD syncs the root, it discovers and creates all child Applications automatically.

```
gitops-repo/
  argocd-apps/
    staging-app.yaml        # Application CRD for staging
    production-app.yaml     # Application CRD for production
    monitoring-app.yaml     # Application CRD for monitoring stack
  base/
    ...
  overlays/
    ...
```

Benefits:
- Adding a new application means committing a YAML file -- no manual ArgoCD UI clicks.
- The full list of managed applications is version-controlled and reviewable.
- Removing an Application YAML from Git (with prune enabled) removes it from ArgoCD.

## Step-by-Step

### Step 1: Install the OpenShift GitOps Operator

Log in as `kubeadmin` (operator installation requires cluster-admin):

```bash
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
```

You can use the automated setup script, or follow the manual steps below.

**Option A: Automated Setup**

```bash
./scripts/setup.sh
```

**Option B: Manual Installation**

Apply the operator subscription:

```bash
oc apply -f manifests/gitops-subscription.yaml
```

```yaml
# manifests/gitops-subscription.yaml
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: openshift-gitops-operator
  namespace: openshift-operators
spec:
  channel: latest
  installPlanApproval: Automatic
  name: openshift-gitops-operator
  source: redhat-operators
  sourceNamespace: openshift-marketplace
```

Wait for the operator to install. This takes 2-3 minutes on CRC:

```bash
# Watch the CSV status
oc get csv -n openshift-gitops -w
```

Expected output (after a few minutes):

```
NAME                               DISPLAY                    VERSION   PHASE
openshift-gitops-operator.v1.x.y   Red Hat OpenShift GitOps   1.x.y     Succeeded
```

Verify the ArgoCD instance is running:

```bash
oc get pods -n openshift-gitops
```

Expected output:

```
NAME                                                        READY   STATUS    RESTARTS   AGE
cluster-7f4d5b6ff8-x2k9p                                   1/1     Running   0          2m
kam-5b4d5c6ff7-j8k2l                                       1/1     Running   0          2m
openshift-gitops-application-controller-0                    1/1     Running   0          2m
openshift-gitops-applicationset-controller-6b9d5c7ff-m3n4p  1/1     Running   0          2m
openshift-gitops-dex-server-5c8d6e7ff9-q4r5s                1/1     Running   0          2m
openshift-gitops-redis-6d9e7f8ff0-t5u6v                     1/1     Running   0          2m
openshift-gitops-repo-server-7e0f8g9ff1-w7x8y               1/1     Running   0          2m
openshift-gitops-server-8f1g9h0ff2-z9a0b                    1/1     Running   0          2m
```

### Step 2: Access the ArgoCD Web UI

Get the ArgoCD Route URL:

```bash
oc get route openshift-gitops-server -n openshift-gitops -o jsonpath='{.spec.host}'
```

Expected output:

```
openshift-gitops-server-openshift-gitops.apps-crc.testing
```

Open `https://openshift-gitops-server-openshift-gitops.apps-crc.testing` in your browser.

You can log in two ways:

**Via OpenShift OAuth** (recommended): Click "Log in via OpenShift" and use your OpenShift credentials.

**Via ArgoCD admin password**: Retrieve the auto-generated admin password:

```bash
oc extract secret/openshift-gitops-cluster -n openshift-gitops --to=- --keys=admin.password 2>/dev/null
```

Expected output:

```
# admin.password
aB3cD4eF5gH6jK7m
```

Log in with username `admin` and the extracted password.

> **Tip**: In production, disable the `admin` account and rely solely on OpenShift OAuth. The admin password is primarily for initial setup and break-glass scenarios.

### Step 3: Prepare the Target Namespace

Create a namespace for ArgoCD to deploy into:

```bash
oc apply -f manifests/gitops-demo-namespace.yaml
```

The key label `argocd.argoproj.io/managed-by: openshift-gitops` tells the GitOps operator that this namespace should be managed by the ArgoCD instance in `openshift-gitops`.

Grant ArgoCD the necessary permissions:

```bash
oc apply -f manifests/argocd-rbac-rolebinding.yaml
```

This creates a RoleBinding granting the ArgoCD application controller `admin` access in the `gitops-demo` namespace.

> **Why is this necessary?** Unlike a self-installed ArgoCD with cluster-admin, the OpenShift GitOps operator follows the principle of least privilege. ArgoCD can only manage namespaces it has been explicitly granted access to. This is more secure than the typical K8s approach of giving ArgoCD cluster-wide admin.

### Step 4: Create an ArgoCD Application (Manual Sync)

Deploy a sample application with manual sync -- ArgoCD will detect the desired state from Git but wait for you to trigger the sync:

```bash
oc apply -f manifests/argocd-app-manual.yaml
```

```yaml
# manifests/argocd-app-manual.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: sample-app-manual
  namespace: openshift-gitops
spec:
  project: default
  source:
    repoURL: https://github.com/redhat-developer/openshift-gitops-getting-started.git
    targetRevision: main
    path: app
  destination:
    server: https://kubernetes.default.svc
    namespace: gitops-demo
  syncPolicy: {}
```

Check the Application status:

```bash
oc get application sample-app-manual -n openshift-gitops
```

Expected output:

```
NAME                SYNC STATUS   HEALTH STATUS
sample-app-manual   OutOfSync     Missing
```

The status is `OutOfSync` because ArgoCD sees the desired state in Git but has not synced it to the cluster yet. This is the manual sync policy in action.

### Step 5: Sync the Application Manually

Trigger the sync using the `oc` CLI (the ArgoCD CLI `argocd` also works, but we will use `oc` to stay consistent):

```bash
# Using the argocd CLI (if installed):
# argocd app sync sample-app-manual

# Using oc to patch the Application to trigger a sync:
oc annotate application sample-app-manual -n openshift-gitops \
  argocd.argoproj.io/refresh=hard --overwrite
```

Alternatively, open the ArgoCD UI, find `sample-app-manual`, and click the **Sync** button.

To sync via the ArgoCD CLI (optional -- install it first):

```bash
# Install ArgoCD CLI (if needed)
# brew install argocd   # macOS
# OR download from https://argo-cd.readthedocs.io/en/stable/cli_installation/

# Log in to ArgoCD
ARGOCD_HOST=$(oc get route openshift-gitops-server -n openshift-gitops -o jsonpath='{.spec.host}')
ARGOCD_PASSWORD=$(oc extract secret/openshift-gitops-cluster -n openshift-gitops --to=- --keys=admin.password 2>/dev/null)
argocd login "${ARGOCD_HOST}" --username admin --password "${ARGOCD_PASSWORD}" --insecure

# Sync the application
argocd app sync sample-app-manual
```

After syncing, check the status again:

```bash
oc get application sample-app-manual -n openshift-gitops
```

Expected output:

```
NAME                SYNC STATUS   HEALTH STATUS
sample-app-manual   Synced        Healthy
```

Verify the app is running in the target namespace:

```bash
oc get all -n gitops-demo
```

Expected output:

```
NAME                                    READY   STATUS    RESTARTS   AGE
pod/gitops-sample-app-6b8d5c7ff-m3n4p   1/1     Running   0          30s

NAME                        TYPE        CLUSTER-IP     EXTERNAL-IP   PORT(S)    AGE
service/gitops-sample-app   ClusterIP   172.30.45.67   <none>        8080/TCP   30s

NAME                                READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/gitops-sample-app   1/1     1            1           30s
```

### Step 6: Create an Application with Automatic Sync

Now deploy the same app with automatic sync, self-heal, and pruning enabled:

```bash
# First, delete the manual app to avoid conflicts
oc delete application sample-app-manual -n openshift-gitops

# Apply the auto-sync version
oc apply -f manifests/argocd-app-auto.yaml
```

```yaml
# Key parts of manifests/argocd-app-auto.yaml
spec:
  syncPolicy:
    automated:
      prune: true        # Delete resources removed from Git
      selfHeal: true      # Revert manual cluster changes
    syncOptions:
      - CreateNamespace=true
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
```

This Application will sync immediately and automatically. Verify:

```bash
oc get application sample-app-auto -n openshift-gitops -w
```

Expected output (after a few seconds):

```
NAME              SYNC STATUS   HEALTH STATUS
sample-app-auto   Synced        Healthy
```

### Step 7: Test Self-Healing

With `selfHeal: true`, ArgoCD will revert any manual changes made directly to the cluster. Try it:

```bash
# Manually scale the deployment (bypassing Git)
oc scale deployment gitops-sample-app -n gitops-demo --replicas=5
```

Watch what happens:

```bash
# ArgoCD will detect the drift and revert it within ~30 seconds
oc get deployment gitops-sample-app -n gitops-demo -w
```

Expected output:

```
NAME                READY   UP-TO-DATE   AVAILABLE   AGE
gitops-sample-app   5/5     5            5           5m
gitops-sample-app   2/2     2            2           5m     # <-- ArgoCD reverts to Git state
```

ArgoCD detected that the live state (5 replicas) differed from the Git state (2 replicas) and corrected it. This is the power of self-healing -- it prevents configuration drift caused by ad-hoc `oc` or `kubectl` changes.

### Step 8: Understand the Kustomize Base + Overlays Pattern

Examine the Kustomize structure included in this lesson. This is how you would organize your own GitOps repository:

```
manifests/kustomize-example/
  base/
    kustomization.yaml     # Shared resource definitions
    deployment.yaml
    service.yaml
    route.yaml
  overlays/
    staging/
      kustomization.yaml   # 2 replicas, moderate resources
    production/
      kustomization.yaml   # 3 replicas, higher resources
```

Preview what each overlay generates:

```bash
# Staging overlay
oc kustomize manifests/kustomize-example/overlays/staging/
```

Expected output (abbreviated):

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: staging-gitops-sample-app
  namespace: staging
  labels:
    app: gitops-sample-app
spec:
  replicas: 2
  ...
  resources:
    requests:
      cpu: 200m
      memory: 256Mi
```

```bash
# Production overlay
oc kustomize manifests/kustomize-example/overlays/production/
```

Expected output (abbreviated):

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prod-gitops-sample-app
  namespace: production
  labels:
    app: gitops-sample-app
spec:
  replicas: 3
  ...
  resources:
    requests:
      cpu: 500m
      memory: 512Mi
    limits:
      cpu: "1"
      memory: 1Gi
```

When you point an ArgoCD Application at an overlay path, ArgoCD runs `kustomize build` automatically and applies the result. No extra configuration needed -- ArgoCD natively supports Kustomize, Helm, and plain YAML directories.

### Step 9: Create an ArgoCD AppProject

In production, you should scope ArgoCD access using `AppProject` resources instead of using the `default` project:

```bash
oc apply -f manifests/argocd-project.yaml
```

```yaml
# manifests/argocd-project.yaml (key parts)
spec:
  description: "Scoped project for OpenShift GitOps tutorial"
  sourceRepos:
    - "https://github.com/redhat-developer/openshift-gitops-getting-started.git"
    - "https://github.com/your-org/gitops-repo.git"
  destinations:
    - namespace: gitops-demo
      server: https://kubernetes.default.svc
    - namespace: staging
      server: https://kubernetes.default.svc
    - namespace: production
      server: https://kubernetes.default.svc
  clusterResourceWhitelist:
    - group: ""
      kind: Namespace
  namespaceResourceWhitelist:
    - group: ""
      kind: "*"
    - group: apps
      kind: Deployment
    - group: route.openshift.io
      kind: Route
```

AppProjects enforce boundaries:
- **`sourceRepos`**: Only these Git repos can be used as sources.
- **`destinations`**: Applications can only deploy to these namespaces.
- **`clusterResourceWhitelist`**: Which cluster-scoped resources (like Namespaces) ArgoCD can create.
- **`namespaceResourceWhitelist`**: Which namespaced resources ArgoCD can manage.

Verify the project was created:

```bash
oc get appproject tutorial-project -n openshift-gitops
```

Expected output:

```
NAME               AGE
tutorial-project   5s
```

### Step 10: Understand the App-of-Apps Pattern

The app-of-apps pattern uses a single "root" ArgoCD Application to manage all other Applications. Look at the manifest:

```yaml
# manifests/argocd-app-of-apps.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: app-of-apps
  namespace: openshift-gitops
spec:
  project: default
  source:
    repoURL: https://github.com/your-org/gitops-repo.git
    targetRevision: main
    path: argocd-apps        # Directory containing Application YAMLs
  destination:
    server: https://kubernetes.default.svc
    namespace: openshift-gitops
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

In your Git repo, the `argocd-apps/` directory would contain Application CRDs:

```
argocd-apps/
  staging-app.yaml          # Points to overlays/staging
  production-app.yaml       # Points to overlays/production
  monitoring-app.yaml       # Points to a monitoring config repo
```

When ArgoCD syncs `app-of-apps`, it creates these child Applications, each of which then syncs its own target. The result is a hierarchy:

```
app-of-apps (root)
  |-- staging-app       --> deploys staging overlay
  |-- production-app    --> deploys production overlay
  |-- monitoring-app    --> deploys monitoring stack
```

> **Note**: Do not apply `argocd-app-of-apps.yaml` in this lesson -- it references `your-org/gitops-repo.git` which does not exist. This manifest is provided as a reference for structuring your own real GitOps repository. In L2-M1.4 (Pipelines + GitOps Together), you will build a complete end-to-end flow with your own repo.

### Step 11: Explore the ArgoCD UI

Open the ArgoCD Web UI (URL from Step 2) and explore:

1. **Application List**: Shows all managed applications, their sync status, and health.
2. **Application Detail View**: Click on `sample-app-auto` to see:
   - **Resource tree**: Visual map of all K8s resources managed by the Application.
   - **Diff view**: Compare live vs desired state for any resource.
   - **History**: See all sync operations with commit SHAs.
   - **Events**: Sync events, errors, and warnings.
3. **Settings > Projects**: View the `tutorial-project` AppProject and its access restrictions.
4. **Settings > Repositories**: See connected Git repositories and their connection status.

You can also use the CLI to inspect application details:

```bash
# Detailed application info
oc get application sample-app-auto -n openshift-gitops -o yaml

# List managed resources
oc get application sample-app-auto -n openshift-gitops \
  -o jsonpath='{range .status.resources[*]}{.kind}/{.name} -> {.status}{"\n"}{end}'
```

Expected output:

```
Deployment/gitops-sample-app -> Synced
Service/gitops-sample-app -> Synced
Route/gitops-sample-app -> Synced
```

## Verification

Run these commands to verify the lesson was completed successfully:

```bash
# 1. Operator is installed and running
oc get csv -n openshift-gitops | grep -i gitops
# Expected: openshift-gitops-operator.v1.x.y   ...   Succeeded

# 2. ArgoCD pods are all running
oc get pods -n openshift-gitops -l app.kubernetes.io/part-of=argocd
# Expected: All pods in Running state

# 3. ArgoCD Route is accessible
ARGOCD_URL=$(oc get route openshift-gitops-server -n openshift-gitops -o jsonpath='{.spec.host}')
echo "ArgoCD UI: https://${ARGOCD_URL}"
curl -sk "https://${ARGOCD_URL}" | head -5
# Expected: HTML content (the ArgoCD web UI)

# 4. The auto-sync Application is Synced and Healthy
oc get application sample-app-auto -n openshift-gitops
# Expected: SYNC STATUS = Synced, HEALTH STATUS = Healthy

# 5. The sample app is running in the target namespace
oc get pods -n gitops-demo
# Expected: 1+ pods in Running state

# 6. The AppProject exists
oc get appproject tutorial-project -n openshift-gitops
# Expected: tutorial-project listed

# 7. Self-heal is active (drift test)
oc scale deployment gitops-sample-app -n gitops-demo --replicas=10
sleep 30
REPLICAS=$(oc get deployment gitops-sample-app -n gitops-demo -o jsonpath='{.spec.replicas}')
echo "Replicas after self-heal: ${REPLICAS}"
# Expected: Replicas reverted to the Git-defined count (e.g., 2), not 10
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| ArgoCD installation | Manual: apply YAML or Helm chart into a namespace | One-click: install OpenShift GitOps operator from OperatorHub |
| ArgoCD upgrades | Manual: track releases, test, re-deploy | Automatic: OLM manages operator lifecycle |
| Web UI access | Create an Ingress or port-forward | Route auto-created with TLS termination |
| Authentication | Configure Dex/OIDC manually in ArgoCD configmap | OpenShift OAuth integration out of the box |
| Namespace permissions | ArgoCD typically gets cluster-admin | Least-privilege: explicit namespace opt-in via labels and RBAC |
| Multi-tenancy | Manual RBAC configuration | AppProjects + OpenShift RBAC integration |
| Application CRD | Same `argoproj.io/v1alpha1 Application` | Same -- the CRD is identical |
| Sync policies | Same manual/auto/prune/self-heal | Same -- sync behavior is identical |
| Kustomize/Helm support | Same native support | Same -- ArgoCD handles both identically |
| Monitoring | Install Prometheus + Grafana for ArgoCD metrics | ArgoCD metrics flow into OpenShift's built-in monitoring stack |

## Key Takeaways

- **OpenShift GitOps operator eliminates ArgoCD setup toil**: one Subscription gives you a fully configured, OAuth-integrated, Route-exposed ArgoCD instance. In vanilla K8s, this takes significant manual configuration.
- **The Application CRD is platform-agnostic**: everything you learn about ArgoCD Applications, sync policies, and app-of-apps works identically on K8s and OpenShift. The difference is purely in how ArgoCD itself is installed and managed.
- **Self-healing prevents configuration drift**: with `selfHeal: true`, any manual `oc` or `kubectl` change that deviates from Git is automatically reverted. This enforces Git as the single source of truth.
- **Kustomize base + overlays is the standard GitOps repo pattern**: define resources once in base, customize per environment in overlays. ArgoCD natively supports this without any extra tooling.
- **AppProjects scope access in production**: never use the `default` project in production. Create AppProjects that restrict source repos, destination namespaces, and allowed resource types.

## Troubleshooting

### Application stuck in "Unknown" or "Progressing"

```bash
# Check ArgoCD application controller logs
oc logs -n openshift-gitops deployment/openshift-gitops-application-controller --tail=50

# Check the Application's conditions
oc get application <name> -n openshift-gitops -o jsonpath='{.status.conditions}'
```

Common causes:
- Git repo is unreachable (firewall, credentials).
- Target namespace does not exist and `CreateNamespace` sync option is not set.
- ArgoCD lacks RBAC to the target namespace.

### "ComparisonError: failed to load target state"

This usually means the manifests in Git have syntax errors:

```bash
# Validate manifests locally
oc apply --dry-run=client -f manifests/sample-app/

# Check ArgoCD repo-server logs for parse errors
oc logs -n openshift-gitops deployment/openshift-gitops-repo-server --tail=50
```

### ArgoCD cannot access a private Git repo

```bash
# Add repository credentials via the ArgoCD CLI
argocd repo add https://github.com/your-org/private-repo.git \
  --username <user> --password <token>

# Or create a Secret in the openshift-gitops namespace
oc create secret generic private-repo-creds \
  -n openshift-gitops \
  --from-literal=url=https://github.com/your-org/private-repo.git \
  --from-literal=username=<user> \
  --from-literal=password=<token> \
  -l argocd.argoproj.io/secret-type=repository
```

### Sync fails with "permission denied"

ArgoCD's service account needs access to the target namespace:

```bash
# Check if the managed-by label is set on the namespace
oc get namespace gitops-demo -o jsonpath='{.metadata.labels.argocd\.argoproj\.io/managed-by}'
# Should output: openshift-gitops

# Verify the RoleBinding exists
oc get rolebinding argocd-admin -n gitops-demo
```

### Self-heal is not reverting changes

Verify the sync policy:

```bash
oc get application sample-app-auto -n openshift-gitops \
  -o jsonpath='{.spec.syncPolicy.automated}'
```

Expected: `{"prune":true,"selfHeal":true}`

If missing, patch the Application:

```bash
oc patch application sample-app-auto -n openshift-gitops \
  --type merge -p '{"spec":{"syncPolicy":{"automated":{"selfHeal":true}}}}'
```

### CRC resource constraints

ArgoCD with all its components consumes roughly 1-2 GB of RAM. If CRC is struggling:

```bash
# Check node resources
oc adm top nodes

# Reduce ArgoCD resource usage (for lab/demo only, not production)
oc patch argocd openshift-gitops -n openshift-gitops --type merge -p '{
  "spec": {
    "controller": {"resources": {"requests": {"cpu": "100m", "memory": "256Mi"}}},
    "server": {"resources": {"requests": {"cpu": "50m", "memory": "128Mi"}}},
    "repo": {"resources": {"requests": {"cpu": "50m", "memory": "128Mi"}}}
  }
}'
```

## Cleanup

Run the cleanup script or follow the manual steps:

**Option A: Automated Cleanup**

```bash
./scripts/cleanup.sh
```

**Option B: Manual Cleanup**

```bash
# Delete ArgoCD Applications
oc delete application sample-app-manual -n openshift-gitops --ignore-not-found
oc delete application sample-app-auto -n openshift-gitops --ignore-not-found
oc delete application app-of-apps -n openshift-gitops --ignore-not-found

# Delete AppProject
oc delete appproject tutorial-project -n openshift-gitops --ignore-not-found

# Delete demo namespace (removes all resources inside it)
oc delete namespace gitops-demo --ignore-not-found

# Delete RBAC
oc delete rolebinding argocd-admin -n gitops-demo --ignore-not-found 2>/dev/null || true

# Clean up by labels
oc delete all -l tutorial-level=2,tutorial-module=M1 --all-namespaces --ignore-not-found
```

> **Note**: The OpenShift GitOps operator is intentionally NOT removed during cleanup because it is needed for the next lesson (L2-M1.4 -- Pipelines + GitOps Together). To fully remove the operator, uncomment the relevant section in `scripts/cleanup.sh`.

## Next Steps

In **L2-M1.4 -- Pipelines + GitOps Together**, you will combine what you learned in L2-M1.1 (Tekton Pipelines) and this lesson (ArgoCD) to build a complete GitOps CI/CD flow: a Tekton pipeline builds and tests your application, updates manifests in a Git repository, and ArgoCD automatically syncs the changes to the cluster. This is the full pull-based GitOps workflow used in production OpenShift environments.
