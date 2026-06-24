# L2-M2.2 — Installing & Managing Operators

**Level:** Practitioner
**Duration:** 30 min

## Overview

In the previous lesson you learned what Operators are, how OLM manages their lifecycle, and how OperatorHub provides a marketplace of pre-packaged operators. Now it is time to install and manage operators hands-on. You will install an operator from OperatorHub using both the Web Console and the CLI, understand the key OLM resources (Subscriptions, InstallPlans, ClusterServiceVersions), configure approval strategies, and scope operator installations with OperatorGroups.

## Prerequisites

- Completed: [L2-M2.1 — Operator Framework Concepts](../1_operator_framework_concepts/)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in as `kubeadmin` (operator installations require cluster-admin or appropriate RBAC)

## K8s Context

In vanilla Kubernetes, installing an operator typically means:

1. Apply a set of CRDs with `kubectl apply`.
2. Create a namespace, ServiceAccount, RBAC roles, and a Deployment for the controller.
3. Manage upgrades manually by applying new manifests or using Helm charts.
4. There is no standard lifecycle management — every operator handles upgrades differently.

If you have used OLM on plain Kubernetes, you had to install OLM first (`operator-sdk olm install`). Most K8s clusters do not ship with OLM at all.

## Concepts

### OLM Resource Model

OpenShift's Operator Lifecycle Manager uses four key Custom Resources to manage operator installations. Understanding the relationship between them is essential:

```
CatalogSource
  └── PackageManifest (read-only, generated)
        └── Subscription (you create this)
              └── InstallPlan (OLM creates this)
                    └── ClusterServiceVersion (OLM creates this)
                          └── Operator Deployment + CRDs
```

**CatalogSource** — A repository of operator bundles. OpenShift ships with several built-in catalogs:
- `redhat-operators` — Red Hat-certified operators
- `certified-operators` — ISV-certified operators
- `redhat-marketplace` — Red Hat Marketplace operators
- `community-operators` — Community-maintained operators

**Subscription** — The resource you create to tell OLM "I want this operator installed." It specifies which operator, from which catalog, which channel (update stream), and the approval strategy. Think of it as a declaration of intent.

**InstallPlan** — OLM generates an InstallPlan when a Subscription is created or when an update is available. It lists every resource that OLM will create (CRDs, Deployments, RBAC, etc.). With manual approval, you must approve the InstallPlan before OLM proceeds.

**ClusterServiceVersion (CSV)** — The runtime representation of an installed operator version. It contains the operator's metadata, deployment spec, required and provided APIs (CRDs), and the current install status. The CSV is what makes the operator appear in the "Installed Operators" view.

### Approval Strategies

| Strategy | Behavior | Use Case |
|----------|----------|----------|
| `Automatic` | OLM installs updates as soon as they appear in the catalog | Dev/test environments, non-critical operators |
| `Manual` | OLM creates an InstallPlan that requires explicit approval | Production environments, change-controlled systems |

In production, **always use `Manual`** approval so you control exactly when operator upgrades happen. Automatic upgrades can introduce breaking changes to CRD schemas or behavior.

### OperatorGroups

An OperatorGroup defines the set of namespaces where an operator's CRD watches take effect. There are three scoping modes:

- **AllNamespaces** — The operator watches every namespace (typical for cluster-scoped operators like the Prometheus operator).
- **OwnNamespace** — The operator watches only the namespace where it is installed.
- **MultiNamespace** — The operator watches a specific list of namespaces (less common).

Every namespace that contains a Subscription **must** have exactly one OperatorGroup. The `openshift-operators` namespace already has an OperatorGroup configured for `AllNamespaces` scope, which is why most cluster-scoped operators are installed there.

## Step-by-Step

### Step 1: Explore Available Operators via CLI

Before installing anything, explore what is available in the cluster's catalogs.

List all CatalogSources:

```bash
oc get catalogsources -n openshift-marketplace
```

Expected output:
```
NAME                  DISPLAY               TYPE   PUBLISHER   AGE
certified-operators   Certified Operators   grpc   Red Hat     30d
community-operators   Community Operators   grpc   Red Hat     30d
redhat-marketplace    Red Hat Marketplace   grpc   Red Hat     30d
redhat-operators      Red Hat Operators      grpc   Red Hat     30d
```

List available operators (PackageManifests):

```bash
oc get packagemanifests -n openshift-marketplace | head -20
```

Search for a specific operator — we will install the **ETCD operator** from the community catalog as our example (it is lightweight and available on CRC):

```bash
oc get packagemanifests -n openshift-marketplace | grep -i etcd
```

Expected output:
```
etcd   Community Operators   18d
```

Inspect the operator's available channels and versions:

```bash
oc describe packagemanifest etcd -n openshift-marketplace | grep -A 5 "Channels:"
```

### Step 2: Install an Operator via the Web Console

This step walks through the GUI approach. If you prefer CLI-only, skip to Step 3.

1. Open the Web Console: `https://console-openshift-console.apps-crc.testing`
2. Log in as `kubeadmin`.
3. Switch to the **Administrator** perspective.
4. Navigate to **Operators > OperatorHub**.
5. In the search bar, type **etcd**.
6. Click the **etcd** tile (Community Operators).
7. Click **Install**.
8. On the Install Operator page:
   - **Update channel**: select `singlenamespace-alpha` (or the available channel).
   - **Installation mode**: choose **A specific namespace on the cluster**.
   - **Installed Namespace**: select or create `etcd-demo`.
   - **Update approval**: select **Manual** (so we can inspect the InstallPlan).
9. Click **Install**.
10. You will see a message: "Manual approval required." Click **Approve** on the InstallPlan to proceed.
11. Wait for the status to show **Succeeded** under **Operators > Installed Operators**.

> **Note:** If you used the Web Console to install, skip to Step 5 to verify. The next steps show the equivalent CLI workflow.

### Step 3: Install an Operator via CLI (Recommended for Automation)

This is the approach you should use in CI/CD pipelines and GitOps workflows. We will install the same ETCD operator but using YAML manifests.

First, create the target namespace and OperatorGroup:

```bash
oc apply -f manifests/namespace.yaml
oc apply -f manifests/operatorgroup.yaml
```

The OperatorGroup scopes the operator to watch only the `etcd-demo` namespace:

```yaml
# manifests/operatorgroup.yaml
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: etcd-demo-og
  namespace: etcd-demo
  labels:
    app: etcd-demo
    tutorial-level: "2"
    tutorial-module: "M2"
spec:
  targetNamespaces:
    - etcd-demo
```

Now create the Subscription with **Manual** approval:

```bash
oc apply -f manifests/subscription-manual.yaml
```

```yaml
# manifests/subscription-manual.yaml
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: etcd
  namespace: etcd-demo
  labels:
    app: etcd-demo
    tutorial-level: "2"
    tutorial-module: "M2"
spec:
  channel: singlenamespace-alpha
  name: etcd
  source: community-operators
  sourceNamespace: openshift-marketplace
  installPlanApproval: Manual
```

After applying the Subscription, OLM creates an InstallPlan that requires approval.

### Step 4: Approve the InstallPlan

Check the InstallPlan status:

```bash
oc get installplans -n etcd-demo
```

Expected output:
```
NAME            CSV                  APPROVAL   APPROVED
install-xxxxx   etcdoperator.v0.9.4  Manual     false
```

Inspect what the InstallPlan will create:

```bash
oc describe installplan -n etcd-demo $(oc get installplans -n etcd-demo -o jsonpath='{.items[0].metadata.name}')
```

This shows every CRD, Deployment, ServiceAccount, and RBAC resource that OLM will install. In production, review this list before approving.

Approve the InstallPlan:

```bash
oc patch installplan $(oc get installplans -n etcd-demo -o jsonpath='{.items[0].metadata.name}') \
  -n etcd-demo \
  --type merge \
  --patch '{"spec":{"approved":true}}'
```

Expected output:
```
installplan.operators.coreos.com/install-xxxxx patched
```

Alternatively, you can use the script provided:

```bash
bash scripts/approve-installplan.sh etcd-demo
```

### Step 5: Verify the Operator Installation

Watch the CSV status progress to `Succeeded`:

```bash
oc get csv -n etcd-demo -w
```

Expected output (after a minute or so):
```
NAME                  DISPLAY   VERSION   REPLACES              PHASE
etcdoperator.v0.9.4   etcd      0.9.4     etcdoperator.v0.9.2   Succeeded
```

Press `Ctrl+C` to stop watching once you see `Succeeded`.

Verify the operator pod is running:

```bash
oc get pods -n etcd-demo
```

Expected output:
```
NAME                              READY   STATUS    RESTARTS   AGE
etcd-operator-xxxxxxxxxx-xxxxx    1/1     Running   0          2m
```

Check all OLM resources created:

```bash
oc get sub,installplan,csv -n etcd-demo
```

### Step 6: Install an Operator with Automatic Approval

For comparison, let us see how Automatic approval works. We will create a second Subscription manifest:

```bash
oc apply -f manifests/namespace-auto.yaml
oc apply -f manifests/operatorgroup-auto.yaml
oc apply -f manifests/subscription-automatic.yaml
```

```yaml
# manifests/subscription-automatic.yaml
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: etcd
  namespace: etcd-auto-demo
  labels:
    app: etcd-auto-demo
    tutorial-level: "2"
    tutorial-module: "M2"
spec:
  channel: singlenamespace-alpha
  name: etcd
  source: community-operators
  sourceNamespace: openshift-marketplace
  installPlanApproval: Automatic
```

With `Automatic` approval, the InstallPlan is automatically approved and the operator installs immediately:

```bash
oc get csv -n etcd-auto-demo -w
```

Expected output:
```
NAME                  DISPLAY   VERSION   REPLACES              PHASE
etcdoperator.v0.9.4   etcd      0.9.4     etcdoperator.v0.9.2   Succeeded
```

Notice that no manual approval step was needed. The InstallPlan shows `APPROVED: true` from the start:

```bash
oc get installplans -n etcd-auto-demo
```

### Step 7: Inspect the ClusterServiceVersion

The CSV contains rich metadata about the installed operator. Explore it:

```bash
oc get csv etcdoperator.v0.9.4 -n etcd-demo -o yaml | head -60
```

Key sections to look at:

```bash
# What CRDs does this operator provide?
oc get csv etcdoperator.v0.9.4 -n etcd-demo \
  -o jsonpath='{range .spec.customresourcedefinitions.owned[*]}{.name}{"\t"}{.version}{"\t"}{.kind}{"\n"}{end}'
```

Expected output:
```
etcdclusters.etcd.database.coreos.com    v1beta2    EtcdCluster
etcdbackups.etcd.database.coreos.com     v1beta2    EtcdBackup
etcdrestores.etcd.database.coreos.com    v1beta2    EtcdRestore
```

Check the operator's install status:

```bash
oc get csv etcdoperator.v0.9.4 -n etcd-demo \
  -o jsonpath='{.status.phase}'
```

Expected output:
```
Succeeded
```

### Step 8: Managing Operator Updates

When a new version is published to the catalog, OLM behavior depends on your approval strategy:

- **Automatic**: OLM creates and auto-approves a new InstallPlan. The operator updates without intervention.
- **Manual**: OLM creates a new InstallPlan with `approved: false`. You must inspect and approve it.

Check the current Subscription status for pending updates:

```bash
oc get subscription etcd -n etcd-demo -o yaml | grep -A 10 "status:"
```

To see if an update is available:

```bash
oc get subscription etcd -n etcd-demo \
  -o jsonpath='{.status.installedCSV}{"\n"}{.status.currentCSV}{"\n"}'
```

If `currentCSV` differs from `installedCSV`, an update is pending. Approve the new InstallPlan to proceed with the upgrade.

## Verification

Run these commands to confirm everything is correctly installed:

```bash
# 1. Check the Subscription exists and has a healthy status
oc get subscription etcd -n etcd-demo -o jsonpath='{.status.state}'
# Expected: AtLatestKnown

# 2. Check the CSV reached Succeeded phase
oc get csv -n etcd-demo -o jsonpath='{.items[0].status.phase}'
# Expected: Succeeded

# 3. Check the operator pod is running
oc get pods -n etcd-demo -l name=etcd-operator
# Expected: 1/1 Running

# 4. Check that the CRDs were created
oc get crd | grep etcd
# Expected: etcdclusters.etcd.database.coreos.com, etcdbackups, etcdrestores

# 5. (Automatic namespace) Verify the auto-approved installation
oc get csv -n etcd-auto-demo -o jsonpath='{.items[0].status.phase}'
# Expected: Succeeded
```

In the Web Console, navigate to **Operators > Installed Operators** and select the `etcd-demo` project. You should see the etcd operator listed with status **Succeeded**.

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Operator catalog | No built-in catalog; find operators yourself | OperatorHub with curated catalogs (Red Hat, Certified, Community) |
| Installation method | `kubectl apply` raw manifests or Helm | Subscription CR through OLM |
| Lifecycle management | Manual; update CRDs and Deployment yourself | OLM handles upgrades via Subscriptions and InstallPlans |
| Approval control | No built-in mechanism | `Automatic` or `Manual` InstallPlan approval strategies |
| Namespace scoping | Configure operator RBAC manually | OperatorGroup defines watch scopes declaratively |
| Dependency resolution | Manual; install dependencies yourself | OLM resolves and installs operator dependencies automatically |
| Web Console integration | No UI for operator management | Full GUI: browse, install, configure, monitor operators |
| Upgrade rollback | Manual restore of previous manifests | OLM tracks CSV history; delete CSV to trigger reinstall of previous version |
| OLM availability | Must install OLM yourself (`operator-sdk olm install`) | Pre-installed on every OpenShift cluster |

## Key Takeaways

- **Subscriptions are the primary resource** you create to install an operator. They declare which operator, channel, catalog source, and approval strategy to use.
- **Always use Manual approval in production.** Automatic approval is convenient for development but can introduce unexpected changes in production clusters.
- **OperatorGroups control blast radius.** They determine which namespaces an operator can manage. The `openshift-operators` namespace already has an AllNamespaces OperatorGroup, making it the default location for cluster-scoped operators.
- **InstallPlans are your audit trail.** Before approving an InstallPlan, inspect it to understand exactly what resources OLM will create or modify. This is your change control gate.
- **CLI-based operator installation is GitOps-friendly.** By storing Namespace, OperatorGroup, and Subscription manifests in Git, you can manage operator installations declaratively through ArgoCD or a pipeline.

## Troubleshooting

**Subscription stuck in "UpgradePending":**
The InstallPlan is waiting for approval. List and approve it:
```bash
oc get installplans -n etcd-demo
oc patch installplan <name> -n etcd-demo --type merge --patch '{"spec":{"approved":true}}'
```

**CSV in "Failed" or "InstallReady" state:**
Check the CSV conditions for error details:
```bash
oc get csv -n etcd-demo -o jsonpath='{.items[0].status.conditions}' | python3 -m json.tool
```

Common causes: insufficient RBAC, missing dependencies, resource constraints.

**"Too many OperatorGroups in namespace" error:**
Each namespace can have only one OperatorGroup. Check for duplicates:
```bash
oc get operatorgroups -n etcd-demo
```

**Operator pod in CrashLoopBackOff:**
Check the operator pod logs:
```bash
oc logs -n etcd-demo -l name=etcd-operator --tail=50
```

Often caused by SCC restrictions (the operator image may require elevated privileges) or missing CRDs.

**Cannot find operator in PackageManifests:**
Verify the CatalogSource is healthy:
```bash
oc get catalogsource -n openshift-marketplace -o wide
```
If a catalog shows `READY: false` or has no `LASTOBSERVED` time, the catalog pod may need restarting:
```bash
oc delete pod -n openshift-marketplace -l olm.catalogSource=community-operators
```

## Cleanup

```bash
# Remove the manual-approval installation
oc delete subscription etcd -n etcd-demo
oc delete csv -n etcd-demo --all
oc delete operatorgroup etcd-demo-og -n etcd-demo
oc delete project etcd-demo

# Remove the automatic-approval installation
oc delete subscription etcd -n etcd-auto-demo
oc delete csv -n etcd-auto-demo --all
oc delete operatorgroup etcd-auto-demo-og -n etcd-auto-demo
oc delete project etcd-auto-demo

# CRDs are cluster-scoped — clean them up if no other installations use them
oc delete crd etcdclusters.etcd.database.coreos.com 2>/dev/null
oc delete crd etcdbackups.etcd.database.coreos.com 2>/dev/null
oc delete crd etcdrestores.etcd.database.coreos.com 2>/dev/null
```

Or use the cleanup script:

```bash
bash scripts/cleanup.sh
```

## Next Steps

In [L2-M2.3 — Using Operators: Database Example](../3_using_operators_database/), you will put operators to practical use by deploying a PostgreSQL or MongoDB database through an operator. You will interact with the operator's Custom Resources to configure, scale, back up, and restore the database — demonstrating the day-2 operations that make operators so valuable.
