# L3-M1.3 — Node Management

**Level:** Expert
**Duration:** 45 min

## Overview

In Kubernetes, you manage nodes manually or rely on cloud-provider autoscalers that sit outside the cluster API. OpenShift introduces the **Machine API** -- a declarative, in-cluster framework for provisioning, configuring, and scaling nodes as first-class Kubernetes resources. This lesson covers MachineSets for declarative node scaling, MachineConfigs and MachineConfigPools for node-level OS configuration, infrastructure node separation, and taints/tolerations at production scale.

You will learn how to add and remove worker nodes declaratively, carve out dedicated infrastructure nodes for platform workloads, and apply OS-level configuration changes across node pools without SSH -- all through the Kubernetes API.

## Prerequisites

- Completed: L3-M1.2 (Cluster Upgrades & Lifecycle)
- OpenShift 4.x cluster (IPI-provisioned recommended; CRC for reading along, but Machine API is limited on CRC)
- `cluster-admin` access
- Familiarity with OpenShift architecture (L1-M1.1) and RBAC (L1-M2.3)
- Understanding of Operators and CRDs (L2-M2.1)

## K8s Context

In vanilla Kubernetes, nodes are either manually joined to the cluster (`kubeadm join`) or managed by a cloud-provider Cluster Autoscaler. There is no in-cluster API object that represents "I want 3 worker nodes of type m5.xlarge." Node configuration is handled externally through Ansible, Puppet, cloud-init scripts, or manual SSH sessions. When you need to change a kernel parameter or add a systemd unit, you configure it outside Kubernetes and hope every node stays consistent.

Kubernetes has the concept of taints and tolerations for scheduling control, and labels for node affinity -- but there is no standard mechanism for declaring groups of nodes with shared configuration and managing their lifecycle declaratively.

## Concepts

### Machine API Architecture

OpenShift introduces a layered abstraction for node lifecycle management:

```
+------------------------------------------------------------------+
|                     Cluster Administrator                         |
+------------------------------------------------------------------+
          |                    |                      |
          v                    v                      v
  +---------------+   +------------------+   +------------------+
  |   MachineSet  |   |  MachineConfig   |   | MachineAutoscaler|
  | (desired count|   | (OS-level config)|   | (scaling rules)  |
  |  + template)  |   +------------------+   +------------------+
  +---------------+           |
          |                   v
          v           +------------------+
  +---------------+   | MachineConfig    |
  |   Machine     |   | Pool (MCP)       |
  | (1:1 with a   |   | (groups nodes    |
  |  cloud VM)    |   |  for config)     |
  +---------------+   +------------------+
          |                   |
          v                   v
  +---------------+   +------------------+
  |     Node      |   |  Machine Config  |
  | (K8s Node     |   |  Daemon (MCD)    |
  |  object)      |   | (applies config  |
  +---------------+   |  on each node)   |
                      +------------------+
```

**Key resources:**

| Resource | API Group | Purpose |
|----------|-----------|---------|
| `Machine` | `machine.openshift.io/v1beta1` | Represents a single VM/bare-metal host. Created by MachineSets. |
| `MachineSet` | `machine.openshift.io/v1beta1` | Declares desired count and template for a group of Machines. Analogous to ReplicaSet for Pods. |
| `MachineConfigPool` | `machineconfiguration.openshift.io/v1` | Groups nodes by label for configuration management. Default pools: `master`, `worker`. |
| `MachineConfig` | `machineconfiguration.openshift.io/v1` | Declares OS-level configuration (files, systemd units, kernel args) applied to nodes in an MCP. |
| `MachineAutoscaler` | `autoscaling.openshift.io/v1beta1` | Sets min/max replica bounds for a MachineSet, used by the Cluster Autoscaler. |
| `ClusterAutoscaler` | `autoscaling.openshift.io/v1` | Cluster-wide autoscaling policy (max nodes, scale-down behavior). |

### MachineSets vs. Manual Node Management

A MachineSet is the node equivalent of a ReplicaSet:

- You declare the desired number of replicas (nodes) and a Machine template (instance type, AMI, network, storage).
- The Machine API controller creates Machine objects, which in turn provision actual VMs through the cloud provider API.
- When you scale down, it cordons, drains, and deletes nodes cleanly.
- Each availability zone typically gets its own MachineSet for fault tolerance.

### MachineConfigs and MachineConfigPools

RHCOS (Red Hat CoreOS) nodes are immutable by design. You do not SSH in and edit files. Instead:

1. You write a **MachineConfig** (MC) declaring the desired state: files to create, systemd units to add/modify, kernel arguments, etc.
2. The MC is associated with a **MachineConfigPool** (MCP) via label selectors.
3. The **Machine Config Operator (MCO)** renders a combined configuration for each pool and the **Machine Config Daemon (MCD)** on each node applies it -- rebooting the node when necessary.

This is the OpenShift equivalent of running Ansible across your fleet, but fully declarative and integrated into the cluster API.

### Infrastructure Nodes

OpenShift recommends separating platform infrastructure workloads (router/ingress, internal registry, monitoring stack, logging) from application workloads. This is done by:

1. Creating an "infra" MachineSet with a specific label (`node-role.kubernetes.io/infra: ""`).
2. Creating an "infra" MachineConfigPool (optional, for infra-specific OS config).
3. Configuring platform operators (ingress, monitoring, registry) to target infra nodes via `nodeSelector` and `tolerations`.

Benefits: application workloads do not compete with platform services for resources, and in some Red Hat subscription models, infra nodes do not count toward worker node entitlements.

### Taints and Tolerations at Scale

While taints/tolerations work identically to Kubernetes, OpenShift uses them systematically:

- **Master nodes** are tainted `node-role.kubernetes.io/master:NoSchedule` by default -- only control plane pods tolerate this.
- **Infra nodes** should be tainted to repel application workloads.
- **Specialized nodes** (GPU, high-memory) use taints to ensure only matching workloads land on them.
- The Machine API lets you bake taints into MachineSet templates so every new node in the set is tainted automatically.

### Failure Modes and Recovery

| Failure | Symptom | Recovery |
|---------|---------|----------|
| MachineConfig renders invalid ignition | MCD reports `Degraded`, nodes stop updating | Fix or delete the bad MC; MCO will re-render |
| MachineConfigPool stuck `Updating` | Nodes do not complete reboot cycle | Check `oc get mcp` for degraded nodes; `oc debug node/` to inspect |
| MachineSet cannot provision VM | Machine stuck in `Provisioning` | Check Machine `.status.errorMessage`; verify cloud credentials and quotas |
| Node drain blocked | Machine deletion hangs | Check PodDisruptionBudgets; force drain with `oc adm drain --force --delete-emptydir-data` |
| MCO Degraded after bad kernel arg | Pool shows `Degraded=True` | Remove the offending MachineConfig; MCO will re-render and reboot |
| Infra node goes down | Router/monitoring pods reschedule slowly | Ensure infra MachineSet has 3+ replicas across AZs for HA |

## Step-by-Step

### Step 1: Explore Existing Machine API Resources

First, examine the current Machine API state of your cluster.

```bash
# List all MachineSets (they live in openshift-machine-api namespace)
oc get machinesets -n openshift-machine-api

# List all Machines and their status
oc get machines -n openshift-machine-api -o wide

# View the default MachineConfigPools
oc get machineconfigpools

# See which MachineConfigs are rendered for each pool
oc get machineconfigs --sort-by=.metadata.name
```

Expected output for `oc get mcp`:

```
NAME     CONFIG                                             UPDATED   UPDATING   DEGRADED   MACHINECOUNT   READYCOUNT   UPDATEDCOUNT   DEGRADEDCOUNT   AGE
master   rendered-master-abc123...                          True      False      False      3              3            3              0               7d
worker   rendered-worker-def456...                          True      False      False      3              3            3              0               7d
```

Examine a MachineSet in detail to understand the template:

```bash
# Pick any worker MachineSet
MACHINESET=$(oc get machinesets -n openshift-machine-api -o jsonpath='{.items[0].metadata.name}')
oc get machineset $MACHINESET -n openshift-machine-api -o yaml
```

Key fields to note in the output:
- `spec.replicas` -- desired node count
- `spec.selector` -- how Machines are selected
- `spec.template.spec.providerSpec` -- cloud-specific VM configuration (instance type, AMI, subnet, etc.)

### Step 2: Scale Worker Nodes with a MachineSet

Scale an existing MachineSet to add a worker node:

```bash
# Check current replica count
oc get machineset $MACHINESET -n openshift-machine-api

# Scale up by 1
oc scale machineset $MACHINESET -n openshift-machine-api --replicas=4

# Watch the new Machine being provisioned
oc get machines -n openshift-machine-api -w
```

The lifecycle of a new Machine:
1. `Provisioning` -- VM is being created in the cloud provider
2. `Provisioned` -- VM exists but is not yet a cluster node
3. `Running` -- VM has joined the cluster as a Node

```bash
# Verify the new node appears
oc get nodes -l node-role.kubernetes.io/worker

# Scale back down (OpenShift will cordon, drain, then delete)
oc scale machineset $MACHINESET -n openshift-machine-api --replicas=3
```

### Step 3: Create a New MachineSet for Infrastructure Nodes

Apply the infrastructure MachineSet. You must customize the `providerSpec` for your cloud provider -- the manifest below shows the structural template with an AWS example.

```bash
# First, extract provider details from an existing MachineSet
oc get machineset $MACHINESET -n openshift-machine-api -o json | jq '.spec.template.spec.providerSpec'
```

Apply the infra MachineSet manifest (customize for your environment):

```bash
oc apply -f manifests/machineset-infra.yaml
```

```yaml
# manifests/machineset-infra.yaml -- see the manifests directory for the full file
apiVersion: machine.openshift.io/v1beta1
kind: MachineSet
metadata:
  name: <cluster-id>-infra-<zone>
  namespace: openshift-machine-api
  labels:
    machine.openshift.io/cluster-api-cluster: <cluster-id>
spec:
  replicas: 3
  selector:
    matchLabels:
      machine.openshift.io/cluster-api-cluster: <cluster-id>
      machine.openshift.io/cluster-api-machineset: <cluster-id>-infra-<zone>
  template:
    metadata:
      labels:
        machine.openshift.io/cluster-api-cluster: <cluster-id>
        machine.openshift.io/cluster-api-machineset: <cluster-id>-infra-<zone>
        machine.openshift.io/cluster-api-machine-role: infra
        machine.openshift.io/cluster-api-machine-type: infra
    spec:
      metadata:
        labels:
          node-role.kubernetes.io/infra: ""
      taints:
        - key: node-role.kubernetes.io/infra
          effect: NoSchedule
      providerSpec:
        # ... cloud-provider specific configuration
```

```bash
# Watch infra machines provision
oc get machines -n openshift-machine-api -l machine.openshift.io/cluster-api-machine-role=infra -w

# Verify infra nodes appear with the correct labels and taints
oc get nodes -l node-role.kubernetes.io/infra
oc describe node <infra-node-name> | grep -A5 Taints
```

### Step 4: Create an Infrastructure MachineConfigPool

Create a dedicated MCP for infra nodes so you can apply infra-specific OS configuration independently of workers.

```bash
oc apply -f manifests/mcp-infra.yaml
```

```yaml
# manifests/mcp-infra.yaml
apiVersion: machineconfiguration.openshift.io/v1
kind: MachineConfigPool
metadata:
  name: infra
  labels:
    app: node-management
    tutorial-level: "3"
    tutorial-module: "M1"
spec:
  machineConfigSelector:
    matchExpressions:
      - key: machineconfiguration.openshift.io/role
        operator: In
        values:
          - worker
          - infra
  nodeSelector:
    matchLabels:
      node-role.kubernetes.io/infra: ""
```

The `machineConfigSelector` includes both `worker` and `infra` roles. This means infra nodes inherit all worker MachineConfigs plus any infra-specific ones. This is the standard pattern -- infra nodes are a superset of worker configuration.

```bash
# Verify the new pool
oc get mcp

# Expected output shows three pools: master, worker, infra
```

### Step 5: Apply a MachineConfig for Kernel Parameters

Apply a MachineConfig that tunes kernel parameters for infra nodes handling high-traffic routing workloads:

```bash
oc apply -f manifests/machineconfig-kernel-tuning.yaml
```

```yaml
# manifests/machineconfig-kernel-tuning.yaml
apiVersion: machineconfiguration.openshift.io/v1
kind: MachineConfig
metadata:
  name: 99-infra-kernel-tuning
  labels:
    machineconfiguration.openshift.io/role: infra
    app: node-management
    tutorial-level: "3"
    tutorial-module: "M1"
spec:
  kernelArguments:
    - "net.core.somaxconn=32768"
    - "net.ipv4.tcp_max_syn_backlog=32768"
```

Watch the MCO roll out the change:

```bash
# The infra MCP will begin updating nodes one at a time
oc get mcp infra -w

# Check which nodes are being updated
oc get nodes -l node-role.kubernetes.io/infra -o custom-columns=NAME:.metadata.name,STATUS:.status.conditions[-1].type,READY:.status.conditions[-1].status
```

**Important:** MachineConfig changes trigger a node reboot. The MCO updates one node at a time by default (configurable via `maxUnavailable` on the MCP). Plan MachineConfig changes during maintenance windows in production.

### Step 6: Apply a MachineConfig to Add a Custom Systemd Unit

Create a MachineConfig that adds a custom systemd unit for log rotation on worker nodes:

```bash
oc apply -f manifests/machineconfig-logrotate.yaml
```

The file content is base64-encoded in the Ignition format that MachineConfig uses (see the manifest in the manifests directory for the full specification).

```bash
# Watch the worker pool update
oc get mcp worker -w

# After the rollout completes, verify on a node
oc debug node/<worker-node-name> -- chroot /host systemctl status custom-logrotate.timer
```

### Step 7: Move Infrastructure Workloads to Infra Nodes

Configure the router (Ingress Controller), internal registry, and monitoring stack to run on infra nodes.

**Ingress Controller (Router):**

```bash
oc apply -f manifests/ingresscontroller-infra.yaml
```

```yaml
# manifests/ingresscontroller-infra.yaml
apiVersion: operator.openshift.io/v1
kind: IngressController
metadata:
  name: default
  namespace: openshift-ingress-operator
spec:
  replicas: 3
  nodePlacement:
    nodeSelector:
      matchLabels:
        node-role.kubernetes.io/infra: ""
    tolerations:
      - key: node-role.kubernetes.io/infra
        effect: NoSchedule
```

**Internal Registry:**

```bash
oc apply -f manifests/registry-infra.yaml
```

**Monitoring Stack:**

```bash
oc apply -f manifests/monitoring-infra.yaml
```

```bash
# Verify router pods moved to infra nodes
oc get pods -n openshift-ingress -o wide

# Verify registry pods moved
oc get pods -n openshift-image-registry -o wide

# Verify monitoring pods moved
oc get pods -n openshift-monitoring -o wide | grep -E 'prometheus|alertmanager|grafana'
```

### Step 8: Configure MachineSet Autoscaling

Set up the Cluster Autoscaler and MachineAutoscaler to automatically scale worker nodes based on pending pod demand.

```bash
oc apply -f manifests/clusterautoscaler.yaml
oc apply -f manifests/machineautoscaler-worker.yaml
```

```bash
# Verify autoscaler is running
oc get clusterautoscaler default -o yaml
oc get machineautoscaler -n openshift-machine-api

# Test by creating pods that exceed current capacity
oc apply -f manifests/autoscale-test-deployment.yaml

# Watch for new machines being provisioned
oc get machines -n openshift-machine-api -w
```

### Step 9: Cordon, Drain, and Remove a Node

Practice the controlled removal of a node:

```bash
# Mark the node as unschedulable
oc adm cordon <node-name>

# Drain all workloads (respecting PDBs, deleting emptyDir data)
oc adm drain <node-name> \
  --ignore-daemonsets \
  --delete-emptydir-data \
  --timeout=120s

# Verify no application pods remain
oc get pods --all-namespaces --field-selector spec.nodeName=<node-name>

# Delete the node object (if not managed by a MachineSet)
oc delete node <node-name>

# If managed by a MachineSet, scale down instead:
oc scale machineset <machineset-name> -n openshift-machine-api --replicas=<N-1>
```

### Step 10: Apply Taints and Tolerations at Scale via MachineSets

Demonstrate adding taints to a MachineSet template so all new nodes in the set are automatically tainted:

```bash
# Patch an existing MachineSet to add a taint
oc patch machineset $MACHINESET -n openshift-machine-api --type=merge -p '{
  "spec": {
    "template": {
      "spec": {
        "taints": [
          {
            "key": "workload-type",
            "value": "general",
            "effect": "PreferNoSchedule"
          }
        ]
      }
    }
  }
}'
```

**Note:** Patching a MachineSet template only affects *new* Machines. Existing nodes are not updated. To taint existing nodes:

```bash
# Taint existing nodes directly
oc adm taint nodes <node-name> workload-type=general:PreferNoSchedule
```

Apply the GPU node MachineSet manifest for a specialized taint example:

```bash
oc apply -f manifests/machineset-gpu.yaml
```

## Verification

Run these commands to verify the lesson completed successfully:

```bash
# 1. Verify MachineConfigPools are healthy (none Degraded)
oc get mcp
# Expected: All pools show UPDATED=True, UPDATING=False, DEGRADED=False

# 2. Verify infra nodes exist and are labeled correctly
oc get nodes -l node-role.kubernetes.io/infra --show-labels
# Expected: Infra nodes visible with correct labels

# 3. Verify infra node taints
oc get nodes -l node-role.kubernetes.io/infra -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.taints}{"\n"}{end}'
# Expected: Each infra node has node-role.kubernetes.io/infra:NoSchedule taint

# 4. Verify router pods run on infra nodes
oc get pods -n openshift-ingress -o wide
# Expected: Router pods scheduled on infra nodes

# 5. Verify MachineConfigs are applied
oc get machineconfig 99-infra-kernel-tuning
# Expected: MachineConfig exists

# 6. Verify autoscaler configuration
oc get clusterautoscaler default
oc get machineautoscaler -n openshift-machine-api
# Expected: Both resources exist and are configured

# 7. Check overall Machine API health
oc get machines -n openshift-machine-api -o custom-columns=NAME:.metadata.name,PHASE:.status.phase,NODE:.status.nodeRef.name
# Expected: All machines in Running phase with associated nodes
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Node provisioning | Manual (`kubeadm join`) or cloud-specific autoscaler | Machine API: MachineSet creates Machines declaratively |
| Node scaling | Cluster Autoscaler (external) | MachineAutoscaler + ClusterAutoscaler (in-cluster CRDs) |
| Node OS configuration | SSH + Ansible/Puppet/cloud-init | MachineConfig + MCO (declarative, API-driven, no SSH) |
| Node grouping | Labels only | MachineConfigPools (labels + config management) |
| Infrastructure separation | Manual node labels + taints | Dedicated infra MachineSets + operator nodePlacement |
| Configuration rollout | Manual, node-by-node | MCO handles rolling updates with configurable maxUnavailable |
| Node OS | Any Linux distribution | RHCOS (immutable, managed by MCO) |
| Kernel tuning | sysctl DaemonSets or manual | MachineConfig with kernelArguments |
| Node lifecycle | `kubectl drain` + manual delete | Machine API handles cordon/drain/delete automatically |
| Subscription impact | N/A | Infra nodes may not count toward subscription costs |

## Key Takeaways

- **MachineSets are ReplicaSets for nodes** -- they provide declarative, self-healing node pools. Scale nodes by changing a replica count, not by running provisioning scripts.
- **MachineConfigs replace SSH and configuration management tools** -- every OS-level change (files, systemd units, kernel parameters) flows through the MachineConfig Operator, ensuring consistency and auditability.
- **Infrastructure nodes are a production best practice** -- separating router, registry, and monitoring workloads from application nodes improves stability and may reduce subscription costs.
- **MachineConfig changes trigger rolling reboots** -- always plan MC changes carefully, test in a non-production MCP first, and apply during maintenance windows. A bad MachineConfig can render an entire node pool degraded.
- **Taints baked into MachineSet templates provide consistent node isolation** -- but remember that template changes only affect new Machines, not existing ones.

## Cleanup

```bash
# Remove the autoscale test deployment
oc delete -f manifests/autoscale-test-deployment.yaml --ignore-not-found

# Remove the autoscaler resources
oc delete -f manifests/machineautoscaler-worker.yaml --ignore-not-found
oc delete -f manifests/clusterautoscaler.yaml --ignore-not-found

# Remove the custom MachineConfigs (WARNING: triggers node reboots)
oc delete machineconfig 99-infra-kernel-tuning --ignore-not-found
oc delete machineconfig 99-worker-custom-logrotate --ignore-not-found

# Remove the infra MachineConfigPool
oc delete mcp infra --ignore-not-found

# Scale down / delete infra MachineSet (deletes infra nodes)
# Replace <cluster-id> and <zone> with your values
# oc delete machineset <cluster-id>-infra-<zone> -n openshift-machine-api

# Restore the default IngressController (remove nodeSelector/tolerations)
oc patch ingresscontroller default -n openshift-ingress-operator \
  --type=merge -p '{"spec": {"nodePlacement": null, "replicas": 2}}'

# Restore registry defaults
oc patch configs.imageregistry.operator.openshift.io/cluster \
  --type=merge -p '{"spec": {"nodeSelector": null, "tolerations": null}}'

# Restore monitoring defaults
oc delete configmap cluster-monitoring-config -n openshift-monitoring --ignore-not-found

# Verify all pools return to healthy state
oc get mcp
```

## Next Steps

In **L3-M1.4 -- etcd & Control Plane Operations**, you will learn how to back up and restore etcd, manage control plane certificates, and recover from master node failures -- critical skills for maintaining the foundation that the Machine API itself depends on.
