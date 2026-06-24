# L1-M1.3 — CLI Tools: oc vs kubectl

**Level:** Foundations
**Duration:** 30 min

## Overview

You already know `kubectl` inside and out. The good news: every `kubectl` command works on OpenShift. The better news: `oc` is a superset of `kubectl` that adds OpenShift-specific commands for builds, routes, projects, authentication, and cluster administration. This lesson walks through the extra commands `oc` provides, demonstrates that `kubectl` still works, and gives you a cheat-sheet so you always know which tool to reach for.

## Prerequisites

- Completed: L1-M1.2 (Installing OpenShift Local / CRC)
- OpenShift cluster running (CRC or Developer Sandbox)
- `oc` CLI installed and on your PATH (`crc oc-env` if using CRC)
- `kubectl` installed (for comparison)

## K8s Context

In Kubernetes, `kubectl` is the single CLI for everything: creating resources, inspecting workloads, managing RBAC, port-forwarding, and debugging pods. You configure access through kubeconfig files and contexts. There is no built-in login flow, no built-in build system, and no concept of "projects" at the CLI level.

## Concepts

### oc is kubectl + OpenShift extras

The `oc` binary embeds the full `kubectl` implementation. Every `kubectl get`, `kubectl apply`, `kubectl describe`, `kubectl logs` command works identically when you swap `kubectl` for `oc`. You do not lose anything by switching.

What `oc` adds falls into five categories:

1. **Authentication** -- `oc login`, `oc logout`, `oc whoami`. OpenShift has a built-in OAuth server, so `oc` can authenticate directly instead of requiring you to manually configure kubeconfig files.

2. **Projects** -- `oc new-project`, `oc project`, `oc projects`. Projects are namespaces with extra metadata and default RBAC. The `oc` commands handle this richer abstraction.

3. **Application deployment** -- `oc new-app`, `oc start-build`, `oc rollout`. OpenShift can build images from source code (S2I) and deploy them in one command. These have no `kubectl` equivalent because Kubernetes has no built-in build system.

4. **Routes** -- `oc expose`, `oc get routes`. OpenShift Routes are the native ingress mechanism, predating Kubernetes Ingress. The `oc` CLI knows how to create and manage them.

5. **Cluster administration** -- `oc adm` contains sub-commands for node management, certificate rotation, policy enforcement, and diagnostics that are specific to the OpenShift control plane.

### When to use which

| Situation | Use |
|-----------|-----|
| Working exclusively on OpenShift | `oc` for everything |
| Writing scripts that run on both K8s and OpenShift | `kubectl` for portable commands, `oc` for OpenShift-specific operations |
| CI/CD pipelines targeting OpenShift | `oc` (handles login, builds, routes) |
| Managing authentication | `oc login` / `oc logout` (no `kubectl` equivalent) |
| Building images on-cluster | `oc new-app` / `oc start-build` (no `kubectl` equivalent) |

## Step-by-Step

### Step 1: Verify both CLIs are available

Confirm that both tools are installed and check their versions.

```bash
oc version
kubectl version --client
```

**Expected output (versions will vary):**
```
$ oc version
Client Version: 4.14.0
Kustomize Version: v5.0.1
Server Version: 4.14.0
Kubernetes Version: v1.27.6+f67aeb3

$ kubectl version --client
Client Version: v1.28.2
Kustomize Version: v5.0.4-0.20230601165947-6ce0bf390ce3
```

Notice that `oc version` also shows the OpenShift server version and the underlying Kubernetes version -- this is your first hint that `oc` knows more about the cluster than `kubectl` does.

### Step 2: Log in with oc login

In Kubernetes, you configure access by editing kubeconfig files or running `aws eks update-kubeconfig`, `gcloud container clusters get-credentials`, etc. In OpenShift, `oc login` handles authentication directly against the OAuth server.

```bash
# Log in as the developer user
oc login -u developer -p developer https://api.crc.testing:6443

# Verify who you are
oc whoami

# See more detail: username, server, and current project
oc whoami --show-server
oc whoami --show-token
oc whoami --show-context
```

**Expected output:**
```
$ oc login -u developer -p developer https://api.crc.testing:6443
Login successful.

You don't have any projects. You can try to create a new project, by running

    oc new-project <projectname>

$ oc whoami
developer

$ oc whoami --show-server
https://api.crc.testing:6443
```

There is no `kubectl login` command. With plain Kubernetes, you would need to manually set up a kubeconfig entry or obtain a token through an external identity provider.

### Step 3: Create a project with oc new-project

In Kubernetes, you create a namespace with `kubectl create namespace my-ns`. In OpenShift, `oc new-project` creates a project (a namespace with metadata and default RBAC).

```bash
# Create a project for this lesson
oc new-project cli-demo --display-name="CLI Demo" --description="Exploring oc vs kubectl"

# List all projects you have access to
oc projects

# Show the current project
oc project
```

**Expected output:**
```
$ oc new-project cli-demo --display-name="CLI Demo" --description="Exploring oc vs kubectl"
Now using project "cli-demo" on server "https://api.crc.testing:6443".

$ oc project
Using project "cli-demo" on server "https://api.crc.testing:6443".
```

Notice three things that `kubectl create namespace` does not do:
- It sets a human-readable display name and description (visible in the Web Console).
- It automatically switches your context to the new project.
- It creates default RoleBindings so the creating user has `admin` access.

### Step 4: Deploy a test application with kubectl (proving compatibility)

Let us deploy a simple application using standard `kubectl` commands to prove they work on OpenShift.

```bash
# Apply a Deployment using kubectl — works identically to vanilla K8s
kubectl apply -f manifests/deployment.yaml

# Check the deployment with kubectl
kubectl get deployments
kubectl get pods

# Describe the pod with kubectl
kubectl describe deployment hello-openshift
```

**Expected output:**
```
$ kubectl apply -f manifests/deployment.yaml
deployment.apps/hello-openshift created

$ kubectl get deployments
NAME              READY   UP-TO-DATE   AVAILABLE   AGE
hello-openshift   1/1     1            1           30s

$ kubectl get pods
NAME                               READY   STATUS    RESTARTS   AGE
hello-openshift-6b4f7c8d9b-abcde   1/1     Running   0          30s
```

Every `kubectl` command works exactly as you expect. The underlying API server speaks standard Kubernetes.

### Step 5: Create a Service using kubectl

```bash
# Apply the service manifest using kubectl
kubectl apply -f manifests/service.yaml

# Verify with kubectl
kubectl get services
```

**Expected output:**
```
$ kubectl get services
NAME              TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE
hello-openshift   ClusterIP   172.30.45.123   <none>        8080/TCP   5s
```

### Step 6: Expose the Service with oc (OpenShift Routes)

Here is where `oc` diverges from `kubectl`. In Kubernetes, you would create an Ingress resource and install an ingress controller. In OpenShift, the HAProxy-based router is pre-installed, and `oc expose` creates a Route in one command.

```bash
# Create a Route to expose the service externally
oc expose service hello-openshift

# View the route
oc get routes
```

**Expected output:**
```
$ oc expose service hello-openshift
route.route.openshift.io/hello-openshift exposed

$ oc get routes
NAME              HOST/PORT                                       PATH   SERVICES          PORT   TERMINATION   WILDCARD
hello-openshift   hello-openshift-cli-demo.apps-crc.testing              hello-openshift   8080                 None
```

There is no `kubectl expose --type=Route` because Routes are an OpenShift-specific resource. You could also use `kubectl get routes` since the Route CRD is registered on the API server, but creating one with `kubectl` would require writing the full YAML. The `oc expose` shortcut is much faster.

```bash
# Test the route (curl the generated URL)
curl -s http://hello-openshift-cli-demo.apps-crc.testing
```

**Expected output:**
```
Hello OpenShift!
```

### Step 7: Use oc status for a cluster-level overview

The `oc status` command gives you a high-level view of your project -- deployments, services, routes, and build activity -- all in one command. There is no `kubectl status` equivalent.

```bash
oc status
```

**Expected output:**
```
In project CLI Demo (cli-demo) on server https://api.crc.testing:6443

http://hello-openshift-cli-demo.apps-crc.testing to pod port 8080 (svc/hello-openshift)
  deployment/hello-openshift deploys openshift/hello-openshift:latest
    deployment #1 running for 2 minutes - 1 pod
```

This single command shows the relationship between your Route, Service, Deployment, and Pods. In Kubernetes, you would need multiple `kubectl get` commands to piece this together.

### Step 8: Explore oc new-app (OpenShift's application deployer)

`oc new-app` is one of the most powerful `oc`-only commands. It can deploy applications from a Docker image, a Git repository (using S2I), or an OpenShift template -- and it automatically creates the Deployment, Service, ImageStream, and BuildConfig as needed.

```bash
# See what oc new-app would create from a Docker image (dry-run)
oc new-app --docker-image=openshift/hello-openshift --name=hello-from-newapp --dry-run -o yaml | head -60

# See what oc new-app would create from a Git repo (dry-run)
oc new-app https://github.com/sclorg/nodejs-ex.git --name=nodejs-demo --dry-run 2>&1 | head -30
```

We are using `--dry-run` here to show what resources would be created without actually creating them. You will use `oc new-app` for real in L1-M3.1 when you learn about Source-to-Image builds.

### Step 9: Explore oc adm (cluster administration)

The `oc adm` subcommand contains cluster-level administrative operations. Most of these require `cluster-admin` privileges (the `kubeadmin` user in CRC).

```bash
# List available oc adm sub-commands
oc adm --help

# Check the cluster node status (works as developer, read-only)
oc get nodes

# Log in as cluster admin to use oc adm commands
oc login -u kubeadmin -p $(cat ~/.crc/machines/crc/kubeadmin-password) https://api.crc.testing:6443

# View top resource consumers (oc adm equivalent of kubectl top)
oc adm top nodes
oc adm top pods -n cli-demo

# Inspect cluster policy
oc adm policy who-can create deployments -n cli-demo

# Check node diagnostics
oc adm node-logs --role=master --tail=10

# Switch back to developer user
oc login -u developer -p developer https://api.crc.testing:6443
oc project cli-demo
```

Key `oc adm` sub-commands with no `kubectl` equivalent:

| Command | Purpose |
|---------|---------|
| `oc adm policy` | Manage RBAC and SCCs |
| `oc adm top` | Resource usage for nodes and pods |
| `oc adm node-logs` | View node-level journal logs |
| `oc adm inspect` | Gather debugging information for a resource |
| `oc adm drain` | Drain a node (also available as `kubectl drain`) |
| `oc adm cordon` | Mark a node unschedulable |
| `oc adm must-gather` | Collect cluster diagnostics for support cases |
| `oc adm upgrade` | Manage cluster upgrades |

### Step 10: Compare oc and kubectl side-by-side

Run the same commands with both CLIs to see they return identical results for standard Kubernetes operations.

```bash
# These produce identical output:
echo "=== kubectl get pods ==="
kubectl get pods -n cli-demo

echo "=== oc get pods ==="
oc get pods -n cli-demo

echo "=== kubectl get services ==="
kubectl get services -n cli-demo

echo "=== oc get services ==="
oc get services -n cli-demo

# Both can use the same flags:
kubectl get pods -n cli-demo -o wide
oc get pods -n cli-demo -o wide

kubectl get pods -n cli-demo -o json | head -5
oc get pods -n cli-demo -o json | head -5
```

The output is identical. Under the hood, both tools talk to the same Kubernetes API server.

## Verification

Run these commands to confirm everything is working:

```bash
# 1. Verify you are logged in
oc whoami
# Expected: developer

# 2. Verify the project exists
oc project
# Expected: Using project "cli-demo"

# 3. Verify the deployment is running
oc get deployments -n cli-demo
# Expected: hello-openshift   1/1

# 4. Verify the route is accessible
oc get routes -n cli-demo
# Expected: hello-openshift   hello-openshift-cli-demo.apps-crc.testing

# 5. Verify kubectl produces the same result
kubectl get deployments -n cli-demo
# Expected: identical to oc get deployments output

# 6. Verify the application responds
curl -s http://hello-openshift-cli-demo.apps-crc.testing
# Expected: Hello OpenShift!
```

## K8s vs OpenShift Comparison

| Command / Concept | kubectl (Kubernetes) | oc (OpenShift) |
|-------------------|---------------------|----------------|
| Authentication | Configure kubeconfig manually | `oc login -u user -p pass <url>` |
| Check current user | `kubectl config current-context` (shows context, not user) | `oc whoami` |
| Create namespace/project | `kubectl create namespace foo` | `oc new-project foo --display-name="..." --description="..."` |
| Switch namespace/project | `kubectl config set-context --current --namespace=foo` | `oc project foo` |
| List namespaces/projects | `kubectl get namespaces` | `oc projects` (shows active project) |
| Deploy from image | Write Deployment YAML, `kubectl apply` | `oc new-app --docker-image=img --name=app` |
| Deploy from source code | Not built-in (need external CI) | `oc new-app https://github.com/repo.git` |
| Expose externally | Create Ingress YAML + install ingress controller | `oc expose service my-svc` (Route created) |
| View routes | `kubectl get ingress` (Ingress only) | `oc get routes` |
| Project overview | Multiple `kubectl get` commands | `oc status` |
| Trigger a build | Not built-in | `oc start-build my-buildconfig` |
| Cluster admin tasks | Various `kubectl` commands | `oc adm <subcommand>` |
| Debug a pod | `kubectl exec -it pod -- /bin/sh` | `oc debug deployment/my-app` (creates a debug copy) |
| View build logs | Not built-in | `oc logs -f build/my-app-1` |
| Rollback | `kubectl rollout undo` | `oc rollout undo` (same) |
| Standard get/describe/apply | `kubectl get/describe/apply` | `oc get/describe/apply` (identical) |

## Key Takeaways

- **oc is a superset of kubectl** -- every `kubectl` command works with `oc`, so you do not lose any existing muscle memory.
- **oc adds authentication, builds, routes, and admin tools** -- these commands (`oc login`, `oc new-app`, `oc expose`, `oc adm`) have no kubectl equivalent because they interact with OpenShift-specific APIs.
- **Use oc when targeting OpenShift** -- there is no reason to use `kubectl` on OpenShift unless you are writing cross-platform scripts.
- **oc status gives you a project-wide view** -- a single command shows deployments, services, routes, and their relationships.
- **kubectl still works for portability** -- if your scripts or manifests need to run on both vanilla K8s and OpenShift, stick with `kubectl` for the common operations and use `oc` only for OpenShift-specific features.

## Cleanup

```bash
# Delete the project and all resources within it
oc delete project cli-demo

# Verify it is gone
oc projects
```

Deleting the project removes the namespace and every resource inside it (Deployments, Services, Routes, Pods, etc.). This is another convenience over `kubectl delete namespace`, which does the same thing but without the project metadata cleanup.

## Next Steps

In **L1-M1.4 -- Web Console Tour**, you will explore OpenShift's Web Console, which provides a graphical interface with two perspectives (Administrator and Developer). You will see the Topology view, navigate projects and workloads, and learn when the console is more efficient than the CLI.
