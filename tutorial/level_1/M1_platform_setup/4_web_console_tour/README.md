# L1-M1.4 — Web Console Tour

**Level:** Foundations
**Duration:** 20 min

## Overview

OpenShift ships a full-featured Web Console that goes far beyond the basic Kubernetes Dashboard. In this lesson you will deploy a simple application and then explore the two console perspectives -- Administrator and Developer -- to understand how OpenShift surfaces workloads, networking, monitoring, and project management through its UI. By the end you will know how to navigate the console confidently and when it is faster than the CLI.

## Prerequisites

- Completed: L1-M1.2 (Installing OpenShift Local)
- OpenShift Local (CRC) running and accessible
- Logged in via `oc` CLI (either as `developer` or `kubeadmin`)

## K8s Context

Kubernetes offers the Dashboard -- an optional, third-party add-on that provides a basic web UI for viewing workloads, pods, and services. You install it yourself, configure RBAC for it, and set up a proxy or token to access it. The Dashboard shows a flat list of resources per namespace and offers limited create/edit capabilities.

If you have used the Kubernetes Dashboard, you know it covers the basics but often sends you back to `kubectl` for anything non-trivial.

## Concepts

### The OpenShift Web Console

The OpenShift Web Console is a first-class component of the platform, not an optional add-on. It is deployed automatically as part of every OpenShift installation and is integrated with the cluster's OAuth server -- you log in with the same credentials you use for `oc login`.

### Two Perspectives

The console offers two distinct perspectives, each designed for a different audience:

**Administrator Perspective** -- Designed for cluster operators and platform engineers. It exposes:
- Cluster-wide resources (nodes, machines, storage classes)
- Operator management (OperatorHub, installed operators)
- Cluster settings (OAuth, alerting, global configuration)
- All namespaces/projects at once
- Monitoring dashboards and alert management

**Developer Perspective** -- Designed for application developers. It exposes:
- Topology view (a visual, interactive graph of your application components)
- Add workflows (deploy from Git, container image, catalog, Helm chart)
- Build and pipeline status
- Project-scoped resource views
- Integrated log viewer and terminal

### Topology View

The Topology view is unique to OpenShift. It renders your deployed workloads as an interactive graph showing Deployments, Services, Routes, and the connections between them. You can:
- Click a workload to see its pods, builds, routes, and metrics in a side panel
- Drag components to visually group them
- See health status at a glance (green ring = healthy, red = failing)
- Open the application's route URL directly from the graph

### Why Does OpenShift Have This?

Kubernetes is infrastructure-focused -- its API and tooling assume you are comfortable with YAML and `kubectl`. OpenShift targets enterprise teams where developers, operators, and security teams share the same cluster. The two-perspective console gives each group a UI tuned to their workflow without exposing unnecessary complexity. The Topology view, in particular, helps developers understand their application architecture visually -- something `kubectl get all` cannot provide.

## Step-by-Step

### Step 1: Create a Project for This Lesson

Before deploying anything, create a dedicated project so cleanup is easy.

```bash
oc new-project console-tour
```

Expected output:

```
Now using project "console-tour" on server "https://api.crc.testing:6443".
...
```

### Step 2: Deploy a Simple Nginx Application

Apply the deployment and service manifests to have a workload visible in the console.

```bash
oc apply -f manifests/deployment.yaml
oc apply -f manifests/service.yaml
oc apply -f manifests/route.yaml
```

Wait for the pod to be ready:

```bash
oc get pods -w
```

Expected output (wait until STATUS is `Running` and READY is `1/1`):

```
NAME                              READY   STATUS    RESTARTS   AGE
console-demo-app-xxxxxxxxx-xxxxx  1/1     Running   0          30s
```

> **Note:** The `nginx:alpine` image works under the `restricted` SCC because it runs as a non-root user (UID 101) and listens on port 8080. Standard Docker Hub nginx (port 80, runs as root) would fail here -- a common surprise for K8s users.

Press `Ctrl+C` to stop watching once the pod is running.

### Step 3: Open the Web Console

Open the Web Console in your browser:

```
https://console-openshift-console.apps-crc.testing
```

You can also get the console URL programmatically:

```bash
oc whoami --show-console
```

Log in with:
- **Username:** `developer`
- **Password:** `developer`

> **Tip:** To see the full Administrator perspective, log in as `kubeadmin` instead. Get the kubeadmin password from `crc console --credentials`.

### Step 4: Explore the Developer Perspective

After logging in as `developer`, you should land in the **Developer** perspective. If not, click the perspective switcher in the top-left corner and select **Developer**.

1. **Topology View** -- Click **Topology** in the left sidebar.
   - You should see the `console-demo-app` Deployment rendered as a circle with a blue ring (indicating it is running).
   - Click the circle to open the side panel. You will see:
     - **Details** tab: Deployment name, labels, annotations, status.
     - **Resources** tab: The pod(s), the Service, the Route, and build status.
   - Click the small **arrow icon** on the top-right of the circle to open the Route URL in a new tab. You should see the nginx welcome page.

2. **Project selector** -- In the top bar, you should see `console-tour` selected. The Developer perspective always works within a single project context, similar to `oc project <name>`.

3. **+Add** -- Click **+Add** in the left sidebar. This shows all the ways to deploy an application:
   - From Git (triggers S2I build)
   - Container Image (deploy from a registry)
   - From Catalog (templates, Helm charts, operators)
   - YAML (paste raw manifests)
   - Upload JAR file

4. **Observe** -- Click **Observe** in the left sidebar.
   - **Dashboard** tab: CPU, memory, and network usage for workloads in this project.
   - **Metrics** tab: Run custom PromQL queries.
   - **Alerts** tab: Any firing alerts for this project.

5. **Search** -- Click **Search** in the left sidebar.
   - Select a resource type (e.g., `Deployment`, `Pod`, `Route`) to list and filter resources in the current project.

### Step 5: Explore the Administrator Perspective

Switch to the **Administrator** perspective using the perspective switcher in the top-left corner.

> **Note:** As `developer`, you will have limited visibility in the Administrator perspective. For the full experience, log in as `kubeadmin`.

1. **Home > Projects** -- Lists all projects you have access to. Click `console-tour` to see its resource consumption and quotas.

2. **Workloads** -- Expand the Workloads section in the left sidebar.
   - **Pods** -- Lists all pods. Click a pod to see its logs, terminal, events, and YAML.
   - **Deployments** -- Lists Deployments. Click `console-demo-app` to see its details, replica count, and revision history.

3. **Networking > Routes** -- Shows all routes. Click `console-demo-app` to see the route URL, TLS configuration, and the backend service.

4. **Monitoring** -- View cluster-wide dashboards and alerts.
   - **Dashboards** tab: Pre-built Grafana-style dashboards for cluster health.
   - **Alerts** tab: Cluster-wide alerts from Prometheus.

5. **Operators > OperatorHub** (kubeadmin only) -- Browse and install operators from Red Hat, community, and certified providers. This replaces the manual operator installation process in vanilla Kubernetes.

6. **Administration > Cluster Settings** (kubeadmin only) -- View cluster version, update channel, OAuth configuration, and global settings.

### Step 6: Useful Console Actions

While still in the console, try these actions to see how the UI maps to CLI operations:

**View pod logs:**
Navigate to Workloads > Pods > click a pod > **Logs** tab.
(CLI equivalent: `oc logs <pod-name>`)

**Open a terminal in a pod:**
Navigate to Workloads > Pods > click a pod > **Terminal** tab.
(CLI equivalent: `oc rsh <pod-name>`)

**Scale a Deployment:**
Navigate to Workloads > Deployments > click `console-demo-app` > click the up/down arrows next to the pod count.
(CLI equivalent: `oc scale deployment console-demo-app --replicas=3`)

**View events:**
Navigate to Home > Events (Administrator perspective) or check the **Events** tab on any resource.
(CLI equivalent: `oc get events`)

**Edit a resource's YAML:**
Click any resource, then select the **YAML** tab. You can edit and save directly.
(CLI equivalent: `oc edit deployment console-demo-app`)

## Verification

1. Confirm the application is running:

```bash
oc get pods -l app=console-demo-app
```

Expected output:

```
NAME                              READY   STATUS    RESTARTS   AGE
console-demo-app-xxxxxxxxx-xxxxx  1/1     Running   0          5m
```

2. Confirm the Route is accessible:

```bash
oc get route console-demo-app
```

Expected output:

```
NAME               HOST/PORT                                      PATH   SERVICES           PORT       TERMINATION   WILDCARD
console-demo-app   console-demo-app-console-tour.apps-crc.testing         console-demo-app   8080-tcp                 None
```

3. Access the route:

```bash
curl -s http://console-demo-app-console-tour.apps-crc.testing | head -5
```

You should see the beginning of the nginx welcome page HTML.

4. In the Web Console:
   - **Developer > Topology** shows the `console-demo-app` with a blue (running) ring.
   - Clicking the route icon opens the nginx welcome page in the browser.
   - **Developer > Observe** shows CPU and memory usage for the pod.

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Web UI | Dashboard (optional add-on) | Web Console (built-in, first-class) |
| Authentication | Manual token/proxy setup for Dashboard | Integrated OAuth -- same login as CLI |
| Perspectives | Single view for all users | Administrator + Developer perspectives |
| Topology visualization | Not available | Interactive Topology view |
| Deploy from UI | Limited (paste YAML) | Multiple workflows: Git, image, catalog, Helm, YAML |
| In-browser terminal | Not available | Built-in pod terminal |
| Operator management | CLI-only (`kubectl apply`) | OperatorHub in the console |
| Monitoring | Install Grafana yourself, access separately | Built-in dashboards and alerts in the console |
| Log viewing | `kubectl logs` only | Integrated log viewer with streaming |
| Resource editing | `kubectl edit` only | YAML editor in the console |

## Key Takeaways

- The OpenShift Web Console is a built-in, production-grade UI -- not an optional add-on like the Kubernetes Dashboard.
- The **Administrator** perspective is for cluster operators (nodes, operators, cluster settings); the **Developer** perspective is for application teams (topology, builds, project-scoped views).
- The **Topology view** provides a visual, interactive graph of your deployed application components -- something with no equivalent in vanilla Kubernetes.
- The console integrates monitoring, logging, terminal access, and YAML editing into a single interface, reducing context-switching between tools.
- Most console actions have direct CLI equivalents -- use whichever is faster for your workflow. The console excels at discovery and overview; the CLI excels at scripting and precision.

## Cleanup

Remove all resources created in this lesson:

```bash
oc delete project console-tour
```

This deletes the project and all resources within it (Deployment, Service, Route, Pods).

Verify:

```bash
oc get project console-tour
```

Expected output:

```
Error from server (NotFound): namespaces "console-tour" not found
```

## Next Steps

In **L1-M2.1 -- Projects vs Namespaces**, you will learn how OpenShift Projects extend Kubernetes Namespaces with additional metadata, default RBAC bindings, and self-provisioning capabilities. You will understand when and why to use `oc new-project` instead of `kubectl create namespace`.
