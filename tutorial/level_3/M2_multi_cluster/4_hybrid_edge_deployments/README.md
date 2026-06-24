# L3-M2.4 — Hybrid & Edge Deployments

**Level:** Expert
**Duration:** 45 min

## Overview

In Kubernetes, you deploy clusters to data centers or cloud providers, and every node has reliable, low-latency connectivity to the control plane. OpenShift extends this model to support deployment topologies where those assumptions break down: bare-metal servers in on-premises data centers, single-node clusters at retail stores or factory floors, ultra-lightweight runtimes on devices at the network edge, and remote worker nodes connected over unreliable WAN links. This lesson covers the full spectrum of OpenShift edge deployment models --- Single Node OpenShift (SNO), MicroShift, remote worker nodes, and Zero Touch Provisioning (ZTP) --- and teaches you when to use each, how they are architected, and how to manage them at scale.

## Prerequisites

- Completed: L3-M2.1 (Advanced Cluster Management)
- Familiarity with RHACM hub-and-spoke architecture
- Understanding of OpenShift installation methods (L3-M1.1)
- OpenShift cluster running (CRC or Developer Sandbox) for simulating configurations
- Access to RHACM hub cluster (or conceptual understanding from L3-M2.1)

## K8s Context

In vanilla Kubernetes, you have one deployment model: a multi-node cluster with separate control plane and worker nodes. Every node needs continuous, reliable connectivity to the API server. Edge computing in the Kubernetes ecosystem typically means either:

- Running full K8s clusters (k3s, k0s, or kubeadm) at each edge site
- Using KubeEdge or similar projects to extend a single cluster to edge nodes
- Managing many small clusters manually or with Cluster API (CAPI)

None of these are integrated into a single, opinionated platform. You stitch together installation tooling, fleet management, GitOps, and observability yourself. There is no standardized provisioning workflow for deploying hundreds of clusters unattended --- you build your own automation from Terraform, Ansible, PXE boot, and custom scripts.

## Concepts

### The Edge Deployment Spectrum

OpenShift provides a deployment model for every point on the edge spectrum. The key insight is that "edge" is not one thing --- it is a continuum from a full data-center-grade cluster down to a single device running a container runtime.

```
+----------------------------------------------------------------------+
|                    OpenShift Edge Deployment Spectrum                  |
+----------------------------------------------------------------------+
|                                                                      |
|  Data Center        Regional Edge       Far Edge        Ultra-Edge   |
|  (Full OCP)         (Compact/SNO)       (SNO)           (MicroShift) |
|                                                                      |
|  100+ nodes          3 nodes             1 node          1 device    |
|  Full HA             Compact HA          No HA           No HA       |
|  Unlimited           Moderate            Constrained     Minimal     |
|  resources           resources           resources       resources   |
|  Reliable net        Reliable net        Intermittent    Disconnected|
|  Full OCP stack      Full OCP stack      Full OCP stack  K8s subset  |
|                                                                      |
|  <-- More capability                  Less footprint -->             |
+----------------------------------------------------------------------+

Management Plane (RHACM Hub)
+----------------------------------------------------------------------+
|  Cluster Lifecycle  |  Policy Engine  |  Observability  |  GitOps    |
+----------------------------------------------------------------------+
```

### Deployment Model Details

**Full OpenShift (Data Center / Cloud)**
Standard multi-node deployment with 3+ control plane nodes and N worker nodes. This is the model you have used throughout this tutorial. Resource requirements: 16+ GB RAM per control plane node, 8+ GB per worker.

**Compact Three-Node Cluster**
Three nodes that serve as both control plane and worker. Used at regional edge sites (e.g., telecom central offices). Same OpenShift feature set, fewer nodes. Schedulable control plane nodes.

**Single Node OpenShift (SNO)**
The entire OpenShift platform --- control plane, worker, router, registry --- runs on a single server. Designed for edge locations like retail stores, factory floors, or cell towers. Resource requirements: 8 vCPUs, 16 GB RAM, 120 GB disk.

```
+-------------------------------------------+
|          Single Node OpenShift             |
|                                           |
|  +-------+  +--------+  +---------+      |
|  | etcd  |  | API    |  | Router  |      |
|  |       |  | Server |  | (HAProxy)|     |
|  +-------+  +--------+  +---------+      |
|                                           |
|  +----------+  +---------+  +--------+   |
|  | Scheduler|  | Registry|  | Kubelet|   |
|  +----------+  +---------+  +--------+   |
|                                           |
|  +----------+  +---------+               |
|  | Workloads|  | Operators|              |
|  +----------+  +---------+               |
|                                           |
|  [ RHCOS or RHEL ]                       |
|  [ Bare Metal / VM ]                     |
+-------------------------------------------+
```

**MicroShift**
An ultra-lightweight Kubernetes distribution based on OpenShift APIs. It runs on RHEL devices with as little as 2 vCPUs and 2 GB RAM. It is not a full OpenShift cluster --- it provides a Kubernetes API subset with OpenShift's Route and security model. Designed for IoT gateways, point-of-sale devices, and industrial controllers.

```
+-----------------------------+
|        MicroShift           |
|                             |
|  +--------+  +--------+    |
|  | API    |  | Router |    |
|  | Server |  | (min)  |    |
|  +--------+  +--------+    |
|                             |
|  +-----------+              |
|  | CRI-O     |              |
|  | (container |             |
|  |  runtime)  |             |
|  +-----------+              |
|                             |
|  +----------+               |
|  | Workloads |              |
|  +----------+               |
|                             |
|  [ RHEL 9 / RHEL for Edge ] |
|  [ x86_64 / ARM64 ]        |
+-----------------------------+
```

**Remote Worker Nodes**
Extend a standard OpenShift cluster by placing worker nodes at remote sites connected over WAN. The control plane stays in the data center. If connectivity is lost, pods on remote workers continue running, but no new scheduling or API operations can occur until the link recovers.

```
Data Center                          Remote Site
+------------------+      WAN       +------------------+
| Control Plane    | <----------->  | Worker Node(s)   |
| (3 masters)      |   Unreliable   | - kubelet        |
| - API Server     |   Latency:     | - CRI-O          |
| - etcd           |   50-500ms     | - Workloads      |
| - Scheduler      |                |                  |
| - Router         |                | Tolerates:       |
| - Registry       |                | - Network loss   |
+------------------+                | - High latency   |
                                    +------------------+
```

### Zero Touch Provisioning (ZTP)

ZTP is the workflow for deploying OpenShift clusters (especially SNO) at scale without on-site personnel. It is the answer to the question: "How do I deploy 1,000 clusters at 1,000 retail stores without sending an engineer to each one?"

```
ZTP Workflow
+--------+     +--------+     +----------+     +----------+     +--------+
| Define |     | Commit |     | RHACM    |     | Bare     |     | Cluster|
| Site   | --> | to Git | --> | Detects  | --> | Metal    | --> | Ready  |
| Config |     | Repo   |     | & Applies|     | Boots    |     | (auto) |
+--------+     +--------+     +----------+     +----------+     +--------+
    |                              |                 |
    |  SiteConfig CR               |  Assisted       |  RHCOS installs
    |  PolicyGenTemplate           |  Installer      |  OCP bootstraps
    |  ClusterInstance CR          |  provisions     |  Policies applied
```

The ZTP pipeline uses:
- **SiteConfig** or **ClusterInstance** CRs: declare a cluster (network, disk, BMC credentials)
- **PolicyGenTemplate** or **PolicyGenerator**: declare desired cluster configuration (operators, performance profiles, networking)
- **Assisted Installer**: drives the installation over IPMI/BMC/Redfish
- **ArgoCD (OpenShift GitOps)**: watches a Git repo and applies site definitions automatically

## Step-by-Step

### Step 1: Understand SNO Resource Requirements and Architecture

Before deploying SNO, you must understand its constraints. SNO combines the roles of control plane, worker, and infrastructure node on a single machine. This means the machine must satisfy the resource requirements of all three roles combined.

Minimum hardware requirements for SNO:

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| vCPUs | 8 | 16 |
| RAM | 16 GB | 32 GB |
| Disk | 120 GB | 250 GB SSD |
| Network | 1 GbE | 10 GbE |

Examine the SNO installation configuration. The `install-config.yaml` for SNO differs from a multi-node cluster in one critical way: it defines a single node in the control plane machine pool and zero workers.

```yaml
# See manifests/sno-install-config.yaml for the full file
```

```bash
# Review the SNO install-config
cat manifests/sno-install-config.yaml
```

### Step 2: Prepare a SiteConfig for ZTP-Based SNO Deployment

In a ZTP workflow, you do not run the installer manually. Instead, you declare each site as a SiteConfig custom resource. RHACM's assisted installer service reads these CRs and provisions the clusters automatically.

```bash
# Review the SiteConfig CR for a retail store edge site
cat manifests/sno-siteconfig.yaml
```

```yaml
# See manifests/sno-siteconfig.yaml for the full definition
```

Key fields in SiteConfig:
- `baseDomain`: the DNS domain for the cluster
- `clusterNetwork` / `machineNetwork`: network CIDRs for the site
- `nodes[].bmcAddress`: the Baseboard Management Controller (IPMI/Redfish) address for remote power management
- `nodes[].bootMACAddress`: the MAC address for PXE boot
- `nodes[].bmcCredentialsName`: a Secret containing BMC username/password
- `nodes[].installerArgs`: additional installer arguments
- `nodes[].cpuset`: CPU cores reserved for platform use (for workload partitioning)

### Step 3: Define Cluster Policies with PolicyGenTemplate

After a cluster is installed, ZTP applies policies to configure it. PolicyGenTemplates (or the newer PolicyGenerator) let you declare the desired state of your fleet.

```bash
# Review the PolicyGenTemplate for edge sites
cat manifests/edge-policy-gen-template.yaml
```

Common policies for edge sites include:
- Performance profile (CPU isolation, huge pages, real-time kernel)
- SR-IOV network configuration
- Local storage operator configuration
- Operator subscriptions (e.g., local storage, performance addon)
- Cluster logging forwarding

### Step 4: Configure Remote Worker Nodes

Remote worker nodes let you extend a data-center cluster to remote sites without deploying a full cluster at each location. This is simpler than SNO when you only need to run a few workloads at a site and want centralized management.

```bash
# Review the MachineSet for remote worker nodes
cat manifests/remote-worker-machineset.yaml
```

Configure node-level network latency tolerance:

```bash
# On the hub/central cluster, set kubelet parameters for remote workers
# The key settings are:
#   node-status-update-frequency: how often kubelet reports status (default 10s)
#   node-monitor-grace-period: how long controller-manager waits (default 40s)
#
# For remote workers on unreliable networks, increase these significantly:
cat manifests/remote-worker-kubelet-config.yaml
```

### Step 5: Understand MicroShift Architecture and Deployment

MicroShift is not deployed via the OpenShift installer. It is an RPM package installed on RHEL 9 or RHEL for Edge. It uses the host's existing storage, networking, and security infrastructure.

```bash
# On a RHEL 9 host, install MicroShift:
sudo dnf install -y microshift
sudo systemctl enable --now microshift

# Wait for MicroShift to start (takes ~2-3 minutes on first boot)
# The kubeconfig is written to /var/lib/microshift/resources/kubeadmin/kubeconfig
export KUBECONFIG=/var/lib/microshift/resources/kubeadmin/kubeconfig

# Verify the cluster is running
oc get nodes
oc get pods -A
```

MicroShift includes:
- Kubernetes API server (single-process, embedded etcd)
- CRI-O container runtime
- OpenShift Router (HAProxy, minimal configuration)
- OVN-Kubernetes networking (simplified)
- CSI driver for LVMS (Logical Volume Manager Storage)

MicroShift does NOT include:
- Operator Lifecycle Manager (OLM)
- OpenShift Console
- Prometheus monitoring stack
- Cluster Version Operator (CVO)
- Machine API

Review the MicroShift application manifest:

```bash
cat manifests/microshift-app-deployment.yaml
```

### Step 6: Deploy a Workload to MicroShift

MicroShift supports standard Kubernetes manifests and OpenShift Routes. Deploy an application using familiar patterns, but sized for constrained resources.

```bash
# Apply the MicroShift-optimized deployment
oc apply -f manifests/microshift-app-deployment.yaml

# Apply the service
oc apply -f manifests/microshift-app-service.yaml

# Apply the route (OpenShift Routes work on MicroShift)
oc apply -f manifests/microshift-app-route.yaml

# Verify
oc get pods
oc get routes
```

### Step 7: Simulate Remote Worker Node Failure and Recovery

Understanding failure modes is critical for edge deployments. When a remote worker node loses connectivity, the following happens:

```
Timeline of a Network Partition
================================

T+0s     Network link drops
T+0-40s  kubelet misses heartbeats
T+40s    Node transitions to NotReady (node-monitor-grace-period)
T+40s    No new pods scheduled to this node
T+5m     Pod eviction begins (default pod-eviction-timeout)
         BUT: existing pods KEEP RUNNING on the node
         (kubelet continues to manage local pods)
T+???    Network recovers
T+???+10s kubelet reconnects, node becomes Ready
         Scheduler resumes normal operation
         Evicted pods are cleaned up if replacements exist
```

```bash
# Simulate monitoring a remote worker node health
# (On a CRC cluster, we can observe node status behavior)

# Check current node status
oc get nodes -o wide

# Watch node conditions
oc describe node <node-name> | grep -A 20 "Conditions:"

# View events related to node status
oc get events --field-selector reason=NodeNotReady -A

# For remote workers, check network latency from the node's perspective
oc debug node/<node-name> -- chroot /host ping -c 5 <api-server-ip>
```

### Step 8: Configure Workload Partitioning for SNO

On SNO, platform components (API server, etcd, controllers) compete with your workloads for CPU and memory. Workload partitioning isolates platform components to specific CPU cores, leaving the remaining cores exclusively for your applications.

```bash
# Review the performance profile for SNO with workload partitioning
cat manifests/sno-performance-profile.yaml
```

```
CPU Core Allocation (Example: 16-core SNO)
==========================================

Cores 0-3:   Platform (API server, etcd, kubelet, CRI-O)
              Managed via workload partitioning
              
Cores 4-15:  Application workloads
              Available for pod scheduling
              Can use CPU Manager for guaranteed QoS pods
```

### Step 9: Plan Fleet Management with RHACM and ZTP

At scale, you manage hundreds or thousands of edge clusters. The management architecture looks like this:

```
Fleet Management Architecture
==============================

                    +------------------+
                    |   Git Repository |
                    | (Site Configs,   |
                    |  Policies, Apps) |
                    +--------+---------+
                             |
                    +--------v---------+
                    |   RHACM Hub      |
                    |   Cluster        |
                    |                  |
                    | +------+ +-----+ |
                    | |ArgoCD| | ACM | |
                    | +------+ +-----+ |
                    | +------+ +-----+ |
                    | |Assist| |Thanos| |
                    | |Inst. | |      | |
                    | +------+ +-----+ |
                    +--------+---------+
                             |
              +--------------+--------------+
              |              |              |
     +--------v---+  +------v-----+  +-----v------+
     | SNO Site 1 |  | SNO Site 2 |  | SNO Site N |
     | (Store #1) |  | (Store #2) |  | (Store #N) |
     | - POS App  |  | - POS App  |  | - POS App  |
     | - Inv. Mgr |  | - Inv. Mgr |  | - Inv. Mgr |
     +------------+  +------------+  +------------+
     
              +--------------+--------------+
              |              |              |
     +--------v---+  +------v-----+  +-----v------+
     | MicroShift |  | MicroShift |  | MicroShift |
     | Device A   |  | Device B   |  | Device C   |
     | (IoT GW)   |  | (Kiosk)    |  | (PLC)      |
     +------------+  +------------+  +------------+
```

```bash
# On the RHACM hub cluster, check managed cluster status
oc get managedclusters -A

# View cluster deployments in progress
oc get agentclusterinstalls -A

# Check policy compliance across all managed clusters
oc get policies -A

# View ZTP pipeline status
oc get applications -n openshift-gitops
```

## Verification

After working through this lesson, verify your understanding by checking the following:

```bash
# 1. Verify you can inspect SNO installation configuration
cat manifests/sno-install-config.yaml | grep -E "replicas|controlPlane|compute"

# 2. Verify SiteConfig structure
cat manifests/sno-siteconfig.yaml | grep -E "clusterName|bmcAddress|bootMACAddress"

# 3. If on a hub cluster with RHACM, verify managed cluster inventory
oc get managedclusters 2>/dev/null || echo "RHACM not available --- review manifests locally"

# 4. Verify MicroShift manifests are valid
oc apply --dry-run=client -f manifests/microshift-app-deployment.yaml
oc apply --dry-run=client -f manifests/microshift-app-service.yaml
oc apply --dry-run=client -f manifests/microshift-app-route.yaml

# 5. Verify remote worker node configuration
cat manifests/remote-worker-kubelet-config.yaml | grep -E "nodeStatusUpdate|eviction"
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Edge cluster options | k3s, k0s, KubeEdge (community) | SNO, MicroShift (Red Hat supported) |
| Single-node deployment | kubeadm single-node (unsupported for production) | SNO: fully supported, production-grade |
| Ultra-lightweight runtime | k3s (~512 MB RAM) | MicroShift (~2 GB RAM, OpenShift API compatible) |
| Remote worker nodes | Built-in but no special WAN handling | Tunable grace periods, tested for high-latency WAN |
| Fleet provisioning | Cluster API + custom PXE/iPXE automation | Zero Touch Provisioning (ZTP) via RHACM |
| Bare-metal provisioning | Manual PXE + kubeadm or Cluster API | Assisted Installer, Metal3, Redfish/IPMI integration |
| Fleet policy management | No built-in solution (use Kyverno, OPA manually) | RHACM Policy Engine, PolicyGenTemplates |
| Workload partitioning | Manual CPU pinning via kubelet config | Integrated workload partitioning with performance profiles |
| Device management | No native solution | MicroShift + RHEL for Edge + Greenboot health checks |
| Disconnected operation | Pods keep running, no built-in tooling | Supported with disconnected registries, tested topologies |

## Key Takeaways

- **SNO (Single Node OpenShift)** runs the full OpenShift platform on a single server with 8+ vCPUs and 16+ GB RAM, suitable for edge locations that need the complete OpenShift feature set including operators and the web console.
- **MicroShift** is an ultra-lightweight Kubernetes distribution for devices with as little as 2 vCPUs and 2 GB RAM; it provides OpenShift-compatible APIs (Routes, SCCs) without the full platform overhead (no OLM, no console, no CVO).
- **Remote worker nodes** extend a central cluster to remote sites over WAN; they tolerate network partitions (existing pods keep running), but new scheduling stops until connectivity recovers. Tune `node-monitor-grace-period` and `pod-eviction-timeout` to match your WAN reliability.
- **Zero Touch Provisioning (ZTP)** automates the deployment of hundreds or thousands of edge clusters by combining SiteConfig CRs, PolicyGenTemplates, the Assisted Installer, and ArgoCD --- all driven from a Git repository with no on-site personnel required.
- **Workload partitioning** on SNO is essential for production: it pins OpenShift platform components to dedicated CPU cores, ensuring your application workloads get predictable performance on the remaining cores.

## Failure Modes and Recovery

### SNO Node Failure

**Failure:** The single node crashes or loses power.
**Impact:** The entire cluster is down. There is no HA --- this is accepted at edge sites where the cost of a second node outweighs the risk.
**Recovery:** The node reboots, RHCOS starts, kubelet reconnects to the local API server, all pods restart. If etcd is on durable storage (SSD), no data is lost. If the disk fails, re-provision via ZTP from the hub cluster.
**Mitigation:** Use Greenboot (RHEL for Edge health checks) to automatically roll back failed OS updates. Monitor via RHACM and set alerts for cluster-down events.

### MicroShift Device Failure

**Failure:** The device loses power or the MicroShift process crashes.
**Impact:** Workloads on the device stop. MicroShift is designed for quick restarts.
**Recovery:** `systemctl restart microshift` or power cycle. MicroShift restarts in ~60 seconds on warm boot. etcd data is stored locally in `/var/lib/microshift`.
**Mitigation:** Use `greenboot` health check scripts. Configure RHEL for Edge with `rpm-ostree` for atomic OS updates with rollback.

### Remote Worker Network Partition

**Failure:** WAN link between data center and remote site drops.
**Impact:** Existing pods keep running (kubelet manages them locally). No new pods can be scheduled. After `pod-eviction-timeout` (default 5m, configurable), the control plane marks pods for eviction --- but eviction only executes when connectivity returns.
**Recovery:** When the link recovers, kubelet reconnects, node becomes Ready, scheduler resumes. If pods were evicted and rescheduled elsewhere, duplicates are cleaned up.
**Mitigation:** Increase `node-monitor-grace-period` to 60-120s for WAN links. Set `pod-eviction-timeout` to 300-600s. Use node labels and taints to prevent rescheduling to other sites.

### ZTP Provisioning Failure

**Failure:** A new site fails to provision (bad BMC credentials, network misconfiguration, disk too small).
**Impact:** The specific site does not come online. Other sites are unaffected.
**Recovery:** Check `agentclusterinstall` status on the hub cluster: `oc get agentclusterinstalls -A`. Review the assisted installer events. Fix the SiteConfig, commit to Git, and ArgoCD re-triggers provisioning.
**Mitigation:** Validate SiteConfigs in CI before merging. Use RHACM cluster pools for pre-provisioned spare clusters.

## Cleanup

```bash
# Remove MicroShift application resources (if deployed)
oc delete -f manifests/microshift-app-route.yaml --ignore-not-found
oc delete -f manifests/microshift-app-service.yaml --ignore-not-found
oc delete -f manifests/microshift-app-deployment.yaml --ignore-not-found

# If testing on CRC, no additional cleanup is needed for review-only exercises.

# On a RHACM hub cluster, to remove a managed SNO site:
# oc delete managedcluster <cluster-name>
# This detaches the cluster but does not wipe it.
# To fully decommission, delete the SiteConfig from the Git repo.
```

## Next Steps

In **L3-M3.1 --- Performance Tuning**, you will learn how to optimize OpenShift for latency-sensitive and high-throughput workloads using the Node Tuning Operator, performance profiles, huge pages, CPU pinning, and NUMA-aware scheduling. Many of these techniques are critical for the SNO and edge deployments covered in this lesson, as edge workloads often have strict real-time or performance requirements.
