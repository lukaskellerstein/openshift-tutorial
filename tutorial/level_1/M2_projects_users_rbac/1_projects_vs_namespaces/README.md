# L1-M2.1 — Projects vs Namespaces

**Level:** Foundations
**Duration:** 20 min

## Overview

In Kubernetes you organize workloads into Namespaces. OpenShift wraps every Namespace in a higher-level object called a **Project** that adds human-readable metadata, default RBAC bindings, and network-policy scaffolding. This lesson shows you exactly what a Project adds over a plain Namespace, how self-provisioning works, and how to customize what every new Project gets by installing a project-request template.

## Prerequisites

- Completed: L1-M1.3 (CLI Tools: `oc` vs `kubectl`)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in as `developer` and able to switch to `kubeadmin` when needed

## K8s Context

In vanilla Kubernetes a Namespace is the only multi-tenancy boundary:

```bash
kubectl create namespace my-app
```

That gives you an isolated scope for names and resource quotas, but nothing else. There are no default RBAC bindings, no human-readable display name, and no built-in way for non-admin users to create their own namespaces safely. Cluster admins typically write custom automation or use tools like Hierarchical Namespaces to fill those gaps.

## Concepts

### Projects are Namespaces — Plus More

Every OpenShift Project is backed by a real Kubernetes Namespace (you can verify with `kubectl get namespaces`). The Project API adds three things on top:

1. **Metadata annotations** — `openshift.io/display-name` and `openshift.io/description` give teams a human-readable label and purpose statement visible in the Web Console.
2. **Default RBAC bindings** — The user who creates a Project is automatically granted the `admin` role inside it. Additional default bindings (e.g., for image-pullers or builders) are created from a template.
3. **Self-provisioning** — Regular (non-admin) users can create their own Projects through the API. This is governed by a ClusterRoleBinding called `self-provisioners` and can be disabled or customized.

### The Project-Request Template

When a user runs `oc new-project`, OpenShift does not simply create a Namespace. It processes a **project-request template** that defines which objects to create. The default template creates:

- The Namespace itself
- A RoleBinding granting the requesting user the `admin` role
- RoleBindings for system service accounts (`builder`, `deployer`, `image-puller`)

You can replace this default template with your own to enforce standards across every new Project — for example, injecting a default NetworkPolicy, LimitRange, or ResourceQuota automatically.

### Self-Provisioning

By default, every authenticated user can create Projects via a ClusterRoleBinding that assigns the `self-provisioner` ClusterRole to the `system:authenticated:oauth` group. Cluster admins can:

- **Disable self-provisioning** entirely by removing this binding
- **Restrict it** to specific groups by editing the binding's subjects

## Step-by-Step

### Step 1: Create a Project with `oc new-project`

Create a Project with a display name and description:

```bash
oc new-project demo-project \
  --display-name="Demo Project" \
  --description="A tutorial project demonstrating Projects vs Namespaces"
```

Expected output:

```
Now using project "demo-project" on server "https://api.crc.testing:6443".
...
```

### Step 2: Inspect the Project metadata

Look at the annotations OpenShift added:

```bash
oc get project demo-project -o yaml
```

You will see annotations like:

```yaml
metadata:
  annotations:
    openshift.io/description: A tutorial project demonstrating Projects vs Namespaces
    openshift.io/display-name: Demo Project
    openshift.io/requester: developer
    openshift.io/sa.scc.mcs: ...
    openshift.io/sa.scc.supplemental-groups: ...
    openshift.io/sa.scc.uid-range: ...
```

Notice `openshift.io/requester` — OpenShift tracks who created the Project. The `sa.scc.*` annotations control the security context defaults for pods in this namespace.

### Step 3: Compare with a plain Kubernetes Namespace

Now create a plain Namespace using `kubectl` (which also works on OpenShift):

```bash
kubectl create namespace demo-namespace
```

Inspect it:

```bash
kubectl get namespace demo-namespace -o yaml
```

You will see a bare Namespace with none of the OpenShift annotations and no automatic RBAC bindings. It exists, but nobody except cluster admins has access to it.

### Step 4: Examine default RBAC bindings

Check the RoleBindings that were automatically created in the Project:

```bash
oc get rolebindings -n demo-project
```

Expected output (abbreviated):

```
NAME                    ROLE                               AGE
admin                   ClusterRole/admin                  1m
system:deployers        ClusterRole/system:deployer        1m
system:image-builders   ClusterRole/system:image-builder   1m
system:image-pullers    ClusterRole/system:image-puller    1m
```

Now check the plain Namespace:

```bash
oc get rolebindings -n demo-namespace
```

Expected output:

```
NAME                    ROLE                               AGE
system:deployers        ClusterRole/system:deployer        1m
system:image-builders   ClusterRole/system:image-builder   1m
system:image-pullers    ClusterRole/system:image-puller    1m
```

The key difference: the Project has an `admin` RoleBinding that grants the creating user (`developer`) the `admin` role. The plain Namespace does not — the `developer` user has no explicit access.

### Step 5: Verify self-provisioning configuration

Switch to the `kubeadmin` user to inspect the self-provisioner binding:

```bash
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
```

```bash
oc get clusterrolebinding self-provisioners -o yaml
```

Expected output (key parts):

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: self-provisioners
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: self-provisioner
subjects:
  - apiGroup: rbac.authorization.k8s.io
    kind: Group
    name: system:authenticated:oauth
```

This means every authenticated OAuth user (i.e., anyone who logged in) can create Projects. To disable self-provisioning, you would remove the `subjects` from this binding.

### Step 6: Create a custom project-request template

A project-request template lets you inject resources into every new Project. The manifest at `manifests/project-request-template.yaml` creates a template that automatically adds a `LimitRange` and a default `NetworkPolicy` to every new Project.

First, review the template:

```yaml
# Custom project-request template
# Automatically injects a LimitRange and NetworkPolicy into every new Project
apiVersion: template.openshift.io/v1
kind: Template
metadata:
  name: project-request
  namespace: openshift-config
objects:
  - apiVersion: project.openshift.io/v1
    kind: Project
    metadata:
      annotations:
        openshift.io/description: ${PROJECT_DESCRIPTION}
        openshift.io/display-name: ${PROJECT_DISPLAYNAME}
        openshift.io/requester: ${PROJECT_REQUESTING_USER}
      name: ${PROJECT_NAME}
  - apiVersion: rbac.authorization.k8s.io/v1
    kind: RoleBinding
    metadata:
      name: admin
      namespace: ${PROJECT_NAME}
    roleRef:
      apiGroup: rbac.authorization.k8s.io
      kind: ClusterRole
      name: admin
    subjects:
      - apiGroup: rbac.authorization.k8s.io
        kind: User
        name: ${PROJECT_ADMIN_USER}
  - apiVersion: v1
    kind: LimitRange
    metadata:
      name: default-limits
      namespace: ${PROJECT_NAME}
    spec:
      limits:
        - type: Container
          defaultRequest:
            cpu: 50m
            memory: 64Mi
  - apiVersion: networking.k8s.io/v1
    kind: NetworkPolicy
    metadata:
      name: allow-from-same-namespace
      namespace: ${PROJECT_NAME}
    spec:
      podSelector: {}
      ingress:
        - from:
            - podSelector: {}
parameters:
  - name: PROJECT_NAME
  - name: PROJECT_DISPLAYNAME
  - name: PROJECT_DESCRIPTION
  - name: PROJECT_ADMIN_USER
  - name: PROJECT_REQUESTING_USER
```

To install this template (requires `kubeadmin`):

```bash
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
oc apply -f manifests/project-request-template.yaml
```

Then tell OpenShift to use it by patching the cluster-level project configuration:

```bash
oc patch project.config.openshift.io/cluster \
  --type=merge \
  -p '{"spec":{"projectRequestTemplate":{"name":"project-request"}}}'
```

After this, every new Project created with `oc new-project` will automatically contain the LimitRange and NetworkPolicy defined in the template.

> **Note:** In CRC you have full cluster-admin access, so you can try this. In the Developer Sandbox you cannot modify cluster-level configuration.

### Step 7: Test the custom template

Switch back to the `developer` user and create a new Project:

```bash
oc login -u developer -p developer https://api.crc.testing:6443
oc new-project template-test --display-name="Template Test"
```

Verify the LimitRange and NetworkPolicy were injected:

```bash
oc get limitrange -n template-test
```

Expected output:

```
NAME             CREATED AT
default-limits   ...
```

```bash
oc get networkpolicy -n template-test
```

Expected output:

```
NAME                        POD-SELECTOR   AGE
allow-from-same-namespace   <none>         ...
```

The template worked — every new Project now gets baseline resource limits and network isolation without any manual intervention.

## Verification

Run these commands to confirm the lesson is complete:

```bash
# 1. Project exists with correct metadata
oc get project demo-project -o jsonpath='{.metadata.annotations.openshift\.io/display-name}'
# Expected: Demo Project

# 2. Plain namespace exists
kubectl get namespace demo-namespace
# Expected: demo-namespace   Active   ...

# 3. Project has admin RoleBinding for developer
oc get rolebinding admin -n demo-project -o jsonpath='{.subjects[0].name}'
# Expected: developer

# 4. Template-created project has a LimitRange (if Step 6/7 were completed)
oc get limitrange -n template-test -o name
# Expected: limitrange/default-limits
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Isolation boundary | `Namespace` | `Project` (wraps Namespace) |
| Human-readable metadata | None built-in | `display-name` and `description` annotations |
| Default RBAC on creation | None — manual setup | Creator gets `admin` role automatically |
| Self-service creation | Not supported by default | Built-in self-provisioning for authenticated users |
| Customizable defaults | Must build your own controller | Project-request template injects resources |
| Tracking who created it | Not tracked | `openshift.io/requester` annotation |
| CLI command | `kubectl create namespace` | `oc new-project` |
| Security defaults | None | SCC UID/MCS/supplemental-group annotations |

## Key Takeaways

- A Project is a Namespace with metadata annotations, automatic RBAC bindings, and security defaults baked in.
- `oc new-project` does more than `kubectl create namespace` — it processes a template that sets up RBAC and injects default resources.
- Self-provisioning lets non-admin users create their own Projects safely, and can be disabled or restricted by editing the `self-provisioners` ClusterRoleBinding.
- Project-request templates let cluster admins enforce standards (LimitRanges, NetworkPolicies, ResourceQuotas) across every new Project without relying on users to do it.
- You can always use `kubectl` to interact with the underlying Namespace, but `oc` gives you the richer Project view.

## Cleanup

```bash
# Delete the projects and namespace created in this lesson
oc delete project demo-project
oc delete project template-test
kubectl delete namespace demo-namespace

# (Optional) Revert the project-request template — requires kubeadmin
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
oc delete template project-request -n openshift-config
oc patch project.config.openshift.io/cluster \
  --type=merge \
  -p '{"spec":{"projectRequestTemplate":{"name":""}}}'

# Switch back to developer
oc login -u developer -p developer https://api.crc.testing:6443
```

## Next Steps

In **L1-M2.2 — Authentication & OAuth**, you will explore OpenShift's built-in OAuth server, learn how identity providers (HTPasswd, LDAP, GitHub) work, and see how `oc login` and token-based authentication differ from Kubernetes service account tokens.
