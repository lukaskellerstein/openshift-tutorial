# L2-M2.1 --- Operator Framework Concepts

**Level:** Practitioner
**Duration:** 30 min

## Overview

Operators extend Kubernetes by encoding domain-specific operational knowledge into software. If you have managed stateful services on Kubernetes, you have likely installed CRDs and controllers manually, maybe from a Helm chart or a raw set of YAML files. OpenShift makes operators a first-class citizen: OLM (Operator Lifecycle Manager) ships pre-installed, OperatorHub provides a curated catalog, and the entire platform -- from networking to monitoring -- is itself managed by operators. In this lesson you will understand how the Operator Framework works, explore the operator maturity model, and see what OpenShift gives you out of the box compared to vanilla Kubernetes.

## Prerequisites

- Level 1 completed (all modules)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in as both `developer` and `kubeadmin` (you will need cluster-admin for some exploration steps)

## K8s Context

You already know CRDs (Custom Resource Definitions) and controllers. In vanilla Kubernetes the pattern is straightforward: you define a CRD, deploy a controller that watches it, and the controller reconciles desired state with actual state. What Kubernetes does *not* provide is a standard way to install, upgrade, or manage the lifecycle of these controllers. You typically `kubectl apply` a bundle of YAML, or use Helm, and handle upgrades yourself. If you have used the Operator SDK or Kubebuilder, you know the development side. But the *lifecycle management* side -- installation channels, automatic upgrades, dependency resolution, RBAC scoping -- is left to you. That is the gap OpenShift fills.

## Concepts

### What Is an Operator?

An operator is a controller that manages a custom resource and encodes the operational knowledge of a human administrator. The key insight is that running complex software (databases, message brokers, monitoring stacks) requires ongoing human decisions: when to scale, how to back up, how to upgrade safely. An operator automates those decisions.

The Operator pattern has three pillars:

1. **Custom Resource Definition (CRD)** -- defines the API (e.g., `PostgresCluster`, `KafkaCluster`).
2. **Controller** -- watches for changes to the custom resource and reconciles the cluster to match the desired state.
3. **Operational logic** -- the encoded knowledge: backup procedures, upgrade strategies, failure recovery.

### Operator Lifecycle Manager (OLM)

OLM is a Kubernetes extension that manages the lifecycle of operators themselves. Think of it as an "operator for operators." On vanilla Kubernetes you must install OLM manually (`operator-sdk olm install`). On OpenShift, OLM is pre-installed and deeply integrated.

OLM introduces several key CRDs:

| CRD | Purpose |
|-----|---------|
| `CatalogSource` | Points to a repository of operators (like a package repository) |
| `Subscription` | Declares intent to install an operator and track an update channel |
| `InstallPlan` | A calculated set of resources to create/update for an installation |
| `ClusterServiceVersion` (CSV) | Describes a specific version of an operator -- its metadata, RBAC requirements, owned CRDs, and deployment |
| `OperatorGroup` | Scopes the namespaces an operator can watch |

The lifecycle flow is:

```
CatalogSource --> Subscription --> InstallPlan --> ClusterServiceVersion --> Operator Deployment
```

### OperatorHub

OperatorHub is a catalog of operators curated and available through the OpenShift Web Console. It aggregates multiple sources:

- **Red Hat Operators** -- built and supported by Red Hat (e.g., OpenShift Pipelines, Service Mesh, Logging).
- **Certified Operators** -- third-party operators certified by Red Hat (e.g., CrunchyData PostgreSQL, Strimzi Kafka).
- **Community Operators** -- community-maintained operators from operatorhub.io.
- **Marketplace** -- commercial operators from Red Hat Marketplace.

In vanilla Kubernetes, you would go to operatorhub.io, find the operator, copy the install instructions, and run them manually. On OpenShift, it is a point-and-click (or single CLI command) experience with built-in dependency resolution.

### Operator Maturity Levels

The Operator Framework defines five maturity levels that describe how much operational knowledge an operator encodes:

```
Level 5: Auto Pilot    -- full automation, auto-tuning, anomaly detection
Level 4: Deep Insights -- metrics, alerts, log processing, workload analysis
Level 3: Full Lifecycle -- backup/restore, failure recovery, upgrades
Level 2: Seamless Upgrades -- operator and operand upgrades, patch management
Level 1: Basic Install  -- automated deployment, CRD-based configuration
```

Most community operators are Level 1 or 2. Production-grade operators (like CrunchyData PostgreSQL or Red Hat AMQ Streams) reach Level 3-4. Level 5 is the aspiration -- an operator that can manage itself with minimal human intervention.

When evaluating an operator, check its maturity level in OperatorHub. A Level 1 operator automates installation but still requires manual intervention for upgrades, backups, and failure recovery.

### OpenShift Platform Operators

Here is what makes OpenShift fundamentally different from vanilla Kubernetes: the platform itself is managed by operators. These are called **Cluster Operators** and they manage core infrastructure:

- `openshift-apiserver` -- manages the OpenShift API server
- `authentication` -- manages OAuth and identity providers
- `console` -- manages the Web Console
- `dns` -- manages CoreDNS
- `image-registry` -- manages the internal container registry
- `ingress` -- manages the HAProxy-based router
- `monitoring` -- manages the Prometheus stack
- `network` -- manages OVN-Kubernetes networking
- `storage` -- manages CSI drivers and storage

This means OpenShift upgrades are themselves operator-driven: the Cluster Version Operator (CVO) orchestrates all cluster operators to move the platform from one version to the next.

## Step-by-Step

### Step 1: Explore Cluster Operators

Log in as `kubeadmin` and list the cluster operators that manage the OpenShift platform:

```bash
oc login -u kubeadmin https://api.crc.testing:6443
oc get clusteroperators
```

Expected output (abbreviated):

```
NAME                                       VERSION   AVAILABLE   PROGRESSING   DEGRADED   SINCE
authentication                             4.14.0    True        False         False      2d
cloud-credential                           4.14.0    True        False         False      2d
cluster-autoscaler                         4.14.0    True        False         False      2d
console                                    4.14.0    True        False         False      2d
dns                                        4.14.0    True        False         False      2d
image-registry                             4.14.0    True        False         False      2d
ingress                                    4.14.0    True        False         False      2d
monitoring                                 4.14.0    True        False         False      2d
network                                    4.14.0    True        False         False      2d
openshift-apiserver                        4.14.0    True        False         False      2d
...
```

Notice the three boolean columns: `AVAILABLE`, `PROGRESSING`, and `DEGRADED`. A healthy cluster has all operators showing `True / False / False`. If any operator is `DEGRADED=True`, the cluster has a problem.

### Step 2: Inspect a Cluster Operator in Detail

Pick the `console` operator and look at its details:

```bash
oc describe clusteroperator console
```

Look for the `Status.Conditions` section, which shows the same three conditions plus `Upgradeable`:

```
Conditions:
  Type                Status  Reason
  ----                ------  ------
  Available           True    AsExpected
  Progressing         False   AsExpected
  Degraded            False   AsExpected
  Upgradeable         True    AsExpected
```

Also inspect `Status.RelatedObjects` to see what resources this operator manages.

### Step 3: Examine OLM Components

OLM runs in the `openshift-operator-lifecycle-manager` namespace. Check the pods:

```bash
oc get pods -n openshift-operator-lifecycle-manager
```

Expected output:

```
NAME                                READY   STATUS    RESTARTS   AGE
catalog-operator-7b8f5d7b4-xxxxx    1/1     Running   0          2d
collect-profiles-xxxxx              0/1     Completed 0          1h
olm-operator-6b8c5f8d9-xxxxx       1/1     Running   0          2d
packageserver-7b9f5c6d8-xxxxx      1/1     Running   0          2d
packageserver-7b9f5c6d8-yyyyy      1/1     Running   0          2d
```

Two key pods run OLM:

- **olm-operator** -- watches `Subscriptions` and `InstallPlans`, creates `ClusterServiceVersions`
- **catalog-operator** -- resolves dependencies from `CatalogSources`, creates `InstallPlans`

The **packageserver** exposes the catalog as a Kubernetes API, which is what powers the OperatorHub UI.

### Step 4: List Available CatalogSources

CatalogSources define where OLM looks for operators:

```bash
oc get catalogsources -n openshift-marketplace
```

Expected output:

```
NAME                  DISPLAY               TYPE   PUBLISHER   AGE
certified-operators   Certified Operators   grpc   Red Hat     2d
community-operators   Community Operators   grpc   Red Hat     2d
redhat-marketplace    Red Hat Marketplace   grpc   Red Hat     2d
redhat-operators      Red Hat Operators      grpc   Red Hat     2d
```

Each CatalogSource is a gRPC-based index of operator bundles. You can browse the contents:

```bash
oc get packagemanifests | head -20
```

This lists every operator available for installation. There are typically 200+ operators available out of the box.

### Step 5: Examine a PackageManifest

Pick an operator and inspect its details. Let us look at the `openshift-pipelines-operator-rh` operator (Tekton):

```bash
oc describe packagemanifest openshift-pipelines-operator-rh -n openshift-marketplace
```

Key fields to look for:

- **Catalog Source**: which CatalogSource provides this operator
- **Channels**: available update channels (e.g., `latest`, `pipelines-1.12`)
- **Default Channel**: the channel selected by default
- **CSV Description**: the ClusterServiceVersion that would be installed, including its maturity level (look for `capabilities` in the annotations)

```bash
# Quick way to see available channels
oc get packagemanifest openshift-pipelines-operator-rh -n openshift-marketplace \
  -o jsonpath='{range .status.channels[*]}{.name}{"\n"}{end}'
```

### Step 6: List Currently Installed Operators

Check what operators are already installed via OLM subscriptions:

```bash
oc get subscriptions -A
```

Then look at the corresponding CSVs:

```bash
oc get csv -A
```

Expected output shows operators that CRC installs by default (may vary):

```
NAMESPACE                              NAME                       DISPLAY          VERSION   PHASE
openshift-operator-lifecycle-manager   packageserver              Package Server   0.19.0    Succeeded
```

The `PHASE: Succeeded` means the operator is healthy and installed correctly.

### Step 7: Understand the CRD-Controller Relationship

Let us trace the CRD-controller pattern with a real example. List all CRDs on the cluster:

```bash
oc get crds | wc -l
```

You will see hundreds of CRDs -- OpenShift ships with far more CRDs than vanilla Kubernetes because every platform feature is CRD-driven. Filter for a specific API group:

```bash
oc get crds | grep route.openshift.io
```

Expected output:

```
routes.route.openshift.io   2024-01-15T00:00:00Z
```

Now look at the CRD definition:

```bash
oc get crd routes.route.openshift.io -o jsonpath='{.spec.versions[0].name}'
```

This shows the API version. The Route controller (managed by the `ingress` cluster operator) watches these CRDs and configures the HAProxy router accordingly. This is the operator pattern in action at the platform level.

### Step 8: Explore via the Web Console

Open the OpenShift Web Console (as `kubeadmin`):

```bash
# Get the console URL
oc whoami --show-console
```

Navigate to:

1. **Operators > OperatorHub** -- browse available operators, filter by category, search by name
2. **Operators > Installed Operators** -- view operators installed in the current namespace
3. **Administration > Cluster Settings > ClusterOperators** -- view the platform cluster operators

In OperatorHub, click on any operator tile to see:
- Description and documentation links
- Maturity level (capability level)
- Available channels
- Provider and support information
- The CRDs it will install

### Step 9: Explore OLM CRDs with a Sample Manifest

Review the sample manifests in this lesson to understand the structure of OLM resources. These are *reference manifests* -- you do not need to apply them now (we will install an operator in the next lesson), but understanding their structure is essential.

Examine the CatalogSource manifest:

```yaml
# manifests/sample-catalogsource.yaml
apiVersion: operators.coreos.com/v1alpha1
kind: CatalogSource
metadata:
  name: my-operator-catalog
  namespace: openshift-marketplace
  labels:
    app: my-operator-catalog
    tutorial-level: "2"
    tutorial-module: "M2"
spec:
  sourceType: grpc
  image: quay.io/example/my-operator-index:v1.0.0
  displayName: My Operator Catalog
  publisher: My Organization
  updateStrategy:
    registryPoll:
      interval: 30m
```

And the Subscription manifest:

```yaml
# manifests/sample-subscription.yaml
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: my-operator
  namespace: openshift-operators
  labels:
    app: my-operator
    tutorial-level: "2"
    tutorial-module: "M2"
spec:
  channel: stable
  name: my-operator
  source: redhat-operators
  sourceNamespace: openshift-marketplace
  installPlanApproval: Manual
```

Key points about the Subscription:

- **channel** -- which update stream to follow (e.g., `stable`, `fast`, `candidate`)
- **source** -- which CatalogSource to pull from
- **installPlanApproval** -- `Automatic` (OLM auto-approves upgrades) or `Manual` (requires human approval). For production, use `Manual`.

## Verification

Confirm you can successfully run all exploration commands:

```bash
# 1. Cluster operators are healthy
oc get clusteroperators | grep -c "True.*False.*False"
# Should return a number equal to the total number of cluster operators

# 2. OLM is running
oc get pods -n openshift-operator-lifecycle-manager -o name | grep -c "olm-operator\|catalog-operator"
# Should return 2

# 3. CatalogSources are available
oc get catalogsources -n openshift-marketplace --no-headers | wc -l
# Should return 4 (redhat-operators, certified-operators, community-operators, redhat-marketplace)

# 4. PackageManifests are accessible
oc get packagemanifests --no-headers | wc -l
# Should return a number > 100
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| OLM | Not installed; must install manually via `operator-sdk olm install` | Pre-installed and integrated into the platform |
| Operator catalog | Browse operatorhub.io, copy YAML, `kubectl apply` | OperatorHub built into Web Console, one-click install |
| Dependency resolution | Manual -- you read the docs and install prerequisites | OLM resolves and installs dependencies automatically |
| Update channels | Not a native concept | Built-in: choose `stable`, `fast`, or `candidate` per operator |
| Upgrade approval | Manual `kubectl apply` of new version | `Automatic` or `Manual` approval via Subscription |
| RBAC for operators | You write your own ClusterRoles | CSV declares required RBAC; OLM creates it |
| Platform management | Add-ons installed separately (CoreDNS, kube-proxy, etc.) | Cluster Operators manage every platform component |
| CRD count (fresh install) | ~10 CRDs | 200+ CRDs (every platform feature is CRD-driven) |
| Operator maturity info | No standard metadata | Capability level (1-5) shown in OperatorHub |
| Catalog sources | Single source (operatorhub.io) or custom | Four built-in sources plus custom catalog support |

## Key Takeaways

- **Operators encode operational knowledge** -- they are not just installers but ongoing automation for complex software lifecycle management (upgrades, backups, scaling, recovery).
- **OLM is pre-installed on OpenShift** -- this removes significant friction compared to vanilla Kubernetes where you must install and manage OLM yourself.
- **OpenShift itself is operator-driven** -- cluster operators manage every platform component, and the Cluster Version Operator orchestrates platform upgrades.
- **Operator maturity levels matter** -- a Level 1 operator only automates installation, while a Level 3+ operator handles the full lifecycle including backups and recovery. Always check the maturity level before relying on an operator in production.
- **OperatorHub provides a curated catalog** with four sources (Red Hat, Certified, Community, Marketplace), dependency resolution, and update channels -- a significant improvement over manually installing operators from raw YAML.

## Cleanup

This lesson was exploratory -- no resources were created. No cleanup is needed.

If you created a test project for exploration:

```bash
oc delete project operator-exploration 2>/dev/null
```

## Next Steps

In **L2-M2.2 -- Installing and Managing Operators**, you will install an operator from OperatorHub using both the Web Console and the CLI. You will work with Subscriptions, InstallPlans, and approval strategies, and learn how to manage operator upgrades in a production-safe manner.
