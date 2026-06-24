# L3-M4.3 — Stateful Workloads at Scale

**Level:** Expert
**Duration:** 45 min

## Overview

In Kubernetes, running stateful workloads means wrangling StatefulSets, PVCs, headless Services, and a lot of operational glue — backups, failover, scaling, and storage tuning are all your responsibility. OpenShift builds on this foundation with operator-managed databases (CrunchyData PostgreSQL, Strimzi Kafka), integrated storage performance controls, and enterprise backup strategies that turn day-2 stateful operations into declarative, auditable workflows. This lesson covers production-grade StatefulSet patterns, operator-managed database deployments, storage IOPS and throughput considerations, and backup strategies for stateful workloads running on OpenShift.

## Prerequisites

- Completed: L2-M2.3 (Using Operators: Database Example)
- OpenShift 4.12+ cluster (CRC for conceptual exercises; a multi-node cluster with ODF for storage performance testing)
- `cluster-admin` access (logged in as `kubeadmin`)
- Familiarity with Kubernetes StatefulSets, PVCs, and StorageClasses
- Basic understanding of PostgreSQL and Kafka operational concepts

> **Note:** CRC can run the operator installations and basic CR creation, but storage performance benchmarks and multi-replica StatefulSets require a cluster with adequate resources (3+ worker nodes, ODF or a CSI driver with IOPS/throughput controls). The lesson notes where CRC limitations apply.

## K8s Context

In vanilla Kubernetes, stateful workloads require significant operational investment:

- **StatefulSets** provide stable network identities and ordered deployment, but you manage everything above the Pod level — replication, failover, backup, and restore are your problem.
- **Persistent Volumes** use StorageClasses for dynamic provisioning, but tuning IOPS, throughput, or selecting the right backend (SSD vs HDD, local vs network) requires deep CSI driver knowledge and manual StorageClass configuration.
- **Database operations** (failover, backup, point-in-time recovery, scaling read replicas) are typically handled by Helm charts with init containers and sidecar scripts — brittle, hard to test, and impossible to audit.
- **Kafka clusters** require ZooKeeper (or KRaft), partition rebalancing, and rack-aware replica placement — all configured through ConfigMaps and StatefulSet annotations that nobody fully understands.
- **Backups** rely on external tools (Velero, custom CronJobs with `pg_dump`, etc.) that run outside the cluster lifecycle.

OpenShift shifts all of this into the operator pattern: declare your desired database topology, and the operator handles provisioning, replication, failover, backup, monitoring, and upgrades.

## Concepts

### StatefulSet Patterns on OpenShift

StatefulSets on OpenShift work identically to Kubernetes, but the platform's security model and operator ecosystem change how you design them.

```
+------------------------------------------------------------------+
|                    StatefulSet Architecture                       |
|                                                                  |
|  +------------------+  +------------------+  +------------------+|
|  | pod-0 (primary)  |  | pod-1 (replica)  |  | pod-2 (replica)  ||
|  | +--------------+ |  | +--------------+ |  | +--------------+ ||
|  | | app container| |  | | app container| |  | | app container| ||
|  | +--------------+ |  | +--------------+ |  | +--------------+ ||
|  | | sidecar      | |  | | sidecar      | |  | | sidecar      | ||
|  | | (backup/mon) | |  | | (backup/mon) | |  | | (backup/mon) | ||
|  | +--------------+ |  | +--------------+ |  | +--------------+ ||
|  |   |  PVC-0     |  |   |  PVC-1     |  |   |  PVC-2     |   ||
|  +---|-------------+  +---|-------------+  +---|-------------+  ||
|      v                    v                    v                  |
|  +-------+            +-------+            +-------+             |
|  | PV-0  |            | PV-1  |            | PV-2  |             |
|  | (SSD) |            | (SSD) |            | (SSD) |             |
|  +-------+            +-------+            +-------+             |
|                                                                  |
|  Headless Service: db-cluster.project.svc.cluster.local          |
|  Per-pod DNS:      pod-0.db-cluster.project.svc.cluster.local    |
+------------------------------------------------------------------+
```

**Key OpenShift considerations for StatefulSets:**

1. **SCC constraints** — Most database images expect root. You need either UBI-based images (preferred) or the `anyuid` SCC granted to the ServiceAccount. Operator-managed databases handle this automatically.
2. **Pod Disruption Budgets** — Critical for quorum-based systems. Always define PDBs alongside StatefulSets.
3. **Anti-affinity rules** — Spread replicas across nodes (and ideally failure domains) using `podAntiAffinity`.
4. **Topology spread constraints** — OpenShift 4.12+ supports `topologySpreadConstraints` for more granular control than anti-affinity alone.

### Operator-Managed Databases

Rather than managing StatefulSets directly, production OpenShift deployments use operators that encode the full operational lifecycle of a database:

```
+-----------------------------------------------------------+
|              Operator-Managed Database Stack               |
|                                                            |
|  +-------------+    +------------------+                   |
|  | Custom      | -> | Operator         |                   |
|  | Resource    |    | Controller       |                   |
|  | (desired    |    | (reconciliation  |                   |
|  |  state)     |    |  loop)           |                   |
|  +-------------+    +--------+---------+                   |
|                              |                             |
|                     Creates / manages:                     |
|                              |                             |
|       +----------+-----------+----------+--------+         |
|       |          |           |          |        |         |
|       v          v           v          v        v         |
|  StatefulSet  Services   Secrets    PDBs   CronJobs       |
|  (pods+PVCs)  (headless  (creds,   (quorum (backups,      |
|               + client)   certs)   guard)  maintenance)   |
|                                                            |
+-----------------------------------------------------------+
```

**CrunchyData PostgreSQL Operator (PGO):**
- Manages PostgreSQL clusters with streaming replication, automatic failover (Patroni-based), connection pooling (PgBouncer), and point-in-time recovery (pgBackRest).
- Supports S3, GCS, and Azure Blob storage for backups.
- Handles major version upgrades in-place.
- Provides built-in monitoring with a Prometheus exporter sidecar.

**Strimzi Kafka Operator:**
- Manages Kafka clusters, ZooKeeper ensembles (or KRaft mode), Kafka Connect, Mirror Maker, and Schema Registry.
- Handles rolling upgrades, partition rebalancing, and rack-aware replica placement.
- Integrates with OpenShift Routes for external access with TLS.
- Supports JBOD storage (multiple volumes per broker) for throughput optimization.

### Storage Performance Considerations

Storage performance is the single most important factor for stateful workloads. The three key metrics are:

| Metric | What It Measures | Impact | Typical Requirements |
|--------|-----------------|--------|---------------------|
| **IOPS** | I/O operations per second | Random read/write performance | PostgreSQL WAL: 3000+ IOPS; Kafka: 1000+ IOPS |
| **Throughput** | MB/s sustained read/write | Sequential I/O performance | Kafka log segments: 100+ MB/s; backup restore: 200+ MB/s |
| **Latency** | Time per I/O operation | Transaction commit time | PostgreSQL fsync: < 1ms p99; Kafka produce ack: < 5ms |

```
Storage Performance Hierarchy (OpenShift):

  Fastest   +------------------+
    |       | Local NVMe/SSD   |  IOPS: 100k+, Latency: < 0.1ms
    |       | (hostPath/local) |  Use: Hot databases, low-latency Kafka
    |       +------------------+
    |       | ODF (Ceph RBD)   |  IOPS: 10k-50k, Latency: 0.5-2ms
    |       | SSD-backed pool  |  Use: General databases, stateful apps
    |       +------------------+
    |       | ODF (CephFS)     |  IOPS: 5k-20k, Latency: 1-5ms
    |       | shared filesystem|  Use: ReadWriteMany workloads, logs
    |       +------------------+
    |       | Cloud EBS/Disks  |  IOPS: varies (gp3: 3k-16k)
    |       | (AWS, GCP, Azure)|  Use: Cloud-hosted clusters
    v       +------------------+
  Slowest   | NFS              |  IOPS: 1k-5k, Latency: 2-10ms
            | (legacy/shared)  |  Use: Non-critical data, shared config
            +------------------+
```

**OpenShift-specific storage tools:**

- **OpenShift Data Foundation (ODF)** — Ceph-based storage with RBD (block), CephFS (file), and RGW (object). Provides multiple StorageClasses with different performance tiers.
- **StorageClass parameters** — CSI drivers expose IOPS/throughput provisioning via StorageClass parameters (e.g., `csi.storage.k8s.io/provisioner-secret-name` for encrypted volumes, `type: io2` for AWS EBS).
- **Volume Snapshot** — CSI-based snapshots for consistent point-in-time copies without application downtime.

### Backup Strategies for Stateful Workloads

```
+--------------------------------------------------------------------+
|                    Backup Strategy Matrix                           |
|                                                                    |
|  Application-Level Backups (preferred for databases):              |
|  +--------------------+  +--------------------+                    |
|  | pg_dump / pgBackRest|  | Kafka MirrorMaker |                    |
|  | (logical/physical) |  | (topic replication)|                    |
|  +--------------------+  +--------------------+                    |
|         |                        |                                 |
|         v                        v                                 |
|  +----------------------------------------------+                  |
|  | Object Storage (S3 / ODF RGW / MinIO)        |                  |
|  | - Versioned buckets                           |                  |
|  | - Lifecycle policies (30d hot, 90d archive)   |                  |
|  +----------------------------------------------+                  |
|                                                                    |
|  Infrastructure-Level Backups (cluster-wide):                      |
|  +--------------------+  +--------------------+                    |
|  | Velero             |  | CSI Volume         |                    |
|  | (full namespace    |  | Snapshots          |                    |
|  |  backup/restore)   |  | (block-level copy) |                    |
|  +--------------------+  +--------------------+                    |
+--------------------------------------------------------------------+
```

**Best practices:**
1. **Application-aware backups first** — `pgBackRest` for PostgreSQL, MirrorMaker2 for Kafka. These understand data consistency guarantees.
2. **CSI snapshots for fast recovery** — Volume snapshots are instant and space-efficient. Use them for pre-upgrade checkpoints.
3. **Velero for disaster recovery** — Backs up entire namespaces (resources + PVs). Use for cluster migration and DR.
4. **3-2-1 rule** — 3 copies of data, on 2 different media types, with 1 offsite. For OpenShift: local PV + CSI snapshot + S3 bucket.

## Step-by-Step

### Step 1: Create the Project and Examine Storage Classes

Create a dedicated project and review available storage to understand your performance options.

```bash
oc new-project stateful-workloads
oc get storageclasses
```

On CRC, you will see a basic StorageClass. On a production cluster with ODF, you would see multiple classes with different performance tiers. Examine the default StorageClass parameters:

```bash
oc describe storageclass $(oc get storageclass -o jsonpath='{.items[?(@.metadata.annotations.storageclass\.kubernetes\.io/is-default-class=="true")].metadata.name}')
```

### Step 2: Deploy a Production StatefulSet Pattern

Apply the base StatefulSet manifest that demonstrates production patterns — anti-affinity, PDBs, resource limits, and proper storage configuration.

```bash
oc apply -f manifests/statefulset-production.yaml
```

Examine the key production elements in the manifest:

```yaml
# From manifests/statefulset-production.yaml — key sections:
# 1. Pod anti-affinity to spread across nodes
# 2. Resource requests and limits (Guaranteed QoS)
# 3. volumeClaimTemplates with StorageClass selection
# 4. Readiness and liveness probes
# 5. PodDisruptionBudget for quorum protection
```

Verify the StatefulSet is running and PVCs are bound:

```bash
oc get statefulset
oc get pods -l app=redis-cluster
oc get pvc -l app=redis-cluster
```

### Step 3: Install the CrunchyData PostgreSQL Operator

Install the PGO operator from OperatorHub. In production, you would use an approved subscription; for this lesson, we install via the CLI.

```bash
# Create the operator namespace and subscription
oc apply -f manifests/pgo-subscription.yaml
```

Wait for the operator to become available:

```bash
oc get csv -n openshift-operators -w
```

You should see `postgresoperator` with a status of `Succeeded`. This typically takes 1-2 minutes.

### Step 4: Deploy a PostgreSQL Cluster with PGO

Apply the PostgreSQL cluster CR that defines a 3-instance HA cluster with backups, connection pooling, and monitoring.

```bash
oc apply -f manifests/postgres-cluster.yaml
```

Watch the operator create all the required resources:

```bash
# Watch pods being created (primary + replicas + pgBouncer + backup jobs)
oc get pods -l postgres-operator.crunchydata.com/cluster=pg-production -w
```

The operator creates:

```bash
# List all resources created by the operator
oc get all,secrets,configmaps,pvc -l postgres-operator.crunchydata.com/cluster=pg-production
```

Verify the cluster is healthy:

```bash
# Check the PostgresCluster status
oc get postgrescluster pg-production -o jsonpath='{.status.instances[*].readyReplicas}'
```

### Step 5: Test PostgreSQL Failover

Simulate a primary failure and observe automatic failover.

```bash
# Identify the current primary
oc get pods -l postgres-operator.crunchydata.com/cluster=pg-production \
  -l postgres-operator.crunchydata.com/role=master \
  -o name

# Delete the primary pod to trigger failover
oc delete pod -l postgres-operator.crunchydata.com/cluster=pg-production \
  -l postgres-operator.crunchydata.com/role=master

# Watch failover happen (Patroni elects a new primary within ~30 seconds)
oc get pods -l postgres-operator.crunchydata.com/cluster=pg-production -w
```

After failover, verify the new primary:

```bash
oc get pods -l postgres-operator.crunchydata.com/cluster=pg-production \
  -l postgres-operator.crunchydata.com/role=master \
  -o name
```

> **Failure mode:** If Patroni cannot elect a new primary (all replicas unhealthy), the cluster enters read-only mode. Recovery: check PVC status (`oc get pvc`), inspect Patroni logs (`oc logs <pod> -c database`), and if needed, restore from backup using `pgBackRest`.

### Step 6: Install the Strimzi Kafka Operator

Install the Strimzi operator for managing Kafka clusters.

```bash
oc apply -f manifests/strimzi-subscription.yaml
```

Wait for the operator to be ready:

```bash
oc get csv -n openshift-operators | grep strimzi
```

### Step 7: Deploy a Kafka Cluster with Strimzi

Apply the Kafka cluster CR that defines a 3-broker cluster with JBOD storage, rack awareness, and external access via Routes.

```bash
oc apply -f manifests/kafka-cluster.yaml
```

Watch the Kafka cluster come up (ZooKeeper first, then Kafka brokers):

```bash
# This takes 3-5 minutes as ZooKeeper must be ready before brokers start
oc get pods -l strimzi.io/cluster=kafka-production -w
```

Verify the Kafka cluster is ready:

```bash
oc get kafka kafka-production -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
```

### Step 8: Test Kafka with a Producer and Consumer

Create a test topic and verify message flow:

```bash
# Create a topic
oc apply -f manifests/kafka-topic.yaml

# Verify the topic was created
oc get kafkatopic test-throughput -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
```

Run a producer and consumer to verify end-to-end message flow:

```bash
# Start a producer (send 1000 messages)
oc run kafka-producer --rm -i --tty \
  --image=quay.io/strimzi/kafka:latest-kafka-3.6.0 \
  --restart=Never \
  -- bin/kafka-producer-perf-test.sh \
    --topic test-throughput \
    --num-records 1000 \
    --record-size 1024 \
    --throughput -1 \
    --producer-props bootstrap.servers=kafka-production-kafka-bootstrap:9092

# Start a consumer to verify messages (in a separate terminal or after the producer)
oc run kafka-consumer --rm -i --tty \
  --image=quay.io/strimzi/kafka:latest-kafka-3.6.0 \
  --restart=Never \
  -- bin/kafka-console-consumer.sh \
    --bootstrap-server kafka-production-kafka-bootstrap:9092 \
    --topic test-throughput \
    --from-beginning \
    --max-messages 10
```

### Step 9: Configure Storage Performance Tuning

Apply a StorageClass optimized for database workloads with specific IOPS and throughput parameters. This example uses AWS EBS; adapt parameters for your storage backend.

```bash
oc apply -f manifests/storageclass-high-iops.yaml
```

For clusters with ODF, you can create a performance-optimized pool:

```bash
# Verify the StorageClass is available
oc get storageclass high-iops-ssd
```

> **Note on CRC:** CRC uses a single-node setup with limited storage options. The StorageClass manifest demonstrates the pattern; actual IOPS tuning requires a production cluster with ODF or cloud-provisioned storage.

### Step 10: Configure Backup for PostgreSQL

The PGO PostgresCluster CR includes a backup section using pgBackRest. Verify backups are running:

```bash
# Check the backup schedule
oc get postgrescluster pg-production -o jsonpath='{.spec.backups.pgbackrest.repos[0].schedules}' | jq .

# Manually trigger a backup
oc annotate postgrescluster pg-production \
  postgres-operator.crunchydata.com/pgbackrest-backup="$(date)" --overwrite

# Watch the backup job
oc get pods -l postgres-operator.crunchydata.com/pgbackrest-backup -w
```

To test a point-in-time recovery, you would create a new cluster from the backup:

```bash
oc apply -f manifests/postgres-restore.yaml
```

> **Failure mode — backup failure:** If pgBackRest cannot write to the backup destination (S3 connectivity, permission issues), check the backup pod logs: `oc logs -l postgres-operator.crunchydata.com/pgbackrest-backup`. Common causes: expired credentials in the backup Secret, S3 bucket policy changes, or network egress rules blocking outbound HTTPS.

## Verification

Run the following commands to verify all components are working:

```bash
# 1. Check the base StatefulSet
echo "=== StatefulSet ==="
oc get statefulset redis-cluster -o wide
oc get pdb redis-cluster-pdb

# 2. Check the PostgreSQL cluster
echo "=== PostgreSQL Cluster ==="
oc get postgrescluster pg-production
oc get pods -l postgres-operator.crunchydata.com/cluster=pg-production

# 3. Check the Kafka cluster
echo "=== Kafka Cluster ==="
oc get kafka kafka-production
oc get pods -l strimzi.io/cluster=kafka-production

# 4. Check PVCs and storage
echo "=== Storage ==="
oc get pvc --sort-by='.spec.resources.requests.storage'

# 5. Check backup status
echo "=== Backups ==="
oc get postgrescluster pg-production -o jsonpath='{.status.pgbackrest}' | jq .
```

**Expected results:**
- `redis-cluster` StatefulSet: 3/3 pods ready, 3 PVCs bound
- `pg-production` PostgreSQL: 3 instances ready (1 primary + 2 replicas), PgBouncer pods running
- `kafka-production` Kafka: 3 brokers ready, 3 ZooKeeper nodes ready
- All PVCs in `Bound` state with expected storage sizes
- pgBackRest showing successful backup history

**In the Web Console:**
1. Navigate to **Workloads > StatefulSets** to see all stateful deployments
2. Check **Storage > PersistentVolumeClaims** for volume health
3. Under **Installed Operators**, verify PGO and Strimzi operator status is `Succeeded`

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| StatefulSet deployment | Manual YAML, manage your own PDBs and anti-affinity | Same StatefulSet API, but operators handle production patterns automatically |
| Database operations | Helm charts with sidecar scripts; manual failover testing | CrunchyData PGO: declarative HA, automated failover via Patroni, built-in pgBackRest |
| Kafka deployment | Manual StatefulSets or Strimzi (install OLM first) | Strimzi via OperatorHub; one-click install, integrated Route-based external access |
| Operator installation | Install OLM yourself, find operators manually | OperatorHub pre-installed; curated, certified operator catalog |
| Storage classes | CSI driver + manual StorageClass YAML | ODF provides multiple performance tiers out of the box; integrated console management |
| Backup/restore | Velero (install separately), custom CronJobs | Operator-managed backups (pgBackRest, MirrorMaker2) + Velero via OperatorHub |
| Storage monitoring | Install custom dashboards | Built-in ODF monitoring dashboards; PVC usage alerts in the console |
| Security for stateful pods | PSA labels on namespace; manual SecurityContext | SCCs enforced; operators pre-configure correct security contexts for their workloads |
| Volume snapshots | CSI driver dependent; manual VolumeSnapshot YAML | ODF CSI supports snapshots natively; console UI for snapshot management |
| Failover testing | Manual pod deletion; hope for the best | Operators handle quorum management; PDBs prevent accidental quorum loss during upgrades |

## Key Takeaways

- **Use operators for production databases** — Never manage PostgreSQL, Kafka, or other complex stateful systems with raw StatefulSets in production. Operators encode years of operational knowledge (failover logic, backup procedures, upgrade paths) that you would otherwise need to build and maintain yourself.
- **Storage performance determines database performance** — Choose your StorageClass based on workload requirements (IOPS for OLTP databases, throughput for streaming systems). Test storage performance before deploying stateful workloads. The gap between NFS (1k IOPS) and local NVMe (100k+ IOPS) is two orders of magnitude.
- **Backup strategies must be application-aware** — CSI volume snapshots and Velero provide infrastructure-level backups, but application-level tools (pgBackRest, MirrorMaker2) understand data consistency guarantees. Use both: application-level for routine recovery, infrastructure-level for disaster recovery.
- **Pod Disruption Budgets are non-negotiable** — Without PDBs, a routine node drain during cluster upgrades can take down your entire database cluster. Always define PDBs with `minAvailable` set to maintain quorum (e.g., 2 out of 3 for a 3-node cluster).
- **Anti-affinity and topology spread prevent correlated failures** — If all your database replicas land on the same node (or in the same availability zone), a single failure takes out the entire cluster. Use `podAntiAffinity` with `requiredDuringSchedulingIgnoredDuringExecution` for hard guarantees.

## Cleanup

```bash
# Delete Kafka resources
oc delete kafkatopic test-throughput
oc delete kafka kafka-production

# Delete PostgreSQL resources
oc delete postgrescluster pg-production

# Wait for operator-managed resources to be cleaned up (PVCs may persist)
sleep 15

# Delete the base StatefulSet
oc delete -f manifests/statefulset-production.yaml

# Delete remaining PVCs (operators intentionally leave PVCs for data safety)
oc delete pvc -l app=redis-cluster
oc delete pvc -l postgres-operator.crunchydata.com/cluster=pg-production
oc delete pvc -l strimzi.io/cluster=kafka-production

# Delete operator subscriptions (optional — these are cluster-wide)
# oc delete -f manifests/pgo-subscription.yaml
# oc delete -f manifests/strimzi-subscription.yaml

# Delete the project
oc delete project stateful-workloads
```

> **Important:** Operators intentionally leave PVCs behind when you delete a database cluster CR. This is a safety feature — it prevents accidental data loss. You must explicitly delete PVCs after verifying you no longer need the data.

## Next Steps

In **L3-M4.4 — Batch & HPC Workloads**, you will explore Jobs, CronJobs, and OpenShift-specific scheduling for batch processing, including NVIDIA GPU Operator integration for ML/HPC workloads and MPI job patterns for distributed computing.
