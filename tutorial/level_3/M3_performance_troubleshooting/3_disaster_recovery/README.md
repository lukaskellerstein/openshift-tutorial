# L3-M3.3 — Disaster Recovery

**Level:** Expert
**Duration:** 45 min

## Overview

In Kubernetes you are responsible for assembling your own disaster-recovery (DR) stack: etcd snapshots, Velero or Kasten, custom scripts, and a runbook that ties them together. OpenShift provides first-party tooling for both cluster-level and application-level DR, but the operational discipline — planning, testing, and maintaining RTO/RPO targets — remains your responsibility. This lesson walks through the full DR lifecycle on OpenShift: etcd backup and restore, quorum-loss recovery, `oc adm backup` for cluster state, Velero for namespaced application workloads, and the planning framework that turns ad-hoc scripts into a production DR strategy.

## Prerequisites

- Completed: L3-M1.4 (etcd & Control Plane Operations)
- OpenShift cluster running (CRC for etcd exercises, multi-node cluster recommended for quorum-loss scenarios)
- `cluster-admin` access (`kubeadmin` on CRC)
- Familiarity with etcd fundamentals (keyspace, snapshots, WAL) from L3-M1.4
- `etcdctl` available (bundled in the etcd pod on control-plane nodes)
- Velero CLI installed locally (for application-level backup exercises)

## K8s Context

Kubernetes provides no built-in backup tooling. Cluster administrators must:

1. Snapshot etcd manually (`etcdctl snapshot save`) and store the file off-cluster.
2. Back up certificate authorities, encryption keys, and static pod manifests independently.
3. Deploy third-party tools (Velero, Kasten K10, Stash) for application-level backup.
4. Restore etcd by stopping the API server, replacing the data directory, and restarting.

The process is well-documented but entirely manual. There are no CRDs, no operator-managed schedules, and no cluster-aware health checks built in.

## Concepts

### Disaster Recovery Architecture on OpenShift

```
+-----------------------------------------------------------------------+
|                     Disaster Recovery Layers                          |
+-----------------------------------------------------------------------+
|                                                                       |
|  Layer 1: Cluster State (etcd)                                        |
|  +-----------------------------------------------------------------+  |
|  | etcd snapshot  -->  /var/lib/etcd  -->  S3 / NFS / External     |  |
|  | Includes: all K8s/OpenShift objects, RBAC, secrets, CRDs        |  |
|  | Does NOT include: PV data, container images, external state     |  |
|  +-----------------------------------------------------------------+  |
|                                                                       |
|  Layer 2: Cluster Configuration                                       |
|  +-----------------------------------------------------------------+  |
|  | oc adm backup  -->  certificates, static pods, machine configs  |  |
|  | Includes: CA bundles, kubeconfigs, MachineConfigs, OAuth config  |  |
|  | Complements etcd: these files live on disk, not in etcd          |  |
|  +-----------------------------------------------------------------+  |
|                                                                       |
|  Layer 3: Application Data (Velero)                                   |
|  +-----------------------------------------------------------------+  |
|  | Velero backup  -->  namespace resources + PV snapshots           |  |
|  | Includes: Deployments, ConfigMaps, Secrets, PVC data (via CSI)  |  |
|  | Portable: can restore to a different cluster                    |  |
|  +-----------------------------------------------------------------+  |
|                                                                       |
|  Layer 4: External Dependencies                                       |
|  +-----------------------------------------------------------------+  |
|  | Git repos, external databases, DNS records, TLS certs, IdP      |  |
|  | Must be backed up independently — OpenShift cannot manage these  |  |
|  +-----------------------------------------------------------------+  |
|                                                                       |
+-----------------------------------------------------------------------+
```

### RTO and RPO Definitions

| Metric | Definition | OpenShift Implication |
|--------|-----------|----------------------|
| **RPO** (Recovery Point Objective) | Maximum tolerable data loss measured in time | How frequently you take etcd snapshots and Velero backups |
| **RTO** (Recovery Time Objective) | Maximum tolerable downtime | How fast you can restore etcd + redeploy workloads |

For most production clusters:

- **RPO target**: 1-4 hours (etcd snapshots every 1-4 hours)
- **RTO target**: 30-120 minutes (depending on cluster size and automation maturity)
- **etcd snapshot size**: typically 100 MB - 2 GB depending on object count
- **Restore time**: 10-30 minutes for etcd; additional time for application workloads

### etcd Backup on OpenShift

OpenShift wraps etcd in a static pod on each control-plane node. The backup script is provided at `/usr/local/bin/cluster-backup.sh` on RHCOS nodes and captures:

1. **etcd snapshot** — the entire key-value store (all API objects)
2. **Static pod resources** — manifests for kube-apiserver, etcd, kube-controller-manager, kube-scheduler
3. **Certificates** — all PKI material needed to bootstrap the control plane

Unlike vanilla Kubernetes, OpenShift's backup script is cluster-aware: it stops the etcd learner if present, verifies quorum health before snapshotting, and packages everything into a single timestamped directory.

### Quorum Loss and Recovery

etcd uses Raft consensus. A 3-node control plane tolerates 1 node failure. Losing 2 of 3 nodes means **quorum loss** — the cluster is read-only and cannot accept writes.

```
3-node etcd cluster quorum scenarios:

  Healthy:  [Node A: OK]  [Node B: OK]  [Node C: OK]   --> Quorum: 2/3 OK
  Degraded: [Node A: OK]  [Node B: OK]  [Node C: DOWN]  --> Quorum: 2/3 OK
  LOST:     [Node A: OK]  [Node B: DOWN] [Node C: DOWN]  --> Quorum: 1/3 FAIL

  Recovery options after quorum loss:
  1. Restore failed nodes (preferred if hardware is recoverable)
  2. Force single-node etcd and rebuild (last resort)
```

OpenShift provides `cluster-restore.sh` which can bootstrap a single surviving node into a functioning single-member etcd cluster, then scale back up.

### Velero on OpenShift

Velero handles application-level backup: namespaced resources, PVC data (via CSI snapshots or Restic/Kopia), and cross-cluster migration. On OpenShift, Velero is typically installed through the **OADP** (OpenShift API for Data Protection) operator, which wraps Velero with:

- OpenShift-aware backup/restore (handles Routes, ImageStreams, BuildConfigs)
- Integration with OpenShift's CSI drivers for volume snapshots
- A `DataProtectionApplication` CRD for declarative configuration
- Support for multiple backup storage locations (S3, Azure Blob, GCS)

### DR Planning Framework

A production DR plan must answer:

| Question | Answer |
|----------|--------|
| What is backed up? | etcd + certs + application namespaces + PV data |
| How often? | etcd: every 4h; Velero: daily (adjust to RPO target) |
| Where are backups stored? | Off-cluster: S3 bucket, NFS share, or dedicated backup infra |
| Who is responsible? | Named on-call rotation with documented runbooks |
| How is it tested? | Monthly DR drill restoring to a staging cluster |
| What is the RTO? | 2 hours from total cluster loss to workloads serving traffic |
| What is the RPO? | 4 hours maximum data loss |
| What is NOT covered? | External databases, DNS propagation, IdP availability |

## Step-by-Step

### Step 1: Take an etcd Snapshot

SSH into a control-plane node and run the OpenShift-provided backup script. On CRC, you can use `oc debug node/` to access the node filesystem.

```bash
# Identify the control plane node
oc get nodes -l node-role.kubernetes.io/master

# Open a debug session on the control plane node
oc debug node/$(oc get nodes -l node-role.kubernetes.io/master -o jsonpath='{.items[0].metadata.name}')

# Inside the debug pod, chroot to the host filesystem
chroot /host

# Run the OpenShift-provided backup script
/usr/local/bin/cluster-backup.sh /home/core/backup-$(date +%Y%m%d-%H%M%S)
```

The backup script creates a directory containing:
- `snapshot_<timestamp>.db` — the etcd snapshot
- `static_kuberesources_<timestamp>.tar.gz` — static pod manifests and certificates

```bash
# Verify the backup contents
ls -lh /home/core/backup-*/

# Verify the snapshot integrity
etcdctl snapshot status /home/core/backup-*/snapshot_*.db --write-out=table
```

Expected output:
```
+----------+----------+------------+------------+
|   HASH   | REVISION | TOTAL KEYS | TOTAL SIZE |
+----------+----------+------------+------------+
| 3e5b1a2f | 1048576  |      12453 |    156 MB  |
+----------+----------+------------+------------+
```

### Step 2: Automate etcd Backups with a CronJob

For production environments, automate etcd snapshots using a CronJob that runs on the control-plane node. Apply the manifests from this lesson.

```bash
# Create the backup namespace
oc new-project etcd-backup

# Create the ServiceAccount and RBAC
oc apply -f manifests/etcd-backup-rbac.yaml

# Grant the ServiceAccount privileged SCC (required for node access)
oc adm policy add-scc-to-user privileged -z etcd-backup-sa -n etcd-backup

# Create the backup CronJob
oc apply -f manifests/etcd-backup-cronjob.yaml
```

```yaml
# From manifests/etcd-backup-cronjob.yaml — runs every 4 hours
apiVersion: batch/v1
kind: CronJob
metadata:
  name: etcd-backup
  namespace: etcd-backup
spec:
  schedule: "0 */4 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: etcd-backup
              image: registry.redhat.io/openshift4/ose-tools-rhel9:latest
              command:
                - /bin/bash
                - -c
                - |
                  /usr/local/bin/cluster-backup.sh /backup/etcd-$(date +%Y%m%d-%H%M%S)
                  # Retain only last 7 days of backups
                  find /backup -maxdepth 1 -type d -mtime +7 -exec rm -rf {} +
              resources:
                requests:
                  cpu: 100m
                  memory: 256Mi
                limits:
                  cpu: 500m
                  memory: 512Mi
              volumeMounts:
                - name: backup-volume
                  mountPath: /backup
          volumes:
            - name: backup-volume
              persistentVolumeClaim:
                claimName: etcd-backup-pvc
          restartPolicy: OnFailure
          nodeSelector:
            node-role.kubernetes.io/master: ""
          tolerations:
            - key: node-role.kubernetes.io/master
              effect: NoSchedule
```

### Step 3: Restore etcd from a Snapshot

Restoring etcd is a disruptive operation. In production, this is a last resort. Here is the procedure for a single control-plane node recovery.

```bash
# SSH to the control plane node (or use oc debug node/)
oc debug node/$(oc get nodes -l node-role.kubernetes.io/master -o jsonpath='{.items[0].metadata.name}')
chroot /host

# Stop the etcd static pod by moving its manifest
# (kubelet watches /etc/kubernetes/manifests — removing the file stops the pod)
mv /etc/kubernetes/manifests/etcd-pod.yaml /tmp/etcd-pod.yaml.bak

# Wait for etcd to stop
crictl ps | grep etcd

# Run the restore script with the snapshot path
/usr/local/bin/cluster-restore.sh /home/core/backup-<timestamp>

# The restore script will:
# 1. Stop etcd and kube-apiserver
# 2. Replace the etcd data directory
# 3. Restore certificates
# 4. Restart etcd with the new data
# 5. Restart the API server

# After restore, verify the cluster
oc get nodes
oc get clusteroperators
```

**Failure mode: Partial restore** -- If the restore script fails midway, the etcd data directory may be in an inconsistent state. The script creates a backup of the existing data directory at `/var/lib/etcd.old` before overwriting. To roll back:

```bash
# Roll back a failed restore
rm -rf /var/lib/etcd
mv /var/lib/etcd.old /var/lib/etcd
mv /tmp/etcd-pod.yaml.bak /etc/kubernetes/manifests/etcd-pod.yaml
```

### Step 4: Recover from Quorum Loss

When 2 of 3 control-plane nodes are permanently lost, you must force a single-node etcd cluster from the surviving node. This is documented in the OpenShift DR runbook.

```bash
# On the surviving control-plane node
oc debug node/<surviving-node>
chroot /host

# 1. Take a fresh snapshot from the surviving node
/usr/local/bin/cluster-backup.sh /home/core/quorum-recovery

# 2. Stop the kubelet to prevent interference
systemctl stop kubelet

# 3. Move all static pod manifests except etcd
mv /etc/kubernetes/manifests/kube-apiserver-pod.yaml /tmp/
mv /etc/kubernetes/manifests/kube-controller-manager-pod.yaml /tmp/
mv /etc/kubernetes/manifests/kube-scheduler-pod.yaml /tmp/

# 4. Force etcd to single-member mode
# Edit the etcd pod manifest to set --force-new-cluster
# This resets the cluster ID and forces the node to be the sole member

# 5. Restore from the snapshot
/usr/local/bin/cluster-restore.sh /home/core/quorum-recovery

# 6. Start kubelet
systemctl start kubelet

# 7. Wait for the API server to become available (5-10 minutes)
# Then verify
oc get nodes
oc get etcd -o=jsonpath='{range .items[0].status.conditions[?(@.type=="EtcdMembersAvailable")]}{.message}{"\n"}{end}'
```

**Failure mode: Split-brain after quorum recovery** -- If a "lost" node comes back online with stale data, it can cause a split-brain. Before recovering, ensure lost nodes are either decommissioned or have their etcd data wiped:

```bash
# On each recovered-but-stale node, BEFORE rejoining:
rm -rf /var/lib/etcd/member
```

### Step 5: Back Up Cluster State with `oc adm backup`

`oc adm backup` captures cluster configuration that lives outside etcd: MachineConfigs, OAuth configuration, and infrastructure state.

```bash
# Back up cluster configuration
oc adm backup --to=/tmp/cluster-backup

# This creates a directory with:
# - machineconfigs/
# - oauth/
# - infrastructure/
# - cluster-version/

# Verify the backup
ls -la /tmp/cluster-backup/
```

Combine this with etcd snapshots for a complete cluster-level backup.

### Step 6: Install OADP (Velero) for Application-Level Backup

OADP (OpenShift API for Data Protection) is the supported way to run Velero on OpenShift. Install it via the Operator.

```bash
# Create the OADP namespace
oc new-project openshift-adp

# Install the OADP operator (via OperatorHub or CLI)
oc apply -f manifests/oadp-subscription.yaml

# Wait for the operator to be ready
oc wait --for=condition=Available deployment/oadp-operator-controller-manager \
  -n openshift-adp --timeout=120s
```

Configure the backup storage location (S3 in this example):

```bash
# Create credentials secret for S3 access
oc create secret generic cloud-credentials \
  -n openshift-adp \
  --from-file=cloud=scripts/credentials-velero

# Apply the DataProtectionApplication CR
oc apply -f manifests/data-protection-application.yaml
```

```yaml
# From manifests/data-protection-application.yaml
apiVersion: oadp.openshift.io/v1alpha1
kind: DataProtectionApplication
metadata:
  name: dr-dpa
  namespace: openshift-adp
spec:
  configuration:
    velero:
      defaultPlugins:
        - openshift
        - aws
        - csi
      resourceTimeout: 10m
    nodeAgent:
      enable: true
      uploaderType: kopia
  backupLocations:
    - velero:
        provider: aws
        default: true
        objectStorage:
          bucket: openshift-dr-backups
          prefix: cluster-01
        config:
          region: us-east-1
          profile: default
        credential:
          name: cloud-credentials
          key: cloud
  snapshotLocations:
    - velero:
        provider: aws
        config:
          region: us-east-1
          profile: default
```

### Step 7: Create and Restore an Application Backup with Velero

Back up a specific namespace and verify restore.

```bash
# Deploy a sample application to test backup/restore
oc new-project dr-test
oc apply -f manifests/sample-app.yaml

# Verify the app is running
oc get pods -n dr-test
oc get routes -n dr-test

# Create a backup of the dr-test namespace
oc apply -f manifests/velero-backup.yaml
```

```yaml
# From manifests/velero-backup.yaml
apiVersion: velero.io/v1
kind: Backup
metadata:
  name: dr-test-backup
  namespace: openshift-adp
spec:
  includedNamespaces:
    - dr-test
  storageLocation: dr-dpa-1
  ttl: 720h
  snapshotMoveData: true
  defaultVolumesToFsBackup: true
```

```bash
# Wait for backup to complete
oc get backup dr-test-backup -n openshift-adp -w

# Verify backup status
oc describe backup dr-test-backup -n openshift-adp

# Simulate disaster: delete the namespace
oc delete project dr-test

# Wait for namespace to be fully deleted
oc get project dr-test  # Should return "not found"

# Restore from backup
oc apply -f manifests/velero-restore.yaml
```

```yaml
# From manifests/velero-restore.yaml
apiVersion: velero.io/v1
kind: Restore
metadata:
  name: dr-test-restore
  namespace: openshift-adp
spec:
  backupName: dr-test-backup
  includedNamespaces:
    - dr-test
  restorePVs: true
```

```bash
# Wait for restore to complete
oc get restore dr-test-restore -n openshift-adp -w

# Verify the application is running again
oc get pods -n dr-test
oc get routes -n dr-test
```

**Failure mode: Restore conflicts** -- If objects already exist in the target namespace, Velero skips them by default. To force overwrite, use `existingResourcePolicy: update` in the Restore spec. Watch for UID mismatches on PVCs, which can leave volumes orphaned.

### Step 8: Set Up a Scheduled Velero Backup

For production, create a Schedule resource so backups run automatically.

```bash
oc apply -f manifests/velero-schedule.yaml
```

```yaml
# From manifests/velero-schedule.yaml
apiVersion: velero.io/v1
kind: Schedule
metadata:
  name: daily-app-backup
  namespace: openshift-adp
spec:
  schedule: "0 2 * * *"
  template:
    includedNamespaces:
      - production
      - staging
    excludedResources:
      - events
      - pods
    storageLocation: dr-dpa-1
    ttl: 720h
    snapshotMoveData: true
    defaultVolumesToFsBackup: true
```

### Step 9: Run a DR Drill

A backup you have never tested is not a backup. Use the provided DR drill script to validate your entire recovery chain.

```bash
# Run the DR drill script
bash scripts/dr-drill.sh
```

The drill script (see `scripts/dr-drill.sh`) performs:

1. Creates a test namespace with a sample stateful application
2. Takes an etcd snapshot
3. Creates a Velero backup of the test namespace
4. Deletes the test namespace
5. Restores from Velero backup
6. Verifies application health and data integrity
7. Reports RTO (elapsed time) and RPO (time since last backup)
8. Cleans up

## Verification

After completing the exercises, verify your DR readiness:

```bash
# 1. Verify etcd backup exists and is valid
oc debug node/$(oc get nodes -l node-role.kubernetes.io/master -o jsonpath='{.items[0].metadata.name}') \
  -- chroot /host ls -lh /home/core/backup-*/

# 2. Verify the automated CronJob is scheduled
oc get cronjob etcd-backup -n etcd-backup

# 3. Verify OADP is healthy
oc get dataprotectionapplication -n openshift-adp
oc get backupstoragelocations -n openshift-adp

# 4. Verify scheduled backups are running
oc get schedules -n openshift-adp
oc get backups -n openshift-adp

# 5. Verify a restore completed successfully
oc get restores -n openshift-adp
```

Expected results:
- etcd backup directory contains a `.db` snapshot and `.tar.gz` static resources
- CronJob shows a schedule of `0 */4 * * *` with recent successful completions
- DataProtectionApplication shows `Available` condition
- BackupStorageLocation shows `Available` phase
- At least one Backup with phase `Completed`
- At least one Restore with phase `Completed`

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| etcd backup tooling | Manual `etcdctl snapshot save` | Built-in `cluster-backup.sh` on RHCOS nodes |
| Certificates backup | Manual: copy CA files from each node | Bundled in `cluster-backup.sh` output |
| etcd restore | Manual: stop API server, replace data dir, restart | `cluster-restore.sh` handles all steps |
| Quorum recovery | Manual forced single-node bootstrap | Guided by `cluster-restore.sh` with pre-checks |
| Cluster config backup | No built-in tool | `oc adm backup` captures MachineConfigs, OAuth, infra |
| Application backup | Velero (install yourself) | OADP operator (Velero + OpenShift-aware plugins) |
| Volume snapshots | CSI snapshot controller (install yourself) | CSI snapshot controller pre-installed |
| Backup of Routes | N/A (no Routes in K8s) | OADP OpenShift plugin handles Routes, ImageStreams |
| Operator-managed backup | No built-in operator | OADP operator with `DataProtectionApplication` CRD |
| DR drill automation | DIY scripts | DIY scripts (same), but with better restore primitives |

## Key Takeaways

- **Two layers of DR**: Cluster-level (etcd + certs) protects the control plane; application-level (OADP/Velero) protects workloads and data. You need both.
- **etcd snapshots capture everything in the API** (Deployments, Secrets, CRDs, RBAC) but NOT persistent volume data or container images. Plan accordingly.
- **Quorum loss is recoverable** but requires forcing a single-node etcd cluster, which is disruptive. The best defense is a properly sized control plane (3 or 5 nodes) and regular backups.
- **OADP adds OpenShift awareness** to Velero: it understands Routes, ImageStreams, BuildConfigs, and SCCs, which plain Velero does not handle correctly.
- **An untested backup is not a backup.** Schedule quarterly DR drills that restore to a staging cluster and verify end-to-end application health. Track your actual RTO and RPO against targets.

## Cleanup

```bash
# Remove the DR test namespace
oc delete project dr-test

# Remove the etcd backup CronJob and namespace
oc delete project etcd-backup

# Remove Velero backups and restores (if testing)
oc delete backup dr-test-backup -n openshift-adp
oc delete restore dr-test-restore -n openshift-adp
oc delete schedule daily-app-backup -n openshift-adp

# Optionally remove OADP (if no longer needed)
oc delete dataprotectionapplication dr-dpa -n openshift-adp
oc delete project openshift-adp

# Remove etcd backups from the control plane node
oc debug node/$(oc get nodes -l node-role.kubernetes.io/master -o jsonpath='{.items[0].metadata.name}') \
  -- chroot /host rm -rf /home/core/backup-*
```

## Next Steps

In **L3-M3.4 (Cost Management)**, you will learn how to track resource consumption across namespaces and clusters using the Cost Management Operator. This builds on the resource-awareness developed here — understanding what you are backing up is closely related to understanding what you are spending. You will implement metering, chargeback models, and resource optimization strategies for production OpenShift clusters.
