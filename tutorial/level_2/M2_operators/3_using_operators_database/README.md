# L2-M2.3 — Using Operators: Database Example

**Level:** Practitioner
**Duration:** 1 hr

## Overview

In Kubernetes, deploying a production-grade PostgreSQL cluster means wrestling with StatefulSets, headless Services, PVCs, backup CronJobs, replication configuration, failover logic, and credential management -- all assembled by hand. Operators eliminate this toil by encoding database expertise into a controller that manages the full lifecycle through Custom Resources. In this lesson you will deploy PostgreSQL using the CrunchyData Postgres Operator (PGO), configure the cluster declaratively, perform backup and restore, and scale replicas -- all by editing a single CR. You will compare this with the manual StatefulSet approach to understand the operational advantage operators provide.

## Prerequisites

- Completed: L2-M2.2 (Installing & Managing Operators)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in as `kubeadmin` (cluster-admin privileges required to install the operator)
- `oc` CLI installed and on PATH
- Familiarity with OLM concepts: Subscriptions, InstallPlans, CSVs (covered in L2-M2.2)

## K8s Context

You know how to deploy PostgreSQL on Kubernetes. The standard approach looks like this:

1. Create a **Secret** with database credentials.
2. Create a **headless Service** for stable DNS names.
3. Create a **StatefulSet** with a volumeClaimTemplate for persistent storage.
4. Manually configure replication (streaming replication, Patroni, or Stolon).
5. Set up **CronJobs** for backups (pg_dump or pgBackRest).
6. Build your own monitoring with custom Prometheus exporters.
7. Handle failover yourself -- or bolt on a third-party HA solution.

This works, but it is a lot of undifferentiated heavy lifting. Every team reinvents the same wheel: backup schedules, failover logic, connection pooling, TLS certificates. When something breaks at 3 AM, you are the database operator.

The Kubernetes community recognized this pattern and created the Operator Framework -- software that encodes operational knowledge into a controller. For databases, this means the operator handles replication, backups, failover, scaling, and upgrades while you simply declare what you want in a Custom Resource.

## Concepts

### Database Operators on OpenShift

OpenShift's OperatorHub includes several certified database operators:

- **CrunchyData Postgres Operator (PGO)** -- Production-grade PostgreSQL with HA, automated backups (pgBackRest), connection pooling (PgBouncer), and monitoring. This is what we use in this lesson.
- **EDB Postgres for Kubernetes** -- Enterprise PostgreSQL from EnterpriseDB.
- **MongoDB Enterprise Operator** -- Managed MongoDB clusters.
- **Redis Enterprise Operator** -- Redis clusters with auto-scaling.

These are not toy wrappers around Helm charts. They implement the full operator maturity model: install, upgrade, full lifecycle management, deep insights, and auto-pilot capabilities.

### The CrunchyData PostgresCluster CRD

When you install the CrunchyData operator, it registers the `PostgresCluster` Custom Resource Definition. This single CRD lets you declare:

- **Instances** -- Number of PostgreSQL replicas, resource limits, storage size, affinity rules.
- **Backups** -- pgBackRest configuration with scheduled full and incremental backups, retention policies, and S3/GCS/Azure storage backends.
- **Users** -- Database users with specific database access, automatically generated Secrets with connection strings.
- **Patroni** -- High-availability configuration (leader election, replication parameters).
- **Connection pooling** -- PgBouncer sidecar for connection management.
- **Monitoring** -- Prometheus exporter sidecar with pre-built ServiceMonitors.

The operator's reconciliation loop continuously watches your `PostgresCluster` CR and drives the actual state toward your desired state. If a replica pod dies, the operator recreates it. If you change the replica count, the operator adds or removes instances. If a backup fails, the operator retries.

### How Operator-Managed Secrets Work

One of the most useful features: the operator automatically generates Kubernetes Secrets containing connection information for each user you define. For a cluster named `hippo` with a user named `appuser`, the operator creates a Secret called `hippo-pguser-appuser` containing:

- `host` -- The service hostname
- `port` -- The PostgreSQL port
- `dbname` -- The database name
- `user` -- The username
- `password` -- An auto-generated secure password
- `uri` -- A full `postgresql://` connection string

Your application pods reference this Secret -- no manual credential management required.

### Declarative Backup and Restore

Instead of writing CronJobs and shell scripts for pg_dump, you declare backup configuration directly in the `PostgresCluster` CR:

```yaml
backups:
  pgbackrest:
    repos:
      - name: repo1
        schedules:
          full: "0 1 * * 0"        # Weekly full backup on Sunday at 1 AM
          incremental: "0 1 * * 1-6" # Daily incremental Mon-Sat at 1 AM
```

Restore is equally declarative: you create a new `PostgresCluster` CR with a `dataSource` field pointing to the backup repository. The operator handles the rest.

## Step-by-Step

### Step 1: Create a Project

Create a dedicated project for this lesson:

```bash
oc new-project postgres-operator-demo
```

Expected output:

```
Now using project "postgres-operator-demo" on server "https://api.crc.testing:6443".
```

### Step 2: Understand the Manual K8s Approach (Optional Review)

Before deploying via the operator, review the manual approach to appreciate what the operator eliminates. The file `manifests/k8s-statefulset-postgres.yaml` contains a basic single-instance PostgreSQL deployment using a StatefulSet -- the way you would do it in vanilla Kubernetes.

Examine the manifest:

```bash
cat manifests/k8s-statefulset-postgres.yaml
```

Notice what you have to manage yourself:

- A Secret for credentials (hardcoded, no rotation).
- A headless Service for DNS.
- A StatefulSet with explicit volume mounts, probes, and env vars.
- No replication, no backups, no failover, no monitoring.

If you want to see it running (optional -- this is for comparison only):

```bash
oc apply -f manifests/k8s-statefulset-postgres.yaml
```

Wait for the pod to start:

```bash
oc get pods -l app=postgres -w
```

Expected output:

```
NAME         READY   STATUS    RESTARTS   AGE
postgres-0   1/1     Running   0          45s
```

Clean up the manual deployment before proceeding -- we will deploy the real thing with the operator:

```bash
oc delete -f manifests/k8s-statefulset-postgres.yaml
oc delete pvc -l app=postgres
```

### Step 3: Install the CrunchyData Postgres Operator

In L2-M2.2 you learned how to install operators via `oc` and the Web Console. Now apply that knowledge. First, check if the operator is already available:

```bash
oc get packagemanifests -n openshift-marketplace | grep -i crunchy
```

Expected output:

```
crunchy-postgres-operator    Certified Operators   45d
```

Install the operator by applying the Subscription:

```bash
oc apply -f manifests/crunchy-subscription.yaml
```

Wait for the operator to install. Watch the CSV until it reaches `Succeeded`:

```bash
oc get csv -n openshift-operators -w
```

Expected output (after 1-2 minutes):

```
NAME                                DISPLAY                           VERSION   REPLACES   PHASE
postgresoperator.v5.5.0             Crunchy Postgres for Kubernetes   5.5.0                Succeeded
```

Press Ctrl+C once you see `Succeeded`. Verify the operator pod is running:

```bash
oc get pods -n openshift-operators -l postgres-operator.crunchydata.com/control-plane=postgres-operator
```

Expected output:

```
NAME                            READY   STATUS    RESTARTS   AGE
pgo-6d4f7b8c9d-x2kl4           1/1     Running   0          90s
```

Verify the CRD was installed:

```bash
oc get crd postgresclusters.postgres-operator.crunchydata.com
```

Expected output:

```
NAME                                                  CREATED AT
postgresclusters.postgres-operator.crunchydata.com     2024-01-15T10:30:00Z
```

### Step 4: Deploy a PostgreSQL Cluster via the Operator

Now for the payoff. Instead of assembling StatefulSets, Services, Secrets, and backup jobs by hand, you apply a single Custom Resource:

```bash
oc apply -f manifests/crunchy-postgrescluster.yaml
```

This one CR declares:

- **2 replicas** with HA (Patroni manages leader election)
- **Resource limits** (250m-1 CPU, 256Mi-1Gi memory)
- **5Gi persistent storage** per instance
- **Automated backups** (weekly full, daily incremental via pgBackRest)
- **10Gi backup storage** volume
- **A database user** (`appuser`) with access to `appdb`
- **PostgreSQL tuning** (max_connections, shared_buffers, work_mem)
- **Pod anti-affinity** to spread replicas across nodes

Watch the operator create all the supporting resources:

```bash
oc get pods -w
```

Over the next 2-3 minutes, you will see the operator create several pods:

```
NAME                           READY   STATUS      RESTARTS   AGE
hippo-instance1-xxxx-0         4/4     Running     0          2m
hippo-instance1-xxxx-1         4/4     Running     0          90s
hippo-repo-host-0              2/2     Running     0          2m
hippo-backup-xxxx              0/1     Completed   0          60s
```

- `hippo-instance1-*` -- PostgreSQL instances (primary + replica)
- `hippo-repo-host-0` -- pgBackRest repository pod for backups
- `hippo-backup-*` -- Initial backup job (runs once on creation)

Press Ctrl+C. Check all the resources the operator created:

```bash
echo "=== Pods ==="
oc get pods -l postgres-operator.crunchydata.com/cluster=hippo

echo ""
echo "=== Services ==="
oc get svc -l postgres-operator.crunchydata.com/cluster=hippo

echo ""
echo "=== Secrets ==="
oc get secrets | grep hippo

echo ""
echo "=== PVCs ==="
oc get pvc -l postgres-operator.crunchydata.com/cluster=hippo
```

Expected output for Services:

```
NAME            TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE
hippo-ha        ClusterIP   172.30.45.123   <none>        5432/TCP   3m
hippo-ha-config ClusterIP   None            <none>        <none>     3m
hippo-pods      ClusterIP   None            <none>        5432/TCP   3m
hippo-primary   ClusterIP   None            <none>        5432/TCP   3m
hippo-replicas  ClusterIP   172.30.67.89    <none>        5432/TCP   3m
```

Expected output for Secrets:

```
hippo-cluster-cert           kubernetes.io/tls   3     3m
hippo-instance1-xxxx-certs   kubernetes.io/tls   4     3m
hippo-pgbackrest             Opaque              1     3m
hippo-pguser-appuser         Opaque              8     3m
hippo-pguser-postgres        Opaque              8     3m
```

The operator created Services (including read-only replicas), TLS certificates, backup configuration, and user credentials -- all from that one CR.

### Step 5: Examine the Auto-Generated Credentials

The operator created a Secret with everything an application needs to connect:

```bash
oc get secret hippo-pguser-appuser -o jsonpath='{.data}' | python3 -c "
import sys, json, base64
data = json.load(sys.stdin)
for k, v in sorted(data.items()):
    val = base64.b64decode(v).decode()
    if k == 'password':
        val = '********'
    print(f'{k}: {val}')
"
```

Expected output:

```
dbname: appdb
host: hippo-primary.postgres-operator-demo.svc
jdbc-uri: jdbc:postgresql://hippo-primary.postgres-operator-demo.svc:5432/appdb?...
password: ********
pgbouncer-host: hippo-pgbouncer.postgres-operator-demo.svc
pgbouncer-port: 5432
pgbouncer-uri: postgresql://appuser:...@hippo-pgbouncer.postgres-operator-demo.svc:5432/appdb
port: 5432
uri: postgresql://appuser:...@hippo-primary.postgres-operator-demo.svc:5432/appdb
user: appuser
verifier: ...
```

The Secret includes the connection URI, JDBC URI, and individual fields. Your application pods simply mount this Secret -- no manual credential management.

### Step 6: Connect to the Database

Test the connection by exec-ing into the primary pod:

```bash
# Find the primary pod
PRIMARY_POD=$(oc get pods \
  -l postgres-operator.crunchydata.com/cluster=hippo,postgres-operator.crunchydata.com/role=master \
  -o name | head -1)

echo "Primary pod: ${PRIMARY_POD}"

# Connect and run a test query
oc exec -it "${PRIMARY_POD}" -- psql -U appuser -d appdb -c "SELECT version();"
```

Expected output:

```
                                                  version
-----------------------------------------------------------------------------------------------------------
 PostgreSQL 15.4 on x86_64-redhat-linux-gnu, compiled by gcc (GCC) 8.5.0 20210514 (Red Hat 8.5.0-18), ...
(1 row)
```

Insert some test data we will use later for the backup/restore test:

```bash
oc exec -it "${PRIMARY_POD}" -- psql -U appuser -d appdb -c "
  CREATE TABLE IF NOT EXISTS demo_data (
    id SERIAL PRIMARY KEY,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );
  INSERT INTO demo_data (message) VALUES
    ('Hello from the operator-managed cluster'),
    ('This data was inserted before backup'),
    ('Operator lifecycle management in action');
  SELECT * FROM demo_data;
"
```

Expected output:

```
 id |                  message                  |         created_at
----+-------------------------------------------+----------------------------
  1 | Hello from the operator-managed cluster   | 2024-01-15 10:45:00.123456
  2 | This data was inserted before backup      | 2024-01-15 10:45:00.123456
  3 | Operator lifecycle management in action   | 2024-01-15 10:45:00.123456
(3 rows)
```

### Step 7: Deploy a Test Application Using Operator-Generated Secrets

Deploy a simple application that connects to the database using the operator-generated Secret:

```bash
oc apply -f manifests/test-app-deployment.yaml
```

Wait for the pod to start and check the logs to verify the connection info was loaded:

```bash
oc wait --for=condition=Available deployment/pg-test-app --timeout=60s
oc logs deployment/pg-test-app
```

Expected output:

```
PostgreSQL client pod ready.
Connection info loaded from operator-generated secret.
Host: hippo-primary.postgres-operator-demo.svc
Port: 5432
Database: appdb
User: appuser
```

The application did not need to know any credentials at deploy time. The operator generated them, and the Deployment references the Secret by its well-known name (`hippo-pguser-appuser`).

### Step 8: Trigger a Manual Backup

The CR already defines scheduled backups (weekly full, daily incremental). To trigger an immediate backup:

```bash
./scripts/manual-backup.sh full
```

Or run the command directly:

```bash
oc annotate postgrescluster hippo \
  postgres-operator.crunchydata.com/pgbackrest-backup="$(date +%F_%H%M%S)" \
  --overwrite
```

Monitor the backup job:

```bash
oc get jobs -l postgres-operator.crunchydata.com/cluster=hippo -w
```

Expected output (after 30-60 seconds):

```
NAME                    COMPLETIONS   DURATION   AGE
hippo-backup-xxxx       1/1           25s        30s
```

Verify the backup from within the primary pod:

```bash
oc exec -it "${PRIMARY_POD}" -- pgbackrest info
```

Expected output (abbreviated):

```
stanza: db
    status: ok
    cipher: none

    db (current)
        wal archive min/max (15): 000000010000000000000001/000000010000000000000004

        full backup: 20240115-104500F
            timestamp start/stop: 2024-01-15 10:45:00+00 / 2024-01-15 10:45:25+00
            wal start/stop: 000000010000000000000003 / 000000010000000000000003
            database size: 30.2MB, database backup size: 30.2MB
            repo1: backup set size: 3.8MB, backup size: 3.8MB
```

### Step 9: Scale the Cluster

Scaling is declarative -- change the replica count in the CR:

```bash
oc apply -f manifests/crunchy-postgrescluster-scaled.yaml
```

This changes `replicas: 2` to `replicas: 3`. Watch the operator create the new instance:

```bash
oc get pods -l postgres-operator.crunchydata.com/cluster=hippo -w
```

Expected output (a new pod appears):

```
NAME                           READY   STATUS    RESTARTS   AGE
hippo-instance1-xxxx-0         4/4     Running   0          10m
hippo-instance1-xxxx-1         4/4     Running   0          10m
hippo-instance1-yyyy-0         4/4     Running   0          30s
```

The new replica automatically:
- Gets its own PVC provisioned
- Streams WAL from the primary to catch up
- Registers with Patroni for HA
- Becomes available for read-only queries via the `hippo-replicas` Service

Verify replication is working:

```bash
oc exec -it "${PRIMARY_POD}" -- psql -U postgres -c "
  SELECT client_addr, state, sync_state, sent_lsn, replay_lsn
  FROM pg_stat_replication;
"
```

Expected output:

```
 client_addr  |   state   | sync_state |  sent_lsn   | replay_lsn
--------------+-----------+------------+-------------+-------------
 10.128.2.15  | streaming | async      | 0/5000060   | 0/5000060
 10.128.3.22  | streaming | async      | 0/5000060   | 0/5000060
(2 rows)
```

To scale back down, edit the CR and set `replicas: 2`, then `oc apply` again. The operator will gracefully decommission the extra replica.

### Step 10: Restore from Backup

Create a new cluster restored from the backup of the original. This is how you would recover from data loss or create a clone for testing:

```bash
oc apply -f manifests/crunchy-restore.yaml
```

The key section in the manifest is:

```yaml
dataSource:
  postgresCluster:
    clusterName: hippo
    repoName: repo1
```

This tells the operator to create a new `PostgresCluster` named `hippo-restored` by restoring from `hippo`'s backup repository. Watch the restore:

```bash
oc get pods -l postgres-operator.crunchydata.com/cluster=hippo-restored -w
```

Expected output (after 2-3 minutes):

```
NAME                                     READY   STATUS    RESTARTS   AGE
hippo-restored-instance1-xxxx-0          4/4     Running   0          2m
hippo-restored-repo-host-0               2/2     Running   0          2m
```

Verify the restored data:

```bash
RESTORED_POD=$(oc get pods \
  -l postgres-operator.crunchydata.com/cluster=hippo-restored,postgres-operator.crunchydata.com/role=master \
  -o name | head -1)

oc exec -it "${RESTORED_POD}" -- psql -U appuser -d appdb -c "SELECT * FROM demo_data;"
```

Expected output:

```
 id |                  message                  |         created_at
----+-------------------------------------------+----------------------------
  1 | Hello from the operator-managed cluster   | 2024-01-15 10:45:00.123456
  2 | This data was inserted before backup      | 2024-01-15 10:45:00.123456
  3 | Operator lifecycle management in action   | 2024-01-15 10:45:00.123456
(3 rows)
```

The data from Step 6 is intact. You just performed a full backup and restore without touching pg_dump, writing shell scripts, or managing PVCs manually.

### Step 11: Explore the Cluster in the Web Console

1. Open the OpenShift Web Console (https://console-openshift-console.apps-crc.testing).
2. Switch to the **Administrator** perspective.
3. Navigate to **Operators > Installed Operators**.
4. Click on **Crunchy Postgres for Kubernetes**.
5. Select the **PostgresCluster** tab.
6. Click on **hippo** to view the cluster details.

The console shows the cluster status, instance count, backup status, and user list -- all derived from the CR's status field. You can also edit the CR directly from the console using the YAML tab.

### Step 12: Observe Self-Healing

One of the most powerful operator capabilities is self-healing. Delete the primary pod and watch the operator recover:

```bash
# Note the current primary
oc get pods -l postgres-operator.crunchydata.com/cluster=hippo,postgres-operator.crunchydata.com/role=master

# Delete it
PRIMARY_POD_NAME=$(oc get pods \
  -l postgres-operator.crunchydata.com/cluster=hippo,postgres-operator.crunchydata.com/role=master \
  -o jsonpath='{.items[0].metadata.name}')

oc delete pod "${PRIMARY_POD_NAME}"
```

Watch what happens:

```bash
oc get pods -l postgres-operator.crunchydata.com/cluster=hippo -w
```

Patroni detects the primary is gone, promotes a replica to primary, and the operator recreates the deleted pod as a new replica. The entire failover takes about 10-15 seconds. Your application, connected via the `hippo-ha` service, experiences a brief interruption but reconnects automatically.

Verify the new primary:

```bash
oc get pods -l postgres-operator.crunchydata.com/cluster=hippo,postgres-operator.crunchydata.com/role=master
```

The pod name will be different -- one of the former replicas has been promoted.

## Verification

Run the verification script or execute these commands to confirm the lesson is complete:

```bash
./scripts/verify-cluster.sh
```

Or manually:

```bash
# 1. Operator is running
oc get pods -n openshift-operators \
  -l postgres-operator.crunchydata.com/control-plane=postgres-operator \
  --field-selector=status.phase=Running
# Expected: 1 pod in Running state

# 2. PostgresCluster CR exists
oc get postgrescluster hippo -o jsonpath='{.metadata.name}'
# Expected: hippo

# 3. All instance pods are running (should be 3 after scaling)
oc get pods -l postgres-operator.crunchydata.com/cluster=hippo \
  --field-selector=status.phase=Running --no-headers | wc -l
# Expected: 4+ (3 instances + 1 repo host)

# 4. User secret exists with connection info
oc get secret hippo-pguser-appuser -o jsonpath='{.data.uri}' | base64 -d
# Expected: postgresql://appuser:...@hippo-primary...:5432/appdb

# 5. Backup completed successfully
oc get jobs -l postgres-operator.crunchydata.com/cluster=hippo \
  --field-selector=status.successful=1 --no-headers | wc -l
# Expected: 1 or more

# 6. Restored cluster is running
oc get postgrescluster hippo-restored -o jsonpath='{.metadata.name}'
# Expected: hippo-restored

# 7. Test data is accessible in the restored cluster
RESTORED_POD=$(oc get pods \
  -l postgres-operator.crunchydata.com/cluster=hippo-restored,postgres-operator.crunchydata.com/role=master \
  -o name | head -1)
oc exec "${RESTORED_POD}" -- psql -U appuser -d appdb -c "SELECT count(*) FROM demo_data;"
# Expected: 3
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes (Manual) | OpenShift (Operator-Managed) |
|--------|--------------------|-----------------------------|
| Deployment | StatefulSet + headless Service + Secret + PVC templates -- 100+ lines of YAML | Single PostgresCluster CR -- ~50 lines, operator creates everything |
| High availability | DIY: install Patroni/Stolon, configure replication, test failover | Built-in: Patroni managed by operator, automatic failover in ~10s |
| Backups | Write CronJobs + shell scripts for pg_dump or pgBackRest | Declarative: `schedules.full: "0 1 * * 0"` in the CR |
| Restore | Manual: create PVC, run pg_restore, fix permissions, update Service | Declarative: create new CR with `dataSource.postgresCluster` |
| Scaling | Edit StatefulSet replicas, manually configure replication for new pods | Edit CR replicas, operator handles replication setup automatically |
| Credentials | Create and manage Secrets manually, no rotation | Auto-generated Secrets with connection URIs, rotation via CR update |
| TLS | Generate certs, mount as volumes, configure PostgreSQL ssl settings | Auto-generated and auto-rotated by the operator |
| Monitoring | Deploy postgres_exporter, write ServiceMonitors, create dashboards | Operator deploys exporter sidecar, pre-built ServiceMonitors |
| Self-healing | StatefulSet restarts pods, but no leader election or promotion | Operator + Patroni: detects failure, promotes replica, recreates pod |
| Upgrades | Rolling update StatefulSet (risky for databases), manual version pins | Operator handles minor version upgrades with proper drain and sync |
| Operator install | N/A (no operator) | One-click from OperatorHub or `oc apply` a Subscription |
| Day-2 ops effort | High: you are the database operator | Low: the software is the database operator |

## Troubleshooting

### Operator pod not starting

```bash
oc get csv -n openshift-operators
oc describe csv <csv-name> -n openshift-operators
```

If the CSV is stuck in `Pending` or `Installing`, check for InstallPlan approval:

```bash
oc get installplan -n openshift-operators
```

If using manual approval, approve the plan:

```bash
oc patch installplan <plan-name> -n openshift-operators \
  --type merge -p '{"spec":{"approved":true}}'
```

### PostgresCluster pods stuck in Pending

Usually a storage issue. Check PVC status:

```bash
oc get pvc -l postgres-operator.crunchydata.com/cluster=hippo
```

If PVCs are stuck in `Pending`, check StorageClass availability:

```bash
oc get storageclass
```

On CRC, the default StorageClass is limited. Reduce the storage request in the CR if needed.

### Pods in CrashLoopBackOff

Check the operator logs for the reconciliation error:

```bash
oc logs -n openshift-operators deployment/pgo --tail=50
```

Check the PostgreSQL pod logs:

```bash
oc logs <pod-name> -c database
```

Common causes: insufficient memory (increase the limits in the CR), SCC issues (the CrunchyData images are designed to run as non-root and work with the `restricted` SCC).

### Cannot connect to the database

Verify the Secret exists and contains the right hostname:

```bash
oc get secret hippo-pguser-appuser -o jsonpath='{.data.host}' | base64 -d
```

Ensure the Service is resolving:

```bash
oc run dns-test --rm -it --image=registry.access.redhat.com/ubi9/ubi-minimal -- \
  nslookup hippo-primary.postgres-operator-demo.svc.cluster.local
```

### Backup jobs failing

Check the backup job logs:

```bash
BACKUP_JOB=$(oc get jobs -l postgres-operator.crunchydata.com/cluster=hippo \
  -o name --sort-by=.metadata.creationTimestamp | tail -1)
oc logs "${BACKUP_JOB}"
```

Common cause: the repo host PVC is full. Check usage:

```bash
oc exec hippo-repo-host-0 -- df -h /pgbackrest
```

## Key Takeaways

- **Operators replace operational toil with declarative configuration** -- instead of assembling StatefulSets, Services, Secrets, CronJobs, and replication scripts, you describe your desired database cluster in a single Custom Resource and the operator handles the rest.
- **The CrunchyData PostgresCluster CRD is a complete database platform** -- HA (Patroni), backups (pgBackRest), auto-generated credentials, TLS, connection pooling, and monitoring are all declared in one CR.
- **Backup and restore are first-class operations** -- scheduled backups are a field in the CR, manual backups are an annotation, and restore is a new CR with a `dataSource` reference. No shell scripts or CronJobs required.
- **Scaling is a one-line change** -- edit `replicas` in the CR and `oc apply`. The operator provisions storage, configures streaming replication, and registers the new instance with Patroni automatically.
- **Self-healing demonstrates the operator pattern's value** -- when a pod dies, Patroni promotes a replica and the operator recreates the failed instance. This is operational knowledge encoded in software, running 24/7.

## Cleanup

Remove all resources created in this lesson:

```bash
# Run the cleanup script
./scripts/cleanup.sh
```

Or manually:

```bash
# Delete the restored cluster
oc delete postgrescluster hippo-restored

# Delete the test application
oc delete deployment pg-test-app

# Delete the primary cluster (this also removes all operator-created resources)
oc delete postgrescluster hippo

# Wait for PVCs to be released, then delete them
oc delete pvc -l postgres-operator.crunchydata.com/cluster=hippo
oc delete pvc -l postgres-operator.crunchydata.com/cluster=hippo-restored

# Delete the project
oc delete project postgres-operator-demo
```

The CrunchyData operator itself remains installed cluster-wide. To remove it:

```bash
oc delete subscription crunchy-postgres-operator -n openshift-operators
oc delete csv -n openshift-operators \
  -l operators.coreos.com/crunchy-postgres-operator.openshift-operators
```

## Next Steps

In the next lesson, **L2-M2.4 -- Building a Simple Operator**, you will move from consuming operators to creating one. Using the Operator SDK, you will scaffold a Go-based operator, implement a reconciliation loop, define your own CRD, and deploy it to the cluster. This will deepen your understanding of how the PostgreSQL operator you just used works under the hood -- and equip you to build operators for your own domain-specific workloads.
