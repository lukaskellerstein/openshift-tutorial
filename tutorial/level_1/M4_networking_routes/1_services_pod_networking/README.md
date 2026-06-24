# L1-M4.1 — Services & Pod Networking

**Level:** Foundations
**Duration:** 20 min

## Overview

In Kubernetes, you already understand that every pod gets its own IP, pods can communicate across nodes via a flat network, and Services provide stable endpoints for discovery and load balancing. OpenShift preserves all of this and adds OVN-Kubernetes as the default software-defined networking (SDN) layer, support for multiple network interfaces via Multus, and tighter default network isolation. This lesson walks you through pod networking on OpenShift, demonstrates that Services (ClusterIP, NodePort, LoadBalancer) work exactly as you expect, and introduces the OpenShift-specific additions you should know about.

## Prerequisites

- Completed: L1-M3.1 (oc new-app & Source-to-Image)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in via `oc login`

## K8s Context

In vanilla Kubernetes, pod networking is handled by a CNI plugin you choose and install yourself -- Calico, Flannel, Cilium, Weave, or others. You pick one, deploy it, and manage its lifecycle. Services (ClusterIP, NodePort, LoadBalancer) provide stable virtual IPs that front a set of pods selected by labels. NetworkPolicies let you control traffic between pods, but their availability depends on whether your CNI plugin supports them. If you want a pod to have multiple network interfaces, you need to set up Multus yourself.

## Concepts

### OVN-Kubernetes -- OpenShift's Default SDN

OpenShift 4.x ships with OVN-Kubernetes as the default CNI plugin. You do not choose or install a CNI -- it is built into the platform. OVN-Kubernetes is based on Open Virtual Network (OVN), which uses Open vSwitch (OVS) under the hood. It provides:

- **Pod-to-pod networking**: Every pod gets a unique IP from a cluster-wide pod network CIDR. Pods can communicate across nodes without NAT, just like any Kubernetes CNI.
- **Service networking**: kube-proxy functionality is handled natively by OVN, using OpenFlow rules instead of iptables. This improves performance at scale compared to iptables-based CNIs.
- **NetworkPolicy support**: Full Kubernetes NetworkPolicy support is built in -- no optional add-on required.
- **Egress controls**: OVN-Kubernetes supports EgressIP, EgressFirewall, and EgressQoS, which are OpenShift-specific extensions beyond standard Kubernetes NetworkPolicy.

**Why does OpenShift mandate OVN-Kubernetes?** OpenShift is an opinionated platform. By standardizing on one CNI, Red Hat can guarantee NetworkPolicy support, provide consistent behavior across clusters, and integrate networking deeply with the platform (for example, the built-in HAProxy router relies on specific SDN behaviors).

### Services Work the Same

Kubernetes Services are unchanged on OpenShift. The three types you know behave identically:

| Service Type | Behavior on OpenShift |
|-------------|----------------------|
| **ClusterIP** | Internal-only virtual IP. Default type. Works exactly as in K8s. |
| **NodePort** | Exposes on a static port on every node. Works as in K8s, but rarely used on OpenShift because Routes are preferred for external access. |
| **LoadBalancer** | Provisions an external load balancer. Works on cloud-based OpenShift (AWS, Azure, GCP). On bare metal, requires MetalLB. Not available on CRC. |

In practice, OpenShift users typically use ClusterIP services paired with Routes (covered in the next lesson) rather than NodePort or LoadBalancer.

### Multus -- Multiple Network Interfaces

In Kubernetes, a pod has a single network interface (the pod network). OpenShift includes Multus CNI out of the box, which allows pods to have additional network interfaces beyond the default cluster network. Use cases include:

- **Separation of traffic**: Management network vs data network.
- **Compliance**: Isolating sensitive traffic on a dedicated VLAN.
- **Network functions**: Pods that act as routers or firewalls need multiple interfaces.

You configure additional networks using a `NetworkAttachmentDefinition` CR (Custom Resource). This is an advanced topic -- most workloads need only the default pod network.

### NetworkPolicy -- Default Behavior

Kubernetes NetworkPolicies work on OpenShift without modification. However, there is one important behavioral difference to know:

- **Kubernetes (default)**: All pod-to-pod traffic is allowed unless you create a NetworkPolicy that restricts it. Policies are additive -- each one opens access.
- **OpenShift (default)**: Same default behavior -- all traffic is allowed between pods. However, OpenShift provides project-level isolation options and EgressFirewall CRDs for controlling outbound traffic, which go beyond what standard NetworkPolicy offers.

We will cover NetworkPolicies in detail in L1-M4.4.

### DNS and Service Discovery

OpenShift uses CoreDNS, just like Kubernetes. Every Service gets a DNS name:

```
<service-name>.<namespace>.svc.cluster.local
```

From within the same project, you can reach a Service by its short name (e.g., `hello-sdn`). From another project, use the full name (e.g., `hello-sdn.l1-m4-networking.svc.cluster.local`).

## Step-by-Step

### Step 1: Create a Project for This Lesson

Create a dedicated project to keep resources organized:

```bash
oc new-project l1-m4-networking --display-name="L1-M4: Networking"
```

Expected output:
```
Now using project "l1-m4-networking" on server "https://api.crc.testing:6443".
```

### Step 2: Deploy a Simple Application

Apply the Deployment manifest from this lesson's `manifests/` directory. This creates a simple httpd (Apache) deployment using Red Hat's UBI-based image, which runs as non-root and is compatible with OpenShift's default SCC:

```bash
oc apply -f manifests/deployment.yaml
```

```yaml
# manifests/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hello-sdn
  labels:
    app: hello-sdn
    tutorial-level: "1"
    tutorial-module: "M4"
spec:
  replicas: 2
  selector:
    matchLabels:
      app: hello-sdn
  template:
    metadata:
      labels:
        app: hello-sdn
        tutorial-level: "1"
        tutorial-module: "M4"
    spec:
      containers:
        - name: httpd
          image: registry.access.redhat.com/ubi9/httpd-24:latest
          ports:
            - containerPort: 8080
```

Wait for the pods to be ready:

```bash
oc get pods -l app=hello-sdn -w
```

Expected output (press Ctrl+C once both pods show `Running`):
```
NAME                         READY   STATUS    RESTARTS   AGE
hello-sdn-6d8f9b7c4-abc12   1/1     Running   0          15s
hello-sdn-6d8f9b7c4-def34   1/1     Running   0          15s
```

### Step 3: Examine Pod Networking

Each pod has a unique IP assigned by OVN-Kubernetes. Inspect the pod IPs:

```bash
oc get pods -l app=hello-sdn -o wide
```

Expected output:
```
NAME                         READY   STATUS    RESTARTS   AGE   IP            NODE
hello-sdn-6d8f9b7c4-abc12   1/1     Running   0          30s   10.217.0.45   crc
hello-sdn-6d8f9b7c4-def34   1/1     Running   0          30s   10.217.0.46   crc
```

The IPs come from the cluster's pod network CIDR. On CRC, this is typically `10.217.0.0/22`. You can verify the cluster network configuration:

```bash
oc get network.config cluster -o jsonpath='{.spec.clusterNetwork[0].cidr}'
```

Expected output:
```
10.217.0.0/22
```

### Step 4: Test Pod-to-Pod Communication

Verify that pods can reach each other directly by IP. Start a debug session in one pod and curl the other:

```bash
# Get the IP of the second pod
POD2_IP=$(oc get pods -l app=hello-sdn -o jsonpath='{.items[1].status.podIP}')

# Start a debug pod and curl the second pod
oc debug deployment/hello-sdn -- curl -s http://${POD2_IP}:8080
```

You should see the default httpd welcome page HTML. This confirms the pod network is functioning -- pods can communicate directly via their IPs, just as in Kubernetes.

### Step 5: Create a ClusterIP Service

Now create a Service to provide a stable endpoint in front of the two pods:

```bash
oc apply -f manifests/service.yaml
```

```yaml
# manifests/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: hello-sdn
  labels:
    app: hello-sdn
    tutorial-level: "1"
    tutorial-module: "M4"
spec:
  type: ClusterIP
  selector:
    app: hello-sdn
  ports:
    - port: 8080
      targetPort: 8080
      protocol: TCP
```

Verify the Service:

```bash
oc get service hello-sdn
```

Expected output:
```
NAME        TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE
hello-sdn   ClusterIP   172.30.120.55   <none>        8080/TCP   5s
```

The ClusterIP (`172.30.x.x`) is a virtual IP that exists only within the cluster. It is stable -- unlike pod IPs, it does not change when pods are rescheduled.

### Step 6: Verify Service Load Balancing

The Service distributes traffic across the pods it selects. Check the endpoints:

```bash
oc get endpoints hello-sdn
```

Expected output:
```
NAME        ENDPOINTS                         AGE
hello-sdn   10.217.0.45:8080,10.217.0.46:8080   10s
```

Both pod IPs appear as endpoints. Now test that the Service routes traffic:

```bash
# Access the service by its DNS name from within the cluster
oc debug deployment/hello-sdn -- curl -s http://hello-sdn:8080 -o /dev/null -w "%{http_code}"
```

Expected output:
```
200
```

The `hello-sdn` short name works because the debug pod runs in the same project. This is standard Kubernetes DNS behavior, powered by CoreDNS on OpenShift.

### Step 7: Inspect the OVN-Kubernetes SDN

OpenShift provides visibility into its SDN configuration. Examine the cluster network operator:

```bash
oc get network.operator cluster -o jsonpath='{.spec.defaultNetwork.type}'
```

Expected output:
```
OVNKubernetes
```

You can also view the full network configuration:

```bash
oc get network.config cluster -o yaml
```

Key fields to look at:

```yaml
spec:
  clusterNetwork:
    - cidr: 10.217.0.0/22       # Pod IP range
      hostPrefix: 23             # Per-node subnet size
  networkType: OVNKubernetes     # The CNI plugin
  serviceNetwork:
    - 172.30.0.0/16              # Service ClusterIP range
```

This is all pre-configured -- unlike Kubernetes, where you install and configure the CNI yourself.

## Verification

Run these commands to confirm everything is working:

```bash
# 1. Both pods are running
oc get pods -l app=hello-sdn

# 2. The Service has a ClusterIP
oc get service hello-sdn

# 3. The Service endpoints match the pod IPs
oc get endpoints hello-sdn

# 4. DNS resolution works within the cluster
oc debug deployment/hello-sdn -- curl -s http://hello-sdn:8080 -o /dev/null -w "%{http_code}\n"

# 5. Confirm the SDN type is OVN-Kubernetes
oc get network.operator cluster -o jsonpath='{.spec.defaultNetwork.type}'
```

All Services should show ClusterIPs in the `172.30.0.0/16` range, and the curl test should return `200`.

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| CNI plugin | Choose and install yourself (Calico, Flannel, Cilium, etc.) | OVN-Kubernetes pre-installed and managed |
| Pod networking | Depends on chosen CNI | Flat pod network via OVN, same model as K8s |
| Services (ClusterIP, NodePort, LB) | Standard | Identical behavior |
| NetworkPolicy | Depends on CNI supporting it | Always available (OVN-Kubernetes) |
| Multiple interfaces | Install Multus yourself | Multus included out of the box |
| Egress control | NetworkPolicy (limited) | EgressFirewall, EgressIP (extended) |
| DNS | CoreDNS (you install it) | CoreDNS pre-installed |
| Service proxy | kube-proxy (iptables/IPVS) | OVN handles this natively (no kube-proxy) |
| External access | Ingress + controller you install | Routes (built-in, next lesson) |

## Key Takeaways

- **Pod networking on OpenShift is the same model as Kubernetes**: every pod gets an IP, pods communicate across nodes without NAT, Services provide stable endpoints. If you know Kubernetes networking, you know OpenShift networking.
- **OVN-Kubernetes is pre-installed and managed**: You do not choose, install, or configure a CNI plugin. OpenShift handles it as part of the platform, which guarantees NetworkPolicy support and consistent behavior.
- **Services work identically**: ClusterIP, NodePort, and LoadBalancer Services behave exactly as they do in Kubernetes. No changes needed to your existing Service manifests.
- **Multus comes free**: OpenShift includes Multus for pods that need multiple network interfaces. In Kubernetes, you would install and manage Multus yourself.
- **OpenShift extends beyond standard NetworkPolicy**: EgressFirewall, EgressIP, and EgressQoS provide additional control over outbound traffic that goes beyond what standard Kubernetes NetworkPolicy offers.

## Cleanup

Remove all resources created in this lesson:

```bash
# Delete the entire project (removes all resources within it)
oc delete project l1-m4-networking
```

If you prefer to keep the project and delete resources selectively:

```bash
oc delete all -l tutorial-level=1,tutorial-module=M4
```

## Next Steps

In **L1-M4.2 -- Routes vs Ingress**, you will learn how to expose Services externally using OpenShift Routes. Routes are OpenShift's native ingress mechanism -- they predate Kubernetes Ingress and offer built-in TLS termination modes (edge, passthrough, re-encrypt) via the pre-installed HAProxy router. You will see how Routes compare to Kubernetes Ingress and when to use each.
