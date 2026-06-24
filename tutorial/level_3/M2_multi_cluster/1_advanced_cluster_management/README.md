# L3-M2.1 — Advanced Cluster Management (ACM)

**Level:** Expert
**Duration:** 1 hr

## Overview

In Kubernetes, managing multiple clusters is entirely your problem -- you might use separate kubeconfig contexts, custom scripts, or third-party tools like Rancher or Cluster API. Red Hat Advanced Cluster Management for Kubernetes (RHACM, commonly called ACM) provides a unified control plane for managing the entire lifecycle of multiple OpenShift and Kubernetes clusters: provisioning, importing, governance, application distribution, and observability. This lesson covers ACM's hub-and-spoke architecture, cluster lifecycle management, policy-based governance, multi-cluster application deployment, and the Placement API that ties it all together.

## Prerequisites

- Completed: L3-M1 (Cluster Administration) -- all five lessons
- At least one OpenShift cluster running with cluster-admin access (this becomes the hub)
- A second cluster available for import (CRC, Developer Sandbox, or cloud-provisioned cluster)
- Familiarity with Operators and OLM (L2-M2)
- Understanding of GitOps concepts (L2-M1.3, L2-M1.4)
- `oc` CLI configured and authenticated as cluster-admin on the hub cluster

## K8s Context

In vanilla Kubernetes, multi-cluster management is fragmented:

- **Cluster provisioning**: You use tools like `kubeadm`, `kops`, `eksctl`, or Cluster API -- each with its own API and workflow.
- **Configuration drift**: There is no built-in mechanism to enforce policies across clusters. You might deploy OPA Gatekeeper or Kyverno on each cluster individually, then hope they stay consistent.
- **Application distribution**: Deploying the same application to multiple clusters means running `kubectl apply` or Helm/ArgoCD against each cluster separately.
- **Observability**: Each cluster runs its own monitoring stack. Correlating metrics and logs across clusters requires manual aggregation (Thanos, Loki, etc.).
- **Kubeconfig sprawl**: Managing credentials for dozens of clusters means maintaining large kubeconfig files, rotating certificates independently, and hoping no one leaks a context.

There is no single upstream Kubernetes project that addresses all of these concerns together. Cluster API handles provisioning but not governance. ArgoCD handles deployment but not cluster lifecycle. OPA handles policy but not across clusters. ACM integrates all of these into a single management plane.

## Concepts

### Hub-and-Spoke Architecture

ACM follows a hub-and-spoke model. Understanding this architecture is critical because every ACM operation flows through it:

```
                    +-------------------------------+
                    |        ACM Hub Cluster         |
                    |                                |
                    |  +----------+ +-------------+  |
                    |  |  Cluster | | Application  | |
                    |  | Lifecycle| | Lifecycle    | |
                    |  +----------+ +-------------+  |
                    |  +----------+ +-------------+  |
                    |  |Governance| |Observability | |
                    |  |  Policy  | |  (Thanos)    | |
                    |  +----------+ +-------------+  |
                    |  +-------------------------+   |
                    |  |   Placement Controller   |  |
                    |  +-------------------------+   |
                    +------+-------+--------+--------+
                           |       |        |
              klusterlet   |       |        |   klusterlet
              agent        |       |        |   agent
                    +------+  +----+----+  +-------+
                    |         |         |          |
              +-----v---+ +--v------+ +v---------+
              | Managed  | | Managed | | Managed   |
              | Cluster  | | Cluster | | Cluster   |
              | (AWS)    | | (Azure) | | (On-Prem) |
              +---------+ +---------+ +-----------+
```

**Hub cluster**: The central OpenShift cluster where ACM is installed. It runs the management controllers and stores the desired state for all managed clusters. The hub never runs your application workloads -- it is a control plane only.

**Managed clusters**: Any OpenShift or conformant Kubernetes cluster that is registered with the hub. Each managed cluster runs a lightweight agent called the **klusterlet** that maintains a secure connection back to the hub. The klusterlet pulls policies, reports status, and executes actions locally. This is important: the hub does not push commands to managed clusters. The klusterlet polls the hub, which means managed clusters can operate behind firewalls without inbound network access.

**Why this matters for production**: The spoke-initiated communication model means ACM works across network boundaries -- managed clusters in private data centers, behind NATs, or in restricted cloud VPCs can all connect to a publicly accessible hub. No VPN tunnels or firewall exceptions are required from hub to spoke.

### Cluster Lifecycle Management

ACM manages the complete lifecycle of clusters:

| Phase | Description | Underlying Technology |
|-------|-------------|----------------------|
| **Create** | Provision new clusters on cloud providers or bare metal | Hive (OpenShift-specific) + Cluster API |
| **Import** | Register existing clusters with the hub | Klusterlet agent deployment |
| **Upgrade** | Orchestrate cluster version upgrades | OpenShift update service integration |
| **Hibernate** | Stop cloud-based clusters to save costs | Hive hibernation (powers off VMs) |
| **Destroy** | Decommission clusters and clean up cloud resources | Hive deprovision |

**Creating clusters**: ACM uses the Hive operator internally. You define a `ClusterDeployment` CR that specifies the cloud provider, region, instance types, and OpenShift version. Hive provisions the infrastructure (VMs, networking, DNS, load balancers) and installs OpenShift. For bare metal, ACM uses the agent-based installer with `InfraEnv` and `BareMetalHost` CRDs.

**Importing clusters**: For clusters you already have (including non-OpenShift Kubernetes clusters), ACM generates a klusterlet deployment manifest that you apply to the target cluster. The klusterlet establishes the connection back to the hub.

### Policy-Based Governance

ACM governance lets you define compliance policies on the hub and enforce them across all managed clusters (or a subset selected by placement rules). The policy framework has three CRDs:

- **Policy**: Defines what to check or enforce. Contains one or more policy templates.
- **PlacementBinding**: Connects a Policy to a Placement (which clusters to target).
- **Placement**: Selects clusters based on labels, claims, or cluster sets.

Policy enforcement modes:

| Mode | Behavior |
|------|----------|
| `inform` | Report violations but do not remediate. Use for auditing. |
| `enforce` | Automatically remediate violations. Use for mandatory standards. |

Policy templates can embed any Kubernetes resource. Common use cases:
- Ensure all clusters have a specific NetworkPolicy
- Enforce resource quotas in all namespaces
- Require specific SCCs or Pod Security Standards
- Mandate image pull policies or registry whitelists
- Deploy monitoring agents or security scanners

### Application Lifecycle

ACM can distribute applications across multiple clusters using its Application model. This builds on top of the Open Cluster Management (OCM) project's subscription model:

- **Application**: Groups related resources under a logical application.
- **Channel**: Points to a source of deployable resources (Git repo, Helm repo, object bucket, or namespace).
- **Subscription**: Connects a Channel to managed clusters, specifying which resources to deploy and how.
- **PlacementRule** (legacy) / **Placement** (current): Selects which clusters receive the application.

ACM also integrates with ArgoCD via the ApplicationSet controller, which is covered in L3-M2.3 (Multi-Cluster GitOps).

### Placement API

The Placement API is the unified mechanism for selecting clusters across all ACM features -- governance, applications, and add-ons. It replaces the older `PlacementRule` API.

Key concepts:
- **ManagedClusterSet**: A group of managed clusters (similar to how a namespace groups resources). Enables RBAC on cluster groups.
- **ManagedClusterSetBinding**: Binds a ManagedClusterSet to a namespace, making those clusters available for Placement in that namespace.
- **Placement**: Selects clusters from bound ManagedClusterSets using predicates (labels, claims, taints/tolerations).
- **PlacementDecision**: The output of a Placement -- the actual list of selected clusters. Controllers watch this to know where to deploy.

```
 ManagedClusterSet            Placement
 (groups clusters)   ----->   (selects from set)
        |                          |
        v                          v
 ManagedClusterSetBinding    PlacementDecision
 (binds set to namespace)    (resolved cluster list)
        |                          |
        v                          v
 Namespace where              PolicyBinding or
 Placement lives              Subscription watches
```

### Failure Modes and Recovery

Understanding how ACM fails is critical for production operations:

**Hub cluster failure**: If the hub goes down, managed clusters continue operating independently. Workloads are not affected -- only management operations (policy updates, new deployments, cluster provisioning) are paused. Recovery: restore the hub from etcd backup (L3-M1.4). ACM state is stored in CRDs, so restoring etcd restores the full management plane.

**Klusterlet disconnect**: If a managed cluster loses connectivity to the hub, it continues running with the last known configuration. Policies already applied remain in effect. When connectivity resumes, the klusterlet reconciles and reports any drift. Long disconnections (>15 minutes by default) are flagged as `ManagedClusterConditionAvailable=False` on the hub.

**Policy enforcement failure**: If a policy cannot be applied (e.g., the managed cluster lacks a required CRD), the policy reports `NonCompliant` status. In `enforce` mode, the controller retries with exponential backoff. Check policy status with:

```bash
oc get policy -A -o custom-columns=NAME:.metadata.name,COMPLIANCE:.status.compliant
```

**Cluster provisioning failure**: Hive provisioning can fail due to cloud quotas, DNS issues, or network problems. The `ClusterDeployment` CR reports detailed conditions. Recovery: fix the underlying issue and the controller retries automatically, or delete and recreate the ClusterDeployment.

## Step-by-Step

### Step 1: Install ACM on the Hub Cluster

ACM is installed via the OperatorHub as the "Advanced Cluster Management for Kubernetes" operator. This must be done as `cluster-admin` on the cluster designated as the hub.

```bash
# Log in to the hub cluster as cluster-admin
oc login -u kubeadmin https://api.hub-cluster.example.com:6443

# Create the namespace for ACM (required name)
oc create namespace open-cluster-management
```

Apply the operator subscription:

```bash
oc apply -f manifests/acm-operator-subscription.yaml
```

```yaml
# manifests/acm-operator-subscription.yaml
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: advanced-cluster-management
  namespace: open-cluster-management
  labels:
    app: acm
    tutorial-level: "3"
    tutorial-module: "M2"
spec:
  channel: release-2.10
  installPlanApproval: Automatic
  name: advanced-cluster-management
  source: redhat-operators
  sourceNamespace: openshift-marketplace
```

Wait for the operator to install:

```bash
# Watch the operator install (takes 2-5 minutes)
oc get csv -n open-cluster-management -w

# Expected output (eventually):
# NAME                                 DISPLAY                                      PHASE
# advanced-cluster-management.v2.10.x  Advanced Cluster Management for Kubernetes   Succeeded
```

### Step 2: Create the MultiClusterHub

Once the operator is installed, create the `MultiClusterHub` CR to deploy all ACM components:

```bash
oc apply -f manifests/multiclusterhub.yaml
```

```yaml
# manifests/multiclusterhub.yaml
apiVersion: operator.open-cluster-management.io/v1
kind: MultiClusterHub
metadata:
  name: multiclusterhub
  namespace: open-cluster-management
  labels:
    app: acm
    tutorial-level: "3"
    tutorial-module: "M2"
spec:
  availabilityConfig: High
```

This deploys all ACM subsystems: cluster lifecycle, governance, application lifecycle, observability, and the web console integration. The deployment takes 10-15 minutes.

```bash
# Monitor the deployment
oc get multiclusterhub -n open-cluster-management -w

# Wait until status shows "Running"
# You can also watch individual components:
oc get pods -n open-cluster-management --watch
```

**Resource impact**: ACM deploys approximately 30-40 pods on the hub cluster. For production, Red Hat recommends dedicating infrastructure nodes for ACM components. The hub cluster should have at least 3 worker nodes with 16 GB RAM each available for ACM.

### Step 3: Import a Managed Cluster

There are two approaches to importing a cluster: via the ACM console (recommended for first-time users) or via CLI manifests. We will use the CLI approach.

First, create a `ManagedCluster` resource on the hub:

```bash
oc apply -f manifests/managed-cluster.yaml
```

```yaml
# manifests/managed-cluster.yaml
apiVersion: cluster.open-cluster-management.io/v1
kind: ManagedCluster
metadata:
  name: spoke-cluster-1
  labels:
    app: acm
    tutorial-level: "3"
    tutorial-module: "M2"
    cloud: AWS
    vendor: OpenShift
    environment: staging
    region: us-east-1
spec:
  hubAcceptsClient: true
  leaseDurationSeconds: 60
```

Next, create the `KlusterletAddonConfig` to configure which add-ons run on the managed cluster:

```bash
oc apply -f manifests/klusterlet-addon-config.yaml
```

```yaml
# manifests/klusterlet-addon-config.yaml
apiVersion: agent.open-cluster-management.io/v1
kind: KlusterletAddonConfig
metadata:
  name: spoke-cluster-1
  namespace: spoke-cluster-1
  labels:
    app: acm
    tutorial-level: "3"
    tutorial-module: "M2"
spec:
  clusterName: spoke-cluster-1
  clusterNamespace: spoke-cluster-1
  applicationManager:
    enabled: true
  certPolicyController:
    enabled: true
  iamPolicyController:
    enabled: true
  policyController:
    enabled: true
  searchCollector:
    enabled: true
```

Now retrieve the import command. ACM generates a klusterlet manifest that you apply on the target cluster:

```bash
# Get the import secret (created automatically when ManagedCluster is created)
oc get secret -n spoke-cluster-1 spoke-cluster-1-import -o jsonpath='{.data.crds\.yaml}' | base64 -d > /tmp/klusterlet-crds.yaml
oc get secret -n spoke-cluster-1 spoke-cluster-1-import -o jsonpath='{.data.import\.yaml}' | base64 -d > /tmp/klusterlet-import.yaml
```

Switch to the managed cluster and apply:

```bash
# Switch context to the managed cluster
oc login -u kubeadmin https://api.spoke-cluster-1.example.com:6443

# Apply the klusterlet CRDs and import manifest
oc apply -f /tmp/klusterlet-crds.yaml
oc apply -f /tmp/klusterlet-import.yaml
```

Switch back to the hub and verify the cluster appears:

```bash
# Switch back to the hub cluster
oc login -u kubeadmin https://api.hub-cluster.example.com:6443

# Check managed cluster status
oc get managedclusters

# Expected output:
# NAME              HUB ACCEPTED   MANAGED CLUSTER URLS                    JOINED   AVAILABLE   AGE
# local-cluster     true           https://api.hub-cluster...:6443         True     True        30m
# spoke-cluster-1   true           https://api.spoke-cluster-1...:6443     True     True        2m
```

### Step 4: Organize Clusters with ManagedClusterSets

ManagedClusterSets group clusters for RBAC and placement. In production, you typically group by environment, region, or business unit:

```bash
oc apply -f manifests/managed-cluster-sets.yaml
```

```yaml
# manifests/managed-cluster-sets.yaml
---
apiVersion: cluster.open-cluster-management.io/v1beta2
kind: ManagedClusterSet
metadata:
  name: production-clusters
  labels:
    app: acm
    tutorial-level: "3"
    tutorial-module: "M2"
spec:
  clusterSelector:
    selectorType: ExclusiveClusterSetLabel
---
apiVersion: cluster.open-cluster-management.io/v1beta2
kind: ManagedClusterSet
metadata:
  name: staging-clusters
  labels:
    app: acm
    tutorial-level: "3"
    tutorial-module: "M2"
spec:
  clusterSelector:
    selectorType: ExclusiveClusterSetLabel
```

Add clusters to sets by labeling them:

```bash
# Add spoke-cluster-1 to the staging set
oc label managedcluster spoke-cluster-1 \
  cluster.open-cluster-management.io/clusterset=staging-clusters
```

Bind the cluster set to a namespace so Placements in that namespace can select clusters from it:

```bash
oc apply -f manifests/clusterset-binding.yaml
```

```yaml
# manifests/clusterset-binding.yaml
apiVersion: cluster.open-cluster-management.io/v1beta2
kind: ManagedClusterSetBinding
metadata:
  name: staging-clusters
  namespace: open-cluster-management
  labels:
    app: acm
    tutorial-level: "3"
    tutorial-module: "M2"
spec:
  clusterSet: staging-clusters
```

### Step 5: Create Governance Policies

Governance policies enforce standards across all managed clusters. We will create a policy that ensures every managed cluster has a namespace-scoped resource quota and a network policy denying all ingress by default.

```bash
oc apply -f manifests/governance-policy.yaml
```

```yaml
# manifests/governance-policy.yaml
---
apiVersion: policy.open-cluster-management.io/v1
kind: Policy
metadata:
  name: policy-resource-quota
  namespace: open-cluster-management
  labels:
    app: acm
    tutorial-level: "3"
    tutorial-module: "M2"
  annotations:
    policy.open-cluster-management.io/standards: NIST SP 800-53
    policy.open-cluster-management.io/categories: CM Configuration Management
    policy.open-cluster-management.io/controls: CM-2 Baseline Configuration
spec:
  remediationAction: inform
  disabled: false
  policy-templates:
    - objectDefinition:
        apiVersion: policy.open-cluster-management.io/v1
        kind: ConfigurationPolicy
        metadata:
          name: policy-resource-quota
        spec:
          remediationAction: inform
          severity: medium
          namespaceSelector:
            include:
              - default
          object-templates:
            - complianceType: musthave
              objectDefinition:
                apiVersion: v1
                kind: ResourceQuota
                metadata:
                  name: default-quota
                spec:
                  hard:
                    requests.cpu: "4"
                    requests.memory: 8Gi
                    limits.cpu: "8"
                    limits.memory: 16Gi
                    pods: "20"
                    services: "10"
---
apiVersion: policy.open-cluster-management.io/v1
kind: Policy
metadata:
  name: policy-deny-all-networkpolicy
  namespace: open-cluster-management
  labels:
    app: acm
    tutorial-level: "3"
    tutorial-module: "M2"
  annotations:
    policy.open-cluster-management.io/standards: NIST SP 800-53
    policy.open-cluster-management.io/categories: SC System and Communications Protection
    policy.open-cluster-management.io/controls: SC-7 Boundary Protection
spec:
  remediationAction: enforce
  disabled: false
  policy-templates:
    - objectDefinition:
        apiVersion: policy.open-cluster-management.io/v1
        kind: ConfigurationPolicy
        metadata:
          name: policy-deny-all-networkpolicy
        spec:
          remediationAction: enforce
          severity: high
          namespaceSelector:
            include:
              - default
          object-templates:
            - complianceType: musthave
              objectDefinition:
                apiVersion: networking.k8s.io/v1
                kind: NetworkPolicy
                metadata:
                  name: deny-all-ingress
                spec:
                  podSelector: {}
                  policyTypes:
                    - Ingress
```

Notice the two different remediation actions: the resource quota policy uses `inform` (audit-only, report violations without fixing them), while the network policy uses `enforce` (automatically create the NetworkPolicy on managed clusters that lack it). In production, you typically start with `inform` to assess the impact, then switch to `enforce` once you are confident the policy will not break anything.

### Step 6: Bind Policies to Clusters Using Placement

Create a Placement and bind it to the governance policies:

```bash
oc apply -f manifests/policy-placement.yaml
```

```yaml
# manifests/policy-placement.yaml
---
apiVersion: cluster.open-cluster-management.io/v1beta1
kind: Placement
metadata:
  name: staging-placement
  namespace: open-cluster-management
  labels:
    app: acm
    tutorial-level: "3"
    tutorial-module: "M2"
spec:
  predicates:
    - requiredClusterSelector:
        labelSelector:
          matchLabels:
            environment: staging
  clusterSets:
    - staging-clusters
---
apiVersion: policy.open-cluster-management.io/v1
kind: PlacementBinding
metadata:
  name: binding-policy-resource-quota
  namespace: open-cluster-management
  labels:
    app: acm
    tutorial-level: "3"
    tutorial-module: "M2"
spec:
  placementRef:
    apiGroup: cluster.open-cluster-management.io
    kind: Placement
    name: staging-placement
  subjects:
    - apiGroup: policy.open-cluster-management.io
      kind: Policy
      name: policy-resource-quota
    - apiGroup: policy.open-cluster-management.io
      kind: Policy
      name: policy-deny-all-networkpolicy
```

Verify the placement resolved correctly:

```bash
# Check which clusters the placement selected
oc get placementdecisions -n open-cluster-management

# Check policy compliance status
oc get policy -n open-cluster-management \
  -o custom-columns=NAME:.metadata.name,REMEDIATION:.spec.remediationAction,COMPLIANCE:.status.compliant
```

### Step 7: Deploy an Application Across Clusters

ACM's application lifecycle distributes workloads across managed clusters using a Channel + Subscription model. We will deploy a simple application from a Git repository:

```bash
oc apply -f manifests/multi-cluster-app.yaml
```

```yaml
# manifests/multi-cluster-app.yaml
---
apiVersion: v1
kind: Namespace
metadata:
  name: multi-cluster-demo
  labels:
    app: acm-demo
    tutorial-level: "3"
    tutorial-module: "M2"
---
apiVersion: apps.open-cluster-management.io/v1
kind: Channel
metadata:
  name: demo-app-channel
  namespace: multi-cluster-demo
  labels:
    app: acm-demo
    tutorial-level: "3"
    tutorial-module: "M2"
spec:
  type: Git
  pathname: https://github.com/stolostron/demo-subscription-gitops.git
---
apiVersion: cluster.open-cluster-management.io/v1beta1
kind: Placement
metadata:
  name: demo-app-placement
  namespace: multi-cluster-demo
  labels:
    app: acm-demo
    tutorial-level: "3"
    tutorial-module: "M2"
spec:
  predicates:
    - requiredClusterSelector:
        labelSelector:
          matchLabels:
            environment: staging
  clusterSets:
    - staging-clusters
---
apiVersion: apps.open-cluster-management.io/v1
kind: Subscription
metadata:
  name: demo-app-subscription
  namespace: multi-cluster-demo
  labels:
    app: acm-demo
    tutorial-level: "3"
    tutorial-module: "M2"
  annotations:
    apps.open-cluster-management.io/git-path: demo
    apps.open-cluster-management.io/git-branch: main
spec:
  channel: multi-cluster-demo/demo-app-channel
  placement:
    placementRef:
      kind: Placement
      name: demo-app-placement
---
apiVersion: app.k8s.io/v1beta1
kind: Application
metadata:
  name: demo-app
  namespace: multi-cluster-demo
  labels:
    app: acm-demo
    tutorial-level: "3"
    tutorial-module: "M2"
spec:
  componentKinds:
    - group: apps.open-cluster-management.io
      kind: Subscription
  selector:
    matchLabels:
      app: acm-demo
```

Verify the application was distributed:

```bash
# Check the subscription status
oc get subscription.apps.open-cluster-management.io -n multi-cluster-demo

# Check which clusters received the application
oc get placementdecisions -n multi-cluster-demo

# Check the application status in the ACM console
# Navigate to: Applications > demo-app > Topology
```

### Step 8: Explore the ACM Web Console

ACM extends the OpenShift web console with multi-cluster views. Log in to the hub cluster's console and explore:

1. **Infrastructure > Clusters**: Shows all managed clusters with their status, version, distribution, and labels. You can import, create, upgrade, hibernate, and destroy clusters from here.

2. **Governance**: Shows all policies, their compliance status across clusters, and violation history. You can drill into individual violations to see exactly what is non-compliant.

3. **Applications**: Shows deployed applications and their distribution across clusters. The topology view visualizes the Channel-Subscription-Placement relationship.

4. **Infrastructure > Cluster sets**: Shows ManagedClusterSets and which clusters belong to each.

```bash
# Get the ACM console route
oc get route multicloud-console -n open-cluster-management -o jsonpath='{.spec.host}'
```

## Verification

Run these commands on the hub cluster to verify everything is working:

```bash
# 1. Verify ACM is healthy
oc get multiclusterhub -n open-cluster-management -o jsonpath='{.status.phase}'
# Expected: Running

# 2. Verify managed clusters are connected
oc get managedclusters -o custom-columns=\
NAME:.metadata.name,\
ACCEPTED:.spec.hubAcceptsClient,\
AVAILABLE:.status.conditions[?(@.type=="ManagedClusterConditionAvailable")].status,\
JOINED:.status.conditions[?(@.type=="ManagedClusterJoined")].status
# Expected: All clusters show AVAILABLE=True, JOINED=True

# 3. Verify cluster sets
oc get managedclustersets
# Expected: production-clusters and staging-clusters listed

# 4. Verify policy compliance
oc get policy -A -o custom-columns=\
NAMESPACE:.metadata.namespace,\
NAME:.metadata.name,\
REMEDIATION:.spec.remediationAction,\
COMPLIANCE:.status.compliant
# Expected: Policies show Compliant (enforce) or NonCompliant (inform, if resources
# do not exist yet on managed clusters)

# 5. Verify application distribution
oc get subscription.apps.open-cluster-management.io -n multi-cluster-demo \
  -o custom-columns=NAME:.metadata.name,STATUS:.status.phase
# Expected: Propagated

# 6. Verify placement decisions
oc get placementdecisions -A -o custom-columns=\
NAMESPACE:.metadata.namespace,\
NAME:.metadata.name,\
DECISIONS:.status.decisions[*].clusterName
# Expected: spoke-cluster-1 appears in the decisions
```

**Web Console verification**:

1. Navigate to the ACM console (route from Step 8).
2. Under **Infrastructure > Clusters**, confirm all imported clusters show a green "Ready" status.
3. Under **Governance**, confirm the network policy shows "Compliant" and the resource quota shows the expected status.
4. Under **Applications**, confirm the demo-app shows "Healthy" with the correct cluster topology.

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift with ACM |
|--------|-----------|-------------------|
| Multi-cluster management | Manual kubeconfig switching or third-party tools (Rancher, Crossplane) | Unified hub-and-spoke control plane with single console |
| Cluster provisioning | Separate tools per provider (eksctl, az aks, kubeadm, Cluster API) | ClusterDeployment CR provisions across AWS, Azure, GCP, vSphere, bare metal |
| Cluster import | N/A -- no native concept | ManagedCluster + klusterlet agent with automatic certificate rotation |
| Policy governance | Deploy OPA/Kyverno per cluster; no cross-cluster aggregation | Centralized Policy CRDs with inform/enforce modes across all clusters |
| Configuration drift | No detection mechanism -- rely on GitOps or custom tooling | Continuous compliance monitoring with remediation and audit trail |
| Application distribution | Run kubectl/Helm/ArgoCD against each cluster separately | Channel + Subscription + Placement deploys to selected clusters automatically |
| Cluster grouping | Labels on contexts (informal) | ManagedClusterSets with RBAC enforcement |
| Cluster selection | N/A | Placement API with label selectors, cluster claims, taints/tolerations |
| Observability | Separate Prometheus/Grafana per cluster | Centralized metrics aggregation via Thanos (covered in L3-M2.2) |
| Cluster lifecycle | Manual upgrades, no hibernation | Upgrade orchestration, hibernation, automated decommissioning |
| Communication model | Direct API access required | Spoke-initiated (klusterlet pulls from hub) -- works behind firewalls |

## Key Takeaways

- **ACM uses a hub-and-spoke model** where the hub cluster is the management plane and managed clusters run lightweight klusterlet agents that initiate communication back to the hub -- enabling management across network boundaries without inbound firewall rules.
- **Cluster lifecycle management** covers the full spectrum: provisioning new clusters via Hive, importing existing clusters, upgrading, hibernating (to save cloud costs), and decommissioning -- all from a single control plane.
- **Policy-based governance** with `inform` and `enforce` modes lets you audit compliance first and then automatically remediate, ensuring consistent security posture (network policies, resource quotas, SCCs) across every cluster in your fleet.
- **The Placement API** (replacing the older PlacementRule) is the unified mechanism for selecting clusters across governance, applications, and add-ons, using ManagedClusterSets, label selectors, and cluster claims.
- **Failure resilience is built-in**: managed clusters continue operating independently if the hub goes down, klusterlets reconnect automatically after network interruptions, and hub state is recoverable from etcd backups.

## Cleanup

```bash
# Remove the demo application
oc delete application demo-app -n multi-cluster-demo
oc delete subscription.apps.open-cluster-management.io demo-app-subscription -n multi-cluster-demo
oc delete channel demo-app-channel -n multi-cluster-demo
oc delete placement demo-app-placement -n multi-cluster-demo
oc delete namespace multi-cluster-demo

# Remove governance policies
oc delete placementbinding binding-policy-resource-quota -n open-cluster-management
oc delete placement staging-placement -n open-cluster-management
oc delete policy policy-resource-quota policy-deny-all-networkpolicy -n open-cluster-management

# Remove cluster set bindings and sets
oc delete managedclustersetbinding staging-clusters -n open-cluster-management
oc delete managedclusterset production-clusters staging-clusters

# Detach managed cluster (removes klusterlet but keeps cluster running)
oc delete managedcluster spoke-cluster-1

# To fully uninstall ACM (only if you want to remove it entirely):
# oc delete multiclusterhub multiclusterhub -n open-cluster-management
# oc delete subscription advanced-cluster-management -n open-cluster-management
# oc delete namespace open-cluster-management

# Clean up labels used in this lesson
oc delete all -l tutorial-level=3,tutorial-module=M2 --all-namespaces 2>/dev/null || true
```

**Important**: Detaching a managed cluster (`oc delete managedcluster`) removes the klusterlet from the spoke but does not delete the cluster itself. The cluster continues running -- it simply is no longer managed by the hub. To destroy a cluster provisioned by ACM, use `oc delete clusterdeployment` instead.

## Next Steps

In **L3-M2.2 -- Multi-Cluster Observability**, you will set up centralized monitoring across all your managed clusters using ACM's observability stack. This builds on the hub-spoke architecture from this lesson, adding Thanos-based metrics aggregation and multi-cluster alerting so you can monitor your entire fleet from a single dashboard.
