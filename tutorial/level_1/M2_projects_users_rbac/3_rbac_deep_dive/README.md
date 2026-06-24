# L1-M2.3 — RBAC Deep Dive

**Level:** Foundations
**Duration:** 30 min

## Overview

OpenShift uses the same RBAC (Role-Based Access Control) model as Kubernetes — Roles, ClusterRoles, RoleBindings, and ClusterRoleBindings — but ships with a rich set of default roles and provides the `oc adm policy` shortcut commands to make RBAC management faster and less error-prone. In this lesson you will explore the default roles OpenShift provides, create custom roles and bindings, and learn the `oc adm policy` workflow that replaces raw `kubectl create rolebinding` commands.

## Prerequisites

- Completed: L1-M2.2 — Authentication & OAuth
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in as `kubeadmin` (cluster admin privileges needed for some steps)
- A second user available (e.g., `developer` in CRC) for testing bindings

## K8s Context

You already know Kubernetes RBAC: a **Role** grants permissions within a namespace, a **ClusterRole** grants them cluster-wide, and you bind them to users or groups with **RoleBindings** or **ClusterRoleBindings**. You have likely written YAML like this:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-reader
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
```

And then created a RoleBinding to connect it to a user. OpenShift uses the exact same API group (`rbac.authorization.k8s.io/v1`) and resources. Everything you know about K8s RBAC still applies.

## Concepts

### Default ClusterRoles

Kubernetes ships with a handful of system roles (`cluster-admin`, `admin`, `edit`, `view`). OpenShift keeps those and adds several more that integrate with its Projects and self-service model:

| Role | Scope | What It Grants |
|------|-------|----------------|
| `cluster-admin` | Cluster | Full control over every resource in every namespace. The superuser. |
| `admin` | Project | Full control within a project — can manage roles, quotas, and membership. Cannot modify the project itself. |
| `edit` | Project | Create, update, and delete most resources (pods, deployments, services, routes, build configs). Cannot manage roles or permissions. |
| `view` | Project | Read-only access to most resources. Cannot see secrets. |
| `basic-user` | Cluster | Can view basic information about projects. Every authenticated user gets this. |
| `self-provisioner` | Cluster | Can create new projects. Bound to all authenticated users by default. |
| `cluster-reader` | Cluster | Read-only access to all resources across the entire cluster. Useful for monitoring tools. |
| `cluster-status` | Cluster | Can view cluster status information. |

The `admin`, `edit`, and `view` roles are designed to be used at the project level via RoleBindings. OpenShift automatically grants the `admin` role to the user who creates a project.

### `oc adm policy` — The RBAC Shortcut

In vanilla Kubernetes, managing RBAC means writing and applying YAML or using `kubectl create rolebinding`. OpenShift provides `oc adm policy` commands that handle the most common operations in a single command:

- `oc adm policy add-role-to-user` — bind a role to a user in a project
- `oc adm policy remove-role-from-user` — remove a role binding from a user
- `oc adm policy add-cluster-role-to-user` — bind a cluster role to a user
- `oc adm policy who-can` — check who can perform an action

These commands create the same RoleBinding/ClusterRoleBinding objects you would create in K8s, they just save you from writing YAML for common operations.

### Custom Roles

When the default roles are too broad or too narrow, you create custom Roles (or ClusterRoles) just as you would in Kubernetes. The RBAC API is identical — OpenShift adds nothing to the spec.

## Step-by-Step

### Step 1: Explore the Default ClusterRoles

Log in as `kubeadmin` so you have permission to inspect cluster-level resources:

```bash
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
```

List all ClusterRoles. OpenShift ships with dozens — filter for the key ones:

```bash
oc get clusterroles | grep -E '^(admin|edit|view|cluster-admin|basic-user|self-provisioner|cluster-reader)\s'
```

Expected output:

```
admin                                                          2024-01-15T10:00:00Z
basic-user                                                     2024-01-15T10:00:00Z
cluster-admin                                                  2024-01-15T10:00:00Z
cluster-reader                                                 2024-01-15T10:00:00Z
edit                                                           2024-01-15T10:00:00Z
self-provisioner                                               2024-01-15T10:00:00Z
view                                                           2024-01-15T10:00:00Z
```

Inspect the `edit` role to see what permissions it grants:

```bash
oc describe clusterrole edit
```

Notice it covers pods, deployments, services, routes, buildconfigs, and more — but not roles or rolebindings. That is the difference between `edit` and `admin`.

### Step 2: Inspect Default RoleBindings in a Project

Create a test project and see what RBAC OpenShift sets up automatically:

```bash
oc new-project rbac-demo --display-name="RBAC Demo"
```

List the RoleBindings that OpenShift created in this project:

```bash
oc get rolebindings -n rbac-demo
```

Expected output:

```
NAME                    ROLE                               AGE
admin                   ClusterRole/admin                  5s
system:deployers        ClusterRole/system:deployer        5s
system:image-builders   ClusterRole/system:image-builder   5s
system:image-pullers    ClusterRole/system:image-puller    5s
```

The `admin` binding was created because `kubeadmin` created the project — OpenShift automatically grants `admin` to the project creator. The other bindings are for service accounts that handle deployments and image operations.

### Step 3: Grant a User Access with `oc adm policy`

Give the `developer` user `view` access to the project:

```bash
oc adm policy add-role-to-user view developer -n rbac-demo
```

Expected output:

```
clusterrole.rbac.authorization.k8s.io/view added: "developer"
```

Verify the new binding was created:

```bash
oc get rolebindings -n rbac-demo
```

You should see a new RoleBinding that binds the `view` ClusterRole to the `developer` user.

Now test it. Log in as `developer` and try to read pods (should succeed) and create a pod (should fail):

```bash
oc login -u developer -p developer https://api.crc.testing:6443
oc get pods -n rbac-demo
```

Expected: empty list (no pods yet), but no permission error.

```bash
oc run test-pod --image=registry.access.redhat.com/ubi9/ubi-minimal:latest -n rbac-demo
```

Expected error:

```
Error from server (Forbidden): pods is forbidden: User "developer" cannot create resource "pods" in API group "" in the namespace "rbac-demo"
```

This confirms `view` is read-only. Log back in as `kubeadmin` for the next steps:

```bash
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
```

### Step 4: Upgrade the User's Access

Upgrade `developer` from `view` to `edit`:

```bash
oc adm policy add-role-to-user edit developer -n rbac-demo
```

Optionally, remove the old `view` binding (the `edit` role is a superset of `view`, so having both is redundant):

```bash
oc adm policy remove-role-from-user view developer -n rbac-demo
```

### Step 5: Check Who Can Perform an Action

The `who-can` command is an OpenShift feature that does not exist in vanilla `kubectl`:

```bash
oc adm policy who-can create deployments -n rbac-demo
```

Expected output:

```
Namespace: rbac-demo
Verb:      create
Resource:  deployments.apps

Users:  developer
        kubeadmin
        system:admin
Groups: system:cluster-admins
        system:masters
...
```

Check who can delete the project:

```bash
oc adm policy who-can delete project -n rbac-demo
```

The `developer` user should NOT appear here (they have `edit`, not `admin`).

### Step 6: Create a Custom Role

When the default roles do not fit your needs, create a custom Role. Apply the custom role that grants read access to pods and the ability to view logs, but nothing else:

```bash
oc apply -f manifests/custom-role-pod-diagnostics.yaml -n rbac-demo
```

Inspect the role:

```bash
oc describe role pod-diagnostics -n rbac-demo
```

Expected output:

```
Name:         pod-diagnostics
Labels:       app=rbac-demo
              tutorial-level=1
              tutorial-module=M2
PolicyRule:
  Resources  Non-Resource URLs  Resource Names  Verbs
  ---------  -----------------  --------------  -----
  pods       []                 []              [get list watch]
  pods/log   []                 []              [get]
  events     []                 []              [get list watch]
```

### Step 7: Bind the Custom Role to a User

Apply the RoleBinding that connects the custom role to the `developer` user:

```bash
oc apply -f manifests/rolebinding-pod-diagnostics.yaml -n rbac-demo
```

First, remove the `edit` role from `developer` so we can test the custom role in isolation:

```bash
oc adm policy remove-role-from-user edit developer -n rbac-demo
```

Now switch to `developer` and verify:

```bash
oc login -u developer -p developer https://api.crc.testing:6443
```

```bash
# Should succeed — our custom role grants get/list/watch on pods
oc get pods -n rbac-demo

# Should fail — our custom role does not grant create
oc run test-pod --image=registry.access.redhat.com/ubi9/ubi-minimal:latest -n rbac-demo
```

Expected error for the create attempt:

```
Error from server (Forbidden): pods is forbidden: User "developer" cannot create resource "pods" in API group "" in the namespace "rbac-demo"
```

Log back in as `kubeadmin`:

```bash
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
```

### Step 8: Inspect Self-Provisioner Access

The `self-provisioner` ClusterRole allows any authenticated user to create projects. See the ClusterRoleBinding:

```bash
oc get clusterrolebinding self-provisioners -o yaml
```

Key section:

```yaml
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: self-provisioner
subjects:
  - apiGroup: rbac.authorization.k8s.io
    kind: Group
    name: system:authenticated:oauth
```

This means every user who authenticates through OAuth can create projects. In production, administrators often remove this binding to control project creation:

```bash
# DO NOT run this in your lab unless you want to restrict project creation
# oc adm policy remove-cluster-role-from-group self-provisioner system:authenticated:oauth
```

### Step 9: Use `oc adm policy` for Cluster-Wide Roles

Grant `developer` the `cluster-reader` role so they can view resources across all namespaces:

```bash
oc adm policy add-cluster-role-to-user cluster-reader developer
```

Verify:

```bash
oc login -u developer -p developer https://api.crc.testing:6443
oc get nodes
```

The `developer` user can now view nodes — something a normal project-scoped user cannot do. This is useful for monitoring dashboards and operators that need read access across the cluster.

Remove the cluster-wide binding when done:

```bash
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
oc adm policy remove-cluster-role-from-user cluster-reader developer
```

## Verification

Run these commands to verify the lesson is complete:

```bash
# Verify the custom role exists
oc get role pod-diagnostics -n rbac-demo
```

Expected output:

```
NAME              CREATED AT
pod-diagnostics   2024-01-15T12:00:00Z
```

```bash
# Verify the RoleBinding exists
oc get rolebinding pod-diagnostics-developer -n rbac-demo
```

Expected output:

```
NAME                          ROLE                   AGE
pod-diagnostics-developer     Role/pod-diagnostics   5m
```

```bash
# Verify who can get pods in the project
oc adm policy who-can get pods -n rbac-demo
```

The `developer` user should appear in the output.

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| RBAC API | `rbac.authorization.k8s.io/v1` | Same API — fully compatible |
| Default roles | `cluster-admin`, `admin`, `edit`, `view` | Same four + `basic-user`, `self-provisioner`, `cluster-reader`, `cluster-status` |
| Granting roles | `kubectl create rolebinding` or YAML | `oc adm policy add-role-to-user` (one-liner) |
| Removing roles | Delete the RoleBinding YAML | `oc adm policy remove-role-from-user` (one-liner) |
| Checking access | `kubectl auth can-i` (single user check) | `oc adm policy who-can` (shows ALL users/groups with access) |
| Project creation | Namespace creation requires RBAC or cluster-admin | `self-provisioner` role lets all authenticated users create projects |
| Auto-granted roles on project create | None | Creator gets `admin` role automatically |
| Custom roles | YAML only | YAML or `oc create role` shortcut |

## Key Takeaways

- OpenShift uses the same RBAC API as Kubernetes (`rbac.authorization.k8s.io/v1`). Your existing K8s RBAC knowledge transfers directly.
- OpenShift ships with additional default roles (`basic-user`, `self-provisioner`, `cluster-reader`) that support its self-service project model.
- The `oc adm policy` commands (`add-role-to-user`, `remove-role-from-user`, `who-can`) are shortcuts that replace writing and applying RoleBinding YAML for common operations.
- When a user creates a project, OpenShift automatically binds the `admin` role to that user — this does not happen in vanilla Kubernetes.
- The `self-provisioner` ClusterRoleBinding is what allows all authenticated users to create projects. Removing it is a common production hardening step.

## Cleanup

```bash
# Log in as kubeadmin
oc login -u kubeadmin -p <password> https://api.crc.testing:6443

# Remove the cluster-reader binding if still present
oc adm policy remove-cluster-role-from-user cluster-reader developer 2>/dev/null

# Delete the test project and all resources within it
oc delete project rbac-demo
```

## Next Steps

In **L1-M2.4 — Security Context Constraints**, you will learn about SCCs — OpenShift's mechanism for controlling what pods can and cannot do at the Linux level (run as root, bind privileged ports, use host networking). SCCs are one of the biggest surprises for Kubernetes users migrating to OpenShift, because pods that work fine on K8s often fail on OpenShift due to the stricter defaults.
