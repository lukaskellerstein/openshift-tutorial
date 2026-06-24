# L1-M2.4 — Security Context Constraints (SCCs)

**Level:** Foundations
**Duration:** 30 min

## Overview

Security Context Constraints (SCCs) are OpenShift's mechanism for controlling what a pod is allowed to do at the OS level — running as root, accessing host networking, using privileged containers, and more. If you have ever deployed a Docker Hub image on OpenShift and watched it crash with a permission error, this lesson explains why that happens and how to fix it. SCCs are the single biggest difference K8s users encounter when they first move to OpenShift.

## Prerequisites

- Completed: L1-M2.3 (RBAC Deep Dive)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in as `developer` via `oc login`
- Access to `kubeadmin` credentials (needed for SCC administration)

## K8s Context

In Kubernetes, pod security was historically governed by **PodSecurityPolicies** (PSPs), which were deprecated in K8s 1.21 and removed in 1.25. The replacement is **Pod Security Admission** (PSA), which enforces three built-in profiles (`privileged`, `baseline`, `restricted`) at the namespace level using labels.

By default, Kubernetes does **not** restrict pods from running as root. Any container image that expects UID 0 will work out of the box. You have to opt into restrictions by configuring PSA labels on your namespaces.

If you are coming from a cluster where you never configured PSPs or PSA, you are used to pods running as root without friction. OpenShift flips that default.

## Concepts

### What Are SCCs?

Security Context Constraints are an OpenShift-specific resource (API group `security.openshift.io/v1`) that define a set of conditions a pod must meet to be admitted to the cluster. They control:

- **Which UIDs/GIDs** a container can run as
- **Whether the container can run as root** (UID 0)
- **Linux capabilities** the container can request (e.g., `NET_RAW`, `SYS_ADMIN`)
- **Whether host namespaces** (network, PID, IPC) can be used
- **Volume types** the pod can mount
- **SELinux context**, seccomp profiles, and more

SCCs are more granular than Kubernetes PSA profiles. While PSA gives you three levels, OpenShift ships with eight built-in SCCs, and you can create custom ones.

### Built-in SCCs

OpenShift includes these SCCs by default (from most restrictive to least):

| SCC | Run as Root? | Key Characteristics |
|-----|-------------|---------------------|
| `restricted-v2` | No | Default for all pods. Random UID, no capabilities, no host access. Most secure. |
| `nonroot-v2` | No | Like `restricted-v2` but allows the user to pick any non-root UID. |
| `hostnetwork-v2` | No | Allows host networking but still no root. |
| `hostaccess` | Yes | Allows host networking, host directories, and running as any UID. |
| `anyuid` | Yes | Like `restricted-v2` but allows running as any UID, including root (UID 0). |
| `privileged` | Yes | No restrictions at all. Full host access. Cluster admins only. |

### How SCCs Are Assigned

SCCs are granted to **service accounts**, not directly to pods. The process:

1. A pod is created and references a service account (defaults to `default`).
2. The admission controller checks which SCCs the service account is allowed to use.
3. It picks the most restrictive SCC that satisfies the pod's `securityContext` requirements.
4. If no SCC matches, the pod is **rejected**.

Every project's `default` service account is bound to the `restricted-v2` SCC. This is why pods that try to run as root are rejected by default.

### Why Does OpenShift Do This?

OpenShift is designed for **multi-tenant enterprise environments** where multiple teams share a cluster. Allowing arbitrary containers to run as root is a security risk:

- A root container that escapes its sandbox has root on the node.
- Many container images run as root unnecessarily (a legacy habit from Docker).
- Enforcing non-root by default pushes teams toward secure images.

OpenShift chose to be **secure by default** rather than permissive by default. This is a deliberate design decision, not a limitation.

## Step-by-Step

### Step 1: List the Built-in SCCs

First, log in as `kubeadmin` to view cluster-level SCC resources:

```bash
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
```

List all SCCs:

```bash
oc get scc
```

Expected output:

```
NAME                              PRIV    CAPS                   SELINUX     RUNASUSER          FSGROUP     SUPGROUP    PRIORITY     READONLYROOTFS   VOLUMES
anyuid                            false   <no value>             MustRunAs   RunAsAny           RunAsAny    RunAsAny    10           false            [...]
hostaccess                        false   <no value>             MustRunAs   MustRunAsRange     MustRunAs   RunAsAny    <no value>   false            [...]
hostnetwork                       false   <no value>             MustRunAs   MustRunAsRange     MustRunAs   MustRunAs   <no value>   false            [...]
hostnetwork-v2                    false   [NET_BIND_SERVICE]     MustRunAs   MustRunAsRange     MustRunAs   MustRunAs   <no value>   false            [...]
nonroot                           false   <no value>             MustRunAs   MustRunAsNonRoot   RunAsAny    RunAsAny    <no value>   false            [...]
nonroot-v2                        false   [NET_BIND_SERVICE]     MustRunAs   MustRunAsNonRoot   RunAsAny    RunAsAny    <no value>   false            [...]
privileged                        true    [*]                    RunAsAny    RunAsAny           RunAsAny    RunAsAny    <no value>   false            [*]
restricted                        false   <no value>             MustRunAs   MustRunAsRange     MustRunAs   RunAsAny    <no value>   false            [...]
restricted-v2                     false   [NET_BIND_SERVICE]     MustRunAs   MustRunAsRange     MustRunAs   RunAsAny    <no value>   false            [...]
```

### Step 2: Examine an SCC in Detail

Look at the default `restricted-v2` SCC to understand what it enforces:

```bash
oc describe scc restricted-v2
```

Key fields to note:

- `Run As User Strategy: MustRunAsRange` — the container gets a random UID from the project's UID range, never UID 0.
- `SELinux Context Strategy: MustRunAs` — SELinux labels are enforced.
- `Allowed Capabilities: NET_BIND_SERVICE` — only this one capability is available.
- `Allow Privileged: false` — no privileged containers.
- `Allow Host Network: false` — cannot use the host's network namespace.

### Step 3: Create a Project for Testing

Switch back to the `developer` user and create a test project:

```bash
oc login -u developer -p developer https://api.crc.testing:6443
oc new-project scc-demo
```

### Step 4: Deploy a Pod That Requires Root (Watch It Fail)

Many Docker Hub images run as root. The official Nginx image is a common example. Let us deploy it and observe the failure.

Apply the Nginx deployment:

```bash
oc apply -f manifests/nginx-root-deployment.yaml
```

```yaml
# Nginx deployment — uses the Docker Hub nginx image which runs as root (UID 0).
# This will FAIL on OpenShift because the restricted-v2 SCC does not allow root.
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-root
  labels:
    app: nginx-root
    tutorial-level: "1"
    tutorial-module: "M2"
spec:
  replicas: 1
  selector:
    matchLabels:
      app: nginx-root
  template:
    metadata:
      labels:
        app: nginx-root
    spec:
      containers:
        - name: nginx
          image: docker.io/library/nginx:1.27
          ports:
            - containerPort: 80
```

Check the pod status:

```bash
oc get pods
```

Expected output — the pod will be in `CrashLoopBackOff` or `Error`:

```
NAME                          READY   STATUS             RESTARTS   AGE
nginx-root-6b8d5f4c9-x2k7j   0/1     CrashLoopBackOff   2          45s
```

Check the logs to see the permission error:

```bash
oc logs deployment/nginx-root
```

You will see errors like:

```
nginx: [emerg] mkdir() "/var/cache/nginx/client_temp" failed (13: Permission denied)
```

The Nginx image tries to run as root and write to directories that require root permissions. The `restricted-v2` SCC forces the container to run as a random non-root UID, so these operations fail.

### Step 5: Examine Which SCC the Pod Was Assigned

Check the pod's annotations to see which SCC was applied:

```bash
oc get pod -l app=nginx-root -o jsonpath='{.items[0].metadata.annotations.openshift\.io/scc}' && echo
```

Expected output:

```
restricted-v2
```

This confirms the pod was admitted under the `restricted-v2` SCC, which forced a non-root UID.

### Step 6: Fix Option A — Use a Non-Root Image

The best fix is to use an image designed to run without root. Red Hat provides UBI (Universal Base Image) variants, and Nginx has an unprivileged variant.

Apply the non-root deployment:

```bash
oc apply -f manifests/nginx-nonroot-deployment.yaml
```

```yaml
# Nginx deployment using the unprivileged image — runs as non-root (UID 101).
# This works with the default restricted-v2 SCC on OpenShift.
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-nonroot
  labels:
    app: nginx-nonroot
    tutorial-level: "1"
    tutorial-module: "M2"
spec:
  replicas: 1
  selector:
    matchLabels:
      app: nginx-nonroot
  template:
    metadata:
      labels:
        app: nginx-nonroot
    spec:
      containers:
        - name: nginx
          image: docker.io/nginxinc/nginx-unprivileged:1.27
          ports:
            - containerPort: 8080
```

Check that it runs successfully:

```bash
oc get pods -l app=nginx-nonroot
```

Expected output:

```
NAME                             READY   STATUS    RESTARTS   AGE
nginx-nonroot-7f4d6c8b5-abc12   1/1     Running   0          15s
```

Verify the UID it is running as:

```bash
oc exec deployment/nginx-nonroot -- id
```

Expected output:

```
uid=101(nginx) gid=101(nginx) groups=101(nginx)
```

This is the **recommended approach**: use images that do not require root.

### Step 7: Fix Option B — Grant the `anyuid` SCC

Sometimes you cannot change the image (third-party vendor, legacy app). In that case, you can grant the `anyuid` SCC to the pod's service account. This allows the container to run as any UID, including root.

**This requires cluster-admin privileges.** Log in as `kubeadmin`:

```bash
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
```

Create a dedicated service account for the privileged workload:

```bash
oc apply -f manifests/nginx-privileged-sa.yaml -n scc-demo
```

```yaml
# Dedicated service account for workloads that need the anyuid SCC.
# Best practice: never grant elevated SCCs to the default service account.
apiVersion: v1
kind: ServiceAccount
metadata:
  name: nginx-anyuid
  namespace: scc-demo
  labels:
    app: nginx-anyuid
    tutorial-level: "1"
    tutorial-module: "M2"
```

Grant the `anyuid` SCC to this service account:

```bash
oc adm policy add-scc-to-user anyuid -z nginx-anyuid -n scc-demo
```

Expected output:

```
clusterrole.rbac.authorization.k8s.io/system:openshift:scc:anyuid added: "nginx-anyuid"
```

Now switch back to `developer` and deploy Nginx using this service account:

```bash
oc login -u developer -p developer https://api.crc.testing:6443
oc apply -f manifests/nginx-anyuid-deployment.yaml -n scc-demo
```

```yaml
# Nginx deployment using the anyuid SCC via a dedicated service account.
# The standard Docker Hub nginx image (which requires root) now works.
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-anyuid
  labels:
    app: nginx-anyuid
    tutorial-level: "1"
    tutorial-module: "M2"
spec:
  replicas: 1
  selector:
    matchLabels:
      app: nginx-anyuid
  template:
    metadata:
      labels:
        app: nginx-anyuid
    spec:
      serviceAccountName: nginx-anyuid
      containers:
        - name: nginx
          image: docker.io/library/nginx:1.27
          ports:
            - containerPort: 80
```

Check the pod:

```bash
oc get pods -l app=nginx-anyuid
```

Expected output:

```
NAME                            READY   STATUS    RESTARTS   AGE
nginx-anyuid-5d8f9c7b6-def34   1/1     Running   0          10s
```

Verify the SCC and UID:

```bash
oc get pod -l app=nginx-anyuid -o jsonpath='{.items[0].metadata.annotations.openshift\.io/scc}' && echo
oc exec deployment/nginx-anyuid -- id
```

Expected output:

```
anyuid
uid=0(root) gid=0(root) groups=0(root)
```

The pod is now running as root under the `anyuid` SCC.

### Step 8: Understand the Security Tradeoff

Granting `anyuid` is a **deliberate weakening of security**. Follow these best practices:

1. **Never grant elevated SCCs to the `default` service account.** Create a dedicated SA.
2. **Use the least-privileged SCC that works.** Try `nonroot-v2` before `anyuid`, and `anyuid` before `privileged`.
3. **Document why** the elevated SCC is needed and who approved it.
4. **Prefer fixing the image** over granting SCCs. Most images can be modified to run as non-root.

### Step 9: Check Which Service Accounts Have Elevated SCCs

As `kubeadmin`, review SCC assignments:

```bash
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
```

List all users/service accounts assigned to the `anyuid` SCC:

```bash
oc get scc anyuid -o jsonpath='{.users}' | tr ',' '\n'
```

You can also check what SCCs a service account can use:

```bash
oc adm policy who-can use scc anyuid -n scc-demo
```

## Verification

Run these checks to confirm the lesson worked correctly:

```bash
# Switch to developer
oc login -u developer -p developer https://api.crc.testing:6443
oc project scc-demo

# 1. The root-requiring Nginx should be failing
oc get pods -l app=nginx-root
# STATUS: CrashLoopBackOff or Error

# 2. The non-root Nginx should be running
oc get pods -l app=nginx-nonroot
# STATUS: Running

# 3. The anyuid Nginx should be running
oc get pods -l app=nginx-anyuid
# STATUS: Running

# 4. Verify the SCCs assigned to each pod
oc get pods -o custom-columns='NAME:.metadata.name,SCC:.metadata.annotations.openshift\.io/scc,STATUS:.status.phase'
```

Expected output:

```
NAME                             SCC             STATUS
nginx-root-6b8d5f4c9-x2k7j      restricted-v2   Running
nginx-nonroot-7f4d6c8b5-abc12    restricted-v2   Running
nginx-anyuid-5d8f9c7b6-def34     anyuid          Running
```

Note: `nginx-root` shows `Running` as its phase but the container inside is crash-looping. Use `oc get pods` for the full status with restarts.

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Pod security mechanism | Pod Security Admission (PSA) with namespace labels | Security Context Constraints (SCCs) bound to service accounts |
| Default behavior | Pods can run as root unless PSA is configured | Pods cannot run as root (`restricted-v2` SCC enforced) |
| Granularity | 3 profiles: `privileged`, `baseline`, `restricted` | 8+ built-in SCCs, plus custom SCCs |
| Assignment target | Namespace-level labels | Service account-level bindings |
| Root containers | Allowed by default | Denied by default |
| Random UID assignment | Not a built-in feature | Automatic — each project gets a UID range |
| Breaking Docker Hub images | Rare | Common (images that require root fail) |
| Philosophy | Opt-in security | Secure by default |

## Key Takeaways

- **OpenShift denies root by default.** Every pod runs under the `restricted-v2` SCC, which assigns a random non-root UID. This is the number-one surprise for K8s users.
- **Fix the image first, grant SCCs second.** The best solution is always to use an image that does not require root. Use Red Hat UBI images or unprivileged variants of popular images.
- **SCCs are bound to service accounts, not pods.** Create dedicated service accounts for workloads that need elevated privileges. Never grant `anyuid` or `privileged` to the `default` SA.
- **SCCs are more granular than K8s PSA.** With eight built-in SCCs and the ability to create custom ones, OpenShift gives you fine-grained control over pod security.
- **This is a feature, not a bug.** The secure-by-default model catches insecure images before they reach production. Embrace it.

## Cleanup

```bash
# Delete all resources created in this lesson
oc login -u developer -p developer https://api.crc.testing:6443
oc delete project scc-demo

# As kubeadmin, remove the SCC binding (project deletion cleans up the SA,
# but the SCC binding may persist)
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
oc adm policy remove-scc-from-user anyuid -z nginx-anyuid -n scc-demo
```

## Next Steps

In **L1-M3.1 — oc new-app & Source-to-Image (S2I)**, you will learn how OpenShift can build container images directly from source code without a Dockerfile. S2I builder images are designed to run as non-root on OpenShift, so everything you learned about SCCs in this lesson applies — S2I is one of OpenShift's answers to the "my Docker Hub image won't run" problem.
