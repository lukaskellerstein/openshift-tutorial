# L2-M4.3 — Load Balancing & DNS

**Level:** Practitioner
**Duration:** 30 min

## Overview

In Kubernetes, exposing services externally on bare-metal clusters requires you to install and configure a load balancer implementation yourself, and DNS record management is typically a manual chore. OpenShift integrates MetalLB as a supported operator for bare-metal load balancing and offers the External DNS Operator for automatic DNS record lifecycle management. This lesson walks through configuring both, plus introduces global load balancing concepts for multi-site architectures.

## Prerequisites

- Completed: L2-M4.1 (Egress & Ingress Control)
- OpenShift cluster running (CRC for concepts, bare-metal or cloud cluster for full MetalLB functionality)
- Cluster admin access (`kubeadmin` on CRC)
- Familiarity with Services of type `LoadBalancer` (L1-M4.1)
- Familiarity with Routes (L1-M4.2)

## K8s Context

In vanilla Kubernetes, Services of type `LoadBalancer` only work when the cloud provider's controller manager provisions an external load balancer (AWS ELB, GCP LB, Azure LB). On bare-metal clusters, those Services remain in `Pending` state forever because there is no cloud integration to assign an external IP. The community solution is MetalLB, which you install, configure, and maintain yourself. For DNS, Kubernetes offers no built-in mechanism to create DNS records when Services or Ingresses are created — ExternalDNS is the widely used community project that bridges this gap, but again you deploy and manage it independently.

## Concepts

### MetalLB on OpenShift

MetalLB is a load balancer implementation for bare-metal Kubernetes clusters that allows Services of type `LoadBalancer` to receive real external IP addresses. OpenShift ships MetalLB as a supported, certified operator available through OperatorHub.

MetalLB operates in two modes:

- **Layer 2 (ARP/NDP) mode** — One node in the cluster "claims" the external IP and responds to ARP (IPv4) or NDP (IPv6) requests. Traffic reaches that node and is then distributed via kube-proxy. Simple to set up but creates a single point of entry (though failover is automatic). This mode works in CRC and any network environment.

- **BGP mode** — MetalLB peers with your network routers via BGP and advertises the allocated IPs. Traffic is distributed across multiple nodes at the network level, providing true load balancing. Requires BGP-capable network infrastructure.

Key MetalLB custom resources:
- **MetalLB** — The operator instance (one per cluster)
- **IPAddressPool** — Defines the range of IPs MetalLB can assign
- **L2Advertisement** — Announces IPs via Layer 2 (ARP/NDP)
- **BGPPeer** — Configures a BGP peer (router)
- **BGPAdvertisement** — Announces IPs via BGP

### External DNS Operator

The External DNS Operator automates DNS record management. When you create a Service of type `LoadBalancer` or a Route with a specific hostname, the operator creates corresponding DNS records in your DNS provider (AWS Route 53, Azure DNS, Google Cloud DNS, Infoblox, etc.).

On OpenShift, External DNS is available as a supported operator that integrates with the platform's credential management and RBAC.

Key custom resources:
- **ExternalDNS** — Configures the operator: which DNS provider, which sources to watch (Service, Route), which zones to manage.

### Global Load Balancing

For multi-site or hybrid cloud architectures, you need load balancing above the cluster level. Global Server Load Balancing (GSLB) distributes traffic across multiple OpenShift clusters based on proximity, health, or policy. Common approaches include:

- **DNS-based GSLB** — Use weighted or geolocation-based DNS records to steer traffic to the nearest healthy cluster
- **Anycast** — Advertise the same IP from multiple locations; the network routes to the nearest one
- **Global load balancer appliances** — F5, Citrix, or cloud-native solutions (AWS Global Accelerator, Cloudflare Load Balancing)

In OpenShift, you can combine MetalLB (per-cluster) with External DNS (per-cluster) and a global DNS strategy for a complete multi-cluster load balancing solution.

## Step-by-Step

### Step 1: Install the MetalLB Operator

Install MetalLB from OperatorHub. You need cluster admin access.

```bash
# Create the MetalLB namespace
oc create namespace metallb-system
```

Apply the operator subscription:

```bash
oc apply -f manifests/metallb-operator-subscription.yaml
```

Wait for the operator to become available:

```bash
# Check that the operator pod is running
oc get pods -n metallb-system -w

# Expected output (after 1-2 minutes):
# NAME                                       READY   STATUS    RESTARTS   AGE
# metallb-operator-controller-manager-xxx    1/1     Running   0          45s
# metallb-operator-webhook-server-xxx        1/1     Running   0          45s
```

Verify the CSV (ClusterServiceVersion) is in `Succeeded` phase:

```bash
oc get csv -n metallb-system

# Expected output:
# NAME                              DISPLAY   VERSION   REPLACES   PHASE
# metallb-operator.v4.14.0          MetalLB   4.14.0               Succeeded
```

### Step 2: Create the MetalLB Instance

With the operator installed, create the MetalLB instance that deploys the speaker and controller pods:

```bash
oc apply -f manifests/metallb-instance.yaml
```

Verify the MetalLB pods are running:

```bash
oc get pods -n metallb-system

# Expected output (after a minute):
# NAME                                       READY   STATUS    RESTARTS   AGE
# metallb-operator-controller-manager-xxx    1/1     Running   0          3m
# metallb-operator-webhook-server-xxx        1/1     Running   0          3m
# controller-xxx                             1/1     Running   0          45s
# speaker-xxxxx                              1/1     Running   0          45s
```

The `controller` manages IP allocation. The `speaker` runs as a DaemonSet on every node and handles the Layer 2 or BGP announcements.

### Step 3: Configure an IP Address Pool

Define the range of IP addresses MetalLB can assign to LoadBalancer Services. Choose addresses from a range that is routable on your network but not managed by DHCP or another allocator.

```bash
oc apply -f manifests/ipaddresspool.yaml
```

> **Note (CRC):** On CRC, use an IP range on the same subnet as the CRC VM (typically `192.168.130.0/24`). The example uses `192.168.130.200-192.168.130.250`.

Verify the pool was created:

```bash
oc get ipaddresspools -n metallb-system

# Expected output:
# NAME              AUTO ASSIGN   AVOID BUGGY IPS   ADDRESSES
# demo-pool         true          false              ["192.168.130.200-192.168.130.250"]
```

### Step 4: Configure Layer 2 Advertisement

Create an L2Advertisement resource to tell MetalLB to announce IPs from the pool using ARP/NDP:

```bash
oc apply -f manifests/l2advertisement.yaml
```

Verify:

```bash
oc get l2advertisements -n metallb-system

# Expected output:
# NAME         IPADDRESSPOOLS   IPADDRESSPOOL SELECTORS   INTERFACES
# demo-l2adv   ["demo-pool"]
```

### Step 5: Deploy a Test Application with LoadBalancer Service

Deploy a simple web application and expose it via a LoadBalancer Service:

```bash
oc new-project l2-m4-lb-demo
oc apply -f manifests/demo-app-deployment.yaml
oc apply -f manifests/demo-app-lb-service.yaml
```

Watch the Service get an external IP assigned by MetalLB:

```bash
oc get svc demo-app-lb -w

# Expected output:
# NAME          TYPE           CLUSTER-IP     EXTERNAL-IP       PORT(S)        AGE
# demo-app-lb   LoadBalancer   172.30.45.12   192.168.130.200   8080:31234/TCP   5s
```

The `EXTERNAL-IP` field now shows a real address from your MetalLB pool, instead of staying `<pending>` forever as it would on bare metal without MetalLB.

Test connectivity:

```bash
curl http://192.168.130.200:8080

# Expected output:
# Hello from demo-app (pod: demo-app-xxx)
```

### Step 6: Configure BGP Mode (Reference)

For production bare-metal environments with BGP-capable routers, BGP mode provides true multi-node load balancing. This step is a reference configuration — it requires a BGP-capable network.

Review the BGP configuration manifests:

```bash
cat manifests/bgp-peer.yaml
cat manifests/bgp-advertisement.yaml
```

In a production environment, you would apply these after coordinating with your network team:

```bash
# Production only — do NOT apply on CRC
# oc apply -f manifests/bgp-peer.yaml
# oc apply -f manifests/bgp-advertisement.yaml
```

The BGP peer configuration tells MetalLB which router to peer with, and the BGP advertisement tells it which IP pools to announce via BGP.

### Step 7: Install and Configure External DNS Operator

The External DNS Operator watches for Services and Routes and creates DNS records automatically.

Install the operator:

```bash
oc apply -f manifests/externaldns-operator-subscription.yaml
```

Wait for the operator:

```bash
oc get csv -n external-dns-operator

# Expected output (after 1-2 minutes):
# NAME                                DISPLAY          VERSION   PHASE
# external-dns-operator.v1.2.0        ExternalDNS      1.2.0     Succeeded
```

### Step 8: Create DNS Provider Credentials

External DNS needs credentials to manage DNS records in your provider. This example uses AWS Route 53:

```bash
# Create the credentials secret (replace with your actual credentials)
oc create secret generic aws-dns-credentials \
  --from-literal=aws_access_key_id=AKIAIOSFODNN7EXAMPLE \
  --from-literal=aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY \
  -n external-dns-operator
```

> **Security note:** In production, use STS (Security Token Service) or IRSA (IAM Roles for Service Accounts) instead of long-lived access keys. For Azure, use managed identities. See the `manifests/externaldns-azure-credentials.yaml` for an Azure example.

### Step 9: Create the ExternalDNS Custom Resource

Apply the ExternalDNS configuration that tells the operator what to watch and where to create records:

```bash
oc apply -f manifests/externaldns-instance.yaml
```

This configuration watches for:
- Services of type `LoadBalancer` with the annotation `external-dns.alpha.kubernetes.io/hostname`
- OpenShift Routes

Verify the operator is running:

```bash
oc get pods -n external-dns-operator

# Expected output:
# NAME                                       READY   STATUS    RESTARTS   AGE
# external-dns-operator-xxx                  1/1     Running   0          2m
# external-dns-demo-dns-xxx                  1/1     Running   0          30s
```

### Step 10: Test Automatic DNS Record Creation

Annotate your LoadBalancer Service to trigger DNS record creation:

```bash
oc annotate svc demo-app-lb \
  external-dns.alpha.kubernetes.io/hostname=demo-app.example.com \
  -n l2-m4-lb-demo
```

The External DNS Operator will create an A record pointing `demo-app.example.com` to the MetalLB-assigned IP.

Verify (if you have access to the DNS zone):

```bash
# Check Route 53 (AWS example)
aws route53 list-resource-record-sets \
  --hosted-zone-id Z1234567890 \
  --query "ResourceRecordSets[?Name=='demo-app.example.com.']"

# Or use dig
dig demo-app.example.com

# Expected output:
# demo-app.example.com.   300   IN   A   192.168.130.200
```

For Routes, the DNS record is created automatically based on the Route's `spec.host`:

```bash
oc apply -f manifests/demo-app-route-dns.yaml

# The External DNS Operator will create a CNAME or A record
# for demo-app-route.example.com pointing to the router's IP
```

### Step 11: Global Load Balancing Architecture (Conceptual)

For multi-cluster architectures, combine per-cluster MetalLB + External DNS with a global DNS strategy:

```
                    Global DNS (Route 53 / Cloudflare)
                    demo-app.example.com
                    Weighted or Geolocation policy
                         /             \
                        /               \
            Cluster A (US-East)    Cluster B (EU-West)
            MetalLB: 10.0.1.100   MetalLB: 10.0.2.100
            ExternalDNS:           ExternalDNS:
            us.demo-app.example    eu.demo-app.example
```

Key considerations for global load balancing:
- **Health checks** — DNS providers like Route 53 can health-check endpoints and remove unhealthy clusters from rotation
- **Latency-based routing** — Steer users to the nearest cluster automatically
- **Failover** — Active-passive configuration where a standby cluster receives traffic only when the primary is down
- **Session affinity** — Consider how sticky sessions work across clusters (typically, they don't — use shared session stores)

## Verification

Confirm MetalLB is working:

```bash
# 1. MetalLB operator and pods are running
oc get pods -n metallb-system
# All pods should be Running

# 2. IP Address Pool is configured
oc get ipaddresspools -n metallb-system
# Should show your configured pool

# 3. LoadBalancer Service has an external IP
oc get svc demo-app-lb -n l2-m4-lb-demo
# EXTERNAL-IP should be an IP from your pool, not <pending>

# 4. The service responds
curl http://$(oc get svc demo-app-lb -n l2-m4-lb-demo -o jsonpath='{.status.loadBalancer.ingress[0].ip}'):8080
# Should return the demo app response
```

Confirm External DNS is working (requires actual DNS provider access):

```bash
# 1. External DNS operator is running
oc get pods -n external-dns-operator
# All pods should be Running

# 2. DNS records were created
oc logs -n external-dns-operator deployment/external-dns-demo-dns | grep "demo-app"
# Should show record creation entries
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| MetalLB installation | Helm chart or raw manifests, community-supported | Certified operator via OperatorHub, Red Hat-supported |
| MetalLB configuration | ConfigMap (legacy) or CRDs | CRDs only (MetalLB, IPAddressPool, L2Advertisement, BGPPeer) |
| External DNS | Community Helm chart, self-managed | Supported operator with console integration |
| DNS source types | Service, Ingress | Service, Ingress, and **Route** (OpenShift-specific) |
| Credential management | Manual Secrets or cloud IAM | Integrated with OpenShift credential operators (CCO) |
| Load balancer for Routes | Built-in HAProxy router handles Route ingress | Same — Routes use the router, not MetalLB directly |
| Operator lifecycle | Manual upgrades | OLM handles upgrades with approval strategies |
| Network integration | Manual BGP/L2 config | Same, but operator validates configuration |
| Global LB | External tools (Route 53, Cloudflare) | Same, plus RHACM for multi-cluster coordination |

## Key Takeaways

- **MetalLB fills the cloud-provider gap** on bare-metal OpenShift clusters, giving LoadBalancer Services real external IPs instead of perpetual `<pending>` status.
- **Layer 2 mode is simple but single-entry** — good for small environments and CRC. BGP mode provides true multi-node distribution for production bare-metal deployments.
- **External DNS automates the DNS lifecycle** — creating and removing DNS records as Services and Routes are created and deleted, eliminating manual DNS management drift.
- **OpenShift Routes already have built-in load balancing** via the HAProxy router. MetalLB is needed when you want external IPs for non-HTTP services or when integrating with external load balancing infrastructure.
- **Global load balancing is a DNS-layer concern** that sits above individual clusters. Combine per-cluster MetalLB + External DNS with a global DNS strategy (weighted, geolocation, failover) for multi-site resilience.

## Cleanup

```bash
# Remove the demo application and project
oc delete project l2-m4-lb-demo

# Remove MetalLB configuration (keeps operator installed)
oc delete l2advertisement demo-l2adv -n metallb-system
oc delete ipaddresspool demo-pool -n metallb-system

# Remove MetalLB instance (keeps operator installed)
oc delete metallb metallb -n metallb-system

# (Optional) Remove the MetalLB operator entirely
oc delete subscription metallb-operator -n metallb-system
oc delete csv -n metallb-system -l operators.coreos.com/metallb-operator.metallb-system

# (Optional) Remove External DNS operator
oc delete subscription external-dns-operator -n external-dns-operator
oc delete csv -n external-dns-operator -l operators.coreos.com/external-dns-operator.external-dns-operator
oc delete secret aws-dns-credentials -n external-dns-operator

# Remove the namespace if no longer needed
oc delete namespace metallb-system
```

## Next Steps

In **L2-M5.1 — Image Security & Compliance**, you will learn how OpenShift enforces image security through image signing, image policies, and registry scanning. You will configure image content policies, work with the Red Hat container catalog, and integrate Quay registry scanning into your workflow.
