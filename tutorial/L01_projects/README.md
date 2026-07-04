# LP-L01 — Projects: Multi-Tenancy Made Practical

**Level:** Personalized
**Duration:** 20 min

## Overview

Projects are OpenShift's enhanced Namespaces — the same underlying Kubernetes object but wrapped with extra metadata, automatic RBAC bindings, and self-provisioning. In this lesson, you create the `shopinsights` project for the tutorial, then set up separate `shopinsights-dev` and `shopinsights-staging` environments with resource quotas and limit ranges. You will understand why Projects exist on top of Namespaces and how they simplify multi-tenant operations.

## Prerequisites

- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in via `oc login` (see [login instructions](../README.md#logging-in-to-your-cluster) — Sandbox tokens expire daily!)

## Quick Run

Want to skip the step-by-step and run everything at once?

```bash
./scripts/run.sh
```

The steps below explain what the script does and why.

## K8s Context

In Kubernetes, Namespaces are resource boundaries — nothing more. You create one with `kubectl create namespace`, and it is an empty container for objects. There are no default RBAC bindings, no display metadata, and no self-provisioning. If a developer needs a new namespace, a cluster admin creates it and then manually sets up RoleBindings so the developer can use it. Resource quotas and limit ranges exist in K8s, but you have to remember to apply them every time — nothing enforces consistency.

## Concepts

### Project = Namespace + Defaults

When you run `oc new-project`, OpenShift creates a standard Kubernetes Namespace and then applies several defaults on top:

1. **Display name and description** — human-readable metadata shown in the Web Console
2. **Default RBAC** — the creator automatically gets `admin` role on the project (can deploy workloads, manage RBAC within the project, but cannot modify the project's quotas)
3. **Annotations** — OpenShift tracks who requested the project and when

The Namespace is the real Kubernetes object underneath. You can still use `kubectl get namespaces` and see Projects listed. They are the same object — Projects just have extra metadata and automation.

### Self-Provisioning

In vanilla Kubernetes, only cluster admins can create namespaces. In OpenShift, any authenticated user can create Projects by default. This is called self-provisioning and is controlled by the `self-provisioners` ClusterRoleBinding.

For a team of developers, this means: no tickets to IT, no waiting for a namespace — just `oc new-project my-feature-branch` and start deploying. Admins can disable self-provisioning or restrict it to specific groups.

### Project Templates

When self-provisioning is enabled, you probably want guardrails. Project templates let admins define what every new Project gets by default: ResourceQuotas, LimitRanges, NetworkPolicies, default RoleBindings. When anyone creates a project, the template is applied automatically.

This solves the K8s problem of "we forgot to add a quota to the new namespace and one team ate all the cluster resources."

### ResourceQuotas and LimitRanges

- **ResourceQuota** — caps the total resources a Project can consume (total CPU, memory, number of pods, number of services, etc.)
- **LimitRange** — sets default resource requests and limits for individual containers, so developers do not have to specify them in every Deployment

Together, they prevent any single Project from monopolizing cluster resources — critical for multi-tenant environments.

## Step-by-Step

### Step 1: Create the Main ShopInsights Project

First, create the primary project that will host the ShopInsights microservices throughout this tutorial:

```bash
oc new-project shopinsights \
  --display-name="ShopInsights" \
  --description="Main project for the ShopInsights tutorial microservices"
```

> **"You may not request a new project via this API"** — this means project self-provisioning is disabled. Two common causes:
>
> - **Developer Sandbox**: you get one pre-assigned project and cannot create new ones. Run `oc projects` to see your project name (e.g., `username-dev`), then use it instead:
>   ```bash
>   oc project <your-sandbox-project>
>   ```
> - **CRC**: you may be logged in as `kubeadmin` or hit a rate limit. Log out and log in as `developer`:
>   ```bash
>   oc login -u developer -p developer https://api.crc.testing:6443
>   oc new-project shopinsights
>   ```
>
> All remaining commands in this tutorial work the same regardless of the project name — just make sure `oc project` shows the right one before continuing.

### Step 2: Create the Dev Project

Now create a `shopinsights-dev` project with a display name and description:

```bash
oc new-project shopinsights-dev \
  --display-name="ShopInsights Dev" \
  --description="Development environment for ShopInsights microservices"
```

Or apply the ProjectRequest manifest:

```bash
oc apply -f manifests/project-dev.yaml
```

```yaml
# manifests/project-dev.yaml
apiVersion: project.openshift.io/v1
kind: ProjectRequest
metadata:
  name: shopinsights-dev
displayName: "ShopInsights Dev"
description: "Development environment for ShopInsights microservices"
```

Notice that `displayName` and `description` are top-level fields on ProjectRequest, not under `metadata` — this is an OpenShift-specific API.

### Step 3: Create the Staging Project

```bash
oc new-project shopinsights-staging \
  --display-name="ShopInsights Staging" \
  --description="Staging environment for ShopInsights — resource-constrained to mirror production limits"
```

Or apply the manifest:

```bash
oc apply -f manifests/project-staging.yaml
```

### Step 4: Compare with kubectl create namespace

To see the difference, try creating a plain Kubernetes namespace:

```bash
kubectl create namespace shopinsights-test
```

Now compare the two:

```bash
# OpenShift Project — has annotations, display name, RBAC
oc describe project shopinsights-dev

# Plain namespace — bare object, no RBAC, no metadata
kubectl describe namespace shopinsights-test
```

Key differences you will see:

| Detail | `oc new-project` | `kubectl create namespace` |
|--------|-------------------|---------------------------|
| Display name | Yes | No |
| Description | Yes | No |
| Creator annotation | `openshift.io/requester: developer` | None |
| Default RBAC | Creator gets `admin` role | No role bindings |

Clean up the test namespace:

```bash
kubectl delete namespace shopinsights-test
```

### Step 5: Inspect Project Metadata

```bash
oc describe project shopinsights-dev
```

Expected output (key sections):

```
Name:           shopinsights-dev
Display Name:   ShopInsights Dev
Description:    Development environment for ShopInsights microservices
Status:         Active
Annotations:    openshift.io/description=Development environment for ShopInsights microservices
                openshift.io/display-name=ShopInsights Dev
                openshift.io/requester=developer
                openshift.io/sa.scc.mcs=...
                openshift.io/sa.scc.supplemental-groups=...
                openshift.io/sa.scc.uid-range=...
```

The `sa.scc.*` annotations define the UID/GID ranges for pods in this project — this is how OpenShift assigns random UIDs per namespace (you will see the SCC behavior in action in L03 when you deploy workloads).

Check the RBAC that was automatically created:

```bash
oc get rolebindings -n shopinsights-dev
```

You will see bindings like `admin` for the `developer` user — this was created automatically by `oc new-project`. In Kubernetes, you would need to create these RoleBindings manually.

### Step 6: Apply a ResourceQuota to Staging

Switch to the staging project:

```bash
oc project shopinsights-staging
```

Apply a ResourceQuota that limits what the staging environment can consume:

```bash
oc apply -f manifests/resource-quota.yaml
```

```yaml
# manifests/resource-quota.yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: staging-quota
  namespace: shopinsights-staging
  labels:
    app: shopinsights
    tutorial: personalized
    lesson: "01"
spec:
  hard:
    pods: "10"
    requests.cpu: "4"
    requests.memory: 8Gi
    limits.cpu: "4"
    limits.memory: 8Gi
```

This means: staging can run at most 10 pods, and total resource requests cannot exceed 4 CPUs and 8 GiB of memory. If someone tries to deploy a pod that would push the total over these limits, it is rejected.

Verify the quota:

```bash
oc describe quota staging-quota -n shopinsights-staging
```

### Step 7: Apply a LimitRange to Staging

A ResourceQuota caps the total, but developers still need to specify resource requests in every Deployment. A LimitRange provides defaults so they do not have to:

```bash
oc apply -f manifests/limit-range.yaml
```

```yaml
# manifests/limit-range.yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: staging-limits
  namespace: shopinsights-staging
  labels:
    app: shopinsights
    tutorial: personalized
    lesson: "01"
spec:
  limits:
    - type: Container
      default:
        cpu: 500m
        memory: 512Mi
      defaultRequest:
        cpu: 100m
        memory: 128Mi
      max:
        cpu: "2"
        memory: 2Gi
      min:
        cpu: 50m
        memory: 64Mi
```

Now any container in `shopinsights-staging` that does not specify resource requests gets `100m` CPU and `128Mi` memory by default. No container can request more than 2 CPUs or 2 GiB memory.

Verify:

```bash
oc describe limitrange staging-limits -n shopinsights-staging
```

### Step 8: Check Self-Provisioning Permissions

Self-provisioning is what allows you (as the `developer` user) to create projects. Verify this:

```bash
# Can the current user create projects?
oc policy can-i create projectrequests

# Who has the self-provisioner role?
oc get clusterrolebinding self-provisioners -o yaml
```

Expected output for the first command: `yes`

The `self-provisioners` ClusterRoleBinding grants the `self-provisioner` ClusterRole to `system:authenticated:oauth`, meaning any authenticated user can create projects.

To disable self-provisioning (do not run this, just understand it):

```bash
# DO NOT RUN — this would prevent developers from creating projects
# oc adm policy remove-cluster-role-from-group self-provisioner system:authenticated:oauth
```

### Step 9: Explore a Project Template (Reference)

The manifest `manifests/project-template.yaml` shows what an admin would configure as a default project template. When applied, every new project automatically gets these resources:

```bash
# View the template (do not apply — this requires cluster-admin)
cat manifests/project-template.yaml
```

The template includes:
- A default ResourceQuota
- A default NetworkPolicy (deny all ingress from other namespaces)
- The standard Project metadata

In production, this is how you enforce consistent governance across all projects without relying on developers to remember to apply quotas.

### Step 10: View Projects in the Web Console

1. Open https://console-openshift-console.apps-crc.testing
2. Switch to the **Administrator** perspective
3. Navigate to **Home -> Projects**
4. You should see `shopinsights`, `shopinsights-dev`, and `shopinsights-staging`
5. Click on `shopinsights-staging` — note the **ResourceQuota** and **LimitRange** sections in the project details

The Web Console shows quota utilization with progress bars — a visual indicator of how close a project is to its limits.

## Verification

```bash
# List all shopinsights projects
oc get projects | grep shopinsights

# Expected output:
# shopinsights          ShopInsights              Active
# shopinsights-dev      ShopInsights Dev          Active
# shopinsights-staging  ShopInsights Staging      Active

# Verify ResourceQuota in staging
oc describe quota staging-quota -n shopinsights-staging

# Verify LimitRange in staging
oc describe limitrange staging-limits -n shopinsights-staging

# Verify RBAC — developer has admin on dev project
oc policy can-i '*' '*' -n shopinsights-dev
# Expected: yes

# Verify self-provisioning
oc policy can-i create projectrequests
# Expected: yes
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Resource boundary | Namespace | Project (= Namespace + metadata + RBAC) |
| Creation | `kubectl create namespace` | `oc new-project` (adds display name, description, RBAC) |
| Default RBAC | None — admin must create RoleBindings | Creator gets `admin` role automatically |
| Self-provisioning | Not supported natively | Any authenticated user can create Projects |
| Display metadata | None | Display name, description, requester annotation |
| Templates | No built-in concept | Project templates enforce defaults (quotas, policies) |
| ResourceQuota | Supported (manual) | Supported (can be automated via templates) |
| LimitRange | Supported (manual) | Supported (can be automated via templates) |
| Web Console | Basic namespace list | Rich project view with quota utilization bars |

## Key Takeaways

- A Project **is** a Namespace — the same Kubernetes object with OpenShift metadata and automation on top
- `oc new-project` gives the creator admin access automatically, so developers can self-serve without cluster admin intervention
- **ResourceQuotas** cap total project consumption; **LimitRanges** set per-container defaults — use both in shared environments
- **Project templates** let admins enforce consistent governance (quotas, network policies, RBAC) across all new projects automatically
- In your ShopInsights workflow, separate projects per environment (dev, staging, prod) provide isolation, independent quotas, and clear ownership

## Cleanup

> Or run `./scripts/cleanup.sh` to clean up automatically.

If you are continuing to L02, keep all three projects — you will use `shopinsights` throughout the remaining lessons, and `shopinsights-dev`/`shopinsights-staging` again in L06 for RBAC demonstrations.

If you want to clean up the dev/staging projects only:

```bash
oc delete project shopinsights-dev
oc delete project shopinsights-staging
```

Note: deleting a project deletes everything inside it (pods, services, quotas, etc.). Do **not** delete the `shopinsights` project — all subsequent lessons use it.

Switch back to the main project:

```bash
oc project shopinsights
```

## Next Steps

Your projects are set up. In [L02: Build & Image Resources](../L02_builds_and_images/), you will build the ShopInsights microservices from source directly on the cluster using BuildConfig, Source-to-Image (S2I), and ImageStreams — no external registry needed.
