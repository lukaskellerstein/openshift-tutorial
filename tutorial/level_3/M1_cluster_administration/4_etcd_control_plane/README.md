# L3-M1.4 — etcd & Control Plane Operations

**Level:** Expert
**Duration:** 30 min

## Overview

In Kubernetes, etcd is the critical key-value store that holds all cluster state, but operators rarely interact with it directly. OpenShift wraps etcd management inside the cluster-etcd-operator, providing automated member management, certificate rotation, and health monitoring. This lesson covers etcd backup and restore procedures, control plane certificate management, disaster recovery for master nodes, and etcd encryption at rest -- the operations that separate a production-grade cluster from a development playground.

## Prerequisites

- Completed: L3-M1.3 (Node Management)
- OpenShift cluster running (CRC or full cluster -- note that CRC runs a single-node control plane, so quorum exercises are conceptual)
- Logged in as `kubeadmin` (cluster-admin privileges required)
- `oc` CLI installed and on PATH
- SSH access to control plane nodes (for full cluster environments)

## K8s Context

In vanilla Kubernetes, etcd management is entirely manual. You install etcd yourself (or use kubeadm which bootstraps it), manage certificates with `kubeadm certs`, run `etcdctl snapshot save` for backups, and handle disaster recovery by restoring snapshots and reconfiguring cluster membership. Certificate rotation requires running `kubeadm certs renew` and restarting control plane components. There is no built-in operator watching etcd health or automating recovery.

If you have managed Kubernetes (EKS, GKE, AKS), the cloud provider hides etcd entirely. OpenShift sits between these extremes: etcd is visible and you can interact with it, but an operator manages the heavy lifting.

## Concepts

### etcd in OpenShift

OpenShift deploys etcd as static pods on every control plane (master) node, managed by the `cluster-etcd-operator`. The operator handles:

- **Member management** -- adding/removing etcd members when control plane nodes scale
- **Health monitoring** -- detecting degraded members and reporting via `ClusterOperator` status
- **Certificate rotation** -- automatically rotating etcd peer, server, and client certificates before expiry
- **Defragmentation** -- periodic defragmentation to reclaim storage space

```
+--------------------------------------------------+
|              OpenShift Control Plane              |
|                                                   |
|  +------------+  +------------+  +------------+   |
|  | Master-0   |  | Master-1   |  | Master-2   |   |
|  |            |  |            |  |            |   |
|  | +--------+ |  | +--------+ |  | +--------+ |   |
|  | | etcd   | |  | | etcd   | |  | | etcd   | |   |
|  | | member | |  | | member | |  | | member | |   |
|  | +---+----+ |  | +---+----+ |  | +---+----+ |   |
|  |     |      |  |     |      |  |     |      |   |
|  | +---+----+ |  | +---+----+ |  | +---+----+ |   |
|  | |  API   | |  | |  API   | |  | |  API   | |   |
|  | | Server | |  | | Server | |  | | Server | |   |
|  | +--------+ |  | +--------+ |  | +--------+ |   |
|  +------------+  +------------+  +------------+   |
|                                                   |
|  +---------------------------------------------+ |
|  |       cluster-etcd-operator                  | |
|  |  - Member management                        | |
|  |  - Health monitoring                         | |
|  |  - Certificate rotation                      | |
|  |  - Defrag scheduling                         | |
|  +---------------------------------------------+ |
+--------------------------------------------------+
```

### etcd Backup Strategy

etcd backups capture the entire cluster state: all Kubernetes resources, OpenShift-specific resources (Routes, BuildConfigs, ImageStreams), RBAC policies, and secrets. A backup consists of:

1. **etcd snapshot** -- a point-in-time snapshot of the etcd data directory
2. **Static pod manifests** -- the control plane pod definitions from `/etc/kubernetes/manifests`
3. **etcd PKI** -- certificates and keys from `/etc/kubernetes/pki/etcd`

OpenShift provides the `cluster-backup.sh` script on every control plane node to capture all three components in a single operation.

### Control Plane Certificates

OpenShift manages a deep certificate hierarchy for the control plane:

```
Root CA
 +-- etcd CA
 |    +-- etcd-peer certificates (member-to-member)
 |    +-- etcd-server certificates (client-to-server)
 |    +-- etcd-client certificates (API server to etcd)
 +-- API Server CA
 |    +-- API server serving cert
 |    +-- API server client certs (kubelet, controller-manager)
 +-- Ingress CA
 |    +-- Wildcard cert (*.apps.<cluster>.<domain>)
 +-- Service CA
      +-- Service serving certs (auto-injected)
```

The `cluster-etcd-operator` and `cluster-kube-apiserver-operator` rotate these certificates automatically. Default rotation happens 30 days before expiry. You can force rotation when needed.

### etcd Encryption at Rest

By default, etcd stores data unencrypted. OpenShift supports encryption at rest for sensitive resources (Secrets, ConfigMaps, Routes, OAuth tokens) using `aescbc` or `aesgcm` encryption. Enabling encryption is an API server configuration change that the operator applies progressively across all API server instances.

### Disaster Recovery Scenarios

| Scenario | Impact | Recovery Method |
|----------|--------|-----------------|
| Single etcd member failure | Degraded but functional (2/3 quorum) | Replace the failed node; operator re-adds member |
| Two etcd members fail | **Quorum lost** -- cluster is read-only | Restore from backup on surviving member |
| All three masters fail | **Total outage** | Full restore from backup to new nodes |
| Expired certificates | API server unreachable | Force certificate rotation |
| Corrupted etcd data | Unpredictable behavior | Restore from last known-good backup |

## Step-by-Step

### Step 1: Check etcd Cluster Health

Verify the etcd cluster is healthy before performing any operations.

```bash
# Check the cluster-etcd-operator status
oc get clusteroperator etcd

# View etcd pod status on all control plane nodes
oc get pods -n openshift-etcd -l app=etcd

# Check etcd member list by exec-ing into an etcd pod
oc rsh -n openshift-etcd -c etcdctl $(oc get pods -n openshift-etcd -l app=etcd -o name | head -1) \
  etcdctl member list -w table

# Check endpoint health
oc rsh -n openshift-etcd -c etcdctl $(oc get pods -n openshift-etcd -l app=etcd -o name | head -1) \
  etcdctl endpoint health --cluster -w table
```

Expected output for a healthy three-member cluster:

```
+------------------+---------+--------+-----------+------------+
|        ID        | STATUS  |  NAME  | PEER URLS | IS LEARNER |
+------------------+---------+--------+-----------+------------+
| 4e4c81c3a6e0c4f2 | started | master-0 | https://10.0.0.10:2380 |  false |
| 7a1b2c3d4e5f6a7b | started | master-1 | https://10.0.0.11:2380 |  false |
| 9f8e7d6c5b4a3928 | started | master-2 | https://10.0.0.12:2380 |  false |
+------------------+---------+--------+-----------+------------+
```

### Step 2: Check etcd Performance Metrics

etcd performance directly impacts cluster responsiveness. Monitor key metrics.

```bash
# Check etcd database size
oc rsh -n openshift-etcd -c etcdctl $(oc get pods -n openshift-etcd -l app=etcd -o name | head -1) \
  etcdctl endpoint status --cluster -w table

# View etcd metrics via Prometheus (if monitoring is configured)
# Key metrics to watch:
#   etcd_server_has_leader           -- should always be 1
#   etcd_server_leader_changes_seen  -- frequent changes indicate instability
#   etcd_disk_wal_fsync_duration     -- should be < 10ms (p99)
#   etcd_network_peer_round_trip_time -- should be < 50ms (p99)
#   etcd_mvcc_db_total_size_in_bytes -- should stay below 8GB (hard limit)

# Check via OpenShift monitoring
oc -n openshift-monitoring exec -c prometheus $(oc get pods -n openshift-monitoring -l app.kubernetes.io/name=prometheus -o name | head -1) -- \
  promtool query instant http://localhost:9090 'etcd_mvcc_db_total_size_in_bytes'
```

**Failure mode -- database size:** etcd has a hard limit of 8GB. If the database approaches this limit, the cluster becomes read-only. Watch `etcd_mvcc_db_total_size_in_bytes` and set alerts at 6GB. Common causes: excessive Events, large Secrets, or too many CRD instances.

### Step 3: Perform an etcd Backup

Run the backup script on a control plane node. In CRC, you can SSH directly; in a full cluster, use `oc debug node/`.

```bash
# On CRC -- SSH into the node
# ssh -i ~/.crc/machines/crc/id_ecdsa core@$(crc ip)

# On a full cluster -- debug into a control plane node
oc debug node/<master-node-name>

# Once inside the debug shell, chroot to the host filesystem
chroot /host

# Run the OpenShift-provided backup script
/usr/local/bin/cluster-backup.sh /home/core/assets/backup

# The script creates a directory like:
#   /home/core/assets/backup/
#     snapshot_<timestamp>.db          -- etcd snapshot
#     static_kuberesources_<timestamp>.tar.gz -- static pod manifests + certs

# Verify the backup
ls -lah /home/core/assets/backup/
```

**Important:** The backup script must run on a control plane node, not from your workstation. It accesses etcd certificates and the data directory directly.

For production environments, automate backups with the CronJob manifest provided in this lesson.

### Step 4: Apply the Automated Backup CronJob

For production clusters, schedule regular etcd backups.

```bash
# Review the backup CronJob manifest
cat manifests/etcd-backup-cronjob.yaml

# Apply the backup CronJob
oc apply -f manifests/etcd-backup-cronjob.yaml

# Verify the CronJob was created
oc get cronjob etcd-backup -n openshift-etcd

# Trigger a manual run to test
oc create job --from=cronjob/etcd-backup etcd-backup-manual-test -n openshift-etcd

# Watch the job complete
oc get jobs -n openshift-etcd -w
```

**Note on CRC:** The CronJob manifest requires a multi-node cluster with proper storage. On CRC, review the manifest conceptually and use the manual backup procedure from Step 3 instead.

### Step 5: Inspect Control Plane Certificates

Check certificate expiration dates and understand the rotation lifecycle.

```bash
# List all certificates managed by the etcd operator
oc get secrets -n openshift-etcd -o name | grep -E 'tls|cert'

# Check etcd certificate expiration
oc get secret etcd-peer-<master-node> -n openshift-etcd -o jsonpath='{.data.tls\.crt}' | \
  base64 -d | openssl x509 -noout -dates -subject

# Check all API server certificates
oc get secret -n openshift-kube-apiserver -o name | grep -E 'cert|tls'

# Use the OpenShift certificate inspection tool
# This shows all certificates and their expiration dates
oc adm certificates approve --help  # view certificate-related commands

# Check certificate signing requests (CSRs)
oc get csr

# View certificate expiration across the cluster
oc get co kube-apiserver -o jsonpath='{.status.conditions[?(@.type=="Progressing")].message}'
```

**Failure mode -- expired certificates:** If certificates expire (for example, a node was powered off for 30+ days and missed rotation), the API server cannot communicate with etcd. Symptoms: `connection refused` errors, nodes showing `NotReady`. Recovery requires force-rotating certificates from the node itself.

### Step 6: Force Certificate Rotation (When Needed)

If certificates are near expiry or have expired, force a rotation.

```bash
# Force rotation of the API server serving certificate
# WARNING: This causes brief API server restarts
oc delete secret serving-cert-<name> -n openshift-kube-apiserver

# Force rotation of etcd certificates
# The etcd operator watches for deleted secrets and regenerates them
oc delete secret etcd-peer-<master-node> -n openshift-etcd

# Monitor the operator as it rotates certificates
oc get clusteroperator etcd -w
oc get clusteroperator kube-apiserver -w

# In a full disaster scenario where the API is unreachable:
# SSH to a master node and run:
# sudo crictl ps | grep kube-apiserver
# sudo crictl logs <container-id>
# Then follow the OpenShift disaster recovery documentation for
# expired certificate recovery
```

**Recovery procedure for fully expired certificates (API unreachable):**

1. SSH into each control plane node
2. Move the expired certificates out of `/etc/kubernetes/pki/etcd/`
3. Restart the kubelet: `sudo systemctl restart kubelet`
4. The machine-config-operator will detect the missing certificates and regenerate them
5. Monitor recovery: `sudo crictl logs <etcd-container-id>`

### Step 7: Enable etcd Encryption at Rest

Encrypt sensitive data stored in etcd. This is a production hardening requirement for compliance (PCI-DSS, HIPAA, SOC2).

```bash
# Check current encryption status
oc get apiserver cluster -o jsonpath='{.spec.encryption.type}'
# Empty or "identity" means no encryption

# Review the encryption configuration manifest
cat manifests/etcd-encryption.yaml

# Apply encryption at rest
oc apply -f manifests/etcd-encryption.yaml

# Monitor the encryption migration
# This takes time -- the API server re-encrypts all existing resources
oc get openshiftapiserver -o=jsonpath='{range .items[0].status.conditions[?(@.type=="Encrypted")]}{.type}{" "}{.status}{" "}{.message}{"\n"}'

# Watch the kube-apiserver operator roll out the change
oc get clusteroperator kube-apiserver -w

# Verify encryption is active (may take 10-20 minutes on large clusters)
oc get apiserver cluster -o jsonpath='{.spec.encryption.type}'
# Should output: aescbc
```

**Failure mode -- encryption rollout stall:** If the encryption migration stalls (one API server instance fails to restart), check:

```bash
oc get pods -n openshift-kube-apiserver
oc logs <stalled-apiserver-pod> -n openshift-kube-apiserver
```

Common cause: insufficient memory on the control plane node during re-encryption. The API server needs extra memory to re-write all resources. Ensure control plane nodes have adequate resources (at minimum 16GB RAM for production).

### Step 8: etcd Disaster Recovery -- Restoring from Backup

This procedure restores a cluster from an etcd backup. **This is a destructive operation -- all changes after the backup are lost.**

```bash
# Prerequisites:
# - A valid etcd backup (snapshot_<timestamp>.db and
#   static_kuberesources_<timestamp>.tar.gz)
# - SSH access to a control plane node

# 1. SSH into the recovery control plane node
# ssh core@<master-node>

# 2. Copy backup files to the node (if not already there)
# scp backup/snapshot_<timestamp>.db core@<master-node>:/home/core/
# scp backup/static_kuberesources_<timestamp>.tar.gz core@<master-node>:/home/core/

# 3. Run the restore script (available on every RHCOS control plane node)
sudo /usr/local/bin/cluster-restore.sh /home/core/

# 4. The restore script will:
#    - Stop etcd and API server static pods
#    - Restore the etcd snapshot
#    - Restore static pod manifests and certificates
#    - Restart the kubelet
#    - etcd starts as a single-member cluster

# 5. On a multi-master cluster, force etcd redeployment to re-add members
# After the first master is restored, run from a machine with oc access:
oc patch etcd cluster -p='{"spec": {"forceRedeploymentReason": "recovery-'"$(date --rfc-3339=ns)"'"}}' --type=merge

# 6. Monitor recovery
oc get nodes
oc get clusteroperators
oc get pods -n openshift-etcd
```

**Recovery timeline:**

| Phase | Duration | Description |
|-------|----------|-------------|
| Restore on first master | 5-10 min | etcd starts as single member |
| Operator re-adds members | 10-20 min | cluster-etcd-operator adds remaining members |
| Full cluster health | 20-40 min | All operators reconcile and report healthy |

### Step 9: Defragment etcd

After heavy delete operations or a restore, defragment etcd to reclaim disk space.

```bash
# Check current database size vs in-use size
oc rsh -n openshift-etcd -c etcdctl $(oc get pods -n openshift-etcd -l app=etcd -o name | head -1) \
  etcdctl endpoint status --cluster -w table

# The output shows DB SIZE and DB SIZE IN USE
# If DB SIZE is significantly larger than IN USE, defragment

# Defragment all members (run one at a time to avoid quorum issues)
oc rsh -n openshift-etcd -c etcdctl $(oc get pods -n openshift-etcd -l app=etcd -o name | head -1) \
  etcdctl defrag --cluster

# Verify reduced database size
oc rsh -n openshift-etcd -c etcdctl $(oc get pods -n openshift-etcd -l app=etcd -o name | head -1) \
  etcdctl endpoint status --cluster -w table
```

**Warning:** Defragmentation briefly locks the etcd member being defragmented. On a three-member cluster, this is safe (quorum is maintained by the other two). Never defragment more than one member simultaneously.

## Verification

After completing the lesson, verify your understanding:

```bash
# 1. Confirm etcd cluster health
oc get clusteroperator etcd -o jsonpath='{.status.conditions[?(@.type=="Available")].status}'
# Expected: True

# 2. Verify a backup exists (on the control plane node)
# ls -la /home/core/assets/backup/

# 3. Check encryption status (if Step 7 was completed)
oc get apiserver cluster -o jsonpath='{.spec.encryption.type}'
# Expected: aescbc

# 4. Verify all cluster operators are healthy
oc get clusteroperators | grep -E 'etcd|kube-apiserver|kube-controller-manager'
# All should show Available=True, Degraded=False

# 5. Confirm certificate validity
oc get csr --no-headers | wc -l
# No pending CSRs (all should be approved)
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| etcd deployment | Manual or kubeadm-managed static pods | cluster-etcd-operator manages static pods |
| etcd backup | Manual `etcdctl snapshot save` | Built-in `cluster-backup.sh` script on nodes |
| etcd restore | Manual snapshot restore + cluster reconfiguration | `cluster-restore.sh` + operator-driven member recovery |
| Certificate management | `kubeadm certs renew` (manual) | Automatic rotation by operators (30 days before expiry) |
| Certificate monitoring | Manual checks with `openssl` | Operator reports via ClusterOperator status |
| Encryption at rest | Manual etcd encryption config in API server manifest | `oc apply` on APIServer resource; operator handles rollout |
| Defragmentation | Manual `etcdctl defrag` | Operator schedules periodic defrag; manual also available |
| Disaster recovery | Fully manual, varies by setup | Documented scripts + operator-assisted recovery |
| Health monitoring | Manual `etcdctl endpoint health` | Operator + Prometheus metrics + alerts pre-configured |
| Member management | Manual `etcdctl member add/remove` | Operator automatically manages membership |

## Key Takeaways

- **etcd is the single most critical component** in your cluster. A corrupted or lost etcd means a lost cluster. Back it up regularly and test restores.
- **OpenShift automates the hard parts** of etcd management (certificates, member scaling, health monitoring) through the cluster-etcd-operator, but you must still understand the manual procedures for disaster recovery.
- **Encryption at rest is a one-command operation** in OpenShift but is irreversible without re-encrypting. Enable it early in the cluster lifecycle for compliance.
- **Certificate rotation is automatic** but can fail if nodes are offline for extended periods. Monitor ClusterOperator status and CSR queues.
- **Backup frequency should match your RPO** (Recovery Point Objective). For production clusters, back up etcd at minimum every 4 hours and retain backups for at least 7 days.

## Cleanup

This lesson primarily uses read-only inspection commands. Clean up any resources created:

```bash
# Remove the automated backup CronJob (if applied)
oc delete -f manifests/etcd-backup-cronjob.yaml --ignore-not-found

# Remove the manual test job (if created)
oc delete job etcd-backup-manual-test -n openshift-etcd --ignore-not-found

# Note: Do NOT revert encryption at rest unless you have a specific reason.
# Reverting encryption requires re-writing all encrypted resources back to
# plaintext, which the operator handles if you set encryption.type to "identity".

# Clean up backup files on the control plane node (optional)
# ssh core@<master-node> "rm -rf /home/core/assets/backup/"
```

## Next Steps

In **L3-M1.5 -- Resource Management & Quotas**, you will learn how to manage cluster capacity through ResourceQuotas, LimitRanges, and ClusterResourceQuotas. You will configure priority classes for workload scheduling and implement capacity planning strategies for production environments. The etcd health monitoring you learned here feeds directly into capacity planning -- an overloaded etcd is often a symptom of a cluster that has outgrown its resource allocations.
