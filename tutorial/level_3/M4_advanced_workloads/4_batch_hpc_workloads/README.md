# L3-M4.4 — Batch & HPC Workloads

**Level:** Expert
**Duration:** 30 min

## Overview

Kubernetes Jobs and CronJobs are the standard primitives for batch processing, and they work identically on OpenShift. But running batch and HPC workloads in production requires more than just creating a Job: you need GPU scheduling, distributed computing frameworks (MPI), job queueing with fair-share policies, and OpenShift-specific scheduling considerations around Security Context Constraints and node affinity.

This lesson starts from the batch primitives you already know, then layers on GPU scheduling with the NVIDIA GPU Operator, distributed MPI workloads with `mpi-operator`, and intelligent job admission with Kueue -- all within OpenShift's security model.

## Prerequisites

- Completed: L3-M1 (Cluster Administration) -- you need comfort with node management, priority classes, and cluster-level configuration
- Completed: L1-M2.4 (SCCs) -- understanding of Security Context Constraints
- OpenShift cluster running (CRC for Jobs/CronJobs; production cluster with GPU nodes for GPU and MPI exercises)
- `oc` CLI authenticated with `cluster-admin` (for PriorityClasses and operator installation)
- Optional: NVIDIA GPU Operator installed (for GPU exercises)
- Optional: mpi-operator installed (for MPI exercises)
- Optional: Kueue operator installed (for job queueing exercises)

## K8s Context

You already know Jobs and CronJobs. A `Job` creates one or more Pods that run to completion, with configurable parallelism, completion count, and backoff policy. A `CronJob` wraps a Job in a schedule. On vanilla Kubernetes, you would install additional components for GPU support (NVIDIA device plugin), MPI (kubeflow mpi-operator), and job queueing (Kueue or Volcano). OpenShift provides these through its operator ecosystem, but adds SCC constraints that affect how batch workloads run.

## Concepts

### Jobs and CronJobs on OpenShift

Jobs and CronJobs are standard Kubernetes resources and behave identically on OpenShift. The key differences are operational:

1. **SCC enforcement**: Job pods run under the `restricted` SCC by default. Many HPC container images expect root access and will fail. You must either use SCC-compatible images (UBI-based) or grant the `anyuid` SCC to the Job's service account.

2. **Indexed Jobs**: Kubernetes 1.24+ (OpenShift 4.11+) supports `completionMode: Indexed`, where each pod gets a unique index via `JOB_COMPLETION_INDEX`. This is essential for data-parallel batch processing where each pod handles a shard.

3. **Pod Priority and Preemption**: OpenShift respects `PriorityClass` for batch scheduling. Critical batch jobs (end-of-day settlement, regulatory reports) should use higher priority classes. Best-effort batch work should use `preemptionPolicy: Never` to avoid disrupting other workloads.

4. **Resource Quotas**: In multi-tenant clusters, `ResourceQuota` limits prevent batch workloads from starving other tenants. Always set `count/jobs.batch` and `count/cronjobs.batch` quotas.

### NVIDIA GPU Operator

The NVIDIA GPU Operator automates GPU node setup on OpenShift:

```
+---------------------------+
|   NVIDIA GPU Operator     |
+---------------------------+
|  - NVIDIA Driver (RHCOS)  |
|  - Container Toolkit      |
|  - Device Plugin          |
|  - GPU Feature Discovery  |
|  - DCGM Exporter          |
|  - MIG Manager            |
+---------------------------+
         |
         v
+---------------------------+
|   GPU-Enabled Nodes       |
|  nvidia.com/gpu resource  |
|  exposed to scheduler     |
+---------------------------+
         |
         v
+---------------------------+
|   GPU Jobs                |
|  requests:                |
|    nvidia.com/gpu: "1"    |
+---------------------------+
```

On vanilla Kubernetes, you would install the NVIDIA device plugin DaemonSet manually. On OpenShift, the GPU Operator is available through OperatorHub and handles driver installation on RHCOS nodes, container toolkit configuration, and device plugin deployment automatically. It also integrates with OpenShift monitoring via the DCGM Exporter (GPU metrics in Prometheus).

Key considerations:
- GPU nodes need the `nvidia.com/gpu` taint so non-GPU workloads are not scheduled there.
- GPU resources are non-shareable by default -- one pod gets exclusive access to a GPU.
- Multi-Instance GPU (MIG) support allows partitioning A100/H100 GPUs into smaller slices.

### MPI Jobs with mpi-operator

MPI (Message Passing Interface) is the standard for distributed HPC workloads -- scientific simulations, numerical analysis, and parallel computing. The `mpi-operator` (from Kubeflow) manages MPI jobs on Kubernetes/OpenShift:

```
+------------------+
|    MPIJob CRD    |
+------------------+
        |
        v
+------------------+     SSH      +------------------+
|    Launcher      |------------->|    Worker 0      |
|    (1 replica)   |------------->|    Worker 1      |
|                  |------------->|    Worker 2      |
|  mpirun -np 4   |------------->|    Worker 3      |
+------------------+              +------------------+
                                  Each worker runs one
                                  MPI rank (process)
```

The launcher pod orchestrates the distributed computation via SSH. The operator sets up SSH keys, hostfiles, and networking between pods. On OpenShift, the main consideration is SCC: MPI containers often need SSH daemon access and may require the `anyuid` SCC.

### Kueue for Job Queueing

Kueue is a Kubernetes-native job queueing system that controls when Jobs are allowed to start based on available cluster capacity and fair-sharing policies. It does not replace the kube-scheduler; instead, it gates job admission.

```
+---------------------------------------------------+
|                    Kueue Architecture              |
+---------------------------------------------------+
|                                                    |
|   Users submit Jobs          Kueue admits Jobs     |
|   (suspend: true)            when capacity allows  |
|        |                           |               |
|        v                           v               |
|  +-----------+    admit    +--------------+        |
|  | LocalQueue| ---------->| ClusterQueue |        |
|  +-----------+             +--------------+        |
|  (namespace)               (cluster-wide)          |
|                                    |               |
|                    +---------------+-------+       |
|                    |                       |       |
|              +----------+           +----------+   |
|              | Resource |           | Resource |   |
|              | Flavor   |           | Flavor   |   |
|              | (CPU)    |           | (GPU)    |   |
|              +----------+           +----------+   |
|                                                    |
|  Features:                                         |
|  - Fair sharing between teams                      |
|  - Resource borrowing across queues                |
|  - Preemption of lower-priority jobs               |
|  - Priority-based admission                        |
+---------------------------------------------------+
```

Key Kueue concepts:
- **ClusterQueue**: Cluster-scoped resource pool with quotas per ResourceFlavor.
- **LocalQueue**: Namespace-scoped queue that users submit Jobs to. Maps to a ClusterQueue.
- **ResourceFlavor**: Represents a type of resource (e.g., CPU-only nodes, GPU nodes).
- **WorkloadPriorityClass**: Kueue-specific priority (separate from PriorityClass).

Jobs submitted to Kueue must have `suspend: true` and the label `kueue.x-k8s.io/queue-name`. Kueue unsuspends them when capacity is available.

## Step-by-Step

### Step 1: Create the Project and Foundation Resources

Set up the project with RBAC, resource quotas, and priority classes.

```bash
# Create the project
oc new-project batch-hpc-demo \
  --display-name="Batch & HPC Demo" \
  --description="L3-M4.4 Batch & HPC Workloads"

# Or use the setup script:
# ./scripts/setup.sh
```

Apply the foundational resources:

```bash
# RBAC: service account and role for batch workloads
oc apply -f manifests/batch-rbac.yaml

# Resource quotas and limit ranges
oc apply -f manifests/resource-quota-batch.yaml

# Priority classes (cluster-scoped, requires cluster-admin)
oc apply -f manifests/priority-classes.yaml
```

Verify the setup:

```bash
oc get sa batch-sa
oc get resourcequota batch-workload-quota
oc get limitrange batch-limit-range
oc get priorityclasses | grep batch
```

Expected output:

```
NAME       SECRETS   AGE
batch-sa   1         5s

NAME                     AGE   REQUEST                                           LIMIT
batch-workload-quota     5s    count/cronjobs.batch: 0/10, count/jobs.batch:...  limits.cpu: 0/16, ...

NAME                AGE
batch-limit-range   5s

batch-critical   100000    false   PreemptLowerPriority   5s
batch-low        10000     false   Never                  5s
batch-normal     50000     false   PreemptLowerPriority   5s
```

### Step 2: Run an Indexed Batch Job

Deploy a Job that uses indexed completion mode. Each pod receives a unique index via `JOB_COMPLETION_INDEX`, enabling data-parallel processing where each pod handles a different shard.

```bash
oc apply -f manifests/job-basic.yaml
```

Watch the pods as they run (2 in parallel, 5 total completions):

```bash
# Watch pods spin up and complete
oc get pods -l app=batch-processor -w

# Check the Job status
oc get job batch-processor -o wide
```

Expected output -- you should see pods completing in pairs:

```
NAME                      READY   STATUS      RESTARTS   AGE
batch-processor-0-xxxxx   0/1     Completed   0          45s
batch-processor-1-xxxxx   0/1     Completed   0          45s
batch-processor-2-xxxxx   1/1     Running     0          10s
batch-processor-3-xxxxx   1/1     Running     0          10s
```

View the output from a specific index:

```bash
# Check logs from index 0
oc logs job/batch-processor --container=processor | head -20

# Or for a specific pod
oc logs batch-processor-0-xxxxx
```

Note that the manifest uses `ttlSecondsAfterFinished: 3600` -- the Job and its pods are automatically cleaned up after one hour. This is critical in production to prevent completed Job objects from accumulating.

### Step 3: Create a Production CronJob

Deploy a CronJob with production-quality settings: concurrency policy, timezone awareness, history limits, and deadlines.

```bash
oc apply -f manifests/cronjob-report.yaml
```

Review the CronJob configuration:

```bash
oc get cronjob daily-report-generator -o yaml | grep -A 5 'spec:'
```

Key production settings to note in the manifest:

- **`concurrencyPolicy: Forbid`** -- if a previous run is still active, skip the new one. Prevents overlapping report runs.
- **`startingDeadlineSeconds: 300`** -- if the CronJob misses its schedule by more than 5 minutes (e.g., cluster was down), skip that run.
- **`timeZone: "America/New_York"`** -- run at 2 AM Eastern, not UTC. Available since K8s 1.27 / OpenShift 4.14.
- **`successfulJobsHistoryLimit: 7`** / **`failedJobsHistoryLimit: 3`** -- retain a week of successful runs and 3 failed runs for debugging.

Trigger a manual run to test:

```bash
oc create job --from=cronjob/daily-report-generator manual-test-run
oc get pods -l app=daily-report-generator -w
oc logs job/manual-test-run
```

### Step 4: GPU Workloads with NVIDIA GPU Operator

> **Note**: This step requires nodes with NVIDIA GPUs and the NVIDIA GPU Operator installed. On CRC (which has no GPU), review the manifests and concepts. On a production cluster, install the operator first.

#### Installing the GPU Operator

The GPU Operator is available through OperatorHub:

```bash
# Verify GPU nodes exist
oc get nodes -l nvidia.com/gpu.present=true

# Install via OperatorHub (Web Console: Operators > OperatorHub > "NVIDIA GPU Operator")
# Or via CLI:
oc get csv -n nvidia-gpu-operator | grep gpu

# Verify the GPU operator pods are running
oc get pods -n nvidia-gpu-operator
```

After installation, verify GPU resources are exposed:

```bash
# Check that nodes advertise GPU resources
oc describe node <gpu-node> | grep -A 5 "nvidia.com/gpu"

# Expected output:
#   nvidia.com/gpu:   1
# or
#   nvidia.com/gpu:   4  (multi-GPU node)
```

#### Run a GPU Job

```bash
oc apply -f manifests/gpu-job.yaml
```

Monitor the GPU job:

```bash
oc get pods -l app=gpu-ml-training -w
oc logs job/gpu-ml-training
```

The manifest includes:
- `nvidia.com/gpu: "1"` in both requests and limits (GPU resources must be equal in requests and limits)
- A toleration for the `nvidia.com/gpu` taint on GPU nodes
- UBI9-based CUDA image for SCC compatibility

#### GPU Monitoring

The GPU Operator deploys a DCGM Exporter that exposes GPU metrics to Prometheus:

```bash
# Check GPU metrics are available
oc get servicemonitor -n nvidia-gpu-operator

# Query GPU utilization in the OpenShift console:
# Observe > Metrics > query: DCGM_FI_DEV_GPU_UTIL
```

### Step 5: MPI Jobs for Distributed Computing

> **Note**: This step requires the `mpi-operator` installed. Install it via:
> ```bash
> # Install mpi-operator from Kubeflow
> kubectl apply -f https://raw.githubusercontent.com/kubeflow/mpi-operator/v0.4.0/deploy/v2beta1/mpi-operator.yaml
> ```

#### Understanding the MPIJob

The MPI operator introduces the `MPIJob` CRD. Review the manifest:

```yaml
# From manifests/mpi-job.yaml (key sections)
spec:
  slotsPerWorker: 1           # One MPI rank per worker pod
  mpiReplicaSpecs:
    Launcher:
      replicas: 1             # Single launcher orchestrates the run
    Worker:
      replicas: 4             # Four workers for parallel computation
```

The launcher pod runs `mpirun -np 4`, which distributes work across the 4 worker pods using SSH. The operator handles:
- SSH key generation and distribution
- Hostfile creation (`/etc/mpi/hostfile`)
- Worker pod readiness gating

#### Deploy the MPI Job

```bash
oc apply -f manifests/mpi-job.yaml
```

Monitor the MPI job:

```bash
# Watch the launcher and workers
oc get pods -l app=mpi-hello-world -w

# Check launcher logs for MPI output
oc logs -l app=mpi-hello-world,role=launcher -f
```

Expected output:

```
Rank 0: PI = 3.141592653589793
Rank 1: PI = 3.141592653589793
Rank 2: PI = 3.141592653589793
Rank 3: PI = 3.141592653589793
```

#### SCC Considerations for MPI

MPI containers typically need SSH daemon access. On OpenShift:

```bash
# If MPI pods fail due to SCC, grant anyuid to the service account
oc adm policy add-scc-to-user anyuid -z default -n batch-hpc-demo

# Verify SCC assignment
oc get pod <mpi-worker-pod> -o jsonpath='{.metadata.annotations.openshift\.io/scc}'
```

This is a security tradeoff. In production, create a custom SCC that grants only the specific capabilities MPI needs rather than the full `anyuid` SCC.

### Step 6: Kueue for Job Queueing and Fair Scheduling

> **Note**: Kueue is available as a community operator or can be installed via OperatorHub on OpenShift 4.13+.

#### Install Kueue

```bash
# Check if Kueue is available in OperatorHub
oc get packagemanifest -n openshift-marketplace | grep kueue

# Or install from upstream:
kubectl apply --server-side -f https://github.com/kubernetes-sigs/kueue/releases/download/v0.6.0/manifests.yaml
```

#### Create Kueue Resources

Apply the ClusterQueue, ResourceFlavors, and LocalQueue:

```bash
oc apply -f manifests/kueue-resources.yaml
```

Verify the setup:

```bash
# Check ClusterQueue
oc get clusterqueue batch-cluster-queue -o wide

# Check LocalQueue
oc get localqueue batch-local-queue

# Check ResourceFlavors
oc get resourceflavor
```

Expected output:

```
NAME                  COHORT   PENDING WORKLOADS
batch-cluster-queue              0

NAME               CLUSTERQUEUE          PENDING WORKLOADS
batch-local-queue  batch-cluster-queue   0
```

#### Submit a Kueue-Managed Job

The key difference from a regular Job: the Job starts with `suspend: true` and carries the `kueue.x-k8s.io/queue-name` label. Kueue evaluates the request against available capacity and unsuspends it when resources are available.

```bash
oc apply -f manifests/kueue-job.yaml
```

Watch Kueue admit the job:

```bash
# The job starts suspended
oc get job kueue-managed-job -o jsonpath='{.spec.suspend}'
# Output: true  (initially)

# Watch Kueue admit it (sets suspend=false)
oc get workloads -w

# Once admitted, pods start running
oc get pods -l app=kueue-managed-job -w
```

#### Monitor Kueue Status

```bash
# Check what workloads are queued / admitted / finished
oc get workloads -o wide

# Check ClusterQueue usage
oc get clusterqueue batch-cluster-queue -o jsonpath='{.status}'

# Check admission events
oc get events --field-selector reason=Admitted
```

## Verification

Run through these checks to confirm the lesson is working correctly:

```bash
# 1. Verify the basic Job completed all 5 indices
oc get job batch-processor -o jsonpath='{.status.succeeded}'
# Expected: 5

# 2. Verify the CronJob exists and has a schedule
oc get cronjob daily-report-generator -o jsonpath='{.spec.schedule}'
# Expected: 0 2 * * *

# 3. Verify the manual test run completed
oc get job manual-test-run -o jsonpath='{.status.conditions[0].type}'
# Expected: Complete

# 4. Verify resource quotas are enforced
oc describe resourcequota batch-workload-quota

# 5. Verify priority classes exist
oc get priorityclasses | grep batch
# Expected: batch-critical, batch-normal, batch-low

# 6. (If Kueue installed) Verify the local queue is connected
oc get localqueue batch-local-queue -o jsonpath='{.spec.clusterQueue}'
# Expected: batch-cluster-queue
```

## Failure Modes and Recovery

### Job Pod Fails Due to SCC

**Symptom**: Pod stuck in `CreateContainerError` or `CrashLoopBackOff` with "permission denied" or "must run as non-root" in events.

**Diagnosis**:
```bash
oc get events --field-selector involvedObject.name=<pod-name>
oc describe pod <pod-name> | grep -A 3 "Security Context"
```

**Recovery**: Either fix the container image to run as non-root (preferred) or grant the appropriate SCC:
```bash
oc adm policy add-scc-to-user anyuid -z <service-account> -n <namespace>
```

### Job Exceeds activeDeadlineSeconds

**Symptom**: Job status shows `Failed` with reason `DeadlineExceeded`. All running pods are terminated.

**Diagnosis**:
```bash
oc get job <job-name> -o jsonpath='{.status.conditions}'
```

**Recovery**: Investigate why the job took longer than expected (resource contention, slow I/O). Increase `activeDeadlineSeconds` or optimize the workload. Resubmit the job -- it is not retried automatically after a deadline failure.

### CronJob Misses Its Schedule

**Symptom**: `LAST SCHEDULE` timestamp is older than expected.

**Diagnosis**:
```bash
oc get cronjob <name> -o jsonpath='{.status.lastScheduleTime}'
oc get events --field-selector involvedObject.name=<cronjob-name>,reason=MissSchedule
```

**Recovery**: If `startingDeadlineSeconds` is set and the window has passed, the run is skipped. This is by design -- stale batch runs may produce incorrect results. If the run is critical, trigger it manually:
```bash
oc create job --from=cronjob/<cronjob-name> recovery-run-$(date +%s)
```

### GPU Not Detected in Pod

**Symptom**: `nvidia-smi` returns "command not found" or no GPUs listed.

**Diagnosis**:
```bash
# Check if the node has GPU resources
oc describe node <node> | grep nvidia.com/gpu

# Check GPU operator pods
oc get pods -n nvidia-gpu-operator

# Check if the device plugin is running on GPU nodes
oc get ds -n nvidia-gpu-operator | grep device-plugin
```

**Recovery**: Verify the GPU Operator is installed and the ClusterPolicy CR is applied. Check that RHCOS has the correct kernel version for the NVIDIA driver. If the driver pod is in `CrashLoopBackOff`, check its logs for kernel module compilation errors.

### Kueue Does Not Admit the Job

**Symptom**: Job stays in `suspend: true` indefinitely.

**Diagnosis**:
```bash
# Check the workload status
oc get workloads -o wide

# Check events for admission failures
oc get events --field-selector reason=Inadmissible

# Check ClusterQueue capacity
oc get clusterqueue batch-cluster-queue -o jsonpath='{.status.flavorsReservation}'
```

**Recovery**: The ClusterQueue may be at capacity. Either wait for running jobs to complete, increase the `nominalQuota`, or preempt lower-priority workloads. If the job's resource request exceeds the queue's maximum, it will never be admitted -- reduce the request or increase the quota.

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Jobs / CronJobs | Native, identical behavior | Identical -- standard K8s resources |
| SCC enforcement | PSA (Pod Security Admission) | SCCs -- stricter defaults, root denied |
| GPU support | Install NVIDIA device plugin manually | NVIDIA GPU Operator via OperatorHub |
| GPU driver management | Manual on each node | Automated by GPU Operator on RHCOS |
| GPU monitoring | Install DCGM exporter manually | Integrated with OpenShift Prometheus |
| MPI operator | Install from Kubeflow manually | Available; SCC grants may be needed |
| Kueue | Install from upstream | Available via OperatorHub (community) |
| Batch image compatibility | Most images work | Must be non-root or grant SCC |
| Node management for HPC | Manual taint/label | MachineSet-driven, automated scaling |
| Priority classes | Manual creation | Same, but integrate with SCC priority |

## Key Takeaways

- **Jobs and CronJobs work identically on OpenShift** -- the API is unchanged. The differences are operational: SCC enforcement, operator-managed GPU drivers, and integrated monitoring.
- **SCC is the primary friction point for batch/HPC workloads.** Many HPC container images assume root access. Use UBI-based images when possible; grant `anyuid` only when necessary and document the security tradeoff.
- **The NVIDIA GPU Operator simplifies GPU node management** on OpenShift by automating driver installation, device plugin deployment, and Prometheus metric export -- all tasks you would handle manually on vanilla Kubernetes.
- **Kueue adds cluster-aware job admission** that prevents batch workloads from overwhelming the cluster. Its ClusterQueue/LocalQueue model maps naturally to OpenShift's multi-tenant project structure.
- **Production batch workloads need defense in depth**: `activeDeadlineSeconds` to prevent runaway jobs, `ttlSecondsAfterFinished` to clean up completed jobs, `ResourceQuota` to limit aggregate consumption, and `PriorityClass` to ensure critical jobs are scheduled first.

## Cleanup

```bash
# Delete all jobs and cronjobs
oc delete job --all -n batch-hpc-demo
oc delete cronjob --all -n batch-hpc-demo

# Delete Kueue resources (if created)
oc delete -f manifests/kueue-job.yaml --ignore-not-found
oc delete -f manifests/kueue-resources.yaml --ignore-not-found

# Delete MPI job (if created)
oc delete -f manifests/mpi-job.yaml --ignore-not-found

# Delete RBAC and quotas
oc delete -f manifests/batch-rbac.yaml --ignore-not-found
oc delete -f manifests/resource-quota-batch.yaml --ignore-not-found

# Delete priority classes (cluster-scoped, requires cluster-admin)
oc delete -f manifests/priority-classes.yaml --ignore-not-found

# Delete the project
oc delete project batch-hpc-demo

# Or use the teardown script:
# ./scripts/teardown.sh
```

## Next Steps

In **L3-M5.1 — Migrating from Kubernetes to OpenShift**, you will take everything you have learned across Levels 1-3 and apply it to a real migration scenario: moving existing Kubernetes workloads to OpenShift. That lesson covers the migration checklist, common pitfalls (SCCs, Routes vs Ingress, image policies), and the Migration Toolkit for Containers (MTC).
