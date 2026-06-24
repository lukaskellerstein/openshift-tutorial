# L3-M1.2 — Cluster Upgrades & Lifecycle

**Level:** Expert
**Duration:** 45 min

## Overview

OpenShift treats cluster upgrades as a first-class, operator-managed operation -- a stark contrast to the manual, component-by-component upgrade process in vanilla Kubernetes. The Cluster Version Operator (CVO) orchestrates Over-The-Air (OTA) upgrades across the entire cluster: control plane components, node operating systems (RHCOS), and platform operators. In this lesson you will learn how to plan, execute, monitor, and troubleshoot production upgrades, including pre-flight health checks, channel selection strategies, and rollback considerations.

## Prerequisites

- Completed: L3-M1.1 (Installation Methods)
- Completed: L1-M1.1 (Architecture Overview) -- understanding of OpenShift control plane components
- Completed: L2-M2.1-2 (Operator Framework Concepts, Installing & Managing Operators) -- understanding of OLM and operator lifecycle
- OpenShift cluster running (CRC or production cluster; some commands require cluster-admin)
- Logged in as `kubeadmin` (cluster-admin privileges required for upgrades)
- `oc` CLI installed and on PATH
- `jq` installed for JSON processing

## K8s Context

In vanilla Kubernetes, upgrading a cluster is a multi-step, manual process:

1. You upgrade the control plane components one by one -- `kube-apiserver`, `kube-controller-manager`, `kube-scheduler`, `etcd` -- following a strict version skew policy.
2. You upgrade `kubelet` on each node individually (often via configuration management tools like Ansible).
3. You upgrade CNI plugins, CoreDNS, kube-proxy, and other add-ons separately.
4. You manage certificate rotation, API deprecations, and storage migrations yourself.
5. Rollback means restoring etcd snapshots and downgrading binaries -- a high-risk, manual operation.

Managed Kubernetes services (EKS, GKE, AKS) automate the control plane upgrade but still leave worker node upgrades to you (node pools, managed node groups, etc.).

OpenShift takes this further: the entire cluster -- control plane, workers, operators, and OS -- is managed as a single versioned unit.

## Concepts

### Cluster Version Operator (CVO)

The CVO is the heart of OpenShift's upgrade system. It:

- Manages the `ClusterVersion` custom resource, which declares the desired cluster version
- Reconciles all cluster operators to their target versions during an upgrade
- Applies manifests in a specific order to ensure safe transitions
- Reports progress and health through conditions on the `ClusterVersion` object

```
+-------------------------------------------------------------+
|                    OpenShift Cluster                         |
|                                                             |
|  +-------------------+    +-----------------------------+   |
|  | ClusterVersion CR |    | Cincinnati / OSUS           |   |
|  | (desired state)   |<---| (Update Graph Service)      |   |
|  +--------+----------+    +-----------------------------+   |
|           |                                                 |
|           v                                                 |
|  +-------------------+                                      |
|  | Cluster Version   |                                      |
|  | Operator (CVO)    |                                      |
|  +--------+----------+                                      |
|           |                                                 |
|           |  Reconciles in order:                           |
|           |                                                 |
|           +---> 1. etcd Operator                            |
|           +---> 2. kube-apiserver Operator                  |
|           +---> 3. kube-controller-manager Operator         |
|           +---> 4. kube-scheduler Operator                  |
|           +---> 5. OpenShift API Server Operator            |
|           +---> 6. ... (30+ cluster operators)              |
|           +---> 7. Machine Config Operator (MCO)            |
|                      |                                      |
|                      v                                      |
|              +-------+--------+                             |
|              | MachineConfig  |                              |
|              | Pool: master   |                              |
|              +-------+--------+                             |
|              | MachineConfig  |                              |
|              | Pool: worker   |                              |
|              +----------------+                             |
+-------------------------------------------------------------+
```

### Upgrade Channels

OpenShift uses upgrade channels to control which versions are available. Each channel represents a different risk/speed tradeoff:

| Channel | Purpose | Use Case |
|---------|---------|----------|
| `candidate-4.x` | Earliest access to new releases | Testing and development environments |
| `fast-4.x` | Release candidates promoted after initial validation | Non-production, early adopter environments |
| `stable-4.x` | Fully validated releases with proven field reliability | Production clusters |
| `eus-4.x` | Extended Update Support (even-numbered minor versions only: 4.12, 4.14, 4.16) | Long-lifecycle production with minimal upgrade frequency |

**EUS (Extended Update Support)** deserves special attention for production operations. EUS versions receive backported bug fixes and security patches for an extended period (18 months vs 12 months for standard releases). With EUS-to-EUS upgrades, you can skip odd-numbered minor versions entirely (e.g., 4.14 directly to 4.16), reducing upgrade frequency by half.

### Update Graph and Cincinnati

OpenShift does not allow arbitrary version jumps. The Cincinnati update service (or its on-premise equivalent, OpenShift Update Service / OSUS) maintains a directed graph of valid upgrade paths. The CVO queries this graph to determine:

- Which versions are reachable from the current version
- Whether conditional update risks apply (known issues with specific upgrade paths)
- Which versions have been pulled due to discovered regressions

```
Update Graph (simplified):

  4.14.10 ---> 4.14.12 ---> 4.14.15 ---> 4.14.18
                  |                          |
                  v                          v
               4.15.2  ---> 4.15.5  ---> 4.15.8
                                            |
                                            v
                                         4.16.0 ---> 4.16.3
                                            ^
                                            |
  4.14.18 ---------(EUS-to-EUS)-------------+
```

### Upgrade Order: Control Plane Then Workers

OpenShift upgrades follow a strict order:

1. **Control plane operators** update first (etcd, API server, controllers, scheduler)
2. **Platform operators** update next (ingress, monitoring, image registry, etc.)
3. **Worker nodes** update last via the Machine Config Operator (MCO)

Worker nodes are updated one at a time (or in configurable batches). For each node, the MCO:
1. Cordons the node (marks it unschedulable)
2. Drains workloads to other nodes
3. Applies the new MachineConfig (OS update, kubelet config, etc.)
4. Reboots the node into the new RHCOS version
5. Uncordons the node

This means your workloads must tolerate pod disruption. PodDisruptionBudgets (PDBs) are critical for production upgrades.

### Rollback Considerations

**Important: OpenShift does not support in-place downgrades.** Once a cluster is upgraded, the supported rollback path is:

- **Control plane:** Restore from an etcd backup taken before the upgrade (this is a full cluster restore, not a graceful downgrade).
- **Workers:** If workers have not yet been updated, you can pause the MachineConfigPool to prevent further worker updates while you assess issues.
- **Partial rollback:** You can pause worker node upgrades mid-flight if problems are detected, leaving already-upgraded workers in place while you investigate.

This is why pre-upgrade validation and canary strategies (upgrading non-production clusters first) are essential.

## Step-by-Step

### Step 1: Check Current Cluster Version and Status

Before any upgrade, understand your starting point.

```bash
# View the current cluster version
oc get clusterversion

# Get detailed version information
oc get clusterversion version -o json | jq '{
  version: .status.desired.version,
  channel: .spec.channel,
  clusterID: .spec.clusterID,
  conditions: [.status.conditions[] | {type, status, message}]
}'

# Check all cluster operator statuses
oc get clusteroperators

# Identify any degraded operators (these MUST be fixed before upgrading)
oc get clusteroperators -o json | jq -r '
  .items[] |
  select(.status.conditions[] |
    select(.type == "Degraded" and .status == "True")) |
  .metadata.name'
```

All operators should show `Available=True`, `Progressing=False`, `Degraded=False`. Any degraded operator will block or cause problems during an upgrade.

### Step 2: Run Pre-Upgrade Health Checks

Apply the pre-upgrade health check script and manifests to validate cluster readiness.

```bash
# Run the pre-upgrade health check script
chmod +x scripts/pre-upgrade-checks.sh
./scripts/pre-upgrade-checks.sh
```

The script checks:
- Cluster operator health
- Node readiness
- Certificate expiration
- etcd health
- PodDisruptionBudget coverage for critical workloads
- Available disk space on nodes
- Pending MachineConfig updates

You should also apply the PodDisruptionBudget manifest to protect critical workloads during the upgrade:

```bash
# Apply PDBs for critical workloads before upgrading
oc apply -f manifests/critical-pdb.yaml

# Verify PDBs are in place
oc get pdb -A
```

### Step 3: Review Upgrade Channel and Available Updates

```bash
# Check current channel
oc get clusterversion version -o jsonpath='{.spec.channel}{"\n"}'

# List available updates in the current channel
oc adm upgrade

# For more detail, including conditional update risks
oc adm upgrade --include-not-recommended
```

If you need to change channels (e.g., from `fast` to `stable`):

```bash
# Switch to the stable channel for your minor version
oc adm upgrade channel stable-4.16

# Verify the channel change
oc get clusterversion version -o jsonpath='{.spec.channel}{"\n"}'

# List updates again (available versions may change with the new channel)
oc adm upgrade
```

To apply the channel configuration declaratively:

```bash
# Apply channel configuration
oc apply -f manifests/cluster-version-channel.yaml
```

### Step 4: Create an etcd Backup Before Upgrading

Always take an etcd backup before a production upgrade. This is your only rollback path if the upgrade goes catastrophically wrong.

```bash
# Create a debug session on a control plane node
oc debug node/$(oc get nodes -l node-role.kubernetes.io/master -o jsonpath='{.items[0].metadata.name}')

# Inside the debug session:
chroot /host
/usr/local/bin/cluster-backup.sh /home/core/backup-pre-upgrade-$(date +%Y%m%d)
exit
exit

# Alternatively, use the backup script
chmod +x scripts/etcd-backup.sh
./scripts/etcd-backup.sh
```

For production environments, apply the automated etcd backup CronJob:

```bash
# Apply the etcd backup CronJob for recurring backups
oc apply -f manifests/etcd-backup-cronjob.yaml

# Verify the CronJob was created
oc get cronjob -n openshift-etcd
```

### Step 5: Initiate the Upgrade

**Option A: Upgrade to a specific version (recommended for production)**

```bash
# Upgrade to a specific version
oc adm upgrade --to=4.16.3

# For EUS-to-EUS upgrades, you may need intermediate steps
# The CVO will guide you through the required path
oc adm upgrade --to=4.16.0
```

**Option B: Upgrade to the latest available version**

```bash
# Upgrade to the latest in the current channel
oc adm upgrade --to-latest
```

**Option C: Apply upgrade configuration declaratively**

```bash
# Apply the upgrade configuration
oc apply -f manifests/cluster-version-upgrade.yaml
```

### Step 6: Monitor the Upgrade Progress

The upgrade will take 30-90 minutes depending on cluster size. Monitor it closely.

```bash
# Watch overall upgrade progress
oc adm upgrade

# Watch cluster operator updates in real time
watch 'oc get clusteroperators'

# Monitor the ClusterVersion conditions
oc get clusterversion version -o json | jq '.status.conditions[] | {type, status, lastTransitionTime, message}'

# Watch node updates (worker node rolling restarts happen last)
watch 'oc get nodes -o wide'

# Monitor MachineConfigPool progress
watch 'oc get mcp'

# Check for pods being drained and rescheduled
oc get events -A --sort-by=.lastTimestamp | grep -E "(Drain|Evict|Schedule)" | tail -20
```

Key things to watch during the upgrade:

1. **Control plane operators** update first -- watch for `Progressing=True` then `Available=True`
2. **MachineConfigPool `master`** updates next -- masters reboot one at a time
3. **MachineConfigPool `worker`** updates last -- workers reboot one at a time

### Step 7: Pause Worker Upgrades (If Issues Detected)

If you detect problems during the upgrade, you can pause worker node updates to prevent further disruption while you investigate.

```bash
# Pause the worker MachineConfigPool
oc patch mcp/worker --type merge --patch '{"spec":{"paused":true}}'

# Verify the pause
oc get mcp worker -o jsonpath='{.spec.paused}{"\n"}'

# Investigate the issue...
oc get clusteroperators | grep -v "True.*False.*False"
oc get events -A --sort-by=.lastTimestamp | tail -30

# Resume when ready
oc patch mcp/worker --type merge --patch '{"spec":{"paused":false}}'
```

You can also apply the pause declaratively:

```bash
oc apply -f manifests/mcp-worker-pause.yaml
```

### Step 8: Post-Upgrade Validation

After the upgrade completes, verify everything is healthy.

```bash
# Verify the new version
oc get clusterversion

# All operators should be Available and not Degraded
oc get clusteroperators
oc get clusteroperators -o json | jq -r '
  .items[] |
  [.metadata.name,
   (.status.conditions[] | select(.type=="Available") | .status),
   (.status.conditions[] | select(.type=="Progressing") | .status),
   (.status.conditions[] | select(.type=="Degraded") | .status)] |
  @tsv' | column -t

# All nodes should be Ready and running the new version
oc get nodes -o wide

# Verify MachineConfigPools are updated and not degraded
oc get mcp

# Check that all pods in openshift-* namespaces are running
oc get pods -A | grep -v Running | grep -v Completed | grep "openshift-"

# Run the post-upgrade validation script
chmod +x scripts/post-upgrade-validation.sh
./scripts/post-upgrade-validation.sh
```

## Verification

After completing the lesson, verify your understanding by confirming:

1. **Cluster version** shows the new version:
   ```bash
   oc get clusterversion version -o jsonpath='{.status.desired.version}{"\n"}'
   ```

2. **All cluster operators** are `Available=True`, `Progressing=False`, `Degraded=False`:
   ```bash
   oc get clusteroperators -o json | jq '[.items[] | {
     name: .metadata.name,
     available: (.status.conditions[] | select(.type=="Available") | .status),
     progressing: (.status.conditions[] | select(.type=="Progressing") | .status),
     degraded: (.status.conditions[] | select(.type=="Degraded") | .status)
   }]'
   ```

3. **All nodes** are Ready and running the expected OS/kubelet version:
   ```bash
   oc get nodes -o custom-columns=NAME:.metadata.name,STATUS:.status.conditions[-1].type,VERSION:.status.nodeInfo.kubeletVersion,OS:.status.nodeInfo.osImage
   ```

4. **MachineConfigPools** show `UPDATED=True` and `DEGRADED=False`:
   ```bash
   oc get mcp
   ```

5. **Workloads** are running normally:
   ```bash
   oc get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded | grep -v NAMESPACE
   ```

## Failure Modes and Recovery

### Degraded Cluster Operator During Upgrade

**Symptom:** Upgrade stalls; `oc adm upgrade` shows "Unable to apply" or a specific operator is `Degraded=True`.

**Recovery:**
```bash
# Identify the degraded operator
oc get clusteroperators | grep -i degraded

# Get details on why it is degraded
oc get clusteroperator <operator-name> -o json | jq '.status.conditions[] | select(.type=="Degraded")'

# Check the operator's pods
oc get pods -n openshift-<operator-name>
oc logs -n openshift-<operator-name> <pod-name>

# Common fix: if a pod is crashlooping, delete it and let the operator recreate it
oc delete pod -n openshift-<operator-name> <pod-name>
```

### Worker Node Stuck During Drain

**Symptom:** A node stays in `SchedulingDisabled` state and the MachineConfigPool shows `UPDATING` indefinitely.

**Recovery:**
```bash
# Check what is preventing the drain
oc get pods --field-selector spec.nodeName=<node-name> -A

# Look for pods without PDBs or with restrictive PDBs
oc get pdb -A

# If a pod is stuck terminating, force delete it (last resort)
oc delete pod <pod-name> -n <namespace> --grace-period=0 --force

# If the node is truly stuck, you may need to uncordon and try again
oc adm uncordon <node-name>
```

### MachineConfigPool Degraded

**Symptom:** `oc get mcp` shows `DEGRADED=True` for master or worker pool.

**Recovery:**
```bash
# Check which node is causing the degradation
oc get mcp worker -o json | jq '.status.conditions[] | select(.type=="NodeDegraded")'

# Check the machine-config-daemon logs on the affected node
oc logs -n openshift-machine-config-operator -l k8s-app=machine-config-daemon --all-containers -c machine-config-daemon | grep -i error

# If a node failed to apply config, you may need to SSH into it
oc debug node/<node-name>
chroot /host
journalctl -u machine-config-daemon-host -f
```

### Full Rollback (etcd Restore)

**Symptom:** Upgrade causes catastrophic failure; cluster is unusable.

**Recovery:** This is the nuclear option. It restores the entire cluster state to the pre-upgrade etcd backup.

```bash
# This must be done from a control plane node (SSH or debug pod)
# 1. Stop all control plane static pods on ALL masters
# 2. Restore etcd from the backup on ONE master
# 3. Restart the control plane on that master
# 4. The other masters will resync

# On the recovery master:
oc debug node/<master-node>
chroot /host
/usr/local/bin/cluster-restore.sh /home/core/backup-pre-upgrade-<date>
```

**Warning:** This reverts ALL cluster state -- not just the version, but all resource changes made since the backup. This is why etcd backups immediately before upgrade are critical.

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Upgrade orchestration | Manual, component-by-component (kubeadm upgrade) | Automated by CVO, single command |
| Version graph | Follow K8s version skew policy manually | Cincinnati service enforces valid paths |
| Control plane upgrade | Upgrade each binary/manifest individually | CVO updates all control plane operators in order |
| Worker node upgrade | Drain + upgrade kubelet + restart (per node) | MCO automates drain, OS update, reboot, uncordon |
| Node OS | Upgrade independently (apt/yum/etc.) | RHCOS upgraded atomically with the cluster |
| Rollback | Restore etcd + downgrade binaries | Restore etcd backup (no in-place downgrade) |
| Upgrade channels | N/A (you pick a version manually) | stable, fast, candidate, eus channels |
| Pre-flight checks | Manual (cluster health, version skew) | CVO checks operator health, Cincinnati validates path |
| Progress monitoring | Check each component individually | `oc adm upgrade`, ClusterVersion conditions |
| Canary upgrades | Manual (upgrade one node at a time) | MCP pausing, maxUnavailable configuration |
| Extended support | Community: ~12 months per minor | EUS: 18 months for even minor versions |
| Disconnected upgrades | Download binaries manually | Mirror release images, run local OSUS |

## Key Takeaways

- **OpenShift upgrades are operator-driven**: The CVO orchestrates the entire process -- control plane, platform operators, and worker nodes -- through a single `oc adm upgrade` command, unlike Kubernetes where you manually upgrade each component.
- **Channel selection is a production strategy decision**: Use `stable` for production, `eus` for minimal upgrade frequency (even minor versions only, with 18-month support), and `fast`/`candidate` for pre-production validation.
- **Pre-upgrade preparation is non-negotiable**: Always verify cluster operator health, take an etcd backup, ensure PodDisruptionBudgets are in place, and test the upgrade on non-production clusters first.
- **Rollback is not a graceful downgrade**: OpenShift does not support in-place version downgrades. Your rollback path is restoring an etcd backup, which reverts all cluster state. This makes canary environments and pre-upgrade testing critical.
- **Worker node upgrades can be controlled**: Pausing MachineConfigPools and configuring `maxUnavailable` gives you fine-grained control over the blast radius during worker node rolling updates.

## Cleanup

This lesson is primarily observational (querying cluster state and understanding upgrade processes). If you applied any manifests:

```bash
# Remove PodDisruptionBudgets created for the lesson
oc delete -f manifests/critical-pdb.yaml --ignore-not-found

# Remove the etcd backup CronJob if applied
oc delete -f manifests/etcd-backup-cronjob.yaml --ignore-not-found

# If you paused the worker MachineConfigPool, resume it
oc patch mcp/worker --type merge --patch '{"spec":{"paused":false}}'

# Remove lesson labels if applied
oc delete all -l tutorial-level=3,tutorial-module=M1 -n openshift-etcd --ignore-not-found
```

**Note:** Do NOT undo a cluster upgrade. If you upgraded the cluster during this lesson, it stays at the new version. Ensure you only perform upgrades on development/test clusters when following this lesson.

## Next Steps

In **L3-M1.3 -- Node Management**, you will learn how MachineSets, MachineConfigPools, and MachineConfigs work together to manage node lifecycle at scale. You will add and remove worker nodes, configure infra nodes, and apply custom MachineConfigs -- building directly on the MCP concepts introduced in this lesson's upgrade process.
