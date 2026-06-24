# L3-M3.2 --- Troubleshooting Methodology

**Level:** Expert
**Duration:** 1 hr

## Overview

When an OpenShift cluster misbehaves in production, the difference between a 5-minute resolution and a 5-hour outage is a systematic debugging approach. You already know `kubectl describe`, `kubectl logs`, and basic pod debugging in Kubernetes. This lesson equips you with OpenShift's purpose-built diagnostic tools -- `must-gather`, `oc adm inspect`, and `sosreport` -- and builds a decision tree for diagnosing the five most common production failures: OOM kills, CrashLoopBackOff, ImagePullBackOff, scheduling failures, and certificate expiry.

## Prerequisites

- L3-M1 (Cluster Administration) completed -- you should be comfortable with node management, MachineConfigs, and etcd operations
- L1-M6.4 (Events & Debugging) for foundational `oc debug` / `oc logs` usage
- L2-M5 (Security Hardening) for understanding SCCs and admission context
- OpenShift cluster running (CRC or production-like environment)
- `cluster-admin` access (some diagnostic tools require elevated privileges)
- `oc` CLI version 4.12+ installed

## K8s Context

In Kubernetes, troubleshooting typically follows this pattern: check pod status with `kubectl get pods`, inspect events with `kubectl describe`, read logs with `kubectl logs`, and if needed, exec into containers or use ephemeral debug containers. For cluster-level issues you rely on control plane component logs, etcd health checks, and whatever monitoring stack you have installed.

OpenShift inherits all of these capabilities through `oc` (which is a superset of `kubectl`), but adds three powerful diagnostic tools that have no Kubernetes equivalent:

1. **`must-gather`** -- automated, comprehensive cluster diagnostic collection
2. **`oc adm inspect`** -- targeted resource state snapshots
3. **`sosreport`** -- node-level OS and runtime diagnostics

These tools exist because OpenShift is a supported product. Red Hat support engineers need standardized diagnostic bundles, and those same tools are invaluable for your own troubleshooting.

## Concepts

### The Diagnostic Pyramid

Production troubleshooting in OpenShift follows a layered approach. Start broad, then narrow down:

```
                    +---------------------+
                    |   Application Logs  |  <-- Pod-level
                    |   oc logs / events  |
                    +----------+----------+
                               |
                    +----------v----------+
                    | Resource Inspection  |  <-- Object-level
                    | oc adm inspect      |
                    +----------+----------+
                               |
                    +----------v----------+
                    |  Cluster Diagnostics |  <-- Cluster-level
                    |  must-gather         |
                    +----------+----------+
                               |
                    +----------v----------+
                    |   Node Diagnostics   |  <-- Node/OS-level
                    |   sosreport / debug  |
                    +----------+----------+
```

### must-gather

`must-gather` is an `oc adm` command that launches a pod on the cluster, collects comprehensive diagnostics, and downloads the results as a tarball. It captures:

- Cluster version and operator status
- All custom resource definitions and instances
- Pod logs from critical namespaces (`openshift-*`, `kube-*`)
- Events from all namespaces
- Node status and machine information
- Network configuration
- Storage state (PVs, PVCs, StorageClasses)

You can also run specialized must-gather images for specific operators (e.g., OpenShift Logging, OpenShift Virtualization, ODF) that collect operator-specific diagnostics.

### oc adm inspect

`oc adm inspect` takes a point-in-time snapshot of specific resources -- their YAML definitions, associated events, and logs. Unlike `must-gather` (which collects everything), `oc adm inspect` is targeted: you specify exactly which resources or namespaces to snapshot. This makes it faster and produces smaller output, ideal for investigating a known problem area.

### sosreport

`sosreport` runs at the node level (not the Kubernetes API level). On RHCOS (Red Hat CoreOS) nodes, it collects OS-level diagnostics: systemd journal, CRI-O runtime logs, kubelet configuration, network interfaces, disk usage, kernel parameters, and more. You access it via `oc debug node/` because RHCOS nodes are immutable and you cannot SSH into them directly.

### Decision Tree for Common Failures

```
Pod not running?
|
+-- Status: ImagePullBackOff?
|   +-- Check image name/tag for typos
|   +-- Check imagePullSecrets
|   +-- Check registry connectivity (egress rules, proxy)
|   +-- Check ImageContentSourcePolicy mirrors
|
+-- Status: CrashLoopBackOff?
|   +-- Check previous container logs: oc logs <pod> --previous
|   +-- Check exit code (OOM = 137, segfault = 139)
|   +-- Check SCC: is the container trying to run as root?
|   +-- Check liveness probe configuration
|   +-- Check resource limits (OOM at container level)
|
+-- Status: OOMKilled?
|   +-- Check container memory limits vs actual usage
|   +-- Check node-level memory pressure
|   +-- Review cgroup settings and kernel OOM scores
|   +-- Consider VPA recommendations
|
+-- Status: Pending (scheduling failure)?
|   +-- Check resource requests vs available capacity
|   +-- Check node taints and pod tolerations
|   +-- Check nodeSelector / nodeAffinity
|   +-- Check PVC binding status
|   +-- Check pod priority and preemption
|
+-- Cluster operator degraded?
|   +-- Check certificate expiry
|   +-- Check etcd health
|   +-- Check control plane pod logs
|   +-- Run must-gather for full diagnostics
```

### Failure Modes and Recovery

#### OOM Kills

When a container exceeds its memory limit, the kernel OOM killer terminates it with signal 9 (exit code 137). The kubelet restarts the container according to its `restartPolicy`. If memory usage consistently exceeds limits, you get CrashLoopBackOff with exponential backoff delays.

**Recovery:** Increase memory limits, fix application memory leaks, or enable swap (OpenShift 4.13+ supports swap via MachineConfig). Check both container-level limits and node-level memory pressure (`oc adm top nodes`).

#### CrashLoopBackOff

This is a symptom, not a root cause. The container starts, crashes, and Kubernetes keeps restarting it with increasing delays (10s, 20s, 40s, ... up to 5 minutes). Common causes:

- Application startup failure (missing config, bad credentials, port conflicts)
- SCC violation (trying to bind to port < 1024, writing to read-only filesystem)
- OOM kill at startup (memory limit too low for JVM startup, etc.)
- Liveness probe fails before the app finishes starting

**Recovery:** Check `oc logs <pod> --previous` for the crash output. Check exit codes. Check events for SCC denials.

#### ImagePullBackOff

The kubelet cannot pull the container image. In OpenShift, this is complicated by image policies, mirroring, and the internal registry.

**Recovery:** Verify image reference (including registry hostname), check `imagePullSecrets`, test registry connectivity from a debug pod, check `ImageContentSourcePolicy` for mirrored registries.

#### Scheduling Failures

Pods stay `Pending` because the scheduler cannot find a suitable node. OpenShift adds complexity with MachineSet-based autoscaling and infrastructure nodes.

**Recovery:** Run `oc describe pod` to see the scheduling failure reason. Check node resources with `oc adm top nodes`. Verify taints, tolerations, and node selectors. Check if PVCs are bound (storage in the wrong zone is a common gotcha).

#### Certificate Expiry

OpenShift automatically rotates most certificates, but misconfigurations or clock skew can cause expiry. Symptoms include API server errors, webhook failures, and operator degradation.

**Recovery:** Check certificate expiry dates. OpenShift 4.x has automatic certificate rotation; forcing rotation may be needed. Check `openshift-kube-apiserver-operator` logs.

## Step-by-Step

### Step 1: Set Up a Troubleshooting Workspace

Create a dedicated project for troubleshooting exercises and deploy workloads that simulate common failure scenarios.

```bash
# Create the troubleshooting project
oc new-project troubleshooting-lab

# Verify you have cluster-admin access (required for must-gather and node debugging)
oc auth can-i '*' '*' --all-namespaces
```

Apply the lab manifests that simulate various failure conditions:

```bash
# Deploy all troubleshooting scenario pods
oc apply -f manifests/
```

These manifests create pods that intentionally trigger OOMKilled, CrashLoopBackOff, ImagePullBackOff, scheduling failures, and a healthy baseline pod.

### Step 2: Triage -- Identify the Problem

Start every troubleshooting session with a broad view, then narrow down.

```bash
# Get a high-level cluster health view
oc get clusterversion
oc get clusteroperators

# Check node health
oc get nodes
oc adm top nodes

# Check pod status in our lab namespace
oc get pods -n troubleshooting-lab -o wide

# Get events sorted by time (most recent last)
oc get events -n troubleshooting-lab --sort-by='.lastTimestamp'
```

Expected output shows pods in various failure states:

```
NAME                   READY   STATUS             RESTARTS      AGE
healthy-app-xxx        1/1     Running            0             2m
oom-victim-xxx         0/1     OOMKilled          3 (30s ago)   2m
crash-loop-xxx         0/1     CrashLoopBackOff   3 (25s ago)   2m
bad-image-xxx          0/1     ImagePullBackOff   0             2m
unschedulable-xxx      0/1     Pending            0             2m
```

### Step 3: Debug OOMKilled Pods

Investigate the pod that is being OOM killed.

```bash
# Check the pod status in detail
oc describe pod -l scenario=oom-kill -n troubleshooting-lab

# Look for the OOMKilled status and exit code 137
oc get pod -l scenario=oom-kill -n troubleshooting-lab -o jsonpath='{.items[0].status.containerStatuses[0].lastState.terminated.reason}'

# Check container memory limits vs node capacity
oc get pod -l scenario=oom-kill -n troubleshooting-lab -o jsonpath='{.items[0].spec.containers[0].resources}'

# Check what the application was doing when it was killed
oc logs -l scenario=oom-kill -n troubleshooting-lab --previous 2>/dev/null || echo "No previous logs available yet"

# Check node-level memory pressure
oc adm top nodes
```

The OOM pod has a memory limit of 50Mi but runs a process that allocates 128Mi. The kernel OOM killer terminates it.

**Fix:** increase the memory limit or fix the application. In production, use VPA to get memory recommendations:

```bash
# Check actual memory usage before the kill
oc adm top pod -n troubleshooting-lab
```

### Step 4: Debug CrashLoopBackOff Pods

Investigate the crashing pod.

```bash
# Check the pod description for restart count and exit codes
oc describe pod -l scenario=crash-loop -n troubleshooting-lab

# Read the logs from the last crash
oc logs -l scenario=crash-loop -n troubleshooting-lab --previous

# Check the exit code
oc get pod -l scenario=crash-loop -n troubleshooting-lab \
  -o jsonpath='{.items[0].status.containerStatuses[0].lastState.terminated.exitCode}'

# Use oc debug to run the image interactively and investigate
# This starts a new pod with the same image but overrides the entrypoint
oc debug deployment/crash-loop -n troubleshooting-lab
```

Inside the debug pod, you can check filesystem permissions, SCC constraints, and environment variables:

```bash
# Inside the debug pod:
id                    # Check the user ID (OpenShift runs as non-root)
ls -la /app/          # Check file permissions
env                   # Check environment variables
cat /etc/os-release   # Check the base image
exit
```

### Step 5: Debug ImagePullBackOff Pods

Investigate the image pull failure.

```bash
# Check the pod events for the exact error
oc describe pod -l scenario=image-pull -n troubleshooting-lab

# Common errors you'll see in events:
# - "repository does not exist"
# - "unauthorized: authentication required"
# - "manifest unknown"
# - "dial tcp: lookup registry.example.com: no such host"

# Check if imagePullSecrets are configured
oc get pod -l scenario=image-pull -n troubleshooting-lab \
  -o jsonpath='{.items[0].spec.imagePullSecrets}'

# Check the service account's pull secrets
oc get sa default -n troubleshooting-lab -o jsonpath='{.imagePullSecrets}'

# Test registry connectivity from within the cluster
oc debug node/$(oc get nodes -o jsonpath='{.items[0].metadata.name}') -- \
  chroot /host curl -s -o /dev/null -w '%{http_code}' https://registry.access.redhat.com/v2/

# Check if ImageContentSourcePolicy is redirecting the image
oc get imagecontentsourcepolicy -o yaml 2>/dev/null || echo "No ICSP configured"
```

### Step 6: Debug Scheduling Failures

Investigate the Pending pod.

```bash
# The describe output shows WHY the pod cannot be scheduled
oc describe pod -l scenario=unschedulable -n troubleshooting-lab

# Look for messages like:
# - "Insufficient cpu" or "Insufficient memory"
# - "node(s) had taints that the pod didn't tolerate"
# - "node(s) didn't match Pod's node affinity/selector"
# - "persistentvolumeclaim is not bound"

# Check available resources on each node
oc adm top nodes
oc describe nodes | grep -A 5 "Allocated resources"

# Check node taints
oc get nodes -o custom-columns=NAME:.metadata.name,TAINTS:.spec.taints

# Check if there are any pending PVCs
oc get pvc -n troubleshooting-lab
```

### Step 7: Use oc adm inspect for Targeted Snapshots

`oc adm inspect` captures the current state of specific resources into a local directory. This is faster than `must-gather` when you know what to look at.

```bash
# Create a directory for inspection output
mkdir -p /tmp/inspect-output

# Inspect a specific namespace -- captures all resources, events, and pod logs
oc adm inspect namespace/troubleshooting-lab --dest-dir=/tmp/inspect-output

# Inspect a specific cluster operator
oc adm inspect clusteroperator/kube-apiserver --dest-dir=/tmp/inspect-output

# Inspect a specific node
oc adm inspect node/$(oc get nodes -o jsonpath='{.items[0].metadata.name}') \
  --dest-dir=/tmp/inspect-output

# Inspect all resources of a specific type
oc adm inspect pods -n troubleshooting-lab --dest-dir=/tmp/inspect-output
```

Examine the captured data:

```bash
# List what was captured
find /tmp/inspect-output -type f | head -30

# The output is organized by resource type:
# /tmp/inspect-output/
#   namespaces/
#     troubleshooting-lab/
#       pods/
#         <pod-name>.yaml        <-- Full pod spec
#         <pod-name>/
#           <container>/
#             logs/
#               current.log      <-- Container logs
#               previous.log     <-- Previous container logs
#       events.yaml              <-- Namespace events
#       configmaps/
#       secrets/                 <-- Secret metadata (not data)

# Check a specific pod's captured state
cat /tmp/inspect-output/namespaces/troubleshooting-lab/pods/*/oom-victim*.yaml 2>/dev/null | head -40
```

### Step 8: Run must-gather for Full Cluster Diagnostics

`must-gather` collects comprehensive diagnostics from the entire cluster. This is what you run when opening a support case or when the problem is not isolated to a single namespace.

```bash
# Run the default must-gather (collects from all openshift-* namespaces)
# This launches a pod, collects data, then downloads a tarball
oc adm must-gather --dest-dir=/tmp/must-gather-output

# The default image collects:
# - Cluster version and update history
# - All ClusterOperator statuses and logs
# - All CRDs and their instances
# - Pod logs from openshift-* and kube-* namespaces
# - Node information and machine objects
# - Network configuration (OVN, SDN)
# - Certificate information
# - Audit logs (if enabled)
```

For operator-specific diagnostics, use specialized must-gather images:

```bash
# Collect OpenShift Logging diagnostics
oc adm must-gather --image=registry.redhat.io/openshift-logging/cluster-logging-rhel9-operator:latest \
  --dest-dir=/tmp/must-gather-logging

# Collect ODF (OpenShift Data Foundation) diagnostics
oc adm must-gather --image=registry.redhat.io/odf4/ocs-must-gather-rhel9:latest \
  --dest-dir=/tmp/must-gather-odf

# Collect Service Mesh diagnostics
oc adm must-gather --image=registry.redhat.io/openshift-service-mesh/istio-must-gather-rhel8:latest \
  --dest-dir=/tmp/must-gather-mesh

# Run multiple must-gather images at once
oc adm must-gather \
  --image=registry.redhat.io/openshift4/ose-must-gather:latest \
  --image=registry.redhat.io/openshift-logging/cluster-logging-rhel9-operator:latest \
  --dest-dir=/tmp/must-gather-combined
```

Navigate the must-gather output:

```bash
# List the top-level structure
ls /tmp/must-gather-output/

# The output structure:
# must-gather-output/
#   quay-io-.../                       <-- Named by must-gather image
#     cluster-scoped-resources/
#       core/
#         nodes/                       <-- Node objects
#         persistentvolumes/
#       config.openshift.io/
#       machine.openshift.io/
#     namespaces/
#       openshift-kube-apiserver/
#         pods/
#           kube-apiserver-master-0/
#             kube-apiserver/
#               logs/
#                 current.log
#       openshift-etcd/
#       openshift-ingress/
#     event-filter.html                <-- Browsable event timeline

# Check cluster operator status
cat /tmp/must-gather-output/*/cluster-scoped-resources/config.openshift.io/clusteroperators.yaml

# Check for certificate-related issues
find /tmp/must-gather-output -name "*.yaml" -exec grep -l "certificate" {} \;
```

### Step 9: Node-Level Debugging with oc debug and sosreport

When the problem is at the node or OS level (kubelet issues, CRI-O problems, disk pressure, kernel panics), you need to inspect the node directly.

```bash
# Start a debug session on a specific node
# This creates a privileged pod with the node's filesystem mounted at /host
oc debug node/$(oc get nodes -o jsonpath='{.items[0].metadata.name}')
```

Inside the debug pod:

```bash
# Chroot into the node's filesystem
chroot /host

# Check kubelet status and recent logs
systemctl status kubelet
journalctl -u kubelet --since "1 hour ago" --no-pager | tail -50

# Check CRI-O runtime status
systemctl status crio
crictl ps -a | head -20
crictl pods --state=notready

# Check disk usage (a common cause of node issues)
df -h
du -sh /var/lib/containers/storage/  # Container image storage
du -sh /var/log/                     # Log storage

# Check system memory and OOM events
free -h
dmesg | grep -i "oom\|out of memory" | tail -10

# Check kernel messages for hardware or filesystem errors
dmesg | tail -50

# Check certificate files
ls -la /etc/kubernetes/static-pod-resources/kube-apiserver-certs/

# Check NTP synchronization (clock skew causes certificate issues)
chronyc tracking

# Run sosreport for comprehensive node diagnostics
# (requires sos package -- available on RHCOS)
sosreport --batch --tmp-dir /host/tmp/ \
  -o crio,container_log,networking,filesys,memory,processor,systemd \
  --case-id=troubleshooting-lab

# Exit the chroot and debug pod
exit
exit
```

Copy the sosreport from the node:

```bash
# The sosreport tarball is on the node's filesystem
# Retrieve it using oc debug
NODE=$(oc get nodes -o jsonpath='{.items[0].metadata.name}')
oc debug node/${NODE} -- cat /host/tmp/sosreport-*.tar.xz > /tmp/sosreport.tar.xz 2>/dev/null
```

### Step 10: Check Certificate Expiry

Certificate issues cause cascading failures in OpenShift. The API server, etcd, the router, and internal service communication all depend on valid certificates.

```bash
# Check cluster-wide certificate status via the kube-apiserver operator
oc get clusteroperator kube-apiserver -o yaml | grep -A 5 "condition"

# Check certificate expiry for the API server
oc get secret -n openshift-kube-apiserver -o json | \
  python3 -c "
import json, sys, base64, subprocess
data = json.load(sys.stdin)
for item in data.get('items', []):
    name = item['metadata']['name']
    if 'cert' in name.lower() or 'tls' in name.lower():
        for key, val in item.get('data', {}).items():
            if key.endswith('.crt') or key.endswith('.pem'):
                print(f'--- {name}/{key} ---')
                try:
                    decoded = base64.b64decode(val)
                    proc = subprocess.run(['openssl', 'x509', '-noout', '-dates', '-subject'],
                                         input=decoded, capture_output=True)
                    print(proc.stdout.decode())
                except Exception as e:
                    print(f'  Error: {e}')
" 2>/dev/null || echo "Python script requires cluster access"

# Simpler: check the router certificate
oc get secret router-certs-default -n openshift-ingress -o jsonpath='{.data.tls\.crt}' | \
  base64 -d | openssl x509 -noout -dates 2>/dev/null

# Check for certificate-related events
oc get events -A --field-selector reason=CertificateExpired 2>/dev/null
oc get events -A | grep -i cert

# OpenShift 4.x auto-rotates certificates
# Check the certificate signing requests queue
oc get csr
oc get csr | grep -i pending
```

### Step 11: Use the Troubleshooting Script

The `scripts/` directory includes a comprehensive diagnostic script that automates the triage process.

```bash
# Run the diagnostic script
bash scripts/diagnose-cluster.sh

# Or run it for a specific namespace
bash scripts/diagnose-cluster.sh troubleshooting-lab
```

The script automates Steps 2-6 and produces a summary report.

### Step 12: Correlate and Resolve

After collecting diagnostics, correlate findings across layers:

```bash
# Timeline correlation: when did the problem start?
# 1. Check cluster events for the timeframe
oc get events -A --sort-by='.lastTimestamp' | grep -i "error\|fail\|kill\|backoff"

# 2. Check cluster operator status changes
oc get clusteroperators -o json | \
  python3 -c "
import json, sys
data = json.load(sys.stdin)
for co in data['items']:
    name = co['metadata']['name']
    for cond in co.get('status', {}).get('conditions', []):
        if cond.get('status') != 'False' and cond['type'] in ['Degraded']:
            print(f'{name}: {cond[\"type\"]}={cond[\"status\"]} ({cond.get(\"message\", \"\")})')
        if cond.get('status') != 'True' and cond['type'] in ['Available']:
            print(f'{name}: {cond[\"type\"]}={cond[\"status\"]} ({cond.get(\"message\", \"\")})')
" 2>/dev/null

# 3. Cross-reference with node conditions
oc get nodes -o json | \
  python3 -c "
import json, sys
data = json.load(sys.stdin)
for node in data['items']:
    name = node['metadata']['name']
    for cond in node.get('status', {}).get('conditions', []):
        if cond['type'] == 'Ready' and cond['status'] != 'True':
            print(f'Node {name}: NotReady -- {cond.get(\"message\", \"\")}')
        if cond['type'] in ['MemoryPressure', 'DiskPressure', 'PIDPressure'] and cond['status'] == 'True':
            print(f'Node {name}: {cond[\"type\"]} -- {cond.get(\"message\", \"\")}')
" 2>/dev/null
```

## Verification

After completing the steps, verify you can successfully use each diagnostic tool:

```bash
# 1. Verify you can identify each failure scenario
echo "=== Pod Status Summary ==="
oc get pods -n troubleshooting-lab -o custom-columns=\
NAME:.metadata.name,\
STATUS:.status.phase,\
REASON:.status.containerStatuses[0].state.waiting.reason,\
RESTARTS:.status.containerStatuses[0].restartCount

# 2. Verify oc adm inspect output exists
echo "=== Inspect Output ==="
ls /tmp/inspect-output/namespaces/troubleshooting-lab/ 2>/dev/null && echo "Inspect data captured successfully"

# 3. Verify must-gather output exists
echo "=== Must-Gather Output ==="
ls /tmp/must-gather-output/ 2>/dev/null && echo "Must-gather data captured successfully"

# 4. Verify you can access node debug
echo "=== Node Access ==="
oc auth can-i debug node --all-namespaces && echo "Node debug access confirmed"

# Expected results:
# - healthy-app pod is Running
# - oom-victim shows OOMKilled or CrashLoopBackOff with exit code 137
# - crash-loop shows CrashLoopBackOff
# - bad-image shows ImagePullBackOff
# - unschedulable shows Pending
# - Inspect and must-gather directories contain diagnostic data
```

You can also verify in the **Web Console**:

1. Navigate to **Workloads > Pods** in the `troubleshooting-lab` project
2. Click on a failing pod to see its **Events** tab
3. Check the **Logs** tab for crash output
4. Use **Administrator > Cluster Settings** to check cluster operator health
5. Use **Observe > Alerting** to see if any alerts fired

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Cluster diagnostics bundle | No built-in tool; use third-party (e.g., `kubectl cluster-info dump`) | `oc adm must-gather` -- comprehensive, extensible, support-ready |
| Resource snapshots | `kubectl get -o yaml` per resource | `oc adm inspect` -- captures resources, events, and logs together |
| Node-level debugging | `ssh` to node + run diagnostics | `oc debug node/` -- privileged pod with host filesystem at `/host` |
| OS diagnostics | Varies by distribution | `sosreport` on RHCOS -- standardized, plugin-based |
| Certificate management | Manual (cert-manager, etc.) | Automatic rotation built-in; `oc get csr` for approval |
| Operator diagnostics | `kubectl logs` on operator pods | Specialized must-gather images per operator |
| Cluster health overview | No standard command | `oc get clusteroperators` -- single view of all components |
| Support workflow | Ad hoc diagnostic collection | `must-gather` tarball -- standard format for Red Hat support |
| Audit logs | Configure manually | Built-in, configurable via API server config |
| Container runtime debugging | `docker`/`containerd` CLI | `crictl` via `oc debug node/` (CRI-O runtime) |

## Key Takeaways

- **Start broad, then narrow:** Use `oc get clusteroperators` and `oc get events` for a high-level view before diving into specific pods or nodes. The diagnostic pyramid (application logs, resource inspection, cluster diagnostics, node diagnostics) keeps you efficient.

- **must-gather is your first move for cluster-wide issues:** It captures everything you need in a single command and produces a tarball that is immediately useful for both self-diagnosis and support escalation. Specialized must-gather images exist for every major operator.

- **oc adm inspect is your surgical tool:** When you know which namespace or resource is affected, `oc adm inspect` is faster and more targeted than must-gather. It captures the resource definition, events, and logs in one shot.

- **Common pod failures follow predictable patterns:** OOMKilled (exit code 137) means memory limits are too low. CrashLoopBackOff requires checking `--previous` logs and exit codes. ImagePullBackOff means checking credentials, registry connectivity, and image policies. Pending pods need scheduling constraint analysis.

- **Certificate issues cause cascading failures:** OpenShift auto-rotates certificates, but clock skew, etcd problems, or manual certificate changes can break rotation. Always check certificate expiry when cluster operators report degraded status.

## Cleanup

```bash
# Delete the troubleshooting lab resources
oc delete project troubleshooting-lab

# Clean up local diagnostic output
rm -rf /tmp/inspect-output
rm -rf /tmp/must-gather-output
rm -rf /tmp/must-gather-logging
rm -rf /tmp/must-gather-odf
rm -rf /tmp/must-gather-mesh
rm -rf /tmp/must-gather-combined
rm -f /tmp/sosreport.tar.xz

# Wait for project deletion to complete
oc wait --for=delete namespace/troubleshooting-lab --timeout=60s 2>/dev/null || true
```

## Next Steps

In **L3-M3.3 -- Disaster Recovery**, you will apply these troubleshooting skills to the most critical scenario: recovering from cluster failures. You will learn etcd snapshot and restore procedures, how to recover from quorum loss, back up and restore cluster state with Velero, and establish disaster recovery runbooks. The diagnostic tools from this lesson -- especially `must-gather` and node-level debugging -- are essential for DR procedures.
