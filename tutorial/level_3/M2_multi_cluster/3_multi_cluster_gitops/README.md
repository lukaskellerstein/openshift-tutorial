# L3-M2.3 -- Multi-Cluster GitOps

**Level:** Expert
**Duration:** 45 min

## Overview

You already know how ArgoCD manages a single cluster via GitOps (L2-M1.3). In production, you rarely have just one cluster -- you have dev, staging, and production environments spread across different clusters, regions, or even cloud providers. This lesson teaches you how to use ArgoCD ApplicationSets to declaratively target multiple clusters, how RHACM Placement policies select which clusters receive which workloads, and how to structure your Git repository so that promoting a change from dev to staging to prod is a clean, auditable git operation rather than a manual `oc apply` against each cluster.

## Prerequisites

- Completed: L3-M2.1 (Advanced Cluster Management -- hub cluster with managed clusters registered)
- Completed: L2-M1.3 (OpenShift GitOps / ArgoCD basics -- Application CRD, sync policies)
- RHACM hub cluster with at least two managed clusters (or simulated with CRC + cluster labels)
- OpenShift GitOps operator installed on the hub cluster
- `oc` and `argocd` CLI tools available
- A Git repository you control (GitHub, GitLab, or Gitea)

## K8s Context

In vanilla Kubernetes with ArgoCD, you deploy to multiple clusters by:

1. Registering each cluster in ArgoCD via `argocd cluster add`.
2. Creating one `Application` CR per cluster, duplicating most of the spec.
3. Managing promotions by manually editing image tags or Kustomize overlays across multiple Application manifests.

This works for two or three clusters, but becomes a maintenance burden at scale. You end up with dozens of nearly identical Application resources, and promoting a release means touching multiple files in multiple places -- a recipe for drift and human error.

ArgoCD introduced `ApplicationSet` to solve this: a single resource that generates multiple `Application` resources from a template plus a list of targets. Kubernetes has no native equivalent -- you are either hand-rolling Application CRs or building custom automation around them.

## Concepts

### ApplicationSet Generators

An `ApplicationSet` contains two parts:

1. **Generators** -- produce a list of parameter sets (one per target cluster/environment).
2. **Template** -- an Application template with parameter placeholders that gets stamped out for each generator entry.

Key generator types for multi-cluster:

| Generator | Use Case |
|-----------|----------|
| `list` | Explicit list of clusters and their parameters. Simple, fully static. |
| `cluster` | Discovers clusters registered in ArgoCD. Filter by labels. |
| `git` | Discovers directories or files in a Git repo. Each directory becomes a target. |
| `matrix` | Combines two generators (e.g., cluster x environment). |
| `merge` | Merges parameter sets from multiple generators with override semantics. |
| `clusterDecisionResource` | Delegates cluster selection to an external controller like RHACM Placement. |

### RHACM Placement Integration

Red Hat Advanced Cluster Management provides `Placement` and `PlacementDecision` CRDs (from L3-M2.1). These let you define rules like "clusters in us-east with at least 8 CPU cores and the label `env=production`." ArgoCD's `clusterDecisionResource` generator reads the resulting `PlacementDecision` to determine target clusters -- this means your cluster selection logic lives in RHACM policies, not in ArgoCD manifests.

### Git Repository Structure for Multi-Cluster

A well-structured GitOps repo separates three concerns:

```
                    +---------------------------+
                    |     GitOps Repository     |
                    +---------------------------+
                    |                           |
          +---------+--------+       +---------+---------+
          |  base/           |       |  overlays/        |
          |  (shared specs)  |       |  (env-specific)   |
          +------------------+       +-------------------+
                                     |                   |
                              +------+------+     +------+------+
                              | dev/        |     | staging/    |
                              +------+------+     +------+------+
                                     |                   |
                              +------+------+     +------+------+
                              | prod/       |     |             |
                              +-------------+     +-------------+
```

The recommended layout using Kustomize:

```
gitops-repo/
  apps/
    my-app/
      base/
        deployment.yaml
        service.yaml
        route.yaml
        kustomization.yaml
      overlays/
        dev/
          kustomization.yaml       # patches: replicas=1, requests low
          replica-patch.yaml
        staging/
          kustomization.yaml       # patches: replicas=2, staging route
          replica-patch.yaml
        prod/
          kustomization.yaml       # patches: replicas=3, prod route, HPA
          replica-patch.yaml
          hpa.yaml
  cluster-config/
    applicationsets/
      my-app-appset.yaml           # The ApplicationSet pointing at apps/my-app
    placements/
      dev-clusters.yaml
      staging-clusters.yaml
      prod-clusters.yaml
```

### Promotion Model

Promoting a release from dev to staging to prod follows this flow:

```
 Developer pushes code
        |
        v
 +------------------+     CI Pipeline builds image,
 |  CI Pipeline      |     tags as v1.2.3, pushes to
 |  (Tekton/Jenkins) |     registry, updates dev overlay
 +--------+---------+
          |
          v
 +--------+---------+     ArgoCD syncs dev clusters
 |  dev overlay      |     automatically (auto-sync)
 |  image: v1.2.3    |
 +--------+---------+
          |
          | PR: update staging/kustomization.yaml
          v            image: v1.2.3
 +--------+---------+     ArgoCD syncs staging clusters
 |  staging overlay  |     (manual sync or auto after
 |  image: v1.2.3    |     PR merge)
 +--------+---------+
          |
          | PR: update prod/kustomization.yaml
          v            image: v1.2.3 (after staging validation)
 +--------+---------+     ArgoCD syncs prod clusters
 |  prod overlay     |     (manual sync required, with
 |  image: v1.2.3    |     approval gate)
 +-------------------+
```

Each promotion is a pull request -- auditable, reviewable, and reversible via `git revert`.

### Failure Modes and Recovery

| Failure | Symptom | Recovery |
|---------|---------|----------|
| ApplicationSet generator returns empty list | No Applications created; workloads vanish from clusters | Check generator config; if using `clusterDecisionResource`, verify PlacementDecision has entries. ArgoCD preserves existing apps with `preserveResourcesOnDeletion` policy. |
| Cluster unreachable during sync | Application shows `Unknown` health; sync times out | ArgoCD retries automatically. Fix network/credentials. If cluster was decommissioned, remove it from the generator list. |
| Git repo structure broken (bad kustomization.yaml) | Sync fails with rendering error | Fix the Kustomize overlay; ArgoCD will not apply broken manifests (safe). Check ArgoCD app details for the specific error. |
| Image tag updated in prod but staging was never validated | Potentially broken prod deployment | Use ApplicationSet `requeueAfterSeconds` and admission webhooks or CI gates to enforce promotion order. Rollback by reverting the Git commit. |
| RHACM Placement selects wrong clusters | Workloads deployed to unintended clusters | Review Placement predicates and cluster labels. Use `PlacementDecision` dry-run to verify. Remove the erroneous Application via ArgoCD then fix Placement. |
| Drift between Git and cluster state | ArgoCD shows `OutOfSync` | If auto-sync is on, ArgoCD self-heals. If manual, investigate who made the out-of-band change and sync. Enable `selfHeal: true` for critical environments. |

## Step-by-Step

### Step 1: Prepare the Git Repository Structure

Create the multi-environment Kustomize layout that ArgoCD will consume. This structure separates base manifests from environment-specific overlays.

```bash
# Create the GitOps repo structure (do this in your Git repo, not on the cluster)
mkdir -p gitops-repo/apps/demo-app/{base,overlays/{dev,staging,prod}}
mkdir -p gitops-repo/cluster-config/{applicationsets,placements}
```

Apply the base Kustomize manifests. These define the common application shape shared across all environments.

The base deployment (`apps/demo-app/base/deployment.yaml`):

```yaml
# Base deployment -- shared across all environments
# Environment-specific patches override replicas, resources, and image tags
apiVersion: apps/v1
kind: Deployment
metadata:
  name: demo-app
  labels:
    app: demo-app
    tutorial-level: "3"
    tutorial-module: "M2"
spec:
  replicas: 1
  selector:
    matchLabels:
      app: demo-app
  template:
    metadata:
      labels:
        app: demo-app
        tutorial-level: "3"
        tutorial-module: "M2"
    spec:
      containers:
        - name: demo-app
          image: image-registry.openshift-image-registry.svc:5000/demo/demo-app:latest
          ports:
            - containerPort: 8080
              protocol: TCP
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 256Mi
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 15
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
          securityContext:
            allowPrivilegeEscalation: false
            runAsNonRoot: true
            seccompProfile:
              type: RuntimeDefault
            capabilities:
              drop:
                - ALL
```

The base service (`apps/demo-app/base/service.yaml`):

```yaml
apiVersion: v1
kind: Service
metadata:
  name: demo-app
  labels:
    app: demo-app
    tutorial-level: "3"
    tutorial-module: "M2"
spec:
  selector:
    app: demo-app
  ports:
    - port: 8080
      targetPort: 8080
      protocol: TCP
```

The base route (`apps/demo-app/base/route.yaml`):

```yaml
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: demo-app
  labels:
    app: demo-app
    tutorial-level: "3"
    tutorial-module: "M2"
spec:
  to:
    kind: Service
    name: demo-app
  port:
    targetPort: 8080
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
```

The base kustomization (`apps/demo-app/base/kustomization.yaml`):

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - deployment.yaml
  - service.yaml
  - route.yaml
commonLabels:
  managed-by: argocd
```

### Step 2: Create Environment-Specific Overlays

Each environment overrides the base with appropriate resource levels, replica counts, and image tags.

**Dev overlay** (`apps/demo-app/overlays/dev/kustomization.yaml`):

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../base
nameSuffix: ""
commonLabels:
  environment: dev
patches:
  - path: replica-patch.yaml
images:
  - name: image-registry.openshift-image-registry.svc:5000/demo/demo-app
    newTag: dev-latest
```

Dev replica patch (`apps/demo-app/overlays/dev/replica-patch.yaml`):

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: demo-app
spec:
  replicas: 1
  template:
    spec:
      containers:
        - name: demo-app
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              cpu: 200m
              memory: 128Mi
```

**Staging overlay** (`apps/demo-app/overlays/staging/kustomization.yaml`):

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../base
commonLabels:
  environment: staging
patches:
  - path: replica-patch.yaml
images:
  - name: image-registry.openshift-image-registry.svc:5000/demo/demo-app
    newTag: v1.0.0
```

Staging replica patch (`apps/demo-app/overlays/staging/replica-patch.yaml`):

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: demo-app
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: demo-app
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 256Mi
```

**Prod overlay** (`apps/demo-app/overlays/prod/kustomization.yaml`):

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../base
  - hpa.yaml
  - network-policy.yaml
commonLabels:
  environment: prod
patches:
  - path: replica-patch.yaml
images:
  - name: image-registry.openshift-image-registry.svc:5000/demo/demo-app
    newTag: v1.0.0
```

Prod replica patch (`apps/demo-app/overlays/prod/replica-patch.yaml`):

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: demo-app
spec:
  replicas: 3
  template:
    spec:
      containers:
        - name: demo-app
          resources:
            requests:
              cpu: 250m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 512Mi
```

Prod HPA (`apps/demo-app/overlays/prod/hpa.yaml`):

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: demo-app
  labels:
    app: demo-app
    tutorial-level: "3"
    tutorial-module: "M2"
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: demo-app
  minReplicas: 3
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

Prod NetworkPolicy (`apps/demo-app/overlays/prod/network-policy.yaml`):

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: demo-app-allow-ingress
  labels:
    app: demo-app
    tutorial-level: "3"
    tutorial-module: "M2"
spec:
  podSelector:
    matchLabels:
      app: demo-app
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              network.openshift.io/policy-group: ingress
      ports:
        - port: 8080
          protocol: TCP
```

### Step 3: Create the ApplicationSet with a List Generator

This is the simplest multi-cluster ApplicationSet. It explicitly lists each cluster and its environment.

Apply the ApplicationSet to your hub cluster (the cluster where ArgoCD runs):

```bash
# Log into the hub cluster
oc login -u admin https://api.hub-cluster.example.com:6443

# Ensure you are in the openshift-gitops namespace
oc project openshift-gitops

# Apply the ApplicationSet
oc apply -f manifests/appset-list-generator.yaml
```

```yaml
# manifests/appset-list-generator.yaml
# ApplicationSet using a list generator -- explicitly maps clusters to environments
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: demo-app
  namespace: openshift-gitops
  labels:
    app: demo-app
    tutorial-level: "3"
    tutorial-module: "M2"
spec:
  goTemplate: true
  goTemplateOptions:
    - missingkey=error
  generators:
    - list:
        elements:
          - cluster: dev-cluster
            url: https://api.dev.example.com:6443
            environment: dev
            namespace: demo-dev
          - cluster: staging-cluster
            url: https://api.staging.example.com:6443
            environment: staging
            namespace: demo-staging
          - cluster: prod-cluster-east
            url: https://api.prod-east.example.com:6443
            environment: prod
            namespace: demo-prod
          - cluster: prod-cluster-west
            url: https://api.prod-west.example.com:6443
            environment: prod
            namespace: demo-prod
  template:
    metadata:
      name: 'demo-app-{{.cluster}}'
      labels:
        app: demo-app
        environment: '{{.environment}}'
        tutorial-level: "3"
        tutorial-module: "M2"
    spec:
      project: default
      source:
        repoURL: https://github.com/your-org/gitops-repo.git
        targetRevision: main
        path: 'apps/demo-app/overlays/{{.environment}}'
      destination:
        server: '{{.url}}'
        namespace: '{{.namespace}}'
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=true
          - PrunePropagationPolicy=foreground
          - ServerSideApply=true
        retry:
          limit: 5
          backoff:
            duration: 5s
            factor: 2
            maxDuration: 3m
```

This generates four `Application` resources -- one for each element in the list. Both prod clusters point to the same `overlays/prod` path, so they get identical configurations.

### Step 4: Use the Cluster Generator with Labels

The cluster generator dynamically discovers clusters registered in ArgoCD rather than hard-coding URLs. This is more scalable -- add a new cluster and label it, and the ApplicationSet picks it up automatically.

```bash
# First, verify which clusters ArgoCD knows about
argocd cluster list

# Add labels to clusters in ArgoCD (if not already labeled)
# These labels match what RHACM sets when importing clusters
argocd cluster set https://api.dev.example.com:6443 \
  --label env=dev \
  --label region=us-east

argocd cluster set https://api.staging.example.com:6443 \
  --label env=staging \
  --label region=us-east

argocd cluster set https://api.prod-east.example.com:6443 \
  --label env=prod \
  --label region=us-east

argocd cluster set https://api.prod-west.example.com:6443 \
  --label env=prod \
  --label region=us-west
```

Apply the cluster-generator-based ApplicationSet:

```bash
oc apply -f manifests/appset-cluster-generator.yaml
```

```yaml
# manifests/appset-cluster-generator.yaml
# ApplicationSet using cluster generator -- dynamically discovers clusters by label
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: demo-app-cluster-gen
  namespace: openshift-gitops
  labels:
    app: demo-app
    tutorial-level: "3"
    tutorial-module: "M2"
spec:
  goTemplate: true
  goTemplateOptions:
    - missingkey=error
  generators:
    - clusters:
        selector:
          matchLabels:
            env: dev
        values:
          environment: dev
          namespace: demo-dev
    - clusters:
        selector:
          matchLabels:
            env: staging
        values:
          environment: staging
          namespace: demo-staging
    - clusters:
        selector:
          matchLabels:
            env: prod
        values:
          environment: prod
          namespace: demo-prod
  template:
    metadata:
      name: 'demo-app-{{.name}}'
      labels:
        app: demo-app
        environment: '{{.values.environment}}'
        tutorial-level: "3"
        tutorial-module: "M2"
    spec:
      project: default
      source:
        repoURL: https://github.com/your-org/gitops-repo.git
        targetRevision: main
        path: 'apps/demo-app/overlays/{{.values.environment}}'
      destination:
        server: '{{.server}}'
        namespace: '{{.values.namespace}}'
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=true
          - PrunePropagationPolicy=foreground
        retry:
          limit: 5
          backoff:
            duration: 5s
            factor: 2
            maxDuration: 3m
```

When ArgoCD discovers a new cluster labeled `env=prod`, it automatically creates an Application for it -- no manifest changes needed.

### Step 5: Integrate with RHACM Placement Policies

RHACM's `Placement` CRD is more powerful than simple label selectors. It can factor in cluster health, resource availability, and custom scoring. The `clusterDecisionResource` generator bridges ArgoCD and RHACM.

First, create the Placement and its binding on the hub cluster:

```bash
oc apply -f manifests/placement-prod.yaml
```

```yaml
# manifests/placement-prod.yaml
# RHACM Placement -- selects production clusters based on labels and health
apiVersion: cluster.open-cluster-management.io/v1beta1
kind: Placement
metadata:
  name: prod-clusters
  namespace: openshift-gitops
  labels:
    tutorial-level: "3"
    tutorial-module: "M2"
spec:
  predicates:
    - requiredClusterSelector:
        labelSelector:
          matchLabels:
            env: prod
        claimSelector:
          matchExpressions:
            - key: platform.open-cluster-management.io
              operator: In
              values:
                - OpenShift
  tolerations:
    - key: cluster.open-cluster-management.io/unreachable
      operator: Exists
      tolerationSeconds: 300
  decisionStrategy:
    groupStrategy:
      clustersPerDecisionGroup: 1
```

Then create the ApplicationSet that consumes the PlacementDecision:

```bash
oc apply -f manifests/appset-placement.yaml
```

```yaml
# manifests/appset-placement.yaml
# ApplicationSet using clusterDecisionResource -- delegates cluster
# selection to RHACM Placement policies
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: demo-app-placement
  namespace: openshift-gitops
  labels:
    app: demo-app
    tutorial-level: "3"
    tutorial-module: "M2"
spec:
  goTemplate: true
  goTemplateOptions:
    - missingkey=error
  generators:
    - clusterDecisionResource:
        configMapRef: acm-placement
        labelSelector:
          matchLabels:
            cluster.open-cluster-management.io/placement: prod-clusters
        requeueAfterSeconds: 180
  template:
    metadata:
      name: 'demo-app-{{.clusterName}}'
      labels:
        app: demo-app
        environment: prod
        tutorial-level: "3"
        tutorial-module: "M2"
    spec:
      project: default
      source:
        repoURL: https://github.com/your-org/gitops-repo.git
        targetRevision: main
        path: apps/demo-app/overlays/prod
      destination:
        server: '{{.server}}'
        namespace: demo-prod
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=true
          - PrunePropagationPolicy=foreground
          - RespectIgnoreDifferences=true
        retry:
          limit: 5
          backoff:
            duration: 5s
            factor: 2
            maxDuration: 3m
  strategy:
    type: RollingSync
    rollingSync:
      steps:
        - matchExpressions:
            - key: region
              operator: In
              values:
                - us-east
        - matchExpressions:
            - key: region
              operator: In
              values:
                - us-west
```

The `strategy.rollingSync` section is critical for production: it deploys to us-east clusters first, and only after those are healthy does it proceed to us-west. This gives you a canary-by-region pattern.

The `requeueAfterSeconds: 180` tells ArgoCD to re-read the PlacementDecision every 3 minutes, so changes to cluster selection are picked up without manual intervention.

### Step 6: Configure the RHACM-ArgoCD Integration ConfigMap

ArgoCD needs to know how to read RHACM's PlacementDecision resources. This is done via a ConfigMap in the ArgoCD namespace:

```bash
oc apply -f manifests/acm-placement-configmap.yaml
```

```yaml
# manifests/acm-placement-configmap.yaml
# ConfigMap that tells ArgoCD how to read RHACM PlacementDecision resources
apiVersion: v1
kind: ConfigMap
metadata:
  name: acm-placement
  namespace: openshift-gitops
  labels:
    tutorial-level: "3"
    tutorial-module: "M2"
data:
  apiVersion: cluster.open-cluster-management.io/v1beta1
  kind: PlacementDecision
  statusListKey: decisions
  matchKey: clusterName
```

### Step 7: Use the Matrix Generator for Complex Topologies

When you need every combination of cluster and application (e.g., deploy three microservices across four clusters), the matrix generator avoids combinatorial explosion in your manifests:

```bash
oc apply -f manifests/appset-matrix-generator.yaml
```

```yaml
# manifests/appset-matrix-generator.yaml
# Matrix generator -- combines app list with cluster discovery
# Generates one Application per (app, cluster) pair
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: platform-apps
  namespace: openshift-gitops
  labels:
    tutorial-level: "3"
    tutorial-module: "M2"
spec:
  goTemplate: true
  goTemplateOptions:
    - missingkey=error
  generators:
    - matrix:
        generators:
          - list:
              elements:
                - appName: frontend
                  appPath: apps/frontend
                - appName: backend-api
                  appPath: apps/backend-api
                - appName: worker
                  appPath: apps/worker
          - clusters:
              selector:
                matchLabels:
                  env: prod
              values:
                environment: prod
  template:
    metadata:
      name: '{{.appName}}-{{.name}}'
      labels:
        app: '{{.appName}}'
        environment: '{{.values.environment}}'
        tutorial-level: "3"
        tutorial-module: "M2"
    spec:
      project: default
      source:
        repoURL: https://github.com/your-org/gitops-repo.git
        targetRevision: main
        path: '{{.appPath}}/overlays/{{.values.environment}}'
      destination:
        server: '{{.server}}'
        namespace: 'platform-{{.values.environment}}'
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=true
        retry:
          limit: 3
          backoff:
            duration: 10s
            factor: 2
            maxDuration: 5m
```

This single ApplicationSet generates `3 apps x N prod clusters` Applications. Adding a fourth microservice or a fifth cluster requires changing only one list -- not creating dozens of new manifests.

### Step 8: Implement the Promotion Workflow

Promotion across environments is a Git operation. Here is the concrete workflow:

```bash
# 1. CI pipeline builds a new image and pushes to the registry
#    Image: quay.io/your-org/demo-app:v1.2.3

# 2. CI pipeline updates the dev overlay automatically
cd gitops-repo
git checkout -b promote/dev-v1.2.3

# Update the dev overlay image tag
cd apps/demo-app/overlays/dev
cat > kustomization.yaml << 'EOF'
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../base
commonLabels:
  environment: dev
patches:
  - path: replica-patch.yaml
images:
  - name: image-registry.openshift-image-registry.svc:5000/demo/demo-app
    newTag: v1.2.3
EOF

git add .
git commit -m "chore(dev): promote demo-app to v1.2.3"
git push origin promote/dev-v1.2.3
# Merge to main -- ArgoCD auto-syncs dev clusters

# 3. After dev validation, promote to staging
git checkout -b promote/staging-v1.2.3
cd apps/demo-app/overlays/staging

# Update staging image tag
sed -i 's/newTag: .*/newTag: v1.2.3/' kustomization.yaml

git add .
git commit -m "chore(staging): promote demo-app to v1.2.3"
git push origin promote/staging-v1.2.3
# Create PR -- require review before merging

# 4. After staging validation, promote to prod
git checkout -b promote/prod-v1.2.3
cd apps/demo-app/overlays/prod

# Update prod image tag
sed -i 's/newTag: .*/newTag: v1.2.3/' kustomization.yaml

git add .
git commit -m "chore(prod): promote demo-app to v1.2.3 [approved: CHANGE-1234]"
git push origin promote/prod-v1.2.3
# Create PR -- require senior review + change approval
```

For production, configure ArgoCD to require manual sync even when auto-sync is enabled for other environments. This is controlled per-ApplicationSet element using the sync policy in each overlay or by setting `automated: {}` (empty, meaning auto-sync off) for production generators.

### Step 9: Set Up Rollback Procedures

When a promotion goes wrong, rollback is a git revert:

```bash
# Identify the promotion commit
git log --oneline apps/demo-app/overlays/prod/

# Revert the promotion commit
git revert <commit-hash>
git push origin main

# ArgoCD detects the revert and syncs the previous image tag
# Verify the rollback
argocd app get demo-app-prod-cluster-east
argocd app get demo-app-prod-cluster-west
```

For immediate rollback without waiting for Git:

```bash
# Emergency: sync to a previous known-good commit
argocd app sync demo-app-prod-cluster-east --revision <known-good-sha>

# This creates drift from Git -- fix by reverting in Git afterward
# ArgoCD will show OutOfSync until Git matches the cluster state
```

### Step 10: Verify the Full Architecture

Review the complete architecture of what you have built:

```
 +---------------------+
 |   Git Repository    |
 |  (Source of Truth)   |
 +----------+----------+
            |
            | webhooks / polling
            v
 +----------+----------+
 |     ArgoCD          |
 |   (Hub Cluster)     |
 |                     |
 |  ApplicationSets    |-------> generators produce
 |                     |         Application CRs
 +--+------+------+---+
    |      |      |
    |      |      +------------------------------------------+
    |      |                                                 |
    |      +----------------------+                          |
    |                             |                          |
    v                             v                          v
 +--+------------------+  +------+--------------+  +--------+------------+
 |  Dev Cluster        |  |  Staging Cluster    |  |  Prod Clusters      |
 |                     |  |                     |  |  (east + west)      |
 |  demo-dev namespace |  |  demo-staging ns    |  |  demo-prod ns       |
 |  replicas: 1        |  |  replicas: 2        |  |  replicas: 3 + HPA  |
 |  auto-sync: ON      |  |  auto-sync: ON      |  |  auto-sync: ON      |
 |  self-heal: ON      |  |  self-heal: ON      |  |  self-heal: ON      |
 |                     |  |                     |  |  rolling deploy:     |
 |                     |  |                     |  |    east -> west      |
 +---------------------+  +---------------------+  +---------------------+

 +---------------------+
 |       RHACM         |
 |    (Hub Cluster)    |
 |                     |
 |  Placement CRDs     |------> PlacementDecision
 |  Cluster labels     |        consumed by ArgoCD
 |  Health checks      |        clusterDecisionResource
 +---------------------+        generator
```

```bash
# Verify ApplicationSet created the expected Applications
oc get applicationsets -n openshift-gitops

# Check generated Applications
oc get applications -n openshift-gitops

# Check sync status of all Applications
argocd app list --output wide

# Verify RHACM PlacementDecisions
oc get placementdecisions -n openshift-gitops

# Check which clusters were selected
oc get placementdecisions -n openshift-gitops -o jsonpath='{.items[*].status.decisions[*].clusterName}'
```

## Verification

Run these commands on the hub cluster to verify everything is working:

```bash
# 1. Verify ApplicationSets exist and are healthy
oc get applicationsets -n openshift-gitops
# Expected: one or more ApplicationSets listed with no errors

# 2. Verify generated Applications
oc get applications -n openshift-gitops -l app=demo-app
# Expected: one Application per cluster/environment combination

# 3. Check sync status (all should be Synced + Healthy)
argocd app list --selector app=demo-app
# Expected output:
# NAME                        CLUSTER                    STATUS   HEALTH
# demo-app-dev-cluster        https://api.dev:6443       Synced   Healthy
# demo-app-staging-cluster    https://api.staging:6443   Synced   Healthy
# demo-app-prod-cluster-east  https://api.prod-east:6443 Synced   Healthy
# demo-app-prod-cluster-west  https://api.prod-west:6443 Synced   Healthy

# 4. Verify resources on a target cluster
oc --context dev-cluster get deployment demo-app -n demo-dev
# Expected: 1/1 READY (dev)

oc --context prod-cluster-east get deployment demo-app -n demo-prod
# Expected: 3/3 READY (prod)

oc --context prod-cluster-east get hpa demo-app -n demo-prod
# Expected: HPA present with min=3, max=10

# 5. Verify Placement integration
oc get placementdecisions -n openshift-gitops \
  -l cluster.open-cluster-management.io/placement=prod-clusters \
  -o yaml
# Expected: status.decisions lists your prod cluster names

# 6. Verify rollout strategy (check events)
oc get applications -n openshift-gitops -l environment=prod \
  -o custom-columns=NAME:.metadata.name,STATUS:.status.sync.status,HEALTH:.status.health.status

# 7. Test the promotion workflow
# Update the dev overlay image tag in Git, push, and verify ArgoCD syncs within ~3 minutes
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes + ArgoCD | OpenShift + ACM + GitOps |
|--------|-------------------|--------------------------|
| Cluster registration | `argocd cluster add` (manual) | ACM auto-imports clusters; ArgoCD reads from ACM |
| Cluster selection | ArgoCD cluster labels (basic) | RHACM Placement CRDs (labels, claims, health, scoring) |
| ApplicationSet | Available (ArgoCD controller) | Same, plus `clusterDecisionResource` for ACM integration |
| Rollout strategy | Manual ordering or custom scripts | `RollingSync` in ApplicationSet with region-based steps |
| Policy enforcement | None built-in; add OPA/Kyverno yourself | ACM Policy framework enforces governance across clusters |
| Observability | Per-cluster ArgoCD dashboard | ACM console shows all clusters; multi-cluster Grafana |
| Namespace creation | Requires `CreateNamespace=true` | Projects with RBAC defaults auto-provisioned |
| Image management | Direct image references | ImageStreams can abstract registry differences per cluster |
| TLS on routes | Ingress + cert-manager | Routes with built-in TLS termination per environment |
| Git repo structure | No convention enforced | Same -- Kustomize overlays pattern is recommended |

## Key Takeaways

- **ApplicationSets eliminate manifest duplication**: A single ApplicationSet resource can generate dozens of Application CRs across clusters and environments. Use the `cluster` generator for dynamic discovery and the `matrix` generator for app-times-cluster combinations.

- **RHACM Placement adds intelligent cluster selection**: Instead of hard-coding cluster URLs, let RHACM decide which clusters should receive workloads based on labels, resource capacity, and health. The `clusterDecisionResource` generator bridges ArgoCD and RHACM.

- **Promotions are pull requests, not manual deploys**: Structure your Git repo with per-environment Kustomize overlays. Promoting a release means changing an image tag in one file and merging a PR. Every promotion is auditable and reversible via `git revert`.

- **Rolling sync prevents global outages**: The `RollingSync` strategy deploys to clusters in a defined order (e.g., region by region). If the first region fails health checks, the rollout stops before reaching other regions.

- **Rollback is always possible through Git**: For planned rollbacks, revert the promotion commit. For emergencies, use `argocd app sync --revision` to pin to a known-good commit, then align Git afterward.

## Cleanup

```bash
# Remove ApplicationSets (this also removes generated Applications)
oc delete applicationset demo-app -n openshift-gitops
oc delete applicationset demo-app-cluster-gen -n openshift-gitops
oc delete applicationset demo-app-placement -n openshift-gitops
oc delete applicationset platform-apps -n openshift-gitops

# Remove Placement resources
oc delete placement prod-clusters -n openshift-gitops

# Remove ConfigMap
oc delete configmap acm-placement -n openshift-gitops

# Clean up resources on target clusters
for ctx in dev-cluster staging-cluster prod-cluster-east prod-cluster-west; do
  oc --context "$ctx" delete namespace demo-dev demo-staging demo-prod --ignore-not-found
done

# Remove tutorial labels from clusters in ArgoCD (optional)
argocd cluster set https://api.dev.example.com:6443 --label env-
argocd cluster set https://api.staging.example.com:6443 --label env-
argocd cluster set https://api.prod-east.example.com:6443 --label env-
argocd cluster set https://api.prod-west.example.com:6443 --label env-

# Verify cleanup
oc get applicationsets -n openshift-gitops
oc get applications -n openshift-gitops -l tutorial-module=M2
```

## Next Steps

In **L3-M2.4 -- Hybrid & Edge Deployments**, you will apply multi-cluster GitOps patterns to edge computing scenarios using Single Node OpenShift (SNO) and MicroShift. You will learn how to handle intermittent connectivity, limited resources, and the unique challenges of deploying to hundreds of edge locations where full-size clusters are impractical.
