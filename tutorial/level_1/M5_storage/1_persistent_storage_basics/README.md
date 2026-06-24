# L1-M5.1 — Persistent Storage Basics

**Level:** Foundations
**Duration:** 20 min

## Overview

In Kubernetes, you already know that pods are ephemeral -- any data written to a container's filesystem disappears when the pod restarts. Persistent Volumes (PVs), Persistent Volume Claims (PVCs), and StorageClasses solve this by decoupling storage from pod lifecycle. OpenShift uses the exact same PV/PVC/StorageClass model, so your existing knowledge transfers directly. This lesson walks through persistent storage on OpenShift, shows how CRC provides storage out of the box, and demonstrates creating a PVC-backed pod.

## Prerequisites

- Completed: L1-M3.1 (oc new-app & Source-to-Image)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in via `oc login`

## K8s Context

You already know the Kubernetes storage model:

- **PersistentVolume (PV)**: A piece of storage provisioned by an admin or dynamically by a StorageClass. It exists independently of any pod.
- **PersistentVolumeClaim (PVC)**: A request for storage by a user. It binds to a PV that satisfies its size and access mode requirements.
- **StorageClass**: Defines a "class" of storage (e.g., fast SSD, slow HDD). When a PVC references a StorageClass, the provisioner creates the PV automatically (dynamic provisioning).

In vanilla Kubernetes, you typically install a CSI driver and create StorageClasses yourself. Nothing is provided out of the box -- the cluster has no opinion about where your storage comes from.

## Concepts

### Persistent Storage on OpenShift -- What Is the Same

The core storage API is identical between Kubernetes and OpenShift. PVs, PVCs, and StorageClasses use the same `apiVersion`, `kind`, and `spec` fields. If you have existing PVC manifests from Kubernetes, they work on OpenShift without modification.

### What OpenShift Adds

**Default StorageClass in CRC**: OpenShift Local (CRC) ships with a pre-configured StorageClass so you can start using persistent storage immediately without installing any CSI drivers. In CRC, this is typically backed by local storage on the single-node cluster.

**`oc set volume` shortcut**: OpenShift provides `oc set volume` to attach PVCs to Deployments without editing YAML. This is a convenience -- it modifies the Deployment spec for you.

**Web Console integration**: The Administrator perspective provides a dedicated Storage section where you can create and manage PVCs, view PV bindings, and check StorageClasses -- all without touching the CLI.

### Dynamic Provisioning

When a StorageClass has a provisioner configured, creating a PVC automatically provisions the underlying PV. This is the standard approach in both Kubernetes and OpenShift. In CRC, the default StorageClass handles this for you, so you never need to manually create PVs.

### Access Modes

PVCs specify how the volume can be mounted:

| Access Mode | Short Name | Meaning |
|-------------|-----------|---------|
| ReadWriteOnce | RWO | Mounted read-write by a single node |
| ReadOnlyMany | ROX | Mounted read-only by many nodes |
| ReadWriteMany | RWX | Mounted read-write by many nodes |

CRC's local storage only supports **RWO**. Production OpenShift clusters with shared storage (NFS, Ceph/ODF, etc.) support RWX.

## Step-by-Step

### Step 1: Create a Project for This Lesson

Create a dedicated project for storage experiments:

```bash
oc new-project l1-m5-storage --display-name="L1-M5: Storage Demo"
```

Expected output:
```
Now using project "l1-m5-storage" on server "https://api.crc.testing:6443".
```

### Step 2: Explore the Default StorageClass

Check what StorageClasses are available in your cluster:

```bash
oc get storageclasses
```

Expected output (CRC):
```
NAME                          PROVISIONER                    RECLAIMPOLICY   VOLUMEBINDINGMODE      ALLOWVOLUMEEXPANSION   AGE
crc-csi-hostpath-provisioner  kubevirt.io.hostpath-provisioner  Delete       WaitForFirstConsumer   false                  30d
```

The `(default)` annotation may appear next to the name, indicating this StorageClass is used when a PVC does not specify one. Inspect it:

```bash
oc get storageclass crc-csi-hostpath-provisioner -o yaml
```

Key fields to note:

- **provisioner**: The CSI driver that creates volumes. In CRC this is a hostpath provisioner (storage on the node's local disk).
- **reclaimPolicy**: `Delete` means the PV is deleted when the PVC is deleted. In production you might use `Retain`.
- **volumeBindingMode**: `WaitForFirstConsumer` means the PV is not created until a pod actually needs it.

### Step 3: Check Existing PVs and PVCs

See if any PVs or PVCs already exist in the cluster:

```bash
# PVs are cluster-scoped (not namespaced)
oc get pv
```

```bash
# PVCs are namespaced -- check the current project
oc get pvc
```

Your new project will have no PVCs yet. The cluster may have PVs from system components.

### Step 4: Create a PVC

Apply the PVC manifest from this lesson's `manifests/` directory:

```bash
oc apply -f manifests/pvc.yaml
```

The manifest requests 1Gi of storage with ReadWriteOnce access:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: storage-demo-pvc
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
oc get pvc storage-demo-pvc
```

Expected output:
```
NAME               STATUS    VOLUME   CAPACITY   ACCESS MODES   STORAGECLASS                   AGE
storage-demo-pvc   Pending                                      crc-csi-hostpath-provisioner    5s
```

The status shows `Pending` because the StorageClass uses `WaitForFirstConsumer` -- the PV will not be created until a pod mounts this PVC.

### Step 5: Create a Pod That Mounts the PVC

Apply the pod manifest that mounts the PVC:

```bash
oc apply -f manifests/pod-with-pvc.yaml
```

The manifest creates a pod that mounts the PVC at `/data`:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: storage-demo-pod
  labels:
    app: storage-demo
    tutorial-level: "1"
    tutorial-module: "M5"
spec:
  containers:
    - name: busybox
      image: busybox:latest
      command: ["sleep", "3600"]
      volumeMounts:
        - name: demo-storage
          mountPath: /data
  volumes:
    - name: demo-storage
      persistentVolumeClaim:
        claimName: storage-demo-pvc
```

Wait for the pod to start:

```bash
oc get pod storage-demo-pod -w
```

Press `Ctrl+C` once the status shows `Running`.

### Step 6: Verify the PVC Is Now Bound

Now that a pod is consuming the PVC, the provisioner creates the PV and binds it:

```bash
oc get pvc storage-demo-pvc
```

Expected output:
```
NAME               STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS                   AGE
storage-demo-pvc   Bound    pvc-a1b2c3d4-e5f6-7890-abcd-ef1234567890   1Gi        RWO            crc-csi-hostpath-provisioner   1m
```

The status is now `Bound` and a PV has been automatically created. Inspect the PV:

```bash
oc get pv
```

### Step 7: Write and Read Data in the Persistent Volume

Write some data to the mounted volume:

```bash
oc exec storage-demo-pod -- sh -c 'echo "Hello from OpenShift persistent storage" > /data/test.txt'
```

Read it back:

```bash
oc exec storage-demo-pod -- cat /data/test.txt
```

Expected output:
```
Hello from OpenShift persistent storage
```

### Step 8: Prove Persistence Across Pod Restarts

Delete the pod and recreate it. The data should survive because it lives on the PV, not in the container:

```bash
# Delete the pod (the PVC and PV remain)
oc delete pod storage-demo-pod
```

```bash
# Verify the PVC is still Bound
oc get pvc storage-demo-pvc
```

```bash
# Recreate the pod
oc apply -f manifests/pod-with-pvc.yaml
```

Wait for the new pod to start, then read the data:

```bash
oc exec storage-demo-pod -- cat /data/test.txt
```

Expected output:
```
Hello from OpenShift persistent storage
```

The data persisted across pod deletion and recreation -- this is the whole point of PVs and PVCs.

### Step 9: Inspect Storage via the Web Console (Optional)

Open the OpenShift Web Console:

1. Navigate to **Administrator** perspective.
2. Go to **Storage > PersistentVolumeClaims**.
3. Select the `l1-m5-storage` project.
4. Click on `storage-demo-pvc` to see its details: status, capacity, access modes, bound PV, and which pod is using it.
5. Go to **Storage > PersistentVolumes** to see the dynamically provisioned PV.
6. Go to **Storage > StorageClasses** to see the available classes.

## Verification

Confirm everything is working:

```bash
# 1. PVC is Bound
oc get pvc storage-demo-pvc -o jsonpath='{.status.phase}'
```

Expected output: `Bound`

```bash
# 2. Pod is Running
oc get pod storage-demo-pod -o jsonpath='{.status.phase}'
```

Expected output: `Running`

```bash
# 3. Data is accessible
oc exec storage-demo-pod -- cat /data/test.txt
```

Expected output: `Hello from OpenShift persistent storage`

```bash
# 4. PV exists and is Bound
oc get pv -l app=storage-demo 2>/dev/null || oc get pv | grep storage-demo-pvc
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| PV/PVC API | `v1` PersistentVolume, PersistentVolumeClaim | Identical -- same API, same fields |
| StorageClass API | `storage.k8s.io/v1` StorageClass | Identical |
| Default StorageClass | None -- must install CSI driver and create one | CRC ships with a default StorageClass |
| Dynamic provisioning | Requires CSI driver setup | Same, but CRC pre-configures one |
| Attach volume to Deployment | Edit YAML manually | `oc set volume` shortcut (or edit YAML) |
| Web Console for storage | Basic dashboard (if installed) | Full Storage section in Administrator perspective |
| CLI for storage inspection | `kubectl get pv,pvc,sc` | `oc get pv,pvc,sc` (identical) |
| Storage backends | Any CSI driver | Same CSI drivers + OpenShift Data Foundation (ODF) |

## Key Takeaways

- **PVs, PVCs, and StorageClasses work identically on OpenShift and Kubernetes.** Your existing manifests and knowledge transfer without changes.
- **CRC provides a default StorageClass** so you can use persistent storage immediately without installing CSI drivers.
- **Dynamic provisioning** automatically creates PVs when you create a PVC that references a StorageClass. You rarely need to create PVs manually.
- **Data survives pod deletion** as long as the PVC exists. The PV holds the data independently of any pod.
- **OpenShift adds convenience, not complexity**: `oc set volume` and the Web Console's Storage section make storage management easier, but the underlying model is pure Kubernetes.

## Cleanup

Remove all resources created in this lesson:

```bash
# Delete the entire project (removes all resources within it)
oc delete project l1-m5-storage
```

If you prefer to delete resources selectively:

```bash
# Delete the pod first (releases the PVC)
oc delete pod storage-demo-pod

# Delete the PVC (the PV will be deleted automatically due to reclaimPolicy: Delete)
oc delete pvc storage-demo-pvc
```

## Next Steps

In **L1-M5.2 -- OpenShift-Specific Storage**, you will explore what OpenShift adds beyond the standard Kubernetes storage model: OpenShift Data Foundation (ODF), CSI driver management, the `oc set volume` shortcut for attaching storage to Deployments, and storage considerations for production clusters.
