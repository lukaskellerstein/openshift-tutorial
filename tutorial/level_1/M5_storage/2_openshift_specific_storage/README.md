# L1-M5.2 — OpenShift-Specific Storage

**Level:** Foundations
**Duration:** 30 min

## Overview

In the previous lesson you worked with PersistentVolumes, PersistentVolumeClaims, and StorageClasses — all standard Kubernetes constructs. OpenShift builds on this foundation with its own storage ecosystem: OpenShift Data Foundation (ODF), tighter CSI driver integration, and the `oc set volume` convenience command. This lesson shows what OpenShift adds to Kubernetes storage, why it matters, and how to use it.

## Prerequisites

- Completed: L1-M5.1 (Persistent Storage Basics)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in via `oc login`

## K8s Context

In vanilla Kubernetes, persistent storage works through three layers:

1. **StorageClasses** define the provisioner (e.g., `kubernetes.io/aws-ebs`, `csi-driver-nfs`).
2. **PersistentVolumes (PVs)** represent actual storage — either pre-provisioned by an admin or dynamically created by a StorageClass.
3. **PersistentVolumeClaims (PVCs)** are how pods request storage.

CSI (Container Storage Interface) is the standard plugin mechanism. You install a CSI driver, register it as a StorageClass, and then create PVCs against it. Dynamic provisioning happens automatically when a PVC references a StorageClass with a CSI provisioner.

In Kubernetes, attaching a volume to a running Deployment means editing the Deployment YAML: adding a `volumes` entry and a `volumeMounts` entry inside the container spec. There is no shortcut command.

## Concepts

### OpenShift Data Foundation (ODF)

OpenShift Data Foundation (formerly OpenShift Container Storage / OCS) is Red Hat's software-defined storage solution for OpenShift. It is an operator-managed deployment of **Ceph** that provides:

- **Block storage** (RBD) — `ocs-storagecluster-ceph-rbd` StorageClass
- **Shared filesystem** (CephFS) — `ocs-storagecluster-cephfs` StorageClass
- **Object storage** (S3-compatible via RADOS Gateway) — accessible via the `ObjectBucketClaim` CRD

**Architecture:**

```
+---------------------------------------------+
|          OpenShift Data Foundation           |
|                                              |
|  +----------+  +---------+  +------------+  |
|  | Ceph RBD |  | CephFS  |  | RADOS GW   |  |
|  | (Block)  |  | (File)  |  | (Object/S3)|  |
|  +----------+  +---------+  +------------+  |
|                                              |
|  Managed by the ODF Operator (Rook-Ceph)     |
+---------------------------------------------+
|           Worker / Storage Nodes             |
+---------------------------------------------+
```

**Why does OpenShift provide this?** In Kubernetes, you bring your own storage backend. In production OpenShift clusters, ODF provides a fully integrated, operator-managed storage layer so teams do not need to set up and maintain external storage systems separately. It is a Ceph cluster running inside OpenShift, managed as an operator.

> **Note:** ODF requires dedicated storage nodes and significant resources. It is NOT available in CRC or the Developer Sandbox. This lesson explains the architecture and shows the PVC patterns so you recognize them in production clusters. The hands-on exercises use CRC's built-in storage.

### CSI Drivers on OpenShift

OpenShift ships with pre-installed CSI drivers for major cloud providers and includes the CSI driver operator for lifecycle management:

| Platform | CSI Driver | StorageClass |
|----------|-----------|--------------|
| AWS | EBS CSI | `gp3-csi`, `gp2-csi` |
| Azure | Azure Disk CSI | `managed-csi` |
| GCP | PD CSI | `standard-csi` |
| vSphere | vSphere CSI | `thin-csi` |
| CRC (local) | hostpath / LVM | varies |

In Kubernetes, you install CSI drivers yourself with Helm charts or raw manifests. OpenShift installs and manages them via cluster operators — they are available out of the box for supported platforms.

### Dynamic Provisioning

Dynamic provisioning works identically to Kubernetes: a PVC referencing a StorageClass triggers the CSI driver to create a PV automatically. OpenShift clusters always have a **default StorageClass** set, so PVCs without an explicit `storageClassName` still get dynamically provisioned.

### `oc set volume` — The OpenShift Shortcut

This is a pure OpenShift convenience command with no `kubectl` equivalent. Instead of manually editing YAML to add volume mounts, `oc set volume` modifies a Deployment (or Pod, etc.) in place:

```bash
# In Kubernetes, you would:
# 1. Edit the Deployment YAML to add a volumes[] entry
# 2. Edit the container spec to add a volumeMounts[] entry
# 3. kubectl apply -f deployment.yaml

# In OpenShift, one command does it all:
oc set volume deployment/my-app --add \
  --type=persistentVolumeClaim \
  --claim-name=my-pvc \
  --mount-path=/data
```

This command patches the Deployment to include the volume and volume mount, then triggers a rollout — all in a single step.

## Step-by-Step

### Step 1: Explore the Default StorageClass

Every OpenShift cluster has a default StorageClass. Let's see what is available.

```bash
oc get storageclasses
```

Expected output (CRC):

```
NAME                             PROVISIONER                        RECLAIMPOLICY   VOLUMEBINDINGMODE      ALLOWVOLUMEEXPANSION   AGE
crc-csi-hostpath-provisioner (default)   kubevirt.io.hostpath-provisioner   Delete          WaitForFirstConsumer   false                  30d
```

The `(default)` annotation means PVCs without an explicit `storageClassName` will use this class. Check the annotation:

```bash
oc get storageclass crc-csi-hostpath-provisioner -o jsonpath='{.metadata.annotations.storageclass\.kubernetes\.io/is-default-class}'
```

Expected output:

```
true
```

### Step 2: Create a Project

```bash
oc new-project storage-lesson
```

### Step 3: Create a CSI-Based PVC

Apply the PVC manifest that uses the default StorageClass for dynamic provisioning:

```bash
oc apply -f manifests/csi-pvc.yaml
```

```yaml
# manifests/csi-pvc.yaml — PVC using dynamic provisioning via the default CSI StorageClass
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: csi-dynamic-pvc
  labels:
    app: storage-demo
    tutorial-level: "1"
    tutorial-module: "M5"
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
```

Check the PVC status:

```bash
oc get pvc csi-dynamic-pvc
```

Expected output (CRC with `WaitForFirstConsumer` binding mode):

```
NAME              STATUS    VOLUME   CAPACITY   ACCESS MODES   STORAGECLASS                   AGE
csi-dynamic-pvc   Pending                                      crc-csi-hostpath-provisioner    5s
```

The PVC is `Pending` because the CRC StorageClass uses `WaitForFirstConsumer` — the PV will not be created until a Pod actually mounts the PVC. This is normal and expected.

### Step 4: Deploy an App That Uses the PVC

Apply the Deployment manifest:

```bash
oc apply -f manifests/app-with-pvc.yaml
```

```yaml
# manifests/app-with-pvc.yaml — Deployment that mounts the CSI-provisioned PVC
apiVersion: apps/v1
kind: Deployment
metadata:
  name: storage-demo
  labels:
    app: storage-demo
    tutorial-level: "1"
    tutorial-module: "M5"
spec:
  replicas: 1
  selector:
    matchLabels:
      app: storage-demo
  template:
    metadata:
      labels:
        app: storage-demo
    spec:
      containers:
        - name: writer
          image: registry.access.redhat.com/ubi9/ubi-minimal:latest
          command: ["/bin/sh", "-c"]
          args:
            - |
              echo "Written at $(date)" > /data/timestamp.txt
              echo "Storage demo running. Data written to /data/timestamp.txt"
              sleep infinity
          volumeMounts:
            - name: data-volume
              mountPath: /data
      volumes:
        - name: data-volume
          persistentVolumeClaim:
            claimName: csi-dynamic-pvc
```

Wait for the pod to start:

```bash
oc rollout status deployment/storage-demo --timeout=120s
```

Now check the PVC again — it should be `Bound`:

```bash
oc get pvc csi-dynamic-pvc
```

Expected output:

```
NAME              STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS                   AGE
csi-dynamic-pvc   Bound    pvc-a1b2c3d4-...                           1Gi        RWO            crc-csi-hostpath-provisioner    60s
```

The CSI driver dynamically created a PV and bound it to the PVC when the Pod was scheduled.

### Step 5: Write and Read Data

Verify the volume is working by reading the file the app wrote:

```bash
oc exec deployment/storage-demo -- cat /data/timestamp.txt
```

Expected output:

```
Written at Tue Jun 24 12:00:00 UTC 2026
```

Write additional data:

```bash
oc exec deployment/storage-demo -- sh -c 'echo "Persistent data survives restarts" >> /data/timestamp.txt'
```

### Step 6: Use `oc set volume` to Add a Volume

Now let's see the OpenShift shortcut. First, create a second Deployment without any volumes:

```bash
oc apply -f manifests/app-no-volume.yaml
```

```yaml
# manifests/app-no-volume.yaml — Deployment with no volumes (we will add one via oc set volume)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: volume-demo
  labels:
    app: volume-demo
    tutorial-level: "1"
    tutorial-module: "M5"
spec:
  replicas: 1
  selector:
    matchLabels:
      app: volume-demo
  template:
    metadata:
      labels:
        app: volume-demo
    spec:
      containers:
        - name: app
          image: registry.access.redhat.com/ubi9/ubi-minimal:latest
          command: ["sleep", "infinity"]
```

Wait for it to start:

```bash
oc rollout status deployment/volume-demo --timeout=120s
```

Now use `oc set volume` to add a new PVC and mount it — all in one command:

```bash
oc set volume deployment/volume-demo \
  --add \
  --type=persistentVolumeClaim \
  --claim-name=auto-pvc \
  --claim-size=512Mi \
  --mount-path=/app-data \
  --name=app-storage
```

Expected output:

```
deployment.apps/volume-demo volume updated
```

This single command:
1. Created a new PVC named `auto-pvc` (512Mi)
2. Added a `volumes` entry to the Deployment spec
3. Added a `volumeMounts` entry to the container spec
4. Triggered a rollout of the Deployment

Verify the PVC was created:

```bash
oc get pvc auto-pvc
```

Verify the volume mount is in the Deployment:

```bash
oc get deployment volume-demo -o jsonpath='{.spec.template.spec.containers[0].volumeMounts}' | python3 -m json.tool
```

Expected output:

```json
[
    {
        "mountPath": "/app-data",
        "name": "app-storage"
    }
]
```

### Step 7: Other `oc set volume` Operations

**List volumes** on a Deployment:

```bash
oc set volume deployment/volume-demo --list
```

Expected output:

```
deployments/volume-demo
  pvc/auto-pvc (allocated 512Mi) as app-storage
    mounted at /app-data
```

**Add an emptyDir volume** (temporary, pod-lifetime storage):

```bash
oc set volume deployment/volume-demo \
  --add \
  --type=emptyDir \
  --mount-path=/tmp/cache \
  --name=cache-vol
```

**Add a ConfigMap as a volume**:

```bash
# First create a ConfigMap
oc create configmap app-config --from-literal=setting=value

# Then mount it
oc set volume deployment/volume-demo \
  --add \
  --type=configmap \
  --configmap-name=app-config \
  --mount-path=/etc/config \
  --name=config-vol
```

**Remove a volume**:

```bash
oc set volume deployment/volume-demo \
  --remove \
  --name=cache-vol
```

### Step 8: Create a PVC with an Explicit StorageClass

In production OpenShift clusters with ODF, you would specify a StorageClass explicitly. Here is what an ODF-targeted PVC looks like:

```bash
oc apply -f manifests/odf-pvc-block.yaml
```

```yaml
# manifests/odf-pvc-block.yaml — PVC targeting ODF block storage (Ceph RBD)
# NOTE: This requires ODF to be installed. On CRC, this will remain Pending.
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: odf-block-pvc
  labels:
    app: odf-demo
    tutorial-level: "1"
    tutorial-module: "M5"
spec:
  storageClassName: ocs-storagecluster-ceph-rbd
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 5Gi
```

And a CephFS-based PVC for shared filesystem access:

```bash
oc apply -f manifests/odf-pvc-filesystem.yaml
```

```yaml
# manifests/odf-pvc-filesystem.yaml — PVC targeting ODF shared filesystem (CephFS)
# NOTE: This requires ODF to be installed. On CRC, this will remain Pending.
# CephFS supports ReadWriteMany (RWX), allowing multiple pods to mount the same volume.
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: odf-filesystem-pvc
  labels:
    app: odf-demo
    tutorial-level: "1"
    tutorial-module: "M5"
spec:
  storageClassName: ocs-storagecluster-cephfs
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 5Gi
```

> **Note:** These PVCs will remain `Pending` on CRC because ODF is not installed. They are included to show the pattern you will encounter on production clusters. The key differences:
> - `ocs-storagecluster-ceph-rbd` provides block storage (RWO) — like an EBS volume.
> - `ocs-storagecluster-cephfs` provides a shared filesystem (RWX) — multiple pods can mount it simultaneously.

Check their status:

```bash
oc get pvc -l app=odf-demo
```

Expected output (CRC, no ODF):

```
NAME                  STATUS    VOLUME   CAPACITY   ACCESS MODES   STORAGECLASS                    AGE
odf-block-pvc         Pending                                      ocs-storagecluster-ceph-rbd     10s
odf-filesystem-pvc    Pending                                      ocs-storagecluster-cephfs       10s
```

## Verification

Run these commands to verify the lesson worked:

```bash
# 1. Check that the dynamically provisioned PVC is Bound
oc get pvc csi-dynamic-pvc -o jsonpath='{.status.phase}'
# Expected: Bound

# 2. Verify data persists in the volume
oc exec deployment/storage-demo -- cat /data/timestamp.txt
# Expected: Shows timestamp and "Persistent data survives restarts"

# 3. Verify oc set volume created the auto-pvc
oc get pvc auto-pvc -o jsonpath='{.status.phase}'
# Expected: Bound

# 4. List volumes on the volume-demo Deployment
oc set volume deployment/volume-demo --list
# Expected: Shows app-storage (pvc/auto-pvc) and config-vol (configmap/app-config)

# 5. Confirm ODF PVCs are Pending (expected on CRC)
oc get pvc -l app=odf-demo -o custom-columns=NAME:.metadata.name,STATUS:.status.phase
# Expected: Both Pending (no ODF on CRC)
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| CSI driver installation | Manual (Helm chart or manifests) | Pre-installed via cluster operators |
| Default StorageClass | Depends on the cluster setup | Always configured on supported platforms |
| Software-defined storage | External (Rook-Ceph, Longhorn, etc.) | ODF operator (Ceph-based, fully integrated) |
| Object storage (S3) | External (MinIO, etc.) | ODF provides `ObjectBucketClaim` CRD |
| Adding volumes to workloads | Edit YAML manually | `oc set volume` one-liner or edit YAML |
| Volume listing | `kubectl describe deployment` and parse output | `oc set volume --list` shows clean summary |
| Storage monitoring | Set up yourself | Built into the Web Console (ODF dashboard) |

## Key Takeaways

- **ODF is OpenShift's integrated storage platform** — a Ceph cluster managed by an operator that provides block (RBD), file (CephFS), and object (S3-compatible) storage. It requires dedicated nodes and is not available on CRC.
- **CSI drivers are pre-installed on OpenShift** for supported platforms, unlike Kubernetes where you install and manage them yourself.
- **`oc set volume` is a powerful shortcut** — it creates PVCs, adds volume mounts, and triggers rollouts in a single command. There is no `kubectl` equivalent.
- **Dynamic provisioning works the same way as Kubernetes** — PVCs reference a StorageClass, and the CSI driver creates the PV automatically. OpenShift always has a default StorageClass configured.
- **CephFS (via ODF) enables ReadWriteMany (RWX) access** — multiple pods can share the same filesystem volume, which is critical for stateful workloads that need shared storage.

## Cleanup

```bash
# Delete the ODF demo PVCs (they are just Pending, no resources consumed)
oc delete pvc -l app=odf-demo

# Delete the volume-demo Deployment and its auto-created PVC
oc delete deployment volume-demo
oc delete pvc auto-pvc
oc delete configmap app-config

# Delete the storage-demo Deployment and its PVC
oc delete deployment storage-demo
oc delete pvc csi-dynamic-pvc

# Delete the project
oc delete project storage-lesson
```

## Next Steps

In **L1-M5.3 — ConfigMaps & Secrets**, you will learn how OpenShift handles configuration data and sensitive values. You already know ConfigMaps and Secrets from Kubernetes — the lesson covers `oc create configmap` and `oc create secret` shortcuts, plus how to link Secrets to ServiceAccounts for image pull credentials and other OpenShift-specific patterns.
