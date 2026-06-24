# L3-M3.1 — Performance Tuning

**Level:** Expert
**Duration:** 1 hr

## Overview

In Kubernetes, performance tuning at the node level typically means SSH-ing into machines, editing sysctl configs, and managing TuneD profiles manually — a fragile, unauditable process that breaks immutable infrastructure principles. OpenShift solves this through the **Node Tuning Operator** and **PerformanceProfile** CRs, which let you declare performance requirements as Kubernetes-native resources. This lesson covers the full stack of performance tuning: from TuneD profiles and huge pages to CPU pinning, NUMA-aware scheduling, and low-latency configurations required by telco and financial workloads.

## Prerequisites

- Completed: L3-M1.3 (Node Management — MachineSets, MachineConfigPools, MachineConfigs)
- OpenShift 4.12+ cluster (CRC for conceptual exercises; a multi-node cluster for full hands-on)
- `cluster-admin` access (logged in as `kubeadmin`)
- Familiarity with Linux performance concepts (NUMA, CPU affinity, huge pages, TuneD)

> **Note:** Some features in this lesson (CPU Manager, NUMA-aware topology, PerformanceProfile) require a multi-node cluster with bare-metal or virtual worker nodes. CRC (single-node) can demonstrate the operator and CR creation, but actual performance isolation requires dedicated worker nodes. The lesson notes where CRC limitations apply.

## K8s Context

In vanilla Kubernetes, performance tuning is a multi-layer manual effort:

- **CPU pinning** requires enabling the `CPUManager` kubelet feature gate, setting `--cpu-manager-policy=static`, and restarting the kubelet — a node-level operation with no declarative API.
- **Huge pages** require kernel boot parameters (`hugepagesz=1G hugepages=16`) set via GRUB, plus `resources.limits` in Pod specs.
- **NUMA awareness** requires the `TopologyManager` kubelet feature gate with a chosen policy (`single-numa-node`, `best-effort`, etc.) — again, kubelet-level configuration.
- **Kernel tuning** means manually running `sysctl` commands or editing `/etc/sysctl.d/` files on each node.
- **TuneD profiles** must be installed and managed outside Kubernetes entirely.

There is no unified, declarative way to say "I need this node pool optimized for low-latency, real-time workloads." OpenShift changes this fundamentally.

## Concepts

### The Node Tuning Operator (NTO)

The Node Tuning Operator ships with every OpenShift installation. It manages **Tuned** CRs (Custom Resources) that map TuneD profiles to nodes based on label selectors. When a Tuned CR is created or updated, the operator:

1. Selects nodes matching the profile's label selector
2. Deploys TuneD daemon pods to those nodes
3. Applies the specified TuneD profile (kernel parameters, sysctl settings, I/O scheduler, etc.)
4. Monitors for drift and reapplies if settings change

```
+---------------------+        +------------------+        +-----------------+
|   Tuned CR          | -----> | Node Tuning      | -----> | TuneD DaemonSet |
| (desired profile)   |        | Operator         |        | (per-node pods) |
+---------------------+        +------------------+        +-----------------+
                                                                   |
                                                                   v
                                                           +-----------------+
                                                           | Node kernel     |
                                                           | sysctl, IRQ,    |
                                                           | CPU gov, I/O    |
                                                           +-----------------+
```

### Huge Pages

Huge pages reduce TLB (Translation Lookaside Buffer) misses by using larger memory pages (2 MiB or 1 GiB instead of the default 4 KiB). This is critical for:

- **Databases** (PostgreSQL, Oracle) — large shared buffers
- **DPDK networking** — packet processing with zero-copy
- **HPC/scientific computing** — large matrix operations
- **In-memory caches** (Redis, Memcached) — reducing page table overhead

OpenShift configures huge pages through MachineConfigs (kernel boot parameters) and exposes them as schedulable resources via `hugepages-2Mi` and `hugepages-1Gi` in Pod resource requests.

### CPU Manager and CPU Pinning

The CPU Manager is a kubelet component that provides CPU affinity for Pods with `Guaranteed` QoS class (requests == limits for all containers). In static policy mode:

```
+--------------------------------------------------+
|                    Node CPUs                      |
|                                                   |
|  +----------+  +----------+  +-----------------+ |
|  | Reserved |  | Reserved |  | Allocatable     | |
|  | CPU 0    |  | CPU 1    |  | CPUs 2-15       | |
|  | (system) |  | (system) |  | (workloads)     | |
|  +----------+  +----------+  +-----------------+ |
|                                 |                 |
|                    +------------+-------+         |
|                    |                    |          |
|              +-----------+       +-----------+    |
|              | Pod A     |       | Pod B     |    |
|              | CPUs 2-5  |       | CPUs 6-9  |    |
|              | (pinned)  |       | (pinned)  |    |
|              +-----------+       +-----------+    |
+--------------------------------------------------+
```

- **Shared pool**: CPUs available to BestEffort and Burstable Pods (shared via CFS scheduler)
- **Exclusive CPUs**: Assigned to Guaranteed Pods with integer CPU requests (pinned, no sharing)
- **Reserved CPUs**: Set aside for system daemons (kubelet, CRI-O, kernel)

### NUMA-Aware Scheduling

Non-Uniform Memory Access (NUMA) architectures have multiple memory domains. Accessing local NUMA memory is faster than remote. The Topology Manager coordinates CPU Manager, Device Manager, and Memory Manager to align resource allocation to NUMA boundaries:

```
+---------------------------+---------------------------+
|        NUMA Node 0        |        NUMA Node 1        |
|                           |                           |
|  CPUs: 0-7                |  CPUs: 8-15               |
|  Memory: 64 GiB           |  Memory: 64 GiB           |
|  NIC: ens1f0 (SR-IOV)     |  NIC: ens1f1 (SR-IOV)     |
|                           |                           |
|  +---------------------+  |                           |
|  | Pod (NUMA-aligned)  |  |                           |
|  | CPU: 2-5 (local)    |  |                           |
|  | Mem: local NUMA 0    |  |                           |
|  | NIC: ens1f0 VF       |  |                           |
|  +---------------------+  |                           |
+---------------------------+---------------------------+
             QPI / UPI interconnect
```

Topology Manager policies:
- `none` — no alignment (default)
- `best-effort` — prefer aligned, but allow misaligned
- `restricted` — reject Pods if alignment is impossible
- `single-numa-node` — all resources must come from one NUMA node

### PerformanceProfile CR

The PerformanceProfile CR (from the Performance Addon Operator, now integrated into NTO as of OpenShift 4.11+) is the unified declarative API for all of the above. A single CR configures:

- CPU partitioning (reserved vs isolated CPUs)
- Huge pages (sizes and counts per NUMA node)
- Topology Manager policy
- Kernel arguments (real-time kernel, isolcpus, nohz_full)
- Additional kernel modules
- Real-time kernel selection

```
+-----------------------------+
|     PerformanceProfile CR   |
+-----------------------------+
         |
         | generates
         v
+--------+--------+--------+
|        |        |        |
v        v        v        v
Tuned CR  MachineConfig  KubeletConfig  RuntimeClass
(sysctl,  (kernel args,  (CPU Manager,  (high-perf
 IRQ)     hugepages)      Topology Mgr)  runtime)
```

### Low-Latency Tuning for Telco/Financial Workloads

Telco 5G RAN (Radio Access Network) and financial trading systems require deterministic, microsecond-level latency. This involves:

1. **Real-time kernel** (`kernel-rt`) — preemptible kernel for bounded latency
2. **CPU isolation** — workload CPUs removed from kernel scheduler, IRQ balancing, and RCU callbacks
3. **Huge pages** — eliminate TLB misses for DPDK and shared memory
4. **NUMA pinning** — all resources from a single NUMA node
5. **IRQ affinity** — move hardware interrupts off workload CPUs
6. **Power management** — disable CPU frequency scaling (`intel_pstate=disable`, `processor.max_cstate=1`)

## Step-by-Step

### Step 1: Verify the Node Tuning Operator

The NTO is pre-installed on every OpenShift cluster. Verify it is running:

```bash
# Check the NTO deployment
oc get deployment -n openshift-cluster-node-tuning-operator

# Verify the operator pod is running
oc get pods -n openshift-cluster-node-tuning-operator

# List existing Tuned profiles
oc get tuned -n openshift-cluster-node-tuning-operator

# View the default Tuned profile
oc get tuned default -n openshift-cluster-node-tuning-operator -o yaml
```

Expected output:
```
NAME                                           READY   UP-TO-DATE   AVAILABLE
cluster-node-tuning-operator                   1/1     1            1

NAME                                           READY   STATUS    RESTARTS
cluster-node-tuning-operator-<hash>            1/1     Running   0
tuned-<hash>                                   1/1     Running   0

NAME      AGE
default   42d
rendered  42d
```

### Step 2: Create a Custom TuneD Profile

Create a custom Tuned CR that optimizes nodes labeled `node-role.kubernetes.io/worker-perf` for database workloads:

```bash
oc apply -f manifests/tuned-db-profile.yaml
```

The manifest (`manifests/tuned-db-profile.yaml`) creates a TuneD profile with:
- Increased `vm.dirty_ratio` and `vm.dirty_background_ratio` for write-heavy workloads
- Larger TCP buffer sizes for network throughput
- Disabled transparent huge pages (databases prefer explicit huge pages)
- Deadline I/O scheduler for predictable latency

```yaml
# manifests/tuned-db-profile.yaml
apiVersion: tuned.openshift.io/v1
kind: Tuned
metadata:
  name: db-optimized
  namespace: openshift-cluster-node-tuning-operator
  labels:
    app: performance-tuning
    tutorial-level: "3"
    tutorial-module: "M3"
spec:
  profile:
    - name: db-optimized
      data: |
        [main]
        summary=Database-optimized profile for write-heavy workloads
        include=openshift-node

        [sysctl]
        # Increase dirty page ratio for write batching
        vm.dirty_ratio=40
        vm.dirty_background_ratio=10
        # Increase max memory map areas (databases use many)
        vm.max_map_count=262144
        # Larger TCP buffers for replication traffic
        net.core.rmem_max=16777216
        net.core.wmem_max=16777216
        net.ipv4.tcp_rmem=4096 87380 16777216
        net.ipv4.tcp_wmem=4096 65536 16777216
        # Increase connection backlog
        net.core.somaxconn=4096
        net.ipv4.tcp_max_syn_backlog=8192
        # Disable swap tendency
        vm.swappiness=10

        [vm]
        transparent_hugepages=never
  recommend:
    - match:
        - label: node-role.kubernetes.io/worker-perf
      priority: 20
      profile: db-optimized
```

Verify the profile is applied:

```bash
# Check that the Tuned CR was created
oc get tuned -n openshift-cluster-node-tuning-operator

# On a multi-node cluster, label a worker node to trigger the profile
# oc label node <worker-node> node-role.kubernetes.io/worker-perf=""

# Check the profile applied to nodes (on a multi-node cluster)
oc get profile -n openshift-cluster-node-tuning-operator
```

### Step 3: Configure Huge Pages via MachineConfig

Huge pages must be configured at boot time via kernel parameters. Create a MachineConfig to allocate huge pages:

```bash
oc apply -f manifests/machineconfig-hugepages.yaml
```

```yaml
# manifests/machineconfig-hugepages.yaml
apiVersion: machineconfiguration.openshift.io/v1
kind: MachineConfig
metadata:
  name: 50-hugepages
  labels:
    machineconfiguration.openshift.io/role: worker-perf
    app: performance-tuning
    tutorial-level: "3"
    tutorial-module: "M3"
spec:
  kernelArguments:
    - hugepagesz=2M
    - hugepages=1024
    - hugepagesz=1G
    - hugepages=4
```

> **Warning:** Applying a MachineConfig to a MachineConfigPool triggers a rolling reboot of all nodes in that pool. In production, always apply during a maintenance window.

> **CRC limitation:** CRC uses a single node. Applying MachineConfigs to the `worker` pool may not work as expected. This step is best performed on a multi-node cluster.

Create a MachineConfigPool to target performance worker nodes (if it does not already exist from L3-M1.3):

```bash
oc apply -f manifests/machineconfigpool-perf.yaml
```

```yaml
# manifests/machineconfigpool-perf.yaml
apiVersion: machineconfiguration.openshift.io/v1
kind: MachineConfigPool
metadata:
  name: worker-perf
  labels:
    app: performance-tuning
    tutorial-level: "3"
    tutorial-module: "M3"
spec:
  machineConfigSelector:
    matchExpressions:
      - key: machineconfiguration.openshift.io/role
        operator: In
        values:
          - worker
          - worker-perf
  nodeSelector:
    matchLabels:
      node-role.kubernetes.io/worker-perf: ""
  maxUnavailable: 1
```

### Step 4: Deploy a Pod That Uses Huge Pages

Once huge pages are allocated on a node, deploy a workload that requests them:

```bash
oc new-project perf-tuning-demo
oc apply -f manifests/pod-hugepages.yaml
```

```yaml
# manifests/pod-hugepages.yaml
apiVersion: v1
kind: Pod
metadata:
  name: hugepages-demo
  namespace: perf-tuning-demo
  labels:
    app: hugepages-demo
    tutorial-level: "3"
    tutorial-module: "M3"
spec:
  containers:
    - name: hugepages-app
      image: registry.access.redhat.com/ubi9/ubi-minimal:latest
      command:
        - /bin/sh
        - -c
        - |
          echo "Checking huge pages allocation..."
          cat /proc/meminfo | grep -i huge
          echo "---"
          echo "Mounted hugepage filesystem:"
          mount | grep hugetlbfs
          echo "---"
          echo "Hugepage files in /hugepages:"
          ls -la /hugepages/ 2>/dev/null || echo "No hugepages mount"
          sleep infinity
      resources:
        requests:
          memory: "256Mi"
          cpu: "500m"
          hugepages-2Mi: "128Mi"
        limits:
          memory: "256Mi"
          cpu: "500m"
          hugepages-2Mi: "128Mi"
      volumeMounts:
        - name: hugepage
          mountPath: /hugepages
  volumes:
    - name: hugepage
      emptyDir:
        medium: HugePages-2Mi
```

Verify the Pod is scheduled and huge pages are available:

```bash
# Check Pod status
oc get pod hugepages-demo -n perf-tuning-demo

# Verify huge pages inside the container
oc logs hugepages-demo -n perf-tuning-demo

# Check node-level huge page allocation
oc debug node/<worker-node> -- chroot /host cat /proc/meminfo | grep -i huge
```

### Step 5: Enable CPU Manager for CPU Pinning

CPU Manager is configured via a KubeletConfig CR. Create one that enables static CPU management:

```bash
oc apply -f manifests/kubeletconfig-cpumanager.yaml
```

```yaml
# manifests/kubeletconfig-cpumanager.yaml
apiVersion: machineconfiguration.openshift.io/v1
kind: KubeletConfig
metadata:
  name: cpumanager-enabled
  labels:
    app: performance-tuning
    tutorial-level: "3"
    tutorial-module: "M3"
spec:
  machineConfigPoolSelector:
    matchLabels:
      custom-kubelet: cpumanager-enabled
  kubeletConfig:
    cpuManagerPolicy: static
    cpuManagerReconcilePeriod: 5s
    reservedSystemCPUs: "0-1"
    topologyManagerPolicy: single-numa-node
    memoryManagerPolicy: Static
    reservedMemory:
      - numaNode: 0
        limits:
          memory: "1Gi"
          hugepages-2Mi: "128Mi"
```

Label the MachineConfigPool to apply the KubeletConfig:

```bash
oc label mcp worker-perf custom-kubelet=cpumanager-enabled
```

> **Important:** After applying the KubeletConfig, nodes in the pool will be drained and rebooted one at a time. Monitor the rollout:

```bash
# Watch the MachineConfigPool rollout
oc get mcp worker-perf -w

# Check node status
oc get nodes -l node-role.kubernetes.io/worker-perf
```

### Step 6: Deploy a CPU-Pinned Workload

For CPU pinning to work, the Pod must have `Guaranteed` QoS (requests == limits for CPU and memory) and request whole-number CPUs:

```bash
oc apply -f manifests/pod-cpu-pinned.yaml
```

```yaml
# manifests/pod-cpu-pinned.yaml
apiVersion: v1
kind: Pod
metadata:
  name: cpu-pinned-workload
  namespace: perf-tuning-demo
  labels:
    app: cpu-pinned-workload
    tutorial-level: "3"
    tutorial-module: "M3"
spec:
  containers:
    - name: latency-sensitive-app
      image: registry.access.redhat.com/ubi9/ubi-minimal:latest
      command:
        - /bin/sh
        - -c
        - |
          echo "CPU pinning verification:"
          echo "CPU affinity (taskset):"
          taskset -p $$ 2>/dev/null || echo "taskset not available"
          echo "---"
          echo "Cgroup cpuset:"
          cat /sys/fs/cgroup/cpuset.cpus 2>/dev/null || \
            cat /sys/fs/cgroup/cpuset/cpuset.cpus 2>/dev/null || \
            echo "cpuset info not available"
          echo "---"
          echo "NUMA info:"
          cat /sys/fs/cgroup/cpuset.mems 2>/dev/null || \
            cat /sys/fs/cgroup/cpuset/cpuset.mems 2>/dev/null || \
            echo "NUMA info not available"
          echo "---"
          echo "/proc/self/status:"
          grep -E "Cpus_allowed|Mems_allowed" /proc/self/status
          sleep infinity
      resources:
        requests:
          memory: "512Mi"
          cpu: "4"
        limits:
          memory: "512Mi"
          cpu: "4"
```

Verify CPU pinning:

```bash
# Check QoS class
oc get pod cpu-pinned-workload -n perf-tuning-demo -o jsonpath='{.status.qosClass}'
# Expected: Guaranteed

# Check CPU assignment
oc logs cpu-pinned-workload -n perf-tuning-demo

# Verify on the node (which CPUs were assigned)
oc debug node/<worker-node> -- chroot /host \
  cat /var/lib/kubelet/cpu_manager_state
```

The `cpu_manager_state` file shows the CPU-to-container mapping:

```json
{
  "policyName": "static",
  "defaultCpuSet": "0-1,10-15",
  "entries": {
    "<container-id>": {
      "latency-sensitive-app": "2-5"
    }
  }
}
```

### Step 7: Create a PerformanceProfile for Low-Latency Workloads

The PerformanceProfile CR combines all of the above into a single declaration. This is the recommended approach for production:

```bash
oc apply -f manifests/performanceprofile-low-latency.yaml
```

```yaml
# manifests/performanceprofile-low-latency.yaml
apiVersion: performance.openshift.io/v2
kind: PerformanceProfile
metadata:
  name: low-latency
  labels:
    app: performance-tuning
    tutorial-level: "3"
    tutorial-module: "M3"
  annotations:
    kubeletconfig.experimental: |
      {"topologyManagerScope": "pod"}
spec:
  # CPU partitioning: reserve CPUs 0-3 for OS/platform, isolate 4-31 for workloads
  cpu:
    reserved: "0-3"
    isolated: "4-31"
    # offlined: "32-63"   # Optional: offline unused CPUs to save power

  # Huge pages allocation per NUMA node
  hugepages:
    defaultHugepagesSize: 1G
    pages:
      - size: 1G
        count: 4
        node: 0
      - size: 2M
        count: 1024
        node: 0
      - size: 1G
        count: 4
        node: 1
      - size: 2M
        count: 1024
        node: 1

  # NUMA-aware scheduling
  numa:
    topologyPolicy: single-numa-node

  # Real-time kernel (required for telco/financial workloads)
  realTimeKernel:
    enabled: true

  # Additional kernel arguments for low-latency
  additionalKernelArgs:
    - nohz_full=4-31
    - tsc=reliable
    - nosoftlockup
    - nmi_watchdog=0
    - intel_pstate=disable
    - idle=poll
    - processor.max_cstate=1
    - intel_idle.max_cstate=0
    - mce=off
    - audit=0

  # Apply to the worker-perf MachineConfigPool
  machineConfigPoolSelector:
    matchLabels:
      machineconfiguration.openshift.io/role: worker-perf

  # Select nodes with the performance label
  nodeSelector:
    node-role.kubernetes.io/worker-perf: ""

  # Workload partitioning hints
  workloadHints:
    highPowerConsumption: true
    realTime: true
    perPodPowerManagement: false

  # Net configuration
  net:
    userLevelNetworking: true
    devices:
      - interfaceName: ens*f0
```

> **Warning:** PerformanceProfile triggers MachineConfig and KubeletConfig generation, causing node reboots. In a production environment with hundreds of nodes, use `maxUnavailable` on the MachineConfigPool to control the blast radius.

Monitor the rollout:

```bash
# Watch the PerformanceProfile status
oc get performanceprofile low-latency -o jsonpath='{.status.conditions}' | python3 -m json.tool

# Watch generated resources
oc get tuned -n openshift-cluster-node-tuning-operator | grep performance
oc get kubeletconfig | grep performance
oc get machineconfig | grep performance
oc get runtimeclass | grep performance

# Monitor node rollout
oc get mcp worker-perf -w
```

### Step 8: Deploy a Low-Latency Workload Using the PerformanceProfile

Deploy a workload that leverages the full low-latency configuration:

```bash
oc apply -f manifests/deployment-low-latency.yaml
```

```yaml
# manifests/deployment-low-latency.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: low-latency-app
  namespace: perf-tuning-demo
  labels:
    app: low-latency-app
    tutorial-level: "3"
    tutorial-module: "M3"
spec:
  replicas: 1
  selector:
    matchLabels:
      app: low-latency-app
  template:
    metadata:
      labels:
        app: low-latency-app
        tutorial-level: "3"
        tutorial-module: "M3"
      annotations:
        # Disable CPU load balancing for isolated CPUs
        cpu-load-balancing.crio.io: disable
        # Disable CPU quota for real-time tasks
        cpu-quota.crio.io: disable
        # Disable IRQ balancing on the container's CPUs
        irq-load-balancing.crio.io: disable
        # Set NUMA alignment
        cpu-c-states.crio.io: disable
        cpu-freq-governor.crio.io: performance
    spec:
      # Use the RuntimeClass generated by PerformanceProfile
      runtimeClassName: performance-low-latency
      nodeSelector:
        node-role.kubernetes.io/worker-perf: ""
      tolerations:
        - key: node-role.kubernetes.io/worker-perf
          operator: Exists
          effect: NoSchedule
      containers:
        - name: latency-app
          image: registry.access.redhat.com/ubi9/ubi-minimal:latest
          command:
            - /bin/sh
            - -c
            - |
              echo "=== Low-Latency Workload Running ==="
              echo "CPU Affinity:"
              taskset -p $$ 2>/dev/null || echo "N/A"
              echo "---"
              echo "NUMA Node:"
              cat /sys/fs/cgroup/cpuset.mems 2>/dev/null || echo "N/A"
              echo "---"
              echo "Huge Pages Available:"
              cat /proc/meminfo | grep -i huge
              echo "---"
              echo "Kernel (should be -rt):"
              uname -r
              echo "---"
              echo "Timer resolution:"
              cat /proc/timer_list 2>/dev/null | head -5 || echo "N/A"
              sleep infinity
          resources:
            requests:
              memory: "1Gi"
              cpu: "4"
              hugepages-1Gi: "2Gi"
            limits:
              memory: "1Gi"
              cpu: "4"
              hugepages-1Gi: "2Gi"
          volumeMounts:
            - name: hugepages-1gi
              mountPath: /hugepages-1Gi
          securityContext:
            capabilities:
              add:
                - SYS_NICE
                - IPC_LOCK
      volumes:
        - name: hugepages-1gi
          emptyDir:
            medium: HugePages-1Gi
```

### Step 9: Validate Performance Settings

Run the validation script to confirm all tuning is active:

```bash
chmod +x scripts/validate-performance.sh
./scripts/validate-performance.sh <worker-node-name>
```

Or manually verify each component:

```bash
# 1. Verify CPU Manager state on the node
oc debug node/<worker-node> -- chroot /host \
  cat /var/lib/kubelet/cpu_manager_state

# 2. Verify huge pages are allocated
oc debug node/<worker-node> -- chroot /host \
  cat /proc/meminfo | grep -i huge

# 3. Verify kernel parameters
oc debug node/<worker-node> -- chroot /host \
  cat /proc/cmdline

# 4. Verify TuneD profile is active
oc debug node/<worker-node> -- chroot /host \
  tuned-adm active

# 5. Verify real-time kernel (if enabled)
oc debug node/<worker-node> -- chroot /host \
  uname -r
# Expected: 4.18.0-xxx.rt13.xxx.el8_x.x86_64

# 6. Verify NUMA topology
oc debug node/<worker-node> -- chroot /host \
  lscpu | grep -i numa

# 7. Verify IRQ affinity (workload CPUs should have no IRQs)
oc debug node/<worker-node> -- chroot /host \
  cat /proc/interrupts | head -3
```

### Step 10: Monitor Performance with Prometheus

OpenShift's built-in monitoring stack exposes performance metrics. Query key metrics:

```bash
# Port-forward Prometheus (or use the Web Console)
# Navigate to Monitoring > Metrics in the OpenShift Console

# Key PromQL queries for performance tuning:

# CPU usage per core (verify pinning is working)
# node_cpu_seconds_total{mode="idle"}

# Huge page usage
# node_memory_HugePages_Total
# node_memory_HugePages_Free

# Context switches (should be low for pinned CPUs)
# node_context_switches_total

# NUMA memory hits vs misses
# node_memory_numa_hit_total
# node_memory_numa_miss_total

# CPU frequency (should be max if pstate disabled)
# node_cpu_scaling_frequency_hertz
```

Check metrics via the CLI:

```bash
# Get the Prometheus route
oc get route prometheus-k8s -n openshift-monitoring -o jsonpath='{.spec.host}'

# Or use the thanos-querier route for multi-cluster
oc get route thanos-querier -n openshift-monitoring -o jsonpath='{.spec.host}'
```

## Verification

Run through this checklist to confirm the lesson was completed successfully:

| Check | Command | Expected Result |
|-------|---------|-----------------|
| NTO is running | `oc get deploy -n openshift-cluster-node-tuning-operator` | 1/1 READY |
| Custom Tuned CR exists | `oc get tuned db-optimized -n openshift-cluster-node-tuning-operator` | CR found |
| PerformanceProfile exists | `oc get performanceprofile low-latency` | CR found |
| Huge pages Pod is running | `oc get pod hugepages-demo -n perf-tuning-demo` | Running |
| Huge pages visible in Pod | `oc logs hugepages-demo -n perf-tuning-demo` | HugePages_Total > 0 |
| CPU-pinned Pod is Guaranteed | `oc get pod cpu-pinned-workload -n perf-tuning-demo -o jsonpath='{.status.qosClass}'` | Guaranteed |
| CPU pinning active on node | `oc debug node/<node> -- chroot /host cat /var/lib/kubelet/cpu_manager_state` | Container has exclusive CPUs |
| RuntimeClass created | `oc get runtimeclass performance-low-latency` | RuntimeClass found |
| Real-time kernel installed | `oc debug node/<node> -- chroot /host uname -r` | Kernel ends with `.rt` |

## Failure Modes and Recovery

### MachineConfig Rollout Stuck

**Symptom:** `oc get mcp worker-perf` shows `UPDATING=True` indefinitely.

**Cause:** A MachineConfig rendered invalid kernel arguments or a conflict between MachineConfigs.

**Recovery:**
```bash
# Check the rendered MachineConfig for errors
oc get mcp worker-perf -o yaml | grep -A5 conditions

# Check which node is stuck
oc get nodes -l node-role.kubernetes.io/worker-perf

# SSH/debug into the stuck node
oc debug node/<stuck-node>
chroot /host
journalctl -u machine-config-daemon -f

# If the node is in a boot loop, remove the problematic MachineConfig
oc delete mc 50-hugepages

# Force a node to re-render its config
oc debug node/<stuck-node> -- chroot /host touch /run/machine-config-daemon-force
```

### Pods Pending Due to Insufficient Huge Pages

**Symptom:** Pod stuck in `Pending` with event `Insufficient hugepages-2Mi`.

**Cause:** Not enough huge pages allocated on any node, or huge pages are fragmented.

**Recovery:**
```bash
# Check available huge pages on nodes
oc describe nodes | grep -A3 hugepages

# Verify the MachineConfig has the right kernel args
oc get mc 50-hugepages -o yaml | grep -A5 kernelArguments

# If hugepages are allocated but reported as 0, the node needs a reboot
# (huge pages must be reserved at boot time for 1G pages)
```

### CPU Manager State Corruption

**Symptom:** Pods fail to start with `cannot allocate cpus` errors even when CPUs are available.

**Cause:** The CPU Manager state file is corrupted (e.g., after an unclean node shutdown).

**Recovery:**
```bash
# Stop the kubelet
oc debug node/<node> -- chroot /host systemctl stop kubelet

# Remove the state file (it will be regenerated)
oc debug node/<node> -- chroot /host rm /var/lib/kubelet/cpu_manager_state

# Restart the kubelet
oc debug node/<node> -- chroot /host systemctl start kubelet
```

### NUMA Topology Manager Rejection

**Symptom:** Pod rejected with `TopologyAffinityError`.

**Cause:** The `single-numa-node` policy cannot satisfy the Pod's resource request from a single NUMA node (e.g., requesting 16 CPUs but each NUMA node only has 8).

**Recovery:**
```bash
# Check NUMA topology on the node
oc debug node/<node> -- chroot /host lscpu | grep -i numa

# Option 1: Reduce the Pod's CPU request to fit one NUMA node
# Option 2: Change the topology policy to 'restricted' or 'best-effort'
# Edit the PerformanceProfile:
#   spec.numa.topologyPolicy: restricted

# Option 3: Use a node with more CPUs per NUMA node
```

### PerformanceProfile Degraded

**Symptom:** `oc get performanceprofile low-latency` shows degraded conditions.

**Cause:** Conflicting KubeletConfigs, invalid CPU sets, or MachineConfig conflicts.

**Recovery:**
```bash
# Check detailed conditions
oc get performanceprofile low-latency -o json | \
  python3 -c "import sys,json; [print(c['type'],c['status'],c.get('message','')) for c in json.load(sys.stdin)['status']['conditions']]"

# Verify no conflicting KubeletConfigs
oc get kubeletconfig
# There should be at most ONE KubeletConfig per MachineConfigPool

# Check for overlapping CPU sets between reserved and isolated
# reserved and isolated MUST NOT overlap and MUST cover all CPUs
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Node tuning | Manual sysctl, TuneD installation | Node Tuning Operator + Tuned CRs (declarative, auto-applied) |
| Huge pages | Manual kernel args via GRUB | MachineConfig or PerformanceProfile CR |
| CPU Manager | Edit kubelet flags, restart kubelet | KubeletConfig CR or PerformanceProfile CR |
| NUMA awareness | Topology Manager kubelet flags | PerformanceProfile `spec.numa.topologyPolicy` |
| Real-time kernel | Manual kernel-rt installation | `spec.realTimeKernel.enabled: true` in PerformanceProfile |
| IRQ affinity | Manual irqbalance configuration | CRI-O annotations + PerformanceProfile |
| CPU isolation | Kernel args (isolcpus, nohz_full) | `spec.cpu.isolated` in PerformanceProfile (generates all args) |
| Drift detection | None (manual auditing) | NTO continuously reconciles, reapplies if settings change |
| Rollout control | Node-by-node manual process | MachineConfigPool `maxUnavailable` for controlled rollouts |
| Unified API | No single abstraction | PerformanceProfile CR generates Tuned, MC, KubeletConfig, RuntimeClass |
| Validation | Manual checks | Operator status conditions, automatic validation |
| RuntimeClass | Must create manually | PerformanceProfile auto-generates a RuntimeClass |

## Key Takeaways

- The **Node Tuning Operator** is pre-installed on every OpenShift cluster and provides declarative, Git-friendly kernel and system tuning through Tuned CRs — eliminating the need to SSH into nodes.
- **PerformanceProfile** is the single unified CR that generates all low-level resources (Tuned, MachineConfig, KubeletConfig, RuntimeClass) from one declaration — this is the recommended approach for production rather than configuring each component individually.
- CPU pinning requires **Guaranteed QoS** (requests == limits) with **integer CPU requests** and the CPU Manager set to `static` policy — fractional CPU requests will use the shared pool, not exclusive cores.
- **NUMA-aware scheduling** with `single-numa-node` topology policy ensures all resources (CPU, memory, devices) come from the same NUMA node, which is critical for latency-sensitive workloads but can cause scheduling failures if resources are fragmented.
- Low-latency tuning for telco/financial workloads combines the real-time kernel, CPU isolation (`nohz_full`, `isolcpus`), huge pages, NUMA pinning, IRQ affinity, and power management — PerformanceProfile orchestrates all of these, but always test in a staging environment first because these changes trigger node reboots and can cause outages if misconfigured.

## Cleanup

```bash
# Delete the demo project and all its resources
oc delete project perf-tuning-demo

# Delete the PerformanceProfile (triggers node rollback and reboot)
oc delete performanceprofile low-latency

# Delete the KubeletConfig
oc delete kubeletconfig cpumanager-enabled

# Remove the custom kubelet label from the MCP
oc label mcp worker-perf custom-kubelet-

# Delete the MachineConfig (triggers node reboot)
oc delete mc 50-hugepages

# Delete the custom Tuned profile
oc delete tuned db-optimized -n openshift-cluster-node-tuning-operator

# Delete the MachineConfigPool (if created for this lesson)
oc delete mcp worker-perf

# Remove the node label (if applied)
# oc label node <worker-node> node-role.kubernetes.io/worker-perf-

# Verify all resources are cleaned up
oc get performanceprofile
oc get tuned -n openshift-cluster-node-tuning-operator
oc get kubeletconfig
oc get mc | grep hugepages
oc get mcp
```

> **Warning:** Deleting the PerformanceProfile and MachineConfigs will trigger node reboots as nodes roll back to their default configuration. Plan accordingly.

## Next Steps

In **L3-M3.2 — Troubleshooting Methodology**, you will learn systematic approaches to diagnosing cluster and application issues, including `must-gather`, `oc adm inspect`, and sosreport. The performance tuning knowledge from this lesson will be directly relevant when troubleshooting performance degradation, scheduling failures, and OOM kills in production clusters.
