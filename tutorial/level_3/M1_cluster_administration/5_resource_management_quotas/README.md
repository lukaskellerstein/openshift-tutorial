# L3-M1.5 — Resource Management & Quotas

**Level:** Expert
**Duration:** 30 min

## Overview

In Kubernetes you already manage resource consumption with ResourceQuotas and LimitRanges at the namespace level. OpenShift adds **ClusterResourceQuotas** — a mechanism for enforcing quotas across multiple projects simultaneously — along with **AppliedClusterResourceQuota** objects that let project-scoped users see which cluster-level quotas affect them. This lesson covers production-grade resource governance: per-project quotas, cluster-wide quotas, LimitRanges for sane defaults, PriorityClasses for workload prioritization, and capacity planning strategies that keep your cluster healthy under load.

## Prerequisites

- Completed: L3-M1.1 (Installation Methods) through L3-M1.4 (etcd & Control Plane Operations)
- OpenShift cluster running (CRC or production cluster)
- Cluster-admin access (`kubeadmin` on CRC)
- Familiarity with K8s ResourceQuota and LimitRange objects (L1-M2 concepts)
- Understanding of OpenShift Projects vs Namespaces (L1-M2.1)

## K8s Context

You already know how Kubernetes controls resource consumption:

- **ResourceQuota** — caps total CPU, memory, storage, and object counts within a single namespace.
- **LimitRange** — sets default requests/limits, min/max constraints, and max limit-to-request ratios per container or pod within a namespace.
- **PriorityClass** — assigns scheduling priority to pods so the scheduler can preempt lower-priority workloads when the cluster is under pressure.

These work identically on OpenShift. The gap in vanilla Kubernetes is that quotas are strictly namespace-scoped: if a team owns five namespaces, you need five separate ResourceQuotas and must manually keep their totals within the team's budget. There is no built-in way to say "team-frontend gets 32 GiB of RAM total across all their namespaces."

## Concepts

### ResourceQuotas and LimitRanges (Same as K8s)

ResourceQuotas and LimitRanges behave identically on OpenShift. Every production project should have both:

- **ResourceQuota** prevents any single project from consuming unbounded resources.
- **LimitRange** ensures every container gets default requests and limits, so no pod is scheduled without resource declarations.

### ClusterResourceQuota (OpenShift Addition)

ClusterResourceQuota (CRQ) is an OpenShift-specific resource that applies a single quota across multiple projects. Projects are selected by either:

1. **Annotation selector** — match projects with a specific annotation (e.g., `openshift.io/requester: team-frontend`).
2. **Label selector** — match projects by labels (e.g., `team: backend`).

This solves the multi-namespace team budget problem that vanilla Kubernetes lacks.

```
+-------------------------------------------------------+
|              ClusterResourceQuota                      |
|  selector: annotation "openshift.io/requester: alice"  |
|  hard:                                                 |
|    requests.cpu: "8"                                   |
|    requests.memory: "16Gi"                             |
|    persistentvolumeclaims: "10"                        |
+-------------------------------------------------------+
        |                    |                    |
   +---------+         +---------+         +---------+
   | alice-  |         | alice-  |         | alice-  |
   | dev     |         | staging |         | prod    |
   | (2 CPU  |         | (2 CPU  |         | (4 CPU  |
   |  used)  |         |  used)  |         |  used)  |
   +---------+         +---------+         +---------+
        Total usage: 8 CPU (at quota limit)
```

### AppliedClusterResourceQuota

When a ClusterResourceQuota targets a project, OpenShift creates an **AppliedClusterResourceQuota** object inside that project. This allows project-scoped users (who cannot read cluster-level resources) to see which quotas apply to them and how much headroom remains. It is a read-only projection — you manage the quota at the cluster level.

### PriorityClasses for Workload Prioritization

PriorityClasses work the same as in Kubernetes. In production OpenShift clusters, they are critical for:

- Ensuring control-plane and infrastructure workloads survive resource pressure.
- Allowing batch/dev workloads to be preempted in favor of production services.
- Preventing low-priority workloads from blocking critical deployments.

OpenShift ships with several built-in PriorityClasses (`system-cluster-critical`, `system-node-critical`, `openshift-user-critical`). You should define additional classes for your workload tiers.

### Capacity Planning Architecture

```
+------------------------------------------------------------------+
|                     Capacity Planning Flow                        |
|                                                                   |
|  1. Inventory           2. Classify              3. Allocate      |
|  +--------------+       +----------------+       +--------------+ |
|  | Node capacity|  -->  | Workload tiers |  -->  | Quotas &     | |
|  | (CPU, mem,   |       | (critical,     |       | LimitRanges  | |
|  |  storage)    |       |  standard,     |       | per project  | |
|  +--------------+       |  batch)        |       +--------------+ |
|                         +----------------+              |         |
|                                                         v         |
|  4. Monitor             5. Alert               6. Adjust          |
|  +--------------+       +----------------+     +--------------+   |
|  | Prometheus   |  -->  | PrometheusRule |  -->| Scale nodes  |   |
|  | metrics on   |       | alerts at 80%  |     | or adjust    |   |
|  | quota usage  |       | utilization    |     | quotas       |   |
|  +--------------+       +----------------+     +--------------+   |
+------------------------------------------------------------------+
```

The flow is: know your capacity, classify workloads, allocate quotas that sum to less than total capacity (with headroom), monitor actual usage, alert before exhaustion, and adjust.

## Step-by-Step

### Step 1: Create Test Projects

Set up multiple projects to demonstrate both per-project and cross-project quotas.

```bash
# Log in as cluster-admin
oc login -u kubeadmin -p <password> https://api.crc.testing:6443

# Create projects for a fictional team
oc new-project quota-demo-dev --display-name="Quota Demo - Dev"
oc new-project quota-demo-staging --display-name="Quota Demo - Staging"
oc new-project quota-demo-prod --display-name="Quota Demo - Prod"

# Label all projects for the same team
oc label namespace quota-demo-dev team=demo-team
oc label namespace quota-demo-staging team=demo-team
oc label namespace quota-demo-prod team=demo-team

# Annotate with the requester (used by ClusterResourceQuota)
oc annotate namespace quota-demo-dev openshift.io/requester=demo-team
oc annotate namespace quota-demo-staging openshift.io/requester=demo-team
oc annotate namespace quota-demo-prod openshift.io/requester=demo-team
```

### Step 2: Apply LimitRanges

LimitRanges ensure every container gets default resource requests and limits. Apply a LimitRange to each project so that no pod runs without resource declarations.

```bash
# Apply the LimitRange to the dev project
oc apply -f manifests/limitrange-default.yaml -n quota-demo-dev
oc apply -f manifests/limitrange-default.yaml -n quota-demo-staging
oc apply -f manifests/limitrange-production.yaml -n quota-demo-prod
```

Verify:

```bash
oc describe limitrange default-limits -n quota-demo-dev
```

Expected output shows default requests and limits for containers.

### Step 3: Apply Per-Project ResourceQuotas

Apply a ResourceQuota to the production project with strict limits.

```bash
oc apply -f manifests/resourcequota-project.yaml -n quota-demo-prod
```

Verify the quota:

```bash
oc describe resourcequota production-quota -n quota-demo-prod
```

Expected output:

```
Name:                   production-quota
Namespace:              quota-demo-prod
Resource                Used  Hard
--------                ----  ----
limits.cpu              0     4
limits.memory           0     8Gi
persistentvolumeclaims  0     5
pods                    0     20
requests.cpu            0     2
requests.memory         0     4Gi
services                0     10
```

### Step 4: Apply a ClusterResourceQuota

This is the OpenShift-specific addition. Create a ClusterResourceQuota that caps resource usage across all three demo-team projects.

```bash
oc apply -f manifests/clusterresourcequota-team.yaml
```

Verify at the cluster level:

```bash
oc describe clusterresourcequota demo-team-quota
```

Expected output:

```
Name:           demo-team-quota
...
Selector:       {"annotations":{"openshift.io/requester":"demo-team"}}
Resource        Used  Hard
--------        ----  ----
requests.cpu    0     8
requests.memory 0     16Gi
pods            0     50
```

### Step 5: Verify AppliedClusterResourceQuota

Switch to a non-admin user and verify that they can see the applied quota in their project.

```bash
# As developer user
oc login -u developer -p developer https://api.crc.testing:6443

# Check which cluster quotas apply to the dev project
oc get appliedclusterresourcequota -n quota-demo-dev
```

Expected output:

```
NAME               AGE
demo-team-quota    30s
```

```bash
# Get details about the applied quota
oc describe appliedclusterresourcequota demo-team-quota -n quota-demo-dev
```

This shows the same quota as the cluster-level object, but is accessible to project-scoped users.

### Step 6: Test Quota Enforcement

Switch back to cluster-admin and deploy workloads to test enforcement.

```bash
oc login -u kubeadmin -p <password> https://api.crc.testing:6443

# Deploy a test workload in the dev project
oc apply -f manifests/deployment-test-workload.yaml -n quota-demo-dev

# Scale up to consume resources
oc scale deployment test-workload -n quota-demo-dev --replicas=3
```

Check quota consumption:

```bash
# Per-project view
oc describe resourcequota -n quota-demo-dev

# Cluster-wide view
oc describe clusterresourcequota demo-team-quota
```

Now try to exceed the quota:

```bash
# This should fail if it would exceed the ClusterResourceQuota
oc apply -f manifests/deployment-quota-buster.yaml -n quota-demo-dev
```

Expected: the pods will fail to schedule once the total usage across all three projects exceeds the ClusterResourceQuota's hard limits.

### Step 7: Configure PriorityClasses

Set up PriorityClasses for workload tiering.

```bash
oc apply -f manifests/priorityclass-production.yaml
oc apply -f manifests/priorityclass-batch.yaml
```

Verify:

```bash
oc get priorityclasses | grep -v system
```

Expected output:

```
NAME                  VALUE        GLOBAL-DEFAULT   AGE
production-critical   1000000      false            5s
batch-low             100          false            5s
```

### Step 8: Deploy Workloads with Priority Classes

Deploy a production workload with high priority and a batch workload with low priority.

```bash
oc apply -f manifests/deployment-production-priority.yaml -n quota-demo-prod
oc apply -f manifests/deployment-batch-priority.yaml -n quota-demo-dev
```

Verify priorities:

```bash
oc get pods -n quota-demo-prod -o custom-columns=NAME:.metadata.name,PRIORITY:.spec.priority,PRIORITY_CLASS:.spec.priorityClassName
oc get pods -n quota-demo-dev -o custom-columns=NAME:.metadata.name,PRIORITY:.spec.priority,PRIORITY_CLASS:.spec.priorityClassName
```

When the cluster is under resource pressure, Kubernetes will preempt the `batch-low` pods before touching the `production-critical` pods.

### Step 9: Capacity Planning — Inspect Current Usage

Use these commands to assess cluster capacity for planning quotas.

```bash
# Total allocatable resources across all nodes
oc adm top nodes

# Detailed per-node resource usage
oc describe nodes | grep -A 5 "Allocated resources"

# All quotas across the cluster
oc get resourcequota --all-namespaces
oc get clusterresourcequota

# Quota usage as a percentage (manual check)
scripts/capacity-report.sh
```

## Verification

Run these checks to confirm all resources are in place and working:

```bash
# 1. LimitRanges exist in all three projects
oc get limitrange -n quota-demo-dev
oc get limitrange -n quota-demo-staging
oc get limitrange -n quota-demo-prod

# 2. Per-project ResourceQuota in prod
oc get resourcequota -n quota-demo-prod

# 3. ClusterResourceQuota exists at the cluster level
oc get clusterresourcequota demo-team-quota

# 4. AppliedClusterResourceQuota is visible in each project
for ns in quota-demo-dev quota-demo-staging quota-demo-prod; do
  echo "--- $ns ---"
  oc get appliedclusterresourcequota -n $ns
done

# 5. PriorityClasses exist
oc get priorityclass production-critical batch-low

# 6. Test workloads are running with correct priority
oc get pods -n quota-demo-prod -o wide
oc get pods -n quota-demo-dev -o wide

# 7. Quota usage is being tracked
oc describe clusterresourcequota demo-team-quota
```

## Failure Modes & Recovery

### Quota Exceeded — Pods Stuck in Pending

**Symptom:** New pods stay in `Pending` state. Events show `exceeded quota`.

```bash
oc get events -n quota-demo-dev --field-selector reason=FailedCreate
```

**Recovery:**

1. Check which quota is exhausted: `oc describe resourcequota -n <project>` and `oc describe clusterresourcequota <name>`.
2. Either scale down existing workloads, increase the quota, or request capacity from the cluster admin.

### LimitRange Blocks Deployment

**Symptom:** Pods fail to create with messages like `minimum cpu usage per Container is 50m, but request is 10m`.

**Recovery:**

1. Review the LimitRange: `oc describe limitrange -n <project>`.
2. Adjust the pod's requests/limits to fall within the LimitRange bounds.
3. Or adjust the LimitRange if the constraint is too tight.

### ClusterResourceQuota Not Applying to a Project

**Symptom:** A new project should be governed by a CRQ, but `oc get appliedclusterresourcequota` returns nothing.

**Recovery:**

1. Verify the project has the correct annotation or label:
   ```bash
   oc get namespace <project> -o jsonpath='{.metadata.annotations.openshift\.io/requester}'
   oc get namespace <project> -o jsonpath='{.metadata.labels.team}'
   ```
2. Verify the CRQ selector matches: `oc describe clusterresourcequota <name>`.
3. Apply the missing annotation/label: `oc annotate namespace <project> openshift.io/requester=<value>`.

### Preemption Cascades

**Symptom:** Low-priority pods are continuously evicted, restarted, and evicted again because the cluster is permanently over-committed.

**Recovery:**

1. Check node capacity vs allocation: `oc adm top nodes`.
2. Add nodes (scale MachineSet) or reduce resource requests on low-priority workloads.
3. Consider setting `preemptionPolicy: Never` on the low-priority PriorityClass to prevent eviction loops (pods will remain Pending instead of being scheduled and then evicted).

### Quota Drift Across Projects

**Symptom:** A ClusterResourceQuota reports inaccurate usage after project deletions or rapid scaling events.

**Recovery:**

1. Check the CRQ status: `oc get clusterresourcequota <name> -o yaml` and inspect the `status.namespaces` field.
2. If usage is stale, delete and recreate the CRQ (this resets accounting). Quotas are purely enforcement objects — no workloads are affected by deleting a CRQ.

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Per-namespace quotas | ResourceQuota | ResourceQuota (identical) |
| Per-namespace defaults | LimitRange | LimitRange (identical) |
| Cross-namespace quotas | Not available natively | ClusterResourceQuota |
| Quota visibility for users | Must have namespace RBAC | AppliedClusterResourceQuota projection |
| Priority classes | PriorityClass | PriorityClass (identical) + built-in `openshift-user-critical` |
| Default project quotas | Must apply manually | Project template with quotas auto-applied |
| Quota scoping | Namespace only | Namespace + annotation/label selectors across projects |
| Capacity monitoring | Prometheus (install yourself) | Built-in Prometheus + console views |
| Self-provisioned projects | N/A | Self-provisioned projects can inherit quotas via templates |

## Key Takeaways

- **ResourceQuotas and LimitRanges work identically** on OpenShift and Kubernetes. Every production project should have both to prevent resource exhaustion and ensure sane defaults.
- **ClusterResourceQuota is OpenShift's key addition** — it lets you set a single resource budget across all projects owned by a team, user, or application group, solving the multi-namespace quota problem that vanilla K8s lacks.
- **AppliedClusterResourceQuota** provides project-scoped visibility into cluster-level quotas, so developers can see their budget without needing cluster-admin access.
- **PriorityClasses** are essential for production workload tiering — define at least three tiers (critical, standard, batch) and assign them consistently to prevent batch workloads from starving production services during resource pressure.
- **Capacity planning is an ongoing process** — set quotas that sum to 70-80% of total cluster capacity, monitor usage with Prometheus, alert at 80% utilization, and scale nodes or adjust quotas before exhaustion.

## Cleanup

```bash
# Log in as cluster-admin
oc login -u kubeadmin -p <password> https://api.crc.testing:6443

# Delete ClusterResourceQuota (cluster-scoped)
oc delete clusterresourcequota demo-team-quota

# Delete PriorityClasses (cluster-scoped)
oc delete priorityclass production-critical batch-low

# Delete projects (this deletes all namespaced resources within them)
oc delete project quota-demo-dev quota-demo-staging quota-demo-prod
```

## Next Steps

In **L3-M2.1 — Advanced Cluster Management (ACM)**, you will move beyond single-cluster administration to managing fleets of OpenShift clusters. ACM introduces hub/managed cluster topology, policy-based governance across clusters, and centralized application distribution — building on the resource management foundations covered here by extending quota and policy enforcement across multiple clusters.
