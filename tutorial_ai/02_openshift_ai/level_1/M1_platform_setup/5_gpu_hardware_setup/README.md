# L1-M1.5 -- GPU and Hardware Setup

**Level:** Foundations
**Duration:** 30 min

## Overview

GPU acceleration is essential for model serving, fine-tuning, and training workloads on OpenShift AI. This lesson walks through the operator stack that makes GPUs available to your AI workloads -- from hardware detection through driver installation to the Hardware Profile abstraction that lets users select GPU configurations from a dropdown instead of hand-writing resource requests in pod specs.

## Prerequisites

- Completed: [L1-M1.2 -- Installing OpenShift AI](../2_installing_openshift_ai/)
- OpenShift cluster with at least one GPU node (bare metal or cloud instances with GPUs)
- `cluster-admin` access (GPU operators require cluster-level privileges)

## K8s Context

On vanilla Kubernetes, making GPUs available to workloads is a multi-step manual process: install Node Feature Discovery to detect hardware, install the NVIDIA GPU Operator (or manually deploy device plugin daemonsets, driver containers, and monitoring exporters), then reference `nvidia.com/gpu` in every pod spec that needs GPU access. There is no concept of a reusable "hardware preset" -- every pod spec must explicitly declare its GPU resource requests, node selectors, and tolerations. GPU sharing (MIG or time-slicing) requires manual device plugin configuration.

OpenShift AI keeps the same GPU operator stack (it works identically on K8s and OpenShift) but adds Hardware Profiles -- reusable resource presets that abstract GPU configuration into a dropdown selection in the dashboard.

## Concepts

### The GPU Operator Stack

Two operators work together to make GPUs available on OpenShift:

1. **Node Feature Discovery (NFD)** -- Scans each node's hardware and labels it with detected features (GPU model, CPU instruction sets, PCI devices). NFD does not install drivers or manage devices -- it only labels nodes. Without NFD, the GPU Operator cannot identify which nodes have GPUs.

2. **NVIDIA GPU Operator** -- Consumes NFD's labels to identify GPU nodes, then deploys a stack of components as DaemonSets:
   - **GPU driver containers** -- compile and load the NVIDIA kernel driver on each GPU node
   - **Container toolkit** -- configures the container runtime to expose GPUs inside containers
   - **Device plugin** -- registers `nvidia.com/gpu` as a schedulable resource with the kubelet
   - **DCGM exporter** -- exposes GPU metrics (utilization, temperature, memory) to Prometheus
   - **GPU Feature Discovery** -- adds fine-grained GPU labels (model, memory, driver version)

```
NFD detects hardware --> GPU Operator deploys drivers + device plugin --> Pods can request nvidia.com/gpu
```

### Hardware Profiles

Hardware Profiles are an OpenShift AI concept (CRD: `infrastructure.opendatahub.io/v1`) that bundle GPU resource specifications into reusable presets. They replace the older Accelerator Profiles, which were deprecated in OpenShift AI 3.0.

A Hardware Profile defines:
- **Resource identifiers** -- what resource to request (e.g., `nvidia.com/gpu`) and how many
- **Node selectors** -- which nodes can run this workload (e.g., only T4 nodes)
- **Tolerations** -- tolerate GPU taints so the pod can schedule on tainted GPU nodes

When users create workbenches or deploy models through the dashboard, they select a Hardware Profile from a dropdown instead of manually specifying resources. This provides:
- Consistency across the team (everyone uses the same resource configuration)
- Guardrails (min/max GPU counts prevent over-allocation)
- Simplicity (users do not need to know the exact resource names or node labels)

Predefined profiles typically include CPU-only options ("Small", "Medium", "Large") alongside GPU profiles for each available GPU type.

### GPU Sharing Strategies

A single physical GPU can be shared between multiple workloads using two approaches:

**MIG (Multi-Instance GPU)** -- Available on NVIDIA A100, A30, and H100 GPUs only. MIG partitions one physical GPU into up to seven isolated instances, each with dedicated compute cores and memory. Workloads in different MIG slices cannot see or affect each other. The GPU Operator manages MIG configuration through the `ClusterPolicy` CR.

**Time-slicing** -- Available on any NVIDIA GPU. Multiple pods share the GPU through rapid context switching, similar to how a CPU time-shares between processes. There is no memory isolation -- workloads can interfere with each other if they exceed memory expectations. Time-slicing is configured through the device plugin ConfigMap.

| Feature | MIG | Time-slicing |
|---------|-----|-------------|
| GPU support | A100, A30, H100 only | Any NVIDIA GPU |
| Memory isolation | Yes (hardware-enforced) | No |
| Compute isolation | Yes | No (context switching) |
| Max partitions | Up to 7 per GPU | Configurable (typically 4-16) |
| Use case | Production multi-tenant | Development, light inference |

## Step-by-Step

### Step 1: Install the Node Feature Discovery Operator

NFD must be installed before the GPU Operator. Install it from OperatorHub.

**Via CLI:**

```bash
# Create the NFD operator namespace and subscription
oc apply -f - <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: openshift-nfd
---
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: openshift-nfd
  namespace: openshift-nfd
spec:
  targetNamespaces:
    - openshift-nfd
---
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: nfd
  namespace: openshift-nfd
spec:
  channel: stable
  name: nfd
  source: redhat-operators
  sourceNamespace: openshift-marketplace
EOF
```

Wait for the operator pod to be ready:

```bash
oc get pods -n openshift-nfd -w
```

Expected output (wait until STATUS is `Running`):

```
NAME                                      READY   STATUS    RESTARTS   AGE
nfd-controller-manager-7b4d5c8f9-x2k4z   2/2     Running   0          45s
```

**Via Web Console:**
1. Navigate to **Operators > OperatorHub**
2. Search for "Node Feature Discovery"
3. Select the Red Hat operator (not the community version)
4. Click **Install**, accept defaults, click **Install**

### Step 2: Create the NodeFeatureDiscovery CR

The operator is installed, but NFD is not scanning nodes yet. You need to create a `NodeFeatureDiscovery` custom resource to start detection.

```bash
oc apply -f - <<EOF
apiVersion: nfd.openshift.io/v1
kind: NodeFeatureDiscovery
metadata:
  name: nfd-instance
  namespace: openshift-nfd
spec:
  operand:
    image: registry.redhat.io/openshift4/ose-node-feature-discovery-rhel9:v4.17
    servicePort: 12000
  workerConfig:
    configData: |
      sources:
        pci:
          deviceClassWhitelist:
            - "0300"
            - "0302"
          deviceLabelFields:
            - vendor
EOF
```

PCI class `0300` is "VGA compatible controller" and `0302` is "3D controller" -- these cover NVIDIA GPUs. After a minute, verify that NFD has labeled your GPU nodes:

```bash
oc get nodes -l feature.node.kubernetes.io/pci-10de.present=true
```

The label `pci-10de` is the PCI vendor ID for NVIDIA. If you see your GPU nodes listed, NFD is working.

### Step 3: Install the NVIDIA GPU Operator

**Via CLI:**

```bash
# Create the GPU operator namespace and subscription
oc apply -f - <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: nvidia-gpu-operator
---
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: nvidia-gpu-operator
  namespace: nvidia-gpu-operator
spec:
  targetNamespaces:
    - nvidia-gpu-operator
---
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: gpu-operator-certified
  namespace: nvidia-gpu-operator
spec:
  channel: v24.9
  name: gpu-operator-certified
  source: certified-operators
  sourceNamespace: openshift-marketplace
EOF
```

**Via Web Console:**
1. Navigate to **Operators > OperatorHub**
2. Search for "NVIDIA GPU Operator"
3. Select the **certified** operator (from "Certified Operators" catalog)
4. Click **Install**, accept defaults, click **Install**

Wait for the operator to be ready:

```bash
oc get pods -n nvidia-gpu-operator -l app=gpu-operator
```

### Step 4: Create the ClusterPolicy CR

The GPU Operator requires a `ClusterPolicy` CR to begin deploying its components (drivers, device plugin, monitoring) onto GPU nodes.

```bash
oc apply -f - <<EOF
apiVersion: nvidia.com/v1
kind: ClusterPolicy
metadata:
  name: gpu-cluster-policy
spec:
  operator:
    defaultRuntime: crio
  driver:
    enabled: true
  toolkit:
    enabled: true
  devicePlugin:
    enabled: true
  dcgmExporter:
    enabled: true
  gfd:
    enabled: true
EOF
```

This triggers the operator to deploy DaemonSets on every GPU node. The process takes several minutes because the driver container must compile the NVIDIA kernel module. Monitor progress:

```bash
oc get pods -n nvidia-gpu-operator -w
```

Wait until all pods show `Running` or `Completed`. You will see pods for each component (driver, toolkit, device-plugin, dcgm-exporter, gfd) on each GPU node.

### Step 5: Verify GPU Node Detection

Once the GPU Operator is fully deployed, verify that GPUs are visible to the cluster.

Check for GPU node labels:

```bash
oc get nodes -l nvidia.com/gpu.present=true
```

Expected output:

```
NAME           STATUS   ROLES    AGE   VERSION
gpu-worker-0   Ready    worker   2d    v1.28.6+k8s
gpu-worker-1   Ready    worker   2d    v1.28.6+k8s
```

Check detailed GPU information:

```bash
oc get nodes -l nvidia.com/gpu.present=true -o json | \
  jq '.items[] | {name: .metadata.name, gpu_model: .metadata.labels["nvidia.com/gpu.product"], gpu_count: .status.allocatable["nvidia.com/gpu"]}'
```

Expected output (varies by hardware):

```json
{
  "name": "gpu-worker-0",
  "gpu_model": "Tesla-T4",
  "gpu_count": "1"
}
```

Run `nvidia-smi` on a GPU node to verify the driver is loaded:

```bash
# Replace <gpu-node-name> with an actual GPU node name from the output above
oc debug node/<gpu-node-name> -- chroot /host nvidia-smi
```

Expected output (abbreviated):

```
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 550.127.05             Driver Version: 550.127.05     CUDA Version: 12.4     |
|   GPU  Name          Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC      |
|   0    Tesla T4             On      | 00000000:00:1E.0  Off |                    0      |
+-----------------------------------------------------------------------------------------+
| Processes:                                                                               |
|  No running processes found                                                              |
+-----------------------------------------------------------------------------------------+
```

### Step 6: Create a Hardware Profile

Now that GPUs are available, create a Hardware Profile so users can select GPU configurations from the OpenShift AI dashboard.

Apply the Hardware Profile manifest:

```bash
oc apply -f manifests/hardware-profile.yaml
```

The manifest creates a Hardware Profile named `gpu-t4` that requests a single NVIDIA T4 GPU. See `manifests/hardware-profile.yaml` for the full YAML with explanations of each field.

Verify the Hardware Profile was created:

```bash
oc get hardwareprofile -n redhat-ods-applications
```

Expected output:

```
NAME     DISPLAY NAME      ENABLED   AGE
gpu-t4   NVIDIA T4 GPU     true      5s
```

### Step 7: Verify Hardware Profile in the Dashboard

1. Open the OpenShift AI dashboard
2. Navigate to **Settings > Hardware profiles**
3. Confirm the "NVIDIA T4 GPU" profile appears in the list and shows as enabled
4. Create a new workbench (or navigate to the workbench creation form) -- the Hardware Profile should appear in the "Hardware profile" dropdown

### Step 8: (Optional) Configure GPU Time-Slicing

If you have limited GPUs and want to share them across multiple workloads during development, configure time-slicing. This allows multiple pods to share a single GPU at the cost of memory isolation.

Create a ConfigMap for the device plugin:

```bash
oc apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: time-slicing-config
  namespace: nvidia-gpu-operator
data:
  t4-timeslice: |
    version: v1
    flags:
      migStrategy: none
    sharing:
      timeSlicing:
        renameByDefault: false
        failRequestsGreaterThanOne: false
        resources:
          - name: nvidia.com/gpu
            replicas: 4
EOF
```

Then patch the ClusterPolicy to reference this ConfigMap:

```bash
oc patch clusterpolicy gpu-cluster-policy -n nvidia-gpu-operator --type merge -p '{
  "spec": {
    "devicePlugin": {
      "config": {
        "name": "time-slicing-config",
        "default": "t4-timeslice"
      }
    }
  }
}'
```

After a minute, verify the allocatable GPU count has multiplied:

```bash
oc get node <gpu-node-name> -o json | jq '.status.allocatable["nvidia.com/gpu"]'
```

With `replicas: 4`, a node with 1 physical GPU will now show `"4"` allocatable GPUs.

**Warning:** Time-slicing does not provide memory isolation. If one pod uses more GPU memory than expected, other pods sharing the same GPU may fail with out-of-memory errors. Use this for development only.

## Verification

Run these checks to confirm everything is working:

```bash
# 1. NFD is running and detecting GPU nodes
oc get pods -n openshift-nfd | grep nfd-worker
oc get nodes -l feature.node.kubernetes.io/pci-10de.present=true

# 2. GPU Operator pods are all running
oc get pods -n nvidia-gpu-operator

# 3. GPUs are allocatable
oc get nodes -l nvidia.com/gpu.present=true -o json | \
  jq '.items[] | {name: .metadata.name, gpu: .status.allocatable["nvidia.com/gpu"]}'

# 4. nvidia-smi works on GPU nodes
oc debug node/<gpu-node-name> -- chroot /host nvidia-smi

# 5. Hardware Profile exists
oc get hardwareprofile -n redhat-ods-applications gpu-t4

# 6. GPU metrics are being exported (DCGM exporter)
oc get pods -n nvidia-gpu-operator -l app=nvidia-dcgm-exporter
```

## K8s vs OpenShift AI Comparison

| Aspect | Kubernetes | OpenShift AI |
|--------|-----------|--------------|
| GPU detection | Install NFD manually via Helm | NFD operator from OperatorHub |
| GPU drivers | Install GPU Operator manually via Helm | GPU Operator from OperatorHub (certified) |
| GPU allocation | Specify `nvidia.com/gpu` in every pod spec | Select Hardware Profile from dashboard dropdown |
| Resource presets | No built-in concept | Hardware Profiles (reusable, team-wide presets) |
| GPU sharing (MIG) | Configure MIG manually via device plugin | GPU Operator manages MIG through ClusterPolicy |
| GPU sharing (time-slice) | Configure device plugin ConfigMap | GPU Operator manages time-slicing config |
| GPU monitoring | Install DCGM exporter manually | Included automatically with GPU Operator |
| Profile management | N/A -- no abstraction layer | Dashboard UI for creating/editing/disabling profiles |

## Key Takeaways

- NFD + NVIDIA GPU Operator are prerequisites for GPU workloads on OpenShift -- install NFD first, then the GPU Operator
- The GPU Operator deploys drivers, device plugin, toolkit, and monitoring as DaemonSets on GPU nodes
- Hardware Profiles abstract GPU resource configuration into reusable presets selected from the dashboard
- Hardware Profiles replace the older Accelerator Profiles (deprecated in OpenShift AI 3.0)
- MIG provides hardware-enforced memory isolation but only works on A100/A30/H100 GPUs
- Time-slicing works on any GPU but offers no memory isolation -- use it for development, not production
- The GPU operator stack works identically on vanilla K8s and OpenShift; Hardware Profiles are the OpenShift AI-specific addition

## Cleanup

```bash
# Remove the Hardware Profile
oc delete hardwareprofile gpu-t4 -n redhat-ods-applications

# Remove time-slicing config (if created)
oc delete configmap time-slicing-config -n nvidia-gpu-operator

# Note: Do NOT remove the GPU Operator or NFD unless you are tearing down the cluster.
# Other workloads and lessons depend on GPU availability.
```

## Next Steps

With GPU hardware detected and Hardware Profiles configured, your platform is ready for GPU-accelerated workloads. In the next lesson, [L1-M1.6 -- GenAI Playground](../6_genai_playground/), you will explore OpenShift AI's built-in interface for interactive prompt testing and model comparison -- no code required.
