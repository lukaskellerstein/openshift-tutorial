# L1-M1.1 — Architecture Overview

**Level:** Foundations
**Duration:** 30 min

## Overview

If you know Kubernetes, you already understand 80% of OpenShift. This lesson covers the other 20% -- the components Red Hat layers on top of Kubernetes to create an opinionated, enterprise-grade platform. By the end, you will have a clear mental model of what OpenShift adds, where those additions live in the architecture, and why they exist.

This is a conceptual lesson. There are no manifests to apply or clusters to configure. Grab a cup of coffee and read through -- the hands-on work starts in L1-M1.2 when you install OpenShift Local (CRC).

## Prerequisites

- Solid understanding of Kubernetes architecture (API server, etcd, scheduler, controller manager, kubelet, kube-proxy)
- Familiarity with Kubernetes concepts: Pods, Deployments, Services, Namespaces, Ingress, RBAC
- No OpenShift cluster required for this lesson

## K8s Context

You already know the Kubernetes control plane: an API server fronting etcd, a scheduler placing pods, a controller manager running reconciliation loops, and kubelets on every node pulling images and running containers. Worker nodes run your workloads, and you bolt on whatever else you need -- an ingress controller, a CI/CD system, a container registry, monitoring, logging, a dashboard.

That "bolt on whatever you need" approach is both Kubernetes' greatest strength and its biggest operational burden. Every cluster is a snowflake of third-party add-ons, each with its own lifecycle, upgrade path, and configuration surface.

OpenShift's thesis is: **what if those add-ons came pre-integrated, pre-configured, and supported as a single product?**

## Concepts

### What OpenShift Actually Is

OpenShift is a Kubernetes distribution. At its core, it runs an OKD/Kubernetes API server -- your `kubectl` commands work unchanged. But Red Hat wraps that core with additional components that turn a bare Kubernetes cluster into a full application platform.

Think of it this way:

```
+-------------------------------------------------------------+
|                    OpenShift Container Platform              |
|  +--------------------------------------------------------+ |
|  |  Web Console  |  OAuth Server  |  OperatorHub (OLM)    | |
|  +--------------------------------------------------------+ |
|  |  HAProxy Router  |  Internal Registry  |  S2I Builds   | |
|  +--------------------------------------------------------+ |
|  |  Monitoring (Prometheus/Grafana)  |  Logging (Loki)     | |
|  +--------------------------------------------------------+ |
|  |              Kubernetes (API, etcd, scheduler)          | |
|  +--------------------------------------------------------+ |
|  |              RHCOS (Red Hat Enterprise Linux CoreOS)     | |
|  +--------------------------------------------------------+ |
+-------------------------------------------------------------+
```

Everything below the OpenShift line is standard Kubernetes. Everything above it is what OpenShift adds.

### The Six Major Additions

#### 1. OAuth Server -- Built-In Authentication

In Kubernetes, authentication is your problem. You configure OIDC, client certificates, webhook token authentication, or some combination -- and you manage the identity provider yourself.

OpenShift ships a built-in OAuth server that handles authentication out of the box. It supports multiple identity providers (HTPasswd, LDAP, GitHub, GitLab, OpenID Connect, Active Directory) and manages OAuth tokens for CLI and API access.

When you run `oc login`, you are authenticating against this OAuth server. It issues a token that gets stored in your kubeconfig. No manual certificate wrangling, no external auth proxy to deploy.

**Why it matters:** Day-one authentication with zero setup. In a Kubernetes cluster, getting authentication right is often a week-long project. In OpenShift, it works out of the box with `oc login -u developer -p developer`.

#### 2. HAProxy Router -- Built-In Ingress

In Kubernetes, you define Ingress resources, but nothing handles them until you install an ingress controller (NGINX, Traefik, HAProxy, etc.). You pick one, deploy it, configure it, and maintain it.

OpenShift ships a pre-installed HAProxy-based router and introduces a custom resource called a **Route**. Routes predate Kubernetes Ingress (OpenShift had them first) and offer features that Ingress is still catching up to:

- **Edge TLS termination** -- HTTPS terminates at the router, traffic to the pod is HTTP
- **Passthrough TLS** -- encrypted traffic passes through to the pod untouched
- **Re-encrypt TLS** -- router terminates the external certificate and re-encrypts with an internal one
- Automatic hostname generation based on the route name and cluster domain
- Sticky sessions, rate limiting, and other HAProxy features via annotations

Kubernetes Ingress also works on OpenShift -- the HAProxy router implements the Ingress spec too. But Routes are the native, more capable option.

**Why it matters:** Exposing an application with TLS takes one YAML file, not an ingress controller deployment plus configuration plus certificate management.

#### 3. Internal Container Registry -- Built-In Image Storage

Kubernetes expects you to push images to an external registry (Docker Hub, Quay, ECR, GCR) and reference them by their full image path. You manage the registry, its authentication, and its storage.

OpenShift includes an internal container registry that runs inside the cluster. More importantly, it introduces **ImageStreams** -- an abstraction layer over container image references that enables:

- **Image change triggers** -- a Deployment automatically redeploys when the image it references is updated
- **Scheduled image imports** -- periodically pull external images into the internal registry
- **Tag management** -- tag images with meaningful names (`my-app:staging`, `my-app:production`) independent of the registry
- **Build integration** -- S2I and Docker builds push directly to ImageStreams

**Why it matters:** The internal registry plus ImageStreams create a coherent image lifecycle inside the cluster. Builds produce images, ImageStreams track them, and Deployments consume them -- all without touching an external registry.

#### 4. Build System -- Source-to-Image (S2I)

Kubernetes has no opinion on how you build container images. You write a Dockerfile, build it somewhere (your laptop, a CI server, Kaniko in a pod), push to a registry, and reference it in a Deployment.

OpenShift includes a complete build system with **BuildConfig** resources that define how to build an image:

- **Source-to-Image (S2I)** -- give OpenShift your source code and a builder image (e.g., `python:3.11-ubi9`). It injects your source into the builder, runs the build process, and produces a runnable image. No Dockerfile needed.
- **Docker builds** -- traditional Dockerfile-based builds, but run inside the cluster
- **Pipeline builds** -- trigger Tekton pipelines from BuildConfigs
- **Webhooks** -- GitHub/GitLab webhooks trigger builds automatically on push

**Why it matters:** Developers can go from source code to a running application without writing a Dockerfile or setting up a CI/CD pipeline. This is OpenShift's biggest conceptual leap from Kubernetes -- the platform handles the build, not just the run.

#### 5. OperatorHub and OLM -- Pre-Installed Operator Ecosystem

In Kubernetes, the Operator Lifecycle Manager (OLM) exists as a project, but you install and configure it yourself. Finding operators means searching the internet, trusting random Helm charts, or building your own.

OpenShift ships with OLM pre-installed and provides **OperatorHub** -- a curated catalog of operators integrated directly into the Web Console. Operators are categorized by:

- **Red Hat operators** -- built and supported by Red Hat
- **Certified operators** -- third-party, tested and certified by Red Hat
- **Community operators** -- community-maintained (use at your own risk in production)

Installing an operator is a few clicks in the console or a `Subscription` YAML applied via CLI. OLM handles installation, upgrades, and dependency resolution.

**Why it matters:** Operators are how you add complex capabilities (databases, monitoring, service meshes) to a cluster. Having a curated, integrated catalog with lifecycle management is the difference between "install this Helm chart and hope it works" and "click install and OLM handles the rest."

#### 6. Web Console -- Far Beyond the K8s Dashboard

The Kubernetes Dashboard is a basic UI for viewing resources. The OpenShift Web Console is a full-featured management interface with two distinct perspectives:

- **Administrator perspective** -- cluster-level operations: nodes, storage, networking, operators, RBAC, monitoring dashboards, alert management
- **Developer perspective** -- application-centric workflows: topology view (visual map of your app), build logs, deployment history, route URLs, integrated terminal, metrics

The console includes features you would need multiple tools for in Kubernetes:
- Visual topology of your applications and their connections
- Integrated terminal for running commands in pods
- Built-in Prometheus metrics and Grafana dashboards
- Operator installation and management
- YAML editor with schema validation

**Why it matters:** The Web Console reduces the barrier to entry. Operations that require `kubectl` plus `jq` plus a separate monitoring UI in Kubernetes are available in a single browser tab.

### Control Plane Architecture

OpenShift's control plane extends the Kubernetes control plane with additional components:

```
+-----------------------------------------------------------------------+
|                     OpenShift Control Plane                            |
|                                                                       |
|  +------------------+  +------------------+  +-------------------+    |
|  |   API Server     |  |    Scheduler     |  | Controller Manager|    |
|  | (K8s + OCP APIs) |  |   (standard)     |  | (K8s + OCP ctrl) |    |
|  +------------------+  +------------------+  +-------------------+    |
|                                                                       |
|  +------------------+  +------------------+  +-------------------+    |
|  |      etcd        |  |   OAuth Server   |  |  OCP Controllers  |    |
|  |   (standard)     |  | (authentication) |  | (build, deploy,   |    |
|  +------------------+  +------------------+  |  image, route)    |    |
|                                              +-------------------+    |
|                                                                       |
|  +------------------+  +------------------+  +-------------------+    |
|  |  Cluster Version |  |   OLM / OHub     |  |  Machine API      |    |
|  |    Operator      |  | (operator mgmt)  |  | (node lifecycle)  |    |
|  +------------------+  +------------------+  +-------------------+    |
|                                                                       |
+-----------------------------------------------------------------------+
```

Key differences from a vanilla Kubernetes control plane:

- **Extended API server** -- serves both Kubernetes APIs (`/api`, `/apis`) and OpenShift-specific APIs (`route.openshift.io`, `build.openshift.io`, `image.openshift.io`, `project.openshift.io`, etc.)
- **OpenShift controllers** -- additional controllers that reconcile OpenShift-specific resources (BuildConfigs, ImageStreams, Routes)
- **Cluster Version Operator (CVO)** -- manages the lifecycle of all OpenShift components. This is how cluster upgrades work: the CVO rolls out updated operator versions in the correct order.
- **Machine API** -- manages the lifecycle of cluster nodes (create, scale, delete) via MachineSets and MachineConfigs. In Kubernetes, you manage nodes yourself or use cloud provider auto-scalers.

### Node Architecture: RHCOS

In Kubernetes, worker nodes can run any Linux distribution. You install kubelet, a container runtime, and whatever else you need. Nodes are pets you manage individually.

OpenShift control plane nodes run **Red Hat Enterprise Linux CoreOS (RHCOS)** -- a purpose-built, immutable operating system:

- **Immutable** -- the root filesystem is read-only. You do not SSH into nodes and install packages. Configuration changes go through **MachineConfig** resources that the Machine Config Operator applies.
- **Managed by the cluster** -- the cluster manages its own nodes' OS. Updates to RHCOS are rolled out as part of OpenShift upgrades.
- **Container-optimized** -- minimal OS footprint, designed to run containers and nothing else.
- **CRI-O runtime** -- OpenShift uses CRI-O (not Docker, not containerd) as the container runtime.

Worker nodes can run either RHCOS or standard RHEL (Red Hat Enterprise Linux), but RHCOS is recommended for consistency.

**Why it matters:** RHCOS eliminates "configuration drift" on nodes. Every node is identical, managed declaratively, and updated atomically. You never SSH into a node to debug a package conflict -- the OS is part of the platform, not a separate concern.

### The Full Picture

Here is how all the pieces fit together in a running OpenShift cluster:

```
+====================================================================+
|                        OpenShift Cluster                            |
|                                                                     |
|  Control Plane Nodes (RHCOS)                                        |
|  +---------------------------------------------------------------+  |
|  |  API Server + OAuth   etcd   Scheduler   Controller Managers  |  |
|  |  CVO   OLM   Machine API   OpenShift Controllers             |  |
|  +---------------------------------------------------------------+  |
|                                                                     |
|  Infrastructure Components (run as pods)                            |
|  +---------------------------------------------------------------+  |
|  |  HAProxy Router         Internal Registry    Monitoring Stack |  |
|  |  (ingress/routes)       (images/streams)     (Prometheus +    |  |
|  |                                               Grafana)        |  |
|  |  Web Console            Logging Stack         DNS             |  |
|  |  (admin + dev views)    (Loki/EFK)           (CoreDNS)       |  |
|  +---------------------------------------------------------------+  |
|                                                                     |
|  Worker Nodes (RHCOS or RHEL)                                       |
|  +---------------------------------------------------------------+  |
|  |  kubelet   CRI-O   OVN-Kubernetes (SDN)   Your Workloads     |  |
|  +---------------------------------------------------------------+  |
|                                                                     |
+====================================================================+
```

Notice that the infrastructure components (router, registry, monitoring, console, logging) all run as pods inside the cluster. They are managed by operators, upgraded by the CVO, and monitored by the same stack they provide. It is turtles all the way down -- and that is by design.

### What About Networking?

OpenShift uses **OVN-Kubernetes** as its default software-defined networking (SDN) layer, replacing the older OpenShift SDN. It provides:

- Pod-to-pod networking (same as Kubernetes CNI)
- NetworkPolicy support (same API as Kubernetes)
- **EgressIP** -- assign stable source IPs to outbound traffic from specific namespaces
- **EgressFirewall** -- restrict which external hosts pods can reach
- **Multus** -- attach multiple network interfaces to a single pod (for specialized workloads like telco/NFV)

From a developer perspective, networking works the same as Kubernetes. The differences show up at the platform/operations level.

## Step-by-Step

Since this is a conceptual lesson, the "steps" are exercises to reinforce the architecture.

### Step 1: Map K8s Concepts to OpenShift Equivalents

Review this mapping and make sure each entry makes sense to you:

| You know this (K8s) | OpenShift calls it / replaces it with |
|---------------------|---------------------------------------|
| Namespace | **Project** (namespace + metadata + RBAC defaults) |
| Ingress + ingress controller | **Route** (built-in HAProxy router) |
| External container registry | **Internal Registry + ImageStreams** |
| External CI/CD (Jenkins, etc.) | **BuildConfig + S2I** (built-in builds) |
| Install OLM yourself | **OLM + OperatorHub** (pre-installed) |
| Kubernetes Dashboard | **Web Console** (Admin + Developer views) |
| External auth (OIDC, certs) | **OAuth Server** (built-in) |
| PodSecurityPolicy / PSA | **Security Context Constraints (SCCs)** |
| Any Linux node OS | **RHCOS** (immutable, managed) |
| containerd / Docker | **CRI-O** (container runtime) |
| Various CNI plugins | **OVN-Kubernetes** (default SDN) |
| `kubectl` | **`oc`** (superset of `kubectl`) |

### Step 2: Understand the "Why" Behind Each Addition

For each OpenShift addition, ask yourself: "What problem does this solve that Kubernetes leaves unsolved?"

- **OAuth Server** -- Solves: "How do my developers log in on day one?"
- **HAProxy Router** -- Solves: "How do I expose apps with TLS without deploying and managing an ingress controller?"
- **Internal Registry** -- Solves: "Where do built images go, and how do deployments track image changes?"
- **S2I / BuildConfig** -- Solves: "How do developers go from source code to a running container without writing a Dockerfile?"
- **OLM / OperatorHub** -- Solves: "How do I install and upgrade complex software (databases, monitoring) in a managed way?"
- **Web Console** -- Solves: "How do I give developers a self-service portal and give admins a single pane of glass?"
- **RHCOS** -- Solves: "How do I prevent configuration drift on nodes and make OS updates part of the platform lifecycle?"
- **SCCs** -- Solves: "How do I enforce pod security by default, not as an opt-in afterthought?"

### Step 3: Trace a Request Through the Architecture

Imagine a user deploys an app from source code. Trace the flow:

1. Developer runs `oc new-app https://github.com/example/my-python-app.git`
2. The **API server** receives the request, authenticated via the **OAuth server**
3. OpenShift detects the language (Python) and creates:
   - A **BuildConfig** (S2I strategy using `python:3.11-ubi9` builder image)
   - An **ImageStream** (to track the output image)
   - A **Deployment** (to run the app)
   - A **Service** (to route internal traffic)
4. The **build controller** starts a build pod that:
   - Clones the Git repo
   - Injects the source into the builder image (S2I)
   - Pushes the resulting image to the **internal registry**
   - Updates the **ImageStream** tag
5. The **image change trigger** on the Deployment detects the new image
6. The **Deployment controller** rolls out new pods with the built image
7. Developer runs `oc expose svc/my-python-app` to create a **Route**
8. The **HAProxy router** picks up the Route and configures a public URL
9. External traffic flows: User -> HAProxy Router -> Service -> Pod
10. The **monitoring stack** (Prometheus) scrapes metrics from the pod
11. The **Web Console** shows the app in the Developer topology view

This entire flow -- from source code to a publicly accessible, monitored application -- happens within the platform. No external CI/CD, no external registry, no external ingress controller.

## Verification

Since this is a conceptual lesson, verify your understanding by answering these questions:

1. **What are the six major components OpenShift adds on top of Kubernetes?**
   OAuth Server, HAProxy Router, Internal Registry + ImageStreams, Build System (S2I/BuildConfig), OLM + OperatorHub, Web Console

2. **What operating system do OpenShift control plane nodes run?**
   RHCOS (Red Hat Enterprise Linux CoreOS) -- an immutable, container-optimized OS managed declaratively

3. **What container runtime does OpenShift use?**
   CRI-O (not Docker, not containerd)

4. **What is the Cluster Version Operator (CVO)?**
   The operator that manages the lifecycle of all OpenShift platform components and orchestrates cluster upgrades

5. **How does OpenShift handle ingress differently from Kubernetes?**
   OpenShift ships a pre-installed HAProxy router and uses Route resources (which support edge, passthrough, and re-encrypt TLS termination). Kubernetes Ingress is also supported.

6. **What is an ImageStream?**
   An abstraction over container image references that enables image change triggers, tag management, and integration with the build system

7. **Why does OpenShift use an immutable node OS?**
   To prevent configuration drift, make node OS updates part of the platform lifecycle, and ensure consistency across all nodes

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| **Distribution** | Vanilla, many distros | Red Hat's opinionated distribution |
| **Authentication** | Bring your own (OIDC, certs) | Built-in OAuth server with multi-provider support |
| **Ingress** | Ingress resource + self-managed controller | Route resource + pre-installed HAProxy router |
| **Container registry** | External (Docker Hub, ECR, etc.) | Built-in internal registry + ImageStreams |
| **Image builds** | External CI/CD | BuildConfig + S2I (built-in) |
| **Operator management** | Install OLM manually | OLM + OperatorHub pre-installed |
| **Web UI** | Basic Dashboard | Full-featured Console (Admin + Dev) |
| **Node OS** | Any supported Linux | RHCOS (immutable, managed) |
| **Container runtime** | containerd (default) | CRI-O |
| **Networking** | Choose a CNI plugin | OVN-Kubernetes (default, pre-configured) |
| **Pod security** | PodSecurity Admission (PSA) | Security Context Constraints (SCCs) |
| **Monitoring** | Install Prometheus yourself | Pre-installed Prometheus + Grafana stack |
| **Logging** | Install EFK/Loki yourself | OpenShift Logging operator |
| **CLI** | `kubectl` | `oc` (superset of `kubectl`) |
| **Upgrades** | Manual component-by-component | CVO-managed, single-command OTA upgrades |

## Key Takeaways

- **OpenShift is Kubernetes**, not a replacement. Every Kubernetes concept you know works unchanged. OpenShift adds platform-level components on top.
- **The six major additions** are: OAuth Server, HAProxy Router, Internal Registry + ImageStreams, Build System (S2I), OLM + OperatorHub, and the Web Console. These are the components that transform Kubernetes from an orchestrator into an application platform.
- **RHCOS makes nodes immutable.** The operating system is managed declaratively via MachineConfig resources and updated as part of cluster upgrades. No SSH, no manual package installs.
- **Everything is an operator.** OpenShift's own components (router, registry, monitoring, console) are managed by operators and reconciled by the Cluster Version Operator. This is the same pattern used for user-installed software.
- **The biggest mental shift** is the build system. In Kubernetes, building images is someone else's problem. In OpenShift, the platform builds, stores, and deploys images as a single integrated workflow.

## Cleanup

No resources were created in this lesson -- nothing to clean up.

## Next Steps

In **L1-M1.2 -- Installing OpenShift Local (CRC)**, you will install and configure a local OpenShift cluster on your machine using Code Ready Containers. You will see these architectural components running as actual pods and interact with the OAuth server, Web Console, and HAProxy router firsthand.
