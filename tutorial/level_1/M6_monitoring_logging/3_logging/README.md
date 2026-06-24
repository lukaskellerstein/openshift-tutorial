# L1-M6.3 — Logging with OpenShift Logging

**Level:** Foundations
**Duration:** 30 min

## Overview

In Kubernetes, setting up centralized logging means manually deploying an EFK/ELK stack (Elasticsearch + Fluentd/Filebeat + Kibana) or a Loki-based stack, then wiring everything together. OpenShift provides a fully integrated logging solution through the OpenShift Logging operator, managed entirely through Custom Resources. In this lesson you will install the operator, deploy a logging stack using the `ClusterLogging` CRD, and configure log forwarding with the `ClusterLogForwarder` CRD.

## Prerequisites

- Completed: L1-M6.1 (Built-in Monitoring Stack)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in as `kubeadmin` (cluster-admin privileges required to install operators)

## K8s Context

In vanilla Kubernetes, centralized logging is entirely DIY. A typical setup involves:

1. **Deploying a log collector** (Fluentd, Fluent Bit, or Vector) as a DaemonSet on every node to scrape container logs from `/var/log/containers/`.
2. **Deploying a log store** (Elasticsearch or Loki) with persistent storage and index management.
3. **Deploying a visualization layer** (Kibana or Grafana) so users can search and analyze logs.

You write Helm charts or raw manifests for each component, manage their lifecycles independently, handle upgrades, and wire authentication yourself. There is no standard Kubernetes API for logging — it is purely an add-on concern.

## Concepts

### OpenShift Logging Architecture

OpenShift Logging wraps the same open-source components you know, but manages them through operators and CRDs:

| Component | Role | Options |
|-----------|------|---------|
| **Collector** | DaemonSet on every node; reads container and node logs | Vector (default in 5.x+) or Fluentd (legacy) |
| **Log Store** | Stores and indexes logs for querying | LokiStack (preferred) or Elasticsearch |
| **Visualization** | UI for searching and browsing logs | OpenShift Console plugin (with Loki) or Kibana (with Elasticsearch) |

### Two Key CRDs

**`ClusterLogging`** — Defines the logging stack deployment: which collector to use, which store to deploy, and sizing/retention settings. Think of it as the "desired state" for your entire logging infrastructure.

**`ClusterLogForwarder`** — Controls where logs are sent. By default, all container logs go to the internal log store. But you can also forward logs to external systems (Splunk, Kafka, Syslog, Cloudwatch, external Elasticsearch/Loki) or filter logs by namespace, label, or log type (application, infrastructure, audit).

### Why Does OpenShift Do This?

1. **Consistency**: Every OpenShift cluster gets logging the same way, reducing operational drift.
2. **Lifecycle management**: The operator handles upgrades, scaling, and certificate rotation for all logging components.
3. **Multi-tenancy**: The logging stack integrates with OpenShift RBAC, so developers see only their project's logs in the console without extra configuration.
4. **Separation of concerns**: `ClusterLogging` defines *what* runs; `ClusterLogForwarder` defines *where* logs go. You can change forwarding rules without redeploying the stack.

### Log Types

OpenShift categorizes logs into three types:

- **Application** — Container logs from user workloads (your pods).
- **Infrastructure** — Logs from OpenShift platform components (API server, controllers, SDN, etc.) and node-level journals.
- **Audit** — API server audit logs, OVN audit logs, and node auditd logs.

## Step-by-Step

### Step 1: Install the OpenShift Logging Operator

The OpenShift Logging operator is installed from OperatorHub. First, create the namespace where it will run, then create a Subscription to install it.

If using the **Loki-based stack** (recommended for OpenShift 4.14+), you also need the **Loki Operator**. We will install both.

**Install via CLI:**

Create the namespace for the logging operator:

```bash
oc apply -f manifests/logging-namespace.yaml
```

Install the Loki Operator (provides the log store):

```bash
oc apply -f manifests/loki-operator-subscription.yaml
```

Install the OpenShift Logging Operator (provides the collector and ties everything together):

```bash
oc apply -f manifests/logging-operator-subscription.yaml
```

Wait for both operators to be installed:

```bash
oc get csv -n openshift-logging --watch
```

Expected output (after a few minutes):

```
NAME                        DISPLAY                  VERSION   REPLACES   PHASE
cluster-logging.v6.1.0      Cluster Logging          6.1.0                Succeeded
loki-operator.v6.1.0        Loki Operator            6.1.0                Succeeded
```

Press `Ctrl+C` once both show `Succeeded`.

**Install via Web Console (alternative):**

1. Navigate to **Operators > OperatorHub**.
2. Search for **Loki Operator** and install it to `openshift-logging` namespace.
3. Search for **Red Hat OpenShift Logging** and install it to `openshift-logging` namespace.
4. Wait for both to show `Succeeded` under **Operators > Installed Operators**.

### Step 2: Create a LokiStack Instance

Before deploying the logging stack, you need a Loki instance to store logs. In CRC/development, we use a minimal `1x.demo` size. In production, you would use `1x.small` or larger with S3-compatible object storage.

For CRC, we will use a simple configuration with filesystem storage (suitable for demos only):

First, create a secret for Loki's object storage configuration. In CRC, we use a minimal configuration:

```bash
oc apply -f manifests/lokistack-secret.yaml
```

Then deploy the LokiStack:

```bash
oc apply -f manifests/lokistack.yaml
```

Wait for the LokiStack pods to come up:

```bash
oc get pods -n openshift-logging -l app.kubernetes.io/name=lokistack --watch
```

Expected output (after several minutes):

```
NAME                                       READY   STATUS    RESTARTS   AGE
logging-loki-compactor-0                   1/1     Running   0          2m
logging-loki-distributor-7b8f5d6c4-xxxxx   1/1     Running   0          2m
logging-loki-gateway-6c9f7d8b5-xxxxx       1/1     Running   0          2m
logging-loki-index-gateway-0               1/1     Running   0          2m
logging-loki-ingester-0                    1/1     Running   0          2m
logging-loki-querier-5f4d6c7b8-xxxxx       1/1     Running   0          2m
logging-loki-query-frontend-abc123-xxxxx   1/1     Running   0          2m
```

Press `Ctrl+C` once pods are running.

### Step 3: Deploy the ClusterLogging Instance

Now deploy the `ClusterLogging` resource. This tells the operator to deploy log collectors (Vector) on every node and wire them to the LokiStack:

```bash
oc apply -f manifests/clusterlogging.yaml
```

Verify the collector pods are running (one per node):

```bash
oc get pods -n openshift-logging -l component=collector
```

Expected output (CRC has one node):

```
NAME                READY   STATUS    RESTARTS   AGE
collector-xxxxx     1/1     Running   0          60s
```

### Step 4: Configure Log Forwarding

The `ClusterLogForwarder` resource controls which logs go where. Deploy the forwarder that sends all three log types (application, infrastructure, audit) to the local LokiStack:

```bash
oc apply -f manifests/clusterlogforwarder.yaml
```

Verify the forwarder is accepted:

```bash
oc get clusterlogforwarder -n openshift-logging
```

Expected output:

```
NAME       AGE
instance   10s
```

Check the status conditions:

```bash
oc get clusterlogforwarder instance -n openshift-logging -o yaml | grep -A 5 conditions
```

You should see conditions with `status: "True"` and `type: Ready`.

### Step 5: Generate and View Logs

Deploy a sample application that generates log output:

```bash
oc new-project logging-demo
oc apply -f manifests/log-generator.yaml
```

Wait for the pod to start:

```bash
oc get pods -n logging-demo --watch
```

Once running, verify it is producing logs:

```bash
oc logs -n logging-demo -l app=log-generator --tail=5
```

Expected output:

```
2024-01-15T10:30:01Z INFO  Log message 1 from the demo application
2024-01-15T10:30:02Z WARN  Log message 2 - this is a warning
2024-01-15T10:30:03Z ERROR Log message 3 - this is an error
2024-01-15T10:30:04Z INFO  Log message 4 from the demo application
2024-01-15T10:30:05Z DEBUG Log message 5 - debug details here
```

### Step 6: Query Logs in the OpenShift Console

With Loki as the log store, logs are queryable directly in the OpenShift Web Console:

1. Navigate to **Observe > Logs** in the Administrator perspective.
2. Select **Application** logs from the log type dropdown.
3. Filter by namespace: `logging-demo`.
4. You should see log entries from the `log-generator` pod.
5. Try a LogQL query: `{kubernetes_namespace_name="logging-demo"} |= "ERROR"` to filter for error messages.

In the Developer perspective:
1. Switch to the `logging-demo` project.
2. Navigate to **Observe > Logs**.
3. Logs from your workloads are automatically scoped to your project.

### Step 7: Explore Log Forwarding to External Systems (Optional)

To understand the flexibility of `ClusterLogForwarder`, review the external forwarding example:

```bash
cat manifests/clusterlogforwarder-external.yaml
```

This example shows how to forward application logs to an external syslog server while keeping infrastructure and audit logs in the internal LokiStack. You do not need to apply this manifest — it is provided as a reference for real-world scenarios.

## Verification

Run these commands to confirm the logging stack is healthy:

```bash
# 1. All logging pods should be Running
oc get pods -n openshift-logging

# 2. ClusterLogging instance should exist
oc get clusterlogging -n openshift-logging

# 3. ClusterLogForwarder should be ready
oc get clusterlogforwarder -n openshift-logging

# 4. Collector pods running on every node
oc get pods -n openshift-logging -l component=collector -o wide

# 5. LokiStack should be ready
oc get lokistack -n openshift-logging

# 6. Sample app logs should be visible
oc logs -n logging-demo -l app=log-generator --tail=3
```

If using the Web Console, navigate to **Observe > Logs** and confirm you can see entries from the `logging-demo` namespace.

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Logging stack | Install EFK/Loki manually (Helm charts, manifests) | Install Logging Operator from OperatorHub |
| Collector deployment | Write your own DaemonSet for Fluentd/Vector | Operator deploys and manages collectors automatically |
| Log store | Deploy and manage Elasticsearch/Loki yourself | `LokiStack` CRD — operator handles sizing, storage, upgrades |
| Configuration | Edit ConfigMaps, Fluentd config files | `ClusterLogging` and `ClusterLogForwarder` CRDs |
| Log forwarding | Custom Fluentd/Vector pipeline config | Declarative `ClusterLogForwarder` with typed outputs |
| Multi-tenancy | Manual RBAC configuration for log access | Integrated with OpenShift RBAC — developers see only their project logs |
| Upgrades | Manual; coordinate across all components | Operator handles rolling upgrades of entire stack |
| Visualization | Deploy Kibana/Grafana separately | Built into OpenShift Console (Loki) or managed Kibana (ES) |
| Log categories | No built-in categorization | Three types: application, infrastructure, audit |

## Key Takeaways

- OpenShift Logging replaces the manual EFK/Loki setup with an operator-managed stack controlled through `ClusterLogging` and `ClusterLogForwarder` CRDs.
- Logs are automatically categorized into application, infrastructure, and audit types, enabling fine-grained forwarding and access control.
- The `ClusterLogForwarder` CRD lets you route different log types to different destinations (internal store, Kafka, Syslog, Splunk, cloud services) without touching the collector configuration.
- Multi-tenancy is built in: developers see only their own project's logs through the OpenShift Console, with no extra RBAC setup needed.
- LokiStack is the recommended log store for new deployments; Elasticsearch is considered legacy in recent OpenShift versions.

## Cleanup

```bash
# Remove the demo application and project
oc delete project logging-demo

# Remove the ClusterLogForwarder
oc delete clusterlogforwarder instance -n openshift-logging

# Remove the ClusterLogging instance
oc delete clusterlogging instance -n openshift-logging

# Remove the LokiStack
oc delete lokistack logging-loki -n openshift-logging

# Remove the storage secret
oc delete secret logging-loki-s3 -n openshift-logging

# Remove the operator subscriptions (optional — keeps operators available for other lessons)
oc delete subscription cluster-logging -n openshift-logging
oc delete subscription loki-operator -n openshift-logging

# Remove the CSV (ClusterServiceVersion) to fully uninstall
oc delete csv -n openshift-logging -l operators.coreos.com/cluster-logging.openshift-logging
oc delete csv -n openshift-logging -l operators.coreos.com/loki-operator.openshift-logging

# Remove the namespace (optional — removes everything)
oc delete namespace openshift-logging
```

## Next Steps

In **L1-M6.4 — Events & Debugging**, you will learn how to use `oc get events`, `oc logs`, `oc debug`, `oc rsh`, and `oc exec` to troubleshoot workloads. You will also discover the `oc debug node/` trick for node-level debugging, which is an OpenShift-specific capability that goes beyond what `kubectl` offers.
