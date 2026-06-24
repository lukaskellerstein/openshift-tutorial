# L2-M4.2 — Multi-Cluster Networking

**Level:** Practitioner
**Duration:** 45 min

## Overview

In production environments, a single Kubernetes or OpenShift cluster rarely operates in isolation. Organizations run multiple clusters for disaster recovery, geographic distribution, data sovereignty, hybrid cloud topologies, or simply to separate workloads across environments. The challenge is connecting services across these cluster boundaries transparently, without application-level changes.

This lesson teaches you how to set up cross-cluster networking on OpenShift using Submariner, configure service discovery with the Kubernetes Multi-Cluster Services (MCS) API (ServiceExport/ServiceImport), and understand the architecture that makes it all work. You will learn when and why multi-cluster networking is needed, how it differs from what you might set up manually in vanilla Kubernetes, and what OpenShift provides out of the box through Red Hat Advanced Cluster Management (RHACM).

## Prerequisites

- Completed: L2-M4.1 (Egress & Ingress Control)
- Completed: L2-M2.1-2 (Operator Framework and Installing Operators)
- Two OpenShift clusters (or one cluster with RHACM for simulation; see note below)
- `oc` CLI configured with contexts for both clusters
- Cluster-admin access on both clusters
- Familiarity with DNS resolution in Kubernetes (CoreDNS, service DNS names)

> **CRC Limitation:** Submariner requires two separate clusters with network connectivity between them. CRC provides only a single cluster. For hands-on practice, you can either: (a) use two Red Hat Developer Sandbox instances, (b) deploy two OpenShift clusters in a cloud provider, or (c) follow this lesson as a guided walkthrough and study the manifests locally. The concepts and architecture apply regardless of the lab setup.

## K8s Context

In vanilla Kubernetes, there is no built-in mechanism for cross-cluster networking. If you need Service A in cluster-east to reach Service B in cluster-west, you have several manual options:

- **Expose via LoadBalancer or NodePort** and hardcode external IPs in your client configuration.
- **Set up a VPN** between cluster networks and manually configure routing.
- **Use an API gateway or service mesh** (like Istio multi-cluster) with manual federation.
- **Deploy a third-party tool** like Submariner, Cilium Cluster Mesh, or Skupper.

None of these are standardized. The Kubernetes Multi-Cluster Services API (KEP-1645) defines `ServiceExport` and `ServiceImport` as the standard interface, but it requires an implementation to back it. Kubernetes itself does not ship one.

In all cases, you must handle:
- **Network connectivity** — tunnels between cluster pod/service CIDRs
- **Service discovery** — how does a pod in Cluster B find a service in Cluster A?
- **Overlapping CIDRs** — most clusters use the same default pod and service CIDR ranges
- **Security** — encrypted tunnels, authentication between clusters

## Concepts

### Submariner: The Cross-Cluster Network Fabric

Submariner is an open-source project (part of the CNCF Sandbox) that provides flat layer-3 networking between pods and services across Kubernetes clusters. On OpenShift, it is integrated into RHACM and available as a supported add-on.

Submariner solves the core problem: making pod and service networks routable across cluster boundaries. It creates encrypted IPsec or WireGuard tunnels between designated gateway nodes in each cluster.

#### Architecture Components

```
                    +------------------+
                    |   Broker Cluster |
                    |   (Metadata Hub) |
                    |                  |
                    |  - CRDs only     |
                    |  - No data plane |
                    +--------+---------+
                             |
                 Metadata sync (via K8s API)
                    /                    \
          +--------+--------+    +--------+--------+
          |   Cluster-A      |    |   Cluster-B      |
          |                  |    |                  |
          | +-- Gateway --+  |    | +-- Gateway --+  |
          | | (IPsec/WG)  |<-------->| (IPsec/WG)  |  |
          | +-------------+  |    | +-------------+  |
          |                  |    |                  |
          | +- Route Agent-+ |    | +- Route Agent-+ |
          | | (all nodes)  | |    | | (all nodes)  | |
          | +--------------+ |    | +--------------+ |
          |                  |    |                  |
          | +- Lighthouse -+ |    | +- Lighthouse -+ |
          | | (DNS + agent)| |    | | (DNS + agent)| |
          | +--------------+ |    | +--------------+ |
          +------------------+    +------------------+
```

The key components are:

1. **Broker** — A Kubernetes API server (can be on a dedicated cluster or one of the participating clusters) that serves as a rendezvous point. Clusters exchange metadata (endpoint info, service exports) through CRDs stored on the broker. No data-plane traffic flows through the broker.

2. **Gateway Engine** — Runs on a designated gateway node in each cluster. Establishes encrypted tunnels (IPsec via Libreswan, or WireGuard) to gateways in other clusters. This is the data plane.

3. **Route Agent** — A DaemonSet running on every node. Configures routing tables so that pod traffic destined for remote clusters is forwarded to the local gateway node.

4. **Lighthouse** — The service discovery component, consisting of:
   - **Lighthouse Agent** — Watches for `ServiceExport` resources locally and syncs them to the broker. Watches the broker for exports from other clusters and creates corresponding `ServiceImport` resources locally.
   - **Lighthouse CoreDNS** — A CoreDNS plugin that resolves the `*.clusterset.local` domain, enabling cross-cluster DNS queries.

5. **Globalnet** (optional) — A NAT-based solution for when cluster pod/service CIDRs overlap. Assigns each cluster a unique "global" CIDR and translates addresses at tunnel endpoints.

### ServiceExport and ServiceImport (MCS API)

The Multi-Cluster Services API is a Kubernetes standard (currently alpha) that defines how services are shared across clusters:

- **ServiceExport** — You create this in the cluster that owns the service. It signals: "I want this service to be discoverable by other clusters."
- **ServiceImport** — Automatically created in remote clusters by the multi-cluster implementation (Submariner's Lighthouse). It represents a service that exists in another cluster.

Once a service is exported, pods in any cluster in the ClusterSet can reach it via a special DNS name:

```
<service-name>.<namespace>.svc.clusterset.local
```

This is distinct from the normal in-cluster DNS (`svc.cluster.local`). The `.clusterset.local` domain is resolved by the Lighthouse CoreDNS plugin.

### Globalnet: Handling Overlapping CIDRs

By default, OpenShift clusters use `10.128.0.0/14` for pod CIDRs and `172.30.0.0/16` for service CIDRs. If you connect two clusters with the same CIDRs, routing breaks because the network cannot distinguish between a local 10.128.x.x address and a remote 10.128.x.x address.

Globalnet solves this by:
1. Assigning each cluster a unique virtual CIDR from a configurable range (default: `242.0.0.0/8`).
2. Performing SNAT (source NAT) on outgoing cross-cluster traffic to the global IP.
3. Performing DNAT (destination NAT) on incoming cross-cluster traffic back to the real pod IP.

The application never sees the global IPs. DNS resolution via Lighthouse returns the global IP, and the Globalnet controller handles the NAT transparently.

### Use Cases

| Use Case | Description |
|----------|-------------|
| **Hybrid Cloud** | Connect an on-premises OpenShift cluster to a cloud-based cluster. Services can migrate between environments transparently. |
| **Disaster Recovery** | Active-passive or active-active clusters in different regions. If Cluster-A fails, Cluster-B can take over service endpoints. |
| **Geographic Distribution** | Place services close to users. A frontend in EU can reach a backend in US via cross-cluster DNS. |
| **Data Sovereignty** | Keep data processing in a specific region while allowing services in other regions to query results cross-cluster. |
| **Environment Separation** | Dev, staging, and prod on separate clusters, but shared services (databases, message queues) accessible cross-cluster. |

## Step-by-Step

### Step 1: Prepare the Cluster Contexts

Before setting up Submariner, configure `oc` with contexts for both clusters. Throughout this lesson, we reference them as `cluster-a` and `cluster-b`.

```bash
# Verify your current contexts
oc config get-contexts
```

Expected output:
```
CURRENT   NAME         CLUSTER         AUTHINFO        NAMESPACE
*         cluster-a    api-cluster-a   admin-cluster-a
          cluster-b    api-cluster-b   admin-cluster-b
```

If you are using RHACM, log in to the hub cluster:

```bash
# Log in to the hub cluster (which will also serve as the broker)
oc login --server=https://api.hub-cluster.example.com:6443

# Verify RHACM is installed
oc get csv -n open-cluster-management | grep advanced-cluster-management
```

Expected output:
```
advanced-cluster-management.v2.9.0   Advanced Cluster Management   Succeeded
```

### Step 2: Install the Submariner Operator

On OpenShift with RHACM, Submariner is installed as an add-on through the RHACM console or CLI. Without RHACM, you can install the Submariner operator directly.

**Option A: Via RHACM (recommended for OpenShift)**

```bash
# Create the ManagedClusterSet (groups clusters that will be connected)
cat <<EOF | oc apply -f -
apiVersion: cluster.open-cluster-management.io/v1beta2
kind: ManagedClusterSet
metadata:
  name: tutorial-clusterset
EOF
```

```bash
# Add clusters to the set
oc label managedcluster cluster-a cluster.open-cluster-management.io/clusterset=tutorial-clusterset --overwrite
oc label managedcluster cluster-b cluster.open-cluster-management.io/clusterset=tutorial-clusterset --overwrite

# Verify cluster set membership
oc get managedclustersets tutorial-clusterset -o yaml
```

**Option B: Direct operator install (without RHACM)**

```bash
# Create the submariner-operator namespace
oc create namespace submariner-operator

# Apply the Subscription from this lesson's manifests
oc apply -f manifests/submariner-subscription.yaml

# Wait for the operator to install
oc get csv -n submariner-operator -w
```

Expected output (wait until PHASE shows Succeeded):
```
NAME                    DISPLAY       VERSION   PHASE
submariner.v0.18.0      Submariner    0.18.0    Succeeded
```

### Step 3: Deploy the Submariner Broker

The broker is the metadata exchange point. Deploy it on the hub cluster (or on one of the participating clusters if you do not have a dedicated hub).

```bash
# Create the broker namespace
oc create namespace submariner-k8s-broker

# Deploy the broker
oc apply -f manifests/submariner-broker.yaml
```

```bash
# Verify the broker is ready
oc get broker -n submariner-k8s-broker
```

Expected output:
```
NAME                AGE
submariner-broker   30s
```

If using RHACM, the broker setup is handled automatically when you enable Submariner on the ManagedClusterSet:

```bash
# Enable Submariner add-on via RHACM
cat <<EOF | oc apply -f -
apiVersion: addon.open-cluster-management.io/v1alpha1
kind: ManagedClusterAddOn
metadata:
  name: submariner
  namespace: cluster-a
spec:
  installNamespace: submariner-operator
---
apiVersion: addon.open-cluster-management.io/v1alpha1
kind: ManagedClusterAddOn
metadata:
  name: submariner
  namespace: cluster-b
spec:
  installNamespace: submariner-operator
EOF
```

### Step 4: Join Clusters to the Broker

Each cluster needs to be configured to connect to the broker. This involves providing the broker API endpoint, credentials, and cluster-specific network configuration.

**Using `subctl` CLI (the Submariner CLI tool):**

```bash
# Install subctl
curl -Ls https://get.submariner.io | VERSION=v0.18.0 bash

# On the broker cluster, extract join credentials
subctl deploy-broker --kubeconfig kubeconfig-hub --globalnet

# Join Cluster-A
subctl join broker-info.subm \
  --kubeconfig kubeconfig-cluster-a \
  --clusterid cluster-a \
  --natt=true

# Join Cluster-B
subctl join broker-info.subm \
  --kubeconfig kubeconfig-cluster-b \
  --clusterid cluster-b \
  --natt=true
```

**Using RHACM SubmarinerConfig (OpenShift-native approach):**

```bash
# Apply the SubmarinerConfig for each managed cluster
# Adjust the manifest for your cloud provider (AWS example shown)
oc apply -f manifests/submariner-cluster.yaml
```

```bash
# Verify the Submariner pods are running on each cluster
oc get pods -n submariner-operator --context cluster-a
```

Expected output:
```
NAME                                          READY   STATUS    RESTARTS   AGE
submariner-gateway-xxxxx                       1/1     Running   0          2m
submariner-routeagent-xxxxx                    1/1     Running   0          2m
submariner-routeagent-yyyyy                    1/1     Running   0          2m
submariner-lighthouse-agent-xxxxx              1/1     Running   0          2m
submariner-lighthouse-coredns-xxxxx            1/1     Running   0          2m
submariner-globalnet-xxxxx                     1/1     Running   0          2m
submariner-operator-xxxxxxx-xxxxx              1/1     Running   0          5m
```

### Step 5: Verify Tunnel Connectivity

Once both clusters have joined, Submariner establishes encrypted tunnels between gateway nodes.

```bash
# Check gateway status on Cluster-A
oc get gateways.submariner.io -n submariner-operator --context cluster-a
```

Expected output:
```
NAME          HA STATUS   CONNECTIONS   AGE
cluster-a     active      1             5m
```

```bash
# Check detailed connection info
oc describe gateway -n submariner-operator --context cluster-a
```

Expected output (truncated):
```
Status:
  Connections:
    Endpoint:
      Cluster ID:  cluster-b
      Backend:     libreswan
      Hostname:    worker-0.cluster-b.example.com
    Status:        connected
    Latency RTT:
      Average:     5.2ms
      Last:        4.8ms
```

```bash
# Use subctl to verify the full deployment
subctl show all --kubeconfig kubeconfig-cluster-a
```

Expected output:
```
Cluster "cluster-a":
 - Submariner Version: 0.18.0
 - Cable Driver: libreswan
 - Global CIDR: 242.0.0.0/16

 GATEWAY        CLUSTER     REMOTE IP       NAT    CABLE DRIVER   STATUS
 worker-0       cluster-b   10.0.1.50       yes    libreswan      connected

 SERVICE DISCOVERY:
 Lighthouse agent: running
 Lighthouse CoreDNS: running
```

You can also run the verification script provided with this lesson:

```bash
./scripts/verify-submariner.sh
```

### Step 6: Deploy a Demo Service on Cluster-A

Now deploy a service on Cluster-A and export it for cross-cluster discovery.

```bash
# Switch to Cluster-A context
oc config use-context cluster-a

# Create the demo namespace
oc apply -f manifests/namespace-demo.yaml

# Deploy the server application
oc apply -f manifests/demo-server-deployment.yaml

# Create the service
oc apply -f manifests/demo-server-service.yaml

# Verify the pods are running
oc get pods -n cross-cluster-demo
```

Expected output:
```
NAME                           READY   STATUS    RESTARTS   AGE
demo-server-5d4f7b8c9-abc12   1/1     Running   0          30s
demo-server-5d4f7b8c9-def34   1/1     Running   0          30s
```

```bash
# Test the service locally first
oc run test-curl --rm -i --restart=Never \
  --image=registry.access.redhat.com/ubi9/ubi-minimal:latest \
  -n cross-cluster-demo \
  -- curl -s http://demo-server.cross-cluster-demo.svc.cluster.local
```

Expected output:
```
<html>
<body>
  <h1>Hello from Cluster-A!</h1>
  <p>This service is exported via Submariner ServiceExport.</p>
</body>
</html>
```

### Step 7: Export the Service with ServiceExport

Create a `ServiceExport` resource to make the service discoverable across the ClusterSet.

```bash
# Export the service
oc apply -f manifests/service-export.yaml

# Verify the export status
oc get serviceexport -n cross-cluster-demo
```

Expected output:
```
NAME          AGE
demo-server   10s
```

```bash
# Check the ServiceExport conditions
oc describe serviceexport demo-server -n cross-cluster-demo
```

Expected output:
```
Name:         demo-server
Namespace:    cross-cluster-demo
API Version:  multicluster.x-k8s.io/v1alpha1
Kind:         ServiceExport
Status:
  Conditions:
    Type:    Valid
    Status:  True
    Message: Service is valid for export
    Type:    Synced
    Status:  True
    Message: Service exported successfully to broker
```

The Lighthouse agent on Cluster-A detects this `ServiceExport`, reads the backing `Service`, and publishes the endpoint information to the broker. The Lighthouse agent on Cluster-B picks up the information from the broker and creates a local `ServiceImport`.

### Step 8: Verify Service Discovery on Cluster-B

Switch to Cluster-B and verify that the service is automatically imported.

```bash
# Switch to Cluster-B context
oc config use-context cluster-b

# Create the demo namespace (the namespace must exist on both sides)
oc apply -f manifests/namespace-demo.yaml

# Check that ServiceImport was auto-created
oc get serviceimport -n cross-cluster-demo
```

Expected output:
```
NAME          TYPE           IP              AGE
demo-server   ClusterSetIP   242.0.255.250   45s
```

Notice the IP is from the Globalnet range (`242.x.x.x`), not the actual pod CIDR on Cluster-A.

```bash
# Deploy a client pod on Cluster-B
oc apply -f manifests/demo-client-deployment.yaml

# Wait for the pod to be ready
oc wait --for=condition=Ready pod -l app=demo-client -n cross-cluster-demo --timeout=60s
```

### Step 9: Test Cross-Cluster Connectivity

From the client pod on Cluster-B, reach the service running on Cluster-A using the `.clusterset.local` DNS domain.

```bash
# Get the client pod name
CLIENT_POD=$(oc get pods -n cross-cluster-demo -l app=demo-client -o jsonpath='{.items[0].metadata.name}')

# Test DNS resolution for the cross-cluster service
oc exec -n cross-cluster-demo $CLIENT_POD -- \
  nslookup demo-server.cross-cluster-demo.svc.clusterset.local
```

Expected output:
```
Server:    172.30.0.10
Address:   172.30.0.10#53

Name:   demo-server.cross-cluster-demo.svc.clusterset.local
Address: 242.0.255.250
```

```bash
# Access the service across clusters
oc exec -n cross-cluster-demo $CLIENT_POD -- \
  curl -s http://demo-server.cross-cluster-demo.svc.clusterset.local
```

Expected output:
```
<html>
<body>
  <h1>Hello from Cluster-A!</h1>
  <p>This service is exported via Submariner ServiceExport.</p>
</body>
</html>
```

The request path is:
1. Client pod on Cluster-B resolves `demo-server.cross-cluster-demo.svc.clusterset.local` via Lighthouse CoreDNS.
2. DNS returns the Globalnet IP (`242.0.255.250`).
3. The route agent on the client's node forwards the traffic to the local gateway node.
4. The gateway on Cluster-B encrypts the traffic and sends it through the IPsec tunnel to Cluster-A's gateway.
5. The gateway on Cluster-A decrypts the traffic.
6. Globalnet performs DNAT, translating the global IP back to the real pod IP.
7. The response follows the reverse path.

### Step 10: Explore Advanced Service Discovery

Submariner supports several advanced service discovery patterns.

**Headless services (StatefulSet endpoints):**

```bash
# Export a headless service to get individual pod DNS records
# Each pod gets: <pod-name>.<cluster-id>.<service>.<ns>.svc.clusterset.local
oc get endpointslice -n cross-cluster-demo -l multicluster.kubernetes.io/service-name=demo-server
```

**Cluster-specific targeting:**

```bash
# You can reach a service in a specific cluster:
# <cluster-id>.<service>.<namespace>.svc.clusterset.local
oc exec -n cross-cluster-demo $CLIENT_POD -- \
  nslookup cluster-a.demo-server.cross-cluster-demo.svc.clusterset.local
```

**Listing all clusterset services:**

```bash
# View all imported services across the cluster
oc get serviceimport --all-namespaces
```

## Verification

Run the following checks to confirm everything is working:

```bash
# 1. Submariner components are running
oc get pods -n submariner-operator
# All pods should show Running status

# 2. Gateway connections are established
oc get gateways.submariner.io -n submariner-operator
# HA STATUS should be "active", CONNECTIONS should show at least 1

# 3. ServiceExport exists on the source cluster (Cluster-A)
oc get serviceexport -n cross-cluster-demo --context cluster-a
# Should list demo-server

# 4. ServiceImport exists on the destination cluster (Cluster-B)
oc get serviceimport -n cross-cluster-demo --context cluster-b
# Should list demo-server with a ClusterSetIP

# 5. Cross-cluster DNS resolution works
oc exec -n cross-cluster-demo $CLIENT_POD -- \
  nslookup demo-server.cross-cluster-demo.svc.clusterset.local
# Should resolve to a Globalnet IP (242.x.x.x)

# 6. Cross-cluster HTTP request works
oc exec -n cross-cluster-demo $CLIENT_POD -- \
  curl -s http://demo-server.cross-cluster-demo.svc.clusterset.local
# Should return the HTML page from Cluster-A

# 7. Run the full verification script
./scripts/verify-submariner.sh
```

### Troubleshooting

**Problem: Gateway shows "connecting" but never reaches "connected"**
- Check that UDP port 4500 (NAT-T) and UDP port 4490 (tunnel metrics) are open between clusters.
- For cloud providers, verify the security groups allow traffic between gateway nodes.
- Check gateway logs: `oc logs -n submariner-operator -l app=submariner-gateway`

**Problem: ServiceExport shows "Valid: True" but ServiceImport is missing on the remote cluster**
- Verify the Lighthouse agent is running on both clusters: `oc get pods -n submariner-operator -l app=submariner-lighthouse-agent`
- Check Lighthouse agent logs: `oc logs -n submariner-operator -l app=submariner-lighthouse-agent`
- Confirm both clusters are connected to the same broker.

**Problem: DNS resolution fails for `.clusterset.local`**
- Verify Lighthouse CoreDNS pods are running: `oc get pods -n submariner-operator -l app=submariner-lighthouse-coredns`
- Check that the cluster's CoreDNS has the lighthouse plugin configured: `oc get configmap dns-default -n openshift-dns -o yaml`
- Look for a `lighthouse` stanza in the Corefile. If missing, the operator may not have patched CoreDNS.

**Problem: Cross-cluster traffic reaches the wrong pods (CIDR overlap)**
- You need Globalnet enabled. Check: `oc get pods -n submariner-operator -l app=submariner-globalnet`
- If Globalnet was not enabled during broker deployment, you must redeploy the broker with `globalnetEnabled: true`.
- Use the `globalnet-enabled-broker.yaml` manifest in this lesson.

**Problem: Connection works intermittently**
- Check gateway node health and network stability.
- Review latency metrics: `oc describe gateway -n submariner-operator` shows RTT statistics.
- Consider using WireGuard instead of Libreswan for better performance: add `--cable-driver wireguard` when joining.

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Multi-cluster networking | No built-in solution; install Submariner, Cilium Cluster Mesh, or Skupper manually | Submariner integrated via RHACM; supported add-on with automated deployment |
| MCS API (ServiceExport/Import) | Standard defined but no default implementation | Submariner Lighthouse provides the implementation; RHACM manages lifecycle |
| Cluster discovery | Manual configuration of each cluster's endpoints | RHACM ManagedClusterSet groups clusters; auto-discovers endpoints |
| Broker deployment | Manual: create CRDs, deploy broker, generate join tokens | RHACM automates broker creation when Submariner is enabled on a ClusterSet |
| Gateway setup | Manual node labeling and firewall configuration | SubmarinerConfig CRD handles cloud provider-specific setup (security groups, instance types) |
| Overlapping CIDRs | Must plan non-overlapping CIDRs upfront or manually deploy Globalnet | Globalnet option available during RHACM Submariner add-on configuration |
| Monitoring | Deploy your own metrics/dashboards | RHACM provides multi-cluster observability; Submariner metrics integrated |
| Certificate management | Manual IPsec/WireGuard key distribution | Automated via RHACM; certificates rotated by the operator |
| DNS integration | Manually configure CoreDNS forwarding for `.clusterset.local` | Lighthouse CoreDNS plugin auto-configured by the operator |
| Operator management | Install operator manually on each cluster | RHACM pushes the operator to managed clusters; handles upgrades centrally |

## Key Takeaways

- **Submariner provides flat L3 networking** across OpenShift clusters using encrypted IPsec or WireGuard tunnels, enabling pods and services to communicate as if they were on the same network.
- **ServiceExport and ServiceImport** (the Kubernetes MCS API) are the standard way to share services across clusters. You create a `ServiceExport` on the source cluster, and Submariner automatically creates a `ServiceImport` with DNS resolution (`*.clusterset.local`) on all other clusters.
- **Globalnet solves overlapping CIDRs** by assigning virtual global IPs and performing NAT at tunnel endpoints, which is critical because most OpenShift clusters share default CIDR ranges.
- **RHACM dramatically simplifies multi-cluster networking** on OpenShift compared to vanilla Kubernetes, handling operator installation, broker deployment, credential distribution, and cloud provider configuration through declarative CRDs.
- **Cross-cluster networking is essential for production patterns** like hybrid cloud connectivity, disaster recovery failover, geographic distribution, and data sovereignty, where services must be reachable across cluster boundaries without application changes.

## Cleanup

Remove the demo application resources from both clusters:

```bash
# On Cluster-B: remove client resources
oc config use-context cluster-b
oc delete -f manifests/demo-client-deployment.yaml
oc delete namespace cross-cluster-demo

# On Cluster-A: remove server and export resources
oc config use-context cluster-a
oc delete -f manifests/service-export.yaml
oc delete -f manifests/demo-server-service.yaml
oc delete -f manifests/demo-server-deployment.yaml
oc delete namespace cross-cluster-demo
```

Or use the cleanup script:

```bash
# Run on each cluster context
./scripts/cleanup.sh
```

> **Note:** The cleanup script removes demo resources only. It does not uninstall Submariner or remove the broker. To fully remove Submariner, uninstall the add-on via RHACM or delete the `submariner-operator` and `submariner-k8s-broker` namespaces.

## Next Steps

In **L2-M4.3 — Load Balancing & DNS**, you will learn how to configure MetalLB for bare-metal load balancing, set up external DNS integration, and explore global load balancing strategies for distributing traffic across clusters and regions. The multi-cluster networking foundation from this lesson pairs directly with DNS-based global load balancing to build geo-distributed applications.
