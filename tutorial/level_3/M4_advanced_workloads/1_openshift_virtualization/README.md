# L3-M4.1 — OpenShift Virtualization (KubeVirt)

**Level:** Expert
**Duration:** 1 hr

## Overview

You know how to run containers on Kubernetes. But what about virtual machines? OpenShift Virtualization (based on the upstream KubeVirt project, commercially branded as Container-Native Virtualization / CNV) lets you run full VMs as first-class citizens alongside containers on the same cluster, managed by the same API, and scheduled by the same scheduler. In this lesson you will install the OpenShift Virtualization operator, create and manage VMs using the `VirtualMachine` and `VirtualMachineInstance` CRDs, perform live migration, take snapshots, and explore the production use cases that make this capability essential for enterprises running legacy Windows workloads and stateful database servers.

## Prerequisites

- Completed: L3-M1 (Cluster Administration) — you need cluster-admin access and familiarity with operators, node management, and storage configuration.
- Completed: L2-M2 (Operators) — understanding of OLM, Subscriptions, and CSVs.
- Completed: L1-M4 (Networking & Routes) — familiarity with Services, Routes, and network policies.
- Completed: L1-M5 (Storage) — understanding of PVs, PVCs, and StorageClasses.
- OpenShift cluster running (CRC with nested virtualization, bare metal, or cloud with metal instances). **CRC requires that your host supports nested virtualization.**
- Hardware virtualization enabled (VT-x / AMD-V) on cluster nodes.
- At least 16 GB RAM available on your cluster for VM workloads.

> **Important:** CRC on macOS with Apple Silicon uses HVF (Hypervisor Framework) which does support nested virtualization. On Intel Macs or Linux hosts, ensure VT-x and nested virtualization are enabled in BIOS/hypervisor settings. Some cloud instances (e.g., AWS `*.metal`) provide bare-metal access needed for KVM.

## K8s Context

In vanilla Kubernetes, running virtual machines is possible but requires significant manual effort. The KubeVirt project provides CRDs and controllers that extend the Kubernetes API to manage VMs, but you must install and configure everything yourself: the operator, CDI (Containerized Data Importer) for disk management, networking plugins for VM connectivity, and storage integrations for live migration. There is no out-of-the-box Web Console integration, no opinionated storage configuration, and no certified support.

If you have used KubeVirt upstream, you know the core CRDs: `VirtualMachine` (the persistent spec, like a Deployment), `VirtualMachineInstance` (the running VM, like a Pod), and `VirtualMachineInstanceReplicaSet` (scaling VMs, rarely used). OpenShift Virtualization builds on this foundation but adds significant enterprise capabilities.

## Concepts

### What OpenShift Virtualization Adds

OpenShift Virtualization is Red Hat's productized, supported distribution of KubeVirt. It goes well beyond what you get by installing KubeVirt on vanilla Kubernetes:

1. **HyperConverged Operator** — A single CR (`HyperConverged`) deploys and manages all sub-components: KubeVirt, CDI, Hostpath Provisioner, networking plugins, and the web console integration. In upstream K8s, you would install each component separately.

2. **Web Console Integration** — Full VM management from the OpenShift Console: create VMs from templates, access VNC/serial consoles, monitor VM metrics, trigger live migrations, and take snapshots. The Developer and Administrator perspectives both expose VM workflows.

3. **Certified Templates** — Pre-built VM templates for RHEL, CentOS, Fedora, and Windows Server. These templates include tuned resource profiles, correct device configurations (VirtIO drivers, TPM for Windows 11), and cloud-init presets.

4. **CDI (Containerized Data Importer)** — Automates importing VM disk images from container registries, HTTP servers, or existing PVCs into new PVCs. Handles format conversion (qcow2 to raw) transparently.

5. **Live Migration** — Move running VMs between nodes with zero downtime. OpenShift configures the dedicated migration network, bandwidth limits, and convergence strategies. Migration policies let you define per-workload migration behavior.

6. **Snapshots and Restore** — Point-in-time snapshots of VM disks and configuration using the CSI VolumeSnapshot API. Restore a VM to a previous state without manual PVC manipulation.

7. **Secondary Networks** — Multus-based secondary network interfaces let VMs connect to external VLANs, bridge networks, or SR-IOV interfaces alongside the pod network. This is critical for VMs that need L2 connectivity to legacy infrastructure.

### Architecture

```
+------------------------------------------------------------------+
|                     OpenShift Cluster                             |
|                                                                   |
|  +-----------------------------+  +----------------------------+  |
|  |     openshift-cnv namespace |  |   virtualization-lab       |  |
|  |                             |  |                            |  |
|  |  HyperConverged CR          |  |  VirtualMachine            |  |
|  |    |                        |  |    |                       |  |
|  |    +-> KubeVirt             |  |    +-> VirtualMachine-     |  |
|  |    |    +-> virt-controller  |  |        Instance (VMI)     |  |
|  |    |    +-> virt-api        |  |         |                  |  |
|  |    |    +-> virt-handler*   |  |         +-> QEMU/KVM       |  |
|  |    |                        |  |              Process       |  |
|  |    +-> CDI                  |  |                            |  |
|  |    |    +-> cdi-controller  |  |  DataVolume --> PVC        |  |
|  |    |    +-> cdi-uploadproxy |  |                            |  |
|  |    |                        |  |  Service --> Route         |  |
|  |    +-> NetworkAddons        |  |  (VM networking)           |  |
|  |         +-> bridge plugin   |  |                            |  |
|  |         +-> macvtap plugin  |  +----------------------------+  |
|  +-----------------------------+                                  |
|                                                                   |
|  Per Node:                                                        |
|  +-----------------------------+  +----------------------------+  |
|  |  Worker Node 1              |  |  Worker Node 2             |  |
|  |                             |  |                            |  |
|  |  virt-handler (DaemonSet)   |  |  virt-handler (DaemonSet)  |  |
|  |  virt-launcher pod:         |  |  virt-launcher pod:        |  |
|  |    +-> libvirtd             |  |    +-> libvirtd            |  |
|  |    +-> QEMU (fedora-vm)     |  |    +-> QEMU (persistent-  |  |
|  |    +-> /dev/kvm             |  |         vm)                |  |
|  |                             |  |    +-> /dev/kvm            |  |
|  +-----------------------------+  +----------------------------+  |
+------------------------------------------------------------------+

* virt-handler runs as a DaemonSet on every schedulable node
```

### VirtualMachine vs VirtualMachineInstance

This distinction is the single most important concept to understand:

| Resource | Analogy | Purpose |
|----------|---------|---------|
| `VirtualMachine` (VM) | Deployment | Persistent specification. Survives VM shutdown. Controls desired state (`running: true/false`). |
| `VirtualMachineInstance` (VMI) | Pod | The actual running VM. Created/deleted by the VM controller. Inspect for runtime status (IP, node, phase). |

When you set `spec.running: true` on a VM, the controller creates a VMI. When you stop the VM, the VMI is deleted but the VM resource remains. This is different from pods, where deleting the pod deletes the workload (unless a Deployment recreates it).

### VM Lifecycle

```
                    +-------+
         create --> | Stopped |
                    +----+----+
                         |
                  virtctl start
                         |
                    +----v----+
                    | Starting |
                    +----+----+
                         |
                    +----v----+      live migrate      +----------+
                    | Running  | ------------------->  | Migrating |
                    +----+----+                        +-----+----+
                         |                                   |
                  virtctl stop                          completed
                         |                                   |
                    +----v----+                        +-----v----+
                    | Stopping |                       | Running   |
                    +----+----+                        | (new node)|
                         |                             +----------+
                    +----v----+
                    | Stopped  |
                    +----------+
```

### Storage Considerations for VMs

VMs need persistent, block-mode storage that supports:

- **ReadWriteMany (RWX)** — required for live migration (the disk must be accessible from both source and target nodes simultaneously during migration).
- **Block volume mode** — VMs perform better with raw block devices than filesystem-based PVCs.
- **VolumeSnapshots** — required for VM snapshot/restore functionality.

OpenShift Data Foundation (ODF/Ceph) provides all three. On bare metal without ODF, you can use NFS (RWX but poor performance) or local storage (no live migration).

| Storage Backend | RWX | Block Mode | Snapshots | Live Migration |
|----------------|-----|-----------|-----------|----------------|
| ODF (Ceph RBD) | Yes | Yes | Yes | Yes |
| NFS | Yes | No | No | Yes (slow) |
| Local Storage | No | Yes | No | No |
| AWS EBS | No | Yes | Yes | No |
| vSphere VMDK | No | Yes | No | No |

### Why Run VMs on OpenShift?

This is the key strategic question. The answer is not "replace VMware" — it is "converge your operational model."

1. **Legacy Windows applications** — .NET Framework apps, SQL Server instances, and Active Directory domain controllers that cannot be containerized. Run them as VMs alongside your containerized microservices, managed by the same CI/CD and monitoring stack.

2. **Database servers** — Some database workloads (Oracle, SQL Server, legacy PostgreSQL deployments) perform better or are only supported in VMs. Run them as VMs with persistent storage while your application tier runs as containers.

3. **Lift-and-shift migration** — Move VMs from VMware/Hyper-V to OpenShift as the first step in modernization. The VM runs as-is; you refactor it later.

4. **Unified operations** — One platform, one API, one monitoring stack, one RBAC model, one CI/CD pipeline for both containers and VMs. This reduces operational complexity significantly.

5. **Development/test environments** — Spin up short-lived VMs for testing kernel modules, OS-level configurations, or software that requires a full OS.

## Step-by-Step

### Step 1: Install the OpenShift Virtualization Operator

The operator must be installed cluster-wide by a cluster-admin. Log in as `kubeadmin` (not `developer`).

```bash
# Log in as cluster-admin
oc login -u kubeadmin -p <password> https://api.crc.testing:6443

# Verify your access
oc auth can-i create subscription -n openshift-cnv
# Expected: yes
```

Create the namespace and install the operator:

```bash
# Create the operator namespace
oc create namespace openshift-cnv

# Apply the OperatorGroup (targets all namespaces)
oc apply -f manifests/cnv-operator-group.yaml

# Apply the Subscription (manual approval for production safety)
oc apply -f manifests/cnv-subscription.yaml
```

Wait for the InstallPlan and approve it:

```bash
# Watch for the InstallPlan to appear
oc get installplan -n openshift-cnv -w

# When it appears, approve it
INSTALL_PLAN=$(oc get installplan -n openshift-cnv \
  -o jsonpath='{.items[?(@.spec.approved==false)].metadata.name}')
oc patch installplan "${INSTALL_PLAN}" -n openshift-cnv \
  --type merge -p '{"spec":{"approved":true}}'

# Wait for the CSV to report Succeeded
oc get csv -n openshift-cnv -w
```

> **Automation:** The `scripts/setup-cnv-operator.sh` script automates these steps, including the InstallPlan approval wait loop.

Alternatively, install via the Web Console:
1. Navigate to **Operators > OperatorHub**.
2. Search for "OpenShift Virtualization".
3. Select the operator, choose **stable** channel, and set approval to **Manual**.
4. Click **Install**, then approve the InstallPlan when prompted.

### Step 2: Activate KubeVirt with the HyperConverged CR

The operator is installed, but KubeVirt is not active until you create the `HyperConverged` CR. This single resource controls the deployment of all sub-components.

```bash
# Apply the HyperConverged CR
oc apply -f manifests/hyperconverged.yaml

# Watch all pods come up (this takes 3-5 minutes)
oc get pods -n openshift-cnv -w
```

Wait until all components are running:

```bash
# Verify the HyperConverged CR is available
oc get hyperconverged kubevirt-hyperconverged -n openshift-cnv \
  -o jsonpath='{.status.conditions[?(@.type=="Available")].status}'
# Expected: True

# Verify KubeVirt is deployed
oc get kubevirt -n openshift-cnv
# Expected: kubevirt-kubevirt-hyperconverged   Deployed   ...

# Verify CDI is deployed
oc get cdi -n openshift-cnv
# Expected: cdi-kubevirt-hyperconverged   Deployed   ...
```

Check that virt-handler is running on every schedulable node:

```bash
oc get ds -n openshift-cnv -l kubevirt.io=virt-handler
# Expected: DESIRED=CURRENT=READY (one per worker node)
```

> **Use the verification script:** Run `./scripts/verify-cnv.sh` for a comprehensive health check.

### Step 3: Create a Project for VMs

Switch to the `developer` user and create a project for this lesson's VMs. Apply the RBAC resources so the developer user can manage VMs.

```bash
# Switch to developer user
oc login -u developer -p developer https://api.crc.testing:6443

# Create the project
oc new-project virtualization-lab \
  --display-name="Virtualization Lab" \
  --description="L3-M4.1 OpenShift Virtualization lesson"
```

As `kubeadmin`, apply the RBAC for VM management:

```bash
# Switch back to kubeadmin for RBAC setup
oc login -u kubeadmin -p <password> https://api.crc.testing:6443

# Apply VM operator role and binding
oc apply -f manifests/rbac.yaml

# Switch back to developer
oc login -u developer -p developer https://api.crc.testing:6443
oc project virtualization-lab
```

### Step 4: Create and Start a VM

Deploy a Fedora-based VM with an HTTP server. The manifest at `manifests/vm-fedora.yaml` uses a `containerDisk` (the VM disk image is packaged as a container image) and `cloudInitNoCloud` (to configure the guest OS at first boot).

```bash
# Apply the VM manifest
oc apply -f manifests/vm-fedora.yaml

# Verify the VM was created (it is not running yet)
oc get vm fedora-vm
# Expected: fedora-vm   Stopped   ...

# Start the VM
oc patch vm fedora-vm --type merge -p '{"spec":{"running":true}}'
# Or use virtctl:
# virtctl start fedora-vm
```

Watch the VMI (the running instance) come up:

```bash
# Watch the VMI lifecycle
oc get vmi fedora-vm -w
# Expected phases: Scheduling -> Scheduled -> Running

# View the virt-launcher pod (this is the pod that hosts the QEMU process)
oc get pods -l kubevirt.io/domain=fedora-vm
# Expected: virt-launcher-fedora-vm-xxxxx   Running   ...
```

Examine the VMI for runtime details:

```bash
# Get the VM's IP address
oc get vmi fedora-vm -o jsonpath='{.status.interfaces[0].ipAddress}'

# Get the node the VM is running on
oc get vmi fedora-vm -o jsonpath='{.status.nodeName}'

# Describe the VMI for full status
oc describe vmi fedora-vm
```

### Step 5: Access the VM Console

Connect to the VM's serial console or VNC:

```bash
# Serial console (text-based, works over SSH)
virtctl console fedora-vm
# Login: fedora / changeme
# Press Ctrl+] to disconnect

# VNC console (graphical, requires a VNC client or browser)
virtctl vnc fedora-vm
```

You can also access the console through the Web Console:
1. Navigate to **Virtualization > VirtualMachines**.
2. Click on `fedora-vm`.
3. Click the **Console** tab.
4. Select **VNC console** or **Serial console**.

Verify the HTTP server is running inside the VM:

```bash
# From within the VM console (after logging in):
curl http://localhost
# Expected: Hello from OpenShift Virtualization

# From outside the VM — get the VMI IP and curl from a debug pod:
VM_IP=$(oc get vmi fedora-vm -o jsonpath='{.status.interfaces[0].ipAddress}')
oc run curl-test --rm -it --restart=Never \
  --image=registry.access.redhat.com/ubi9/ubi-minimal:latest \
  -- curl -s "http://${VM_IP}"
# Expected: Hello from OpenShift Virtualization
```

### Step 6: Expose the VM via Service and Route

VMs participate in the same networking model as pods. You expose them with standard Services and Routes, exactly as you learned in L1-M4.

```bash
# Apply the Service and Route
oc apply -f manifests/vm-service.yaml
oc apply -f manifests/vm-route.yaml

# Get the Route URL
oc get route fedora-vm-http -o jsonpath='{.spec.host}'
# Expected: fedora-vm-http-virtualization-lab.apps-crc.testing

# Test the route
curl -k https://$(oc get route fedora-vm-http -o jsonpath='{.spec.host}')
# Expected: Hello from OpenShift Virtualization
```

Notice: the Service selector uses `kubevirt.io/domain: fedora-vm` — this label is automatically applied to the virt-launcher pod by KubeVirt. From the Service's perspective, the VM looks like any other pod.

### Step 7: Create a VM with Persistent Storage

The Fedora VM uses a `containerDisk` — ephemeral storage that is lost when the VM is deleted. For production workloads, you need persistent storage.

The `manifests/vm-persistent.yaml` manifest uses a `DataVolume` to automatically import a disk image into a PVC:

```bash
# Apply the persistent VM (this triggers a DataVolume import)
oc apply -f manifests/vm-persistent.yaml

# Watch the DataVolume import progress
oc get dv persistent-vm-rootdisk -w
# Expected phases: ImportScheduled -> ImportInProgress -> Succeeded

# Once the import completes, start the VM
oc patch vm persistent-vm --type merge -p '{"spec":{"running":true}}'

# Verify the VM is running
oc get vmi persistent-vm
```

> **Note on StorageClass:** The manifest references `ocs-storagecluster-ceph-rbd-virtualization`. If you are using CRC or a different storage backend, change `storageClassName` to match your cluster's default StorageClass. Run `oc get sc` to see available options. For CRC, use the default StorageClass (typically `crc-csi-hostpath-provisioner`) — but be aware that live migration will not work without RWX storage.

### Step 8: VM Lifecycle Operations

Learn the complete VM lifecycle using `virtctl` and `oc`:

```bash
# Stop a running VM (graceful shutdown via ACPI)
oc patch vm fedora-vm --type merge -p '{"spec":{"running":false}}'
# Or: virtctl stop fedora-vm

# Verify the VMI is gone (the VM resource remains)
oc get vm fedora-vm
# Expected: fedora-vm   Stopped   ...
oc get vmi fedora-vm
# Expected: No resources found

# Restart a stopped VM
oc patch vm fedora-vm --type merge -p '{"spec":{"running":true}}'
# Or: virtctl start fedora-vm

# Restart a running VM (stop + start)
# virtctl restart fedora-vm

# Pause a running VM (freeze CPU, keep memory)
# virtctl pause vm fedora-vm

# Unpause
# virtctl unpause vm fedora-vm

# Force stop (equivalent to pulling the power cord — use only as last resort)
# virtctl stop fedora-vm --force --grace-period=0
```

**Failure mode — VM stuck in Stopping state:**

If a VM is stuck in the `Stopping` state (usually because the guest OS is not responding to ACPI shutdown):

```bash
# Check the VMI phase
oc get vmi fedora-vm -o jsonpath='{.status.phase}'

# Force delete the VMI (last resort)
oc delete vmi fedora-vm --force --grace-period=0

# If the virt-launcher pod is stuck:
oc delete pod -l kubevirt.io/domain=fedora-vm --force --grace-period=0
```

### Step 9: Live Migration

Live migration moves a running VM from one node to another with zero downtime. This is used for node maintenance, load balancing, and hardware upgrades.

**Requirements for live migration:**
- Storage must be `ReadWriteMany` (RWX) — the disk must be accessible from both nodes during migration.
- The VM must have `evictionStrategy: LiveMigrate` set in the spec.
- The target node must have sufficient resources.
- The VM must not use `hostPath` volumes or `hostNetwork`.

```bash
# Verify the persistent VM supports live migration
oc get vm persistent-vm -o jsonpath='{.spec.template.spec.evictionStrategy}'
# Expected: LiveMigrate

# Check which node the VM is currently on
oc get vmi persistent-vm -o jsonpath='{.status.nodeName}'
```

Apply the migration policy for production workloads:

```bash
# Apply the MigrationPolicy (cluster-scoped, requires kubeadmin)
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
oc apply -f manifests/migration-policy.yaml
oc login -u developer -p developer https://api.crc.testing:6443
oc project virtualization-lab
```

Trigger a live migration:

```bash
# Initiate live migration
virtctl migrate persistent-vm

# Watch the migration progress
oc get vmim -w
# Expected phases: Scheduling -> TargetReady -> Running -> Succeeded

# After migration, check the new node
oc get vmi persistent-vm -o jsonpath='{.status.nodeName}'
# The node should be different from before

# Verify the VM is still running and accessible
oc get vmi persistent-vm
```

> **CRC limitation:** CRC is a single-node cluster, so live migration will not work (there is no target node). To test live migration, you need a multi-node cluster (bare metal, cloud, or a full OCP installation with 2+ worker nodes).

**Failure mode — Migration stuck or failed:**

```bash
# Check migration status
oc describe vmim -l kubevirt.io/vm-name=persistent-vm

# Common causes:
# 1. Target node has insufficient resources -> check oc describe node
# 2. Storage is not RWX -> check PVC access mode
# 3. VM is writing to disk faster than migration can copy (dirty page rate too high)
#    -> Solution: migration policy with allowAutoConverge: true (slows VM CPU to reduce writes)
# 4. Network bandwidth insufficient -> increase bandwidthPerMigration in MigrationPolicy

# Cancel a stuck migration
oc delete vmim -l kubevirt.io/vm-name=persistent-vm
```

**Node maintenance workflow (the production use case):**

```bash
# Mark a node as unschedulable (cordon)
oc adm cordon <node-name>

# VMs with evictionStrategy: LiveMigrate will be automatically migrated
# VMs without it will be shut down

# Drain the node (triggers migrations/shutdowns)
oc adm drain <node-name> --delete-emptydir-data --ignore-daemonsets

# Perform maintenance...

# Uncordon the node
oc adm uncordon <node-name>
```

### Step 10: VM Snapshots and Restore

Snapshots capture the state of a VM's disks at a point in time. They require a CSI driver that supports VolumeSnapshots (ODF/Ceph provides this).

```bash
# Ensure the persistent VM is stopped before snapshotting
# (online snapshots are supported but require quiescing the guest)
oc patch vm persistent-vm --type merge -p '{"spec":{"running":false}}'

# Wait for the VM to stop
oc wait vm persistent-vm --for=jsonpath='{.status.printableStatus}'=Stopped --timeout=120s

# Create a snapshot
oc apply -f manifests/vm-snapshot.yaml

# Watch the snapshot progress
oc get vmsnapshot persistent-vm-snap-01 -w
# Expected: readyToUse=true

# Check snapshot details
oc describe vmsnapshot persistent-vm-snap-01
```

Restore from a snapshot:

```bash
# Ensure the VM is stopped
oc get vm persistent-vm -o jsonpath='{.status.printableStatus}'
# Expected: Stopped

# Apply the restore
oc apply -f manifests/vm-snapshot-restore.yaml

# Watch the restore progress
oc get vmrestore persistent-vm-restore-01 -w
# Expected: complete=true

# Start the VM — it is now back to the snapshot state
oc patch vm persistent-vm --type merge -p '{"spec":{"running":true}}'
```

**Failure mode — Snapshot creation fails:**

```bash
# Check VolumeSnapshotClass exists
oc get volumesnapshotclass

# If no VolumeSnapshotClass exists, snapshots cannot be taken.
# ODF creates one automatically. For other storage backends:
# oc apply -f - <<EOF
# apiVersion: snapshot.storage.k8s.io/v1
# kind: VolumeSnapshotClass
# metadata:
#   name: csi-snapshot-class
# driver: <your-csi-driver>
# deletionPolicy: Delete
# EOF

# Check snapshot status for errors
oc get vmsnapshot persistent-vm-snap-01 -o jsonpath='{.status.conditions}'
```

### Step 11: Windows VM Workload (Legacy Application Use Case)

The `manifests/vm-windows.yaml` demonstrates running a Windows Server VM. This is the primary enterprise use case — running legacy .NET Framework applications, SQL Server, or Active Directory domain controllers.

Key configuration differences for Windows VMs:

```yaml
# Windows requires special clock, CPU, and Hyper-V enlightenment settings:
domain:
  clock:
    utc: {}
    timer:
      hpet:
        present: false         # Disable HPET (Windows performs better without it)
      hyperv: {}               # Use Hyper-V reference timer
  features:
    hyperv:                    # Hyper-V enlightenments (paravirtualization for Windows)
      relaxed: {}              # Relaxed timing (prevents BSOD on overcommitted hosts)
      vapic: {}                # Virtual APIC (reduces interrupt overhead)
      spinlocks:
        spinlocks: 8191        # Optimize spinlock retries
      vpindex: {}              # Virtual processor index
      runtime: {}              # Runtime enlightenment
      synic: {}                # Synthetic interrupt controller
      stimer:
        direct: {}             # Synthetic timer (direct mode)
  devices:
    disks:
      - name: rootdisk
        disk:
          bus: sata            # Use SATA initially (until VirtIO drivers are installed)
      - name: virtiocontainerdisk
        cdrom:
          bus: sata            # VirtIO driver ISO mounted as CD-ROM
    tpm: {}                    # TPM device (required for Windows 11/Server 2025)
```

> **Note:** The Windows VM manifest assumes you have already imported a Windows ISO into a PVC named `windows-iso`. This lesson does not cover Windows installation, which is a standard process through the VNC console. The VirtIO drivers CD-ROM is mounted automatically from the `virtio-win` container image.

### Step 12: Secondary Networking for VMs

For VMs that need L2 connectivity to physical networks (e.g., VMs migrated from VMware that expect VLAN access), configure a secondary network using a `NetworkAttachmentDefinition`.

```bash
# Apply the bridge network attachment (requires kubeadmin and a bridge on the node)
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
oc apply -f manifests/network-attachment-bridge.yaml
oc login -u developer -p developer https://api.crc.testing:6443
oc project virtualization-lab
```

To attach a VM to this network, add a second interface in the VM spec:

```yaml
# Additional interface in the VM spec (not applied in this lesson)
spec:
  template:
    spec:
      domain:
        devices:
          interfaces:
            - name: default
              masquerade: {}           # Pod network (default)
            - name: bridge-net
              bridge: {}              # Bridge to external network
      networks:
        - name: default
          pod: {}
        - name: bridge-net
          multus:
            networkName: vm-bridge-network
```

> **Production consideration:** Bridge networks require the `NodeNetworkConfigurationPolicy` (from the `kubernetes-nmstate` operator) to create the bridge interface (`br-ext`) on each node. This is a cluster-admin operation. In production, use SR-IOV for high-performance VM networking — it provides near-native network performance by passing a physical NIC's virtual function directly to the VM.

## Verification

Run the verification script or execute these checks manually:

```bash
# Run automated health check
./scripts/verify-cnv.sh

# Manual verification checklist:

# 1. Operator is healthy
oc get csv -n openshift-cnv | grep kubevirt
# Expected: kubevirt-hyperconverged-operator.v4.x.x   Succeeded

# 2. HyperConverged CR is Available
oc get hyperconverged -n openshift-cnv
# Expected: kubevirt-hyperconverged   ... Available

# 3. VMs are created
oc get vm -n virtualization-lab
# Expected: fedora-vm, persistent-vm listed

# 4. At least one VM is running
oc get vmi -n virtualization-lab
# Expected: fedora-vm or persistent-vm in Running phase

# 5. Service and Route are working
curl -k https://$(oc get route fedora-vm-http -n virtualization-lab -o jsonpath='{.spec.host}')
# Expected: Hello from OpenShift Virtualization

# 6. Snapshot was created (if Step 10 was completed)
oc get vmsnapshot -n virtualization-lab
# Expected: persistent-vm-snap-01   readyToUse=true
```

In the Web Console, verify:
1. Navigate to **Virtualization > VirtualMachines** — you should see your VMs listed with their status.
2. Click on a running VM and access the **Console** tab.
3. Check the **Metrics** tab for CPU, memory, network, and disk usage.
4. Check the **Snapshots** tab for any snapshots taken.

## K8s vs OpenShift Comparison

| Aspect | Kubernetes + KubeVirt | OpenShift Virtualization |
|--------|----------------------|--------------------------|
| Installation | Install KubeVirt, CDI, network plugins separately | Single operator + HyperConverged CR deploys everything |
| Management UI | No built-in UI; kubectl only | Full Web Console integration (create, console, migrate, snapshot) |
| VM Templates | Create your own | Certified templates for RHEL, Fedora, Windows |
| Disk Import | Manual CDI configuration | DataVolume automates import with format conversion |
| Live Migration | Manual network/storage setup | Pre-configured migration network, MigrationPolicy CRD |
| Snapshots | Depends on CSI driver, manual VolumeSnapshot | VirtualMachineSnapshot/Restore CRDs with console integration |
| Networking | Basic pod network only | Multus, bridge, SR-IOV, macvtap via NetworkAddons |
| Windows Support | Manual Hyper-V enlightenments | Pre-configured templates with VirtIO drivers |
| Node Maintenance | Manual drain + migration | Integrated node maintenance operator |
| Monitoring | Deploy your own dashboards | Pre-built Prometheus alerts and Grafana dashboards |
| Support | Community only | Red Hat enterprise support |
| Storage Integration | Any CSI, manual config | ODF-optimized StorageProfiles, automatic access mode selection |
| RBAC | Define your own roles | Pre-defined VM operator/viewer roles |

## Key Takeaways

- **VMs are pods under the hood.** A `VirtualMachineInstance` runs inside a `virt-launcher` pod. It gets a pod IP, is scheduled by the Kubernetes scheduler, and is exposed via standard Services and Routes. The entire Kubernetes networking and storage model applies.

- **The `VirtualMachine` CRD is to VMs what a `Deployment` is to pods.** The VM resource is the persistent specification; the VMI is the ephemeral running instance. Stopping a VM deletes the VMI but preserves the VM. This lifecycle model is unique to KubeVirt and has no direct Kubernetes equivalent.

- **Live migration requires RWX storage.** This is the most common production gotcha. Without shared storage (ODF/Ceph, NFS), you cannot live-migrate VMs, which means you cannot perform zero-downtime node maintenance on VM workloads.

- **OpenShift Virtualization is not just KubeVirt.** The operator adds Web Console integration, certified templates, migration policies, snapshot management, and node maintenance workflows that make running VMs in production viable. Upstream KubeVirt alone requires significant operational investment.

- **The primary use case is convergence, not replacement.** OpenShift Virtualization is most valuable when you need VMs and containers to coexist on the same platform — legacy Windows applications next to modern microservices, stateful database VMs alongside stateless API containers, all managed through a single operational model.

## Cleanup

Remove the lesson resources but keep the CNV operator installed (other lessons may use it):

```bash
# Run the cleanup script
./scripts/cleanup.sh
```

Or clean up manually:

```bash
# Stop all VMs
oc patch vm fedora-vm -n virtualization-lab --type merge -p '{"spec":{"running":false}}'
oc patch vm persistent-vm -n virtualization-lab --type merge -p '{"spec":{"running":false}}'

# Wait for VMIs to terminate
oc wait vmi --all -n virtualization-lab --for=delete --timeout=120s

# Delete all VMs, snapshots, restores
oc delete vm --all -n virtualization-lab
oc delete vmsnapshot --all -n virtualization-lab
oc delete vmrestore --all -n virtualization-lab

# Delete services, routes
oc delete service,route -l tutorial-level=3,tutorial-module=M4 -n virtualization-lab

# Delete DataVolumes and PVCs
oc delete dv --all -n virtualization-lab
oc delete pvc --all -n virtualization-lab

# Delete the MigrationPolicy (cluster-scoped)
oc login -u kubeadmin -p <password> https://api.crc.testing:6443
oc delete migrationpolicy production-migration-policy

# Delete the project
oc delete project virtualization-lab
```

To also remove the CNV operator entirely:

```bash
./scripts/cleanup.sh --full
```

> **CRC note:** VMs consume significant resources. Always clean up after this lesson to free memory and CPU for other lessons.

## Next Steps

In **L3-M4.2 — OpenShift AI (RHOAI)**, you will explore Red Hat OpenShift AI for machine learning workloads, including JupyterHub notebooks, model serving with ModelMesh, data science pipelines, and GPU scheduling. Where this lesson showed how OpenShift extends Kubernetes to run VMs, L3-M4.2 shows how it extends the platform for AI/ML workloads — another domain where the unified operational model pays dividends.
